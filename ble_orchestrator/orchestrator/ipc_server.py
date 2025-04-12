"""
IPCサーバーモジュール - プロセス間通信でリクエストを受け付ける
"""

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

from .config import IPC_LISTEN_HOST, IPC_LISTEN_PORT, IPC_MAX_CONNECTIONS, IPC_SOCKET_PATH
from .types import (
    BLERequest,
    ReadRequest,
    RequestPriority,
    ScanRequest,
    ScanResult,
    WriteRequest,
)

logger = logging.getLogger(__name__)


class IPCServer:
    """
    Unix SocketベースのIPCサーバー
    """

    def __init__(
        self,
        handle_scan_func: Callable[[str], Optional[ScanResult]],
        enqueue_request_func: Callable[[BLERequest], Any],
        get_status_func: Callable[[], Dict[str, Any]],
    ):
        """
        初期化
        handle_scan_func: スキャン結果を取得する関数
        enqueue_request_func: BLEリクエストをキューに入れる関数
        get_status_func: サービスステータスを取得する関数
        """
        self._handle_scan_func = handle_scan_func
        self._enqueue_request_func = enqueue_request_func
        self._get_status_func = get_status_func
        self._server = None
        self._stop_event = asyncio.Event()
        self._task = None
        self._connections = set()

    async def start(self) -> None:
        """
        サーバーを開始
        """
        if self._task is not None:
            logger.warning("IPC server is already running")
            return

        self._stop_event.clear()

        # ソケットモードの判定
        use_tcp = "BLE_ORCHESTRATOR_TCP" in os.environ
        
        if use_tcp:
            # TCP/IPソケット
            self._server = await asyncio.start_server(
                self._handle_client, 
                IPC_LISTEN_HOST, 
                IPC_LISTEN_PORT,
                backlog=IPC_MAX_CONNECTIONS
            )
            addr = self._server.sockets[0].getsockname()
            logger.info(f"IPC server started on {addr[0]}:{addr[1]}")
        else:
            # Unixドメインソケット
            # 既存のソケットファイルを削除
            try:
                if os.path.exists(IPC_SOCKET_PATH):
                    os.unlink(IPC_SOCKET_PATH)
            except OSError as e:
                logger.error(f"Could not remove existing socket file: {e}")

            # ソケットサーバー起動
            self._server = await asyncio.start_unix_server(
                self._handle_client, IPC_SOCKET_PATH
            )
            os.chmod(IPC_SOCKET_PATH, 0o666)  # アクセス権を設定
            logger.info(f"IPC server started on {IPC_SOCKET_PATH}")

        # サーバータスク開始
        self._task = asyncio.create_task(self._serve_forever())

    async def _serve_forever(self) -> None:
        """
        サーバーループを実行
        """
        try:
            async with self._server:
                await self._server.serve_forever()
        except asyncio.CancelledError:
            logger.info("IPC server task cancelled")
        except Exception as e:
            logger.error(f"Error in IPC server: {e}")
        finally:
            logger.info("IPC server stopped")

    async def stop(self) -> None:
        """
        サーバーを停止
        """
        if self._task is None:
            return

        logger.info("Stopping IPC server...")
        self._stop_event.set()
        
        # アクティブな接続をクローズ
        for writer in self._connections:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._connections.clear()
        
        # サーバー停止
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            
        # タスク終了待機
        if self._task:
            try:
                self._task.cancel()
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            
        self._task = None
        
        # UNIXソケットの場合はファイル削除
        if os.path.exists(IPC_SOCKET_PATH):
            try:
                os.unlink(IPC_SOCKET_PATH)
            except OSError as e:
                logger.error(f"Could not remove socket file: {e}")

        logger.info("IPC server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """
        クライアント接続のハンドラ
        """
        # クライアント情報取得
        peer = writer.get_extra_info("peername")
        client_id = str(uuid.uuid4())[:8]
        logger.info(f"New client connection {client_id} from {peer}")
        
        self._connections.add(writer)
        
        try:
            while not self._stop_event.is_set():
                # リクエスト読み取り
                data = await reader.readline()
                if not data:
                    logger.info(f"Client {client_id} disconnected")
                    break
                
                # リクエスト処理
                try:
                    request_str = data.decode().strip()
                    logger.debug(f"Received from client {client_id}: {request_str}")
                    
                    request = json.loads(request_str)
                    command = request.get("command")
                    
                    response = await self._process_command(command, request)
                    
                    # レスポンス送信
                    response_json = json.dumps(response) + "\n"
                    writer.write(response_json.encode())
                    await writer.drain()
                    
                except json.JSONDecodeError:
                    error_resp = {"status": "error", "error": "Invalid JSON"}
                    writer.write((json.dumps(error_resp) + "\n").encode())
                    await writer.drain()
                except Exception as e:
                    logger.error(f"Error processing request from client {client_id}: {e}")
                    error_resp = {"status": "error", "error": str(e)}
                    writer.write((json.dumps(error_resp) + "\n").encode())
                    await writer.drain()
                    
        except asyncio.CancelledError:
            logger.info(f"Client handler for {client_id} was cancelled")
        except ConnectionError:
            logger.info(f"Connection to client {client_id} was lost")
        except Exception as e:
            logger.error(f"Unexpected error in client handler for {client_id}: {e}")
        finally:
            # 接続をクローズ
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            self._connections.discard(writer)
            logger.info(f"Client {client_id} connection closed")

    async def _process_command(self, command: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        コマンドを処理してレスポンスを返す
        """
        if command == "get_scan_result":
            # スキャン結果取得
            mac_address = request.get("mac_address")
            if not mac_address:
                return {"status": "error", "error": "Missing mac_address parameter"}
                
            result = self._handle_scan_func(mac_address)
            
            if result:
                return {
                    "status": "success",
                    "data": result.to_dict()
                }
            else:
                return {
                    "status": "error",
                    "error": f"Device {mac_address} not found or scan data expired"
                }
                
        elif command == "read_sensor":
            # センサー読み取り
            mac_address = request.get("mac_address")
            service_uuid = request.get("service_uuid")
            characteristic_uuid = request.get("characteristic_uuid")
            priority_str = request.get("priority", "NORMAL")
            timeout = float(request.get("timeout", 10.0))
            
            if not all([mac_address, service_uuid, characteristic_uuid]):
                return {
                    "status": "error", 
                    "error": "Missing required parameters (mac_address, service_uuid, characteristic_uuid)"
                }
                
            # 優先度の解決
            try:
                priority = RequestPriority[priority_str]
            except KeyError:
                priority = RequestPriority.NORMAL
                
            # リクエスト作成
            read_request = ReadRequest(
                request_id=str(uuid.uuid4()),
                mac_address=mac_address,
                service_uuid=service_uuid,
                characteristic_uuid=characteristic_uuid,
                priority=priority,
                timeout_sec=timeout
            )
            
            # キューに追加
            request_id = await self._enqueue_request_func(read_request)
            
            return {
                "status": "success",
                "request_id": request_id,
                "message": "Read request queued successfully"
            }
            
        elif command == "send_command":
            # コマンド送信
            mac_address = request.get("mac_address")
            service_uuid = request.get("service_uuid")
            characteristic_uuid = request.get("characteristic_uuid")
            data_hex = request.get("data")
            response_required = request.get("response_required", False)
            priority_str = request.get("priority", "NORMAL")
            timeout = float(request.get("timeout", 10.0))
            
            if not all([mac_address, service_uuid, characteristic_uuid, data_hex]):
                return {
                    "status": "error", 
                    "error": "Missing required parameters (mac_address, service_uuid, characteristic_uuid, data)"
                }
                
            # データ変換
            try:
                if isinstance(data_hex, list):
                    data = bytes(data_hex)
                else:
                    data = bytes.fromhex(data_hex)
            except ValueError:
                return {"status": "error", "error": "Invalid hex data format"}
                
            # 優先度の解決
            try:
                priority = RequestPriority[priority_str]
            except KeyError:
                priority = RequestPriority.NORMAL
                
            # リクエスト作成
            write_request = WriteRequest(
                request_id=str(uuid.uuid4()),
                mac_address=mac_address,
                service_uuid=service_uuid,
                characteristic_uuid=characteristic_uuid,
                data=data,
                response_required=response_required,
                priority=priority,
                timeout_sec=timeout
            )
            
            # キューに追加
            request_id = await self._enqueue_request_func(write_request)
            
            return {
                "status": "success",
                "request_id": request_id,
                "message": "Write request queued successfully"
            }
            
        elif command == "get_request_status":
            # リクエストのステータス取得
            request_id = request.get("request_id")
            if not request_id:
                return {"status": "error", "error": "Missing request_id parameter"}
                
            # ステータス取得ロジックはメインサービスで実装
            return {
                "status": "pending",
                "message": "Request status retrieval not implemented yet"
            }
            
        elif command == "status":
            # サービスステータス取得
            status_data = self._get_status_func()
            return {
                "status": "success",
                "data": status_data
            }
            
        else:
            return {
                "status": "error",
                "error": f"Unknown command: {command}"
            }
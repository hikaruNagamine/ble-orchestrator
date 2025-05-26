"""
IPCサーバーモジュール - プロセス間通信でリクエストを受け付ける
"""

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any, Callable, Dict, List, Optional, Union, Set, Awaitable

from .config import IPC_LISTEN_HOST, IPC_LISTEN_PORT, IPC_MAX_CONNECTIONS, IPC_SOCKET_PATH
from .types import (
    BLERequest,
    ReadRequest,
    RequestPriority,
    ScanRequest,
    ScanResult,
    WriteRequest,
    NotificationRequest,
    NotificationData,
    RequestStatus
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
        
        # 通知購読クライアント管理
        self._notification_subscribers: Dict[str, Set[asyncio.StreamWriter]] = {}  # callback_id -> set of writers

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
        
        # 全クライアント接続を切断
        for writer in list(self._connections):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.error(f"Error closing client connection: {e}")
        
        # 全通知購読を解除
        self._notification_subscribers.clear()
        
        # サーバー停止
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            
        # タスク停止
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                logger.warning("IPC server task forcibly cancelled")
                
        self._connections.clear()
        self._task = None
        
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
                    
                    response = await self._process_command(command, request, writer, client_id)
                    
                    # レスポンス送信
                    response_json = json.dumps(response) + "\n"
                    writer.write(response_json.encode())
                    await writer.drain()
                    logger.debug(f"Sent response to client {client_id}: {response_json}")
                    
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
            logger.info(f"Client handler for {client_id} cancelled")
        except Exception as e:
            logger.error(f"Error in client handler for {client_id}: {e}")
        finally:
            # クライアント登録から削除
            self._connections.discard(writer)
            
            # 通知購読リストからも削除
            for callback_id, subscribers in list(self._notification_subscribers.items()):
                if writer in subscribers:
                    subscribers.discard(writer)
                    # 空になったらキーを削除
                    if not subscribers:
                        del self._notification_subscribers[callback_id]
            
            # 接続を閉じる
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.error(f"Error closing connection for client {client_id}: {e}")
            
            logger.info(f"Client {client_id} connection closed")

    async def _process_command(
        self, command: str, request: Dict[str, Any], writer: asyncio.StreamWriter, client_id: str
    ) -> Dict[str, Any]:
        """
        コマンドに応じた処理を実行
        """
        logger.debug(f"Processing command: {command} from client {client_id}")
        
        if command == "get_status":
            # サービスステータス取得
            return {
                "status": "success",
                "data": self._get_status_func()
            }
            
        if command == "get_scan_result" or command == "get_scan_data":
            # スキャン結果取得
            logger.debug(f"Handling scan request: {request}")
            mac_address = request.get("mac_address")
            service_uuid = request.get("service_uuid")
            characteristic_uuid = request.get("characteristic_uuid")
            
            if not mac_address:
                return {"status": "error", "error": "Missing mac_address parameter"}
                
            # get_scan_dataの場合はScanRequestを作成して処理
            if command == "get_scan_data":
                logger.debug(f"Creating ScanRequest for device {mac_address}")
                # リクエスト作成
                scan_request = ScanRequest(
                    request_id=request.get("request_id", str(uuid.uuid4())),
                    mac_address=mac_address,
                    service_uuid=service_uuid,
                    characteristic_uuid=characteristic_uuid,
                    priority=RequestPriority.NORMAL
                )
                
                try:
                    # リクエストキューに追加
                    await self._enqueue_request_func(scan_request)
                    
                    # リクエスト完了を待機
                    await scan_request.wait_until_done(timeout=10.0)
                    
                    if scan_request.status == RequestStatus.COMPLETED:
                        logger.debug(f"Scan request completed: {scan_request.response_data}")
                        return {
                            "status": "success",
                            "data": scan_request.response_data,
                            "request_id": scan_request.request_id
                        }
                    else:
                        error_msg = scan_request.error_message or "Request failed"
                        logger.error(f"Scan request failed: {error_msg}")
                        return {
                            "status": "error",
                            "error": error_msg,
                            "request_id": scan_request.request_id
                        }
                        
                except asyncio.TimeoutError:
                    logger.error(f"Scan request timed out for {mac_address}")
                    return {
                        "status": "error",
                        "error": "Request timed out",
                        "request_id": scan_request.request_id
                    }
                except Exception as e:
                    logger.error(f"Error processing scan request: {e}")
                    return {
                        "status": "error",
                        "error": str(e),
                        "request_id": request.get("request_id", "unknown")
                    }
            
            # 通常のget_scan_result
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
                request_id=request.get("request_id", str(uuid.uuid4())),
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
                request_id=request.get("request_id", str(uuid.uuid4())),
                mac_address=mac_address,
                service_uuid=service_uuid,
                characteristic_uuid=characteristic_uuid,
                data=data,
                response_required=response_required,
                priority=priority,
                timeout_sec=timeout
            )
            
            try:
                # キューに追加
                await self._enqueue_request_func(write_request)
                
                # リクエスト完了を待機
                await write_request.wait_until_done(timeout=timeout)

                if write_request.status == RequestStatus.COMPLETED:
                    logger.debug(f"Write request completed: {write_request.response_data}")
                    return {
                        "status": "success",
                        "data": write_request.response_data,
                        "request_id": write_request.request_id
                    }
                else:
                    error_msg = write_request.error_message or "Request failed"
                    logger.error(f"Write request failed: {error_msg}")
                    return {
                        "status": "error",
                        "error": error_msg,
                        "request_id": write_request.request_id
                    }
            except asyncio.TimeoutError:
                logger.error(f"Write request timed out for {mac_address}")
                return {
                    "status": "error",
                    "error": "Request timed out",
                    "request_id": write_request.request_id
                }
            
        elif command == "subscribe_notifications":
            # 通知購読
            mac_address = request.get("mac_address")
            service_uuid = request.get("service_uuid")
            characteristic_uuid = request.get("characteristic_uuid")
            unsubscribe = request.get("unsubscribe", False)
            
            if not all([mac_address, service_uuid, characteristic_uuid]):
                return {
                    "status": "error", 
                    "error": "Missing required parameters (mac_address, service_uuid, characteristic_uuid)"
                }
            
            # コールバックIDの生成またはキー取得
            key = f"{mac_address}:{characteristic_uuid}"
            callback_id = request.get("callback_id", f"{client_id}_{key}")
            
            # 通知リクエスト作成
            notification_request = NotificationRequest(
                request_id=str(uuid.uuid4()),
                mac_address=mac_address,
                service_uuid=service_uuid,
                characteristic_uuid=characteristic_uuid,
                callback_id=callback_id,
                unsubscribe=unsubscribe
            )
            
            # 購読設定
            if not unsubscribe:
                # 購読クライアントを登録
                if callback_id not in self._notification_subscribers:
                    self._notification_subscribers[callback_id] = set()
                self._notification_subscribers[callback_id].add(writer)
                logger.info(f"Client {client_id} subscribed to notifications with callback_id {callback_id}")
            else:
                # 購読解除
                if callback_id in self._notification_subscribers:
                    self._notification_subscribers[callback_id].discard(writer)
                    if not self._notification_subscribers[callback_id]:
                        del self._notification_subscribers[callback_id]
                logger.info(f"Client {client_id} unsubscribed from notifications with callback_id {callback_id}")
            
            # 通知マネージャーに登録
            request_id = await self._enqueue_request_func(notification_request)
            
            return {
                "status": "success",
                "request_id": request_id,
                "callback_id": callback_id,
                "message": f"Notification {'unsubscribed' if unsubscribe else 'subscribed'} successfully"
            }
            
        else:
            # 不明なコマンド
            return {
                "status": "error",
                "error": f"Unknown command: {command}"
            }

    async def send_notification(self, notification: NotificationData) -> None:
        """
        通知を購読中のクライアントに送信
        """
        callback_id = notification.callback_id
        if callback_id not in self._notification_subscribers:
            # この通知を購読しているクライアントがいない
            return
            
        # 通知データを辞書に変換
        notification_dict = {
            "type": "notification",
            "callback_id": notification.callback_id,
            "mac_address": notification.mac_address,
            "characteristic_uuid": notification.characteristic_uuid,
            "value": notification.value.hex(),
            "timestamp": notification.timestamp
        }
        
        notification_json = json.dumps(notification_dict) + "\n"
        
        # 通知を送信
        disconnected_clients = []
        for writer in self._notification_subscribers[callback_id]:
            try:
                writer.write(notification_json.encode())
                await writer.drain()
            except Exception as e:
                logger.error(f"Error sending notification to client: {e}")
                disconnected_clients.append(writer)
        
        # 切断されたクライアントをリストから削除
        for writer in disconnected_clients:
            self._notification_subscribers[callback_id].discard(writer)
            
        # 空になったらキーを削除
        if not self._notification_subscribers[callback_id]:
            del self._notification_subscribers[callback_id]
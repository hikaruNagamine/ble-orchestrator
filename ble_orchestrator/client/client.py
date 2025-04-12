"""
BLE Orchestratorのクライアントライブラリ
UNIXソケットまたはTCPソケットを使ってIPC通信を行う
"""

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class BLEOrchestratorClient:
    """
    BLE Orchestratorのクライアント
    シンプルなインターフェースでBLE操作を要求
    """

    def __init__(
        self, 
        socket_path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout: float = 10.0
    ):
        """
        初期化
        socket_path: UNIXソケットパス（Linuxのみ）
        host, port: TCPソケットパラメータ
        timeout: 通信タイムアウト
        """
        self.socket_path = socket_path or os.environ.get(
            "BLE_ORCHESTRATOR_SOCKET", 
            "/tmp/ble-orchestrator.sock"
        )
        self.host = host or os.environ.get("BLE_ORCHESTRATOR_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("BLE_ORCHESTRATOR_PORT", "8378"))
        self.timeout = timeout
        self.use_tcp = bool(host and port) or "BLE_ORCHESTRATOR_TCP" in os.environ
        self._reader = None
        self._writer = None
        
        if self.use_tcp:
            logger.debug(f"Using TCP socket {self.host}:{self.port}")
        else:
            logger.debug(f"Using UNIX socket {self.socket_path}")

    async def connect(self) -> None:
        """
        サーバーに接続
        """
        try:
            if self.use_tcp:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=self.timeout
                )
            else:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(self.socket_path),
                    timeout=self.timeout
                )
            logger.debug("Connected to BLE Orchestrator")
        except (ConnectionRefusedError, FileNotFoundError) as e:
            raise ConnectionError(f"Failed to connect to BLE Orchestrator: {e}")
        except asyncio.TimeoutError:
            raise TimeoutError("Connection to BLE Orchestrator timed out")

    async def close(self) -> None:
        """
        接続を閉じる
        """
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
                logger.debug("Connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            self._writer = None
            self._reader = None

    async def __aenter__(self):
        """
        コンテキストマネージャーのエントリー
        """
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        コンテキストマネージャーのイグジット
        """
        await self.close()

    async def _send_request(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        リクエストを送信して応答を受信
        """
        if not self._reader or not self._writer:
            await self.connect()
            
        # リクエスト作成
        request = {"command": command, **params}
        request_str = json.dumps(request) + "\n"
        
        try:
            # リクエスト送信
            self._writer.write(request_str.encode())
            await self._writer.drain()
            
            # 応答受信
            response_bytes = await asyncio.wait_for(
                self._reader.readline(), 
                timeout=self.timeout
            )
            
            if not response_bytes:
                raise ConnectionError("Connection closed by server")
                
            # 応答解析
            response = json.loads(response_bytes.decode())
            
            # エラー処理
            if response.get("status") == "error":
                error_msg = response.get("error", "Unknown error")
                raise RuntimeError(f"Server returned error: {error_msg}")
                
            return response
                
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request timed out after {self.timeout} seconds")
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON response from server")

    async def get_scan_result(self, mac_address: str) -> Dict[str, Any]:
        """
        スキャン結果を取得
        
        引数:
            mac_address: MACアドレス
            
        戻り値:
            スキャン結果の辞書
        """
        response = await self._send_request("get_scan_result", {"mac_address": mac_address})
        return response.get("data", {})

    async def read_sensor(
        self, 
        mac_address: str, 
        service_uuid: str, 
        characteristic_uuid: str,
        priority: str = "NORMAL",
        timeout: float = 10.0
    ) -> str:
        """
        センサー値を読み取り
        
        引数:
            mac_address: MACアドレス
            service_uuid: サービスUUID
            characteristic_uuid: 特性UUID
            priority: 優先度（HIGH/NORMAL/LOW）
            timeout: タイムアウト秒数
            
        戻り値:
            リクエストID
        """
        response = await self._send_request("read_sensor", {
            "mac_address": mac_address,
            "service_uuid": service_uuid,
            "characteristic_uuid": characteristic_uuid,
            "priority": priority,
            "timeout": timeout
        })
        return response.get("request_id", "")

    async def send_command(
        self, 
        mac_address: str, 
        service_uuid: str, 
        characteristic_uuid: str,
        data: Union[str, bytes, List[int]],
        response_required: bool = False,
        priority: str = "NORMAL",
        timeout: float = 10.0
    ) -> str:
        """
        コマンドを送信
        
        引数:
            mac_address: MACアドレス
            service_uuid: サービスUUID
            characteristic_uuid: 特性UUID
            data: 送信データ（16進文字列、バイト列、整数リスト）
            response_required: レスポンスが必要かどうか
            priority: 優先度（HIGH/NORMAL/LOW）
            timeout: タイムアウト秒数
            
        戻り値:
            リクエストID
        """
        # データ形式の変換
        if isinstance(data, bytes):
            data_hex = data.hex()
        elif isinstance(data, list):
            data_hex = bytes(data).hex()
        else:
            data_hex = data  # 文字列前提
            
        response = await self._send_request("send_command", {
            "mac_address": mac_address,
            "service_uuid": service_uuid,
            "characteristic_uuid": characteristic_uuid,
            "data": data_hex,
            "response_required": response_required,
            "priority": priority,
            "timeout": timeout
        })
        return response.get("request_id", "")

    async def get_request_status(self, request_id: str) -> Dict[str, Any]:
        """
        リクエストの処理状況を確認
        
        引数:
            request_id: リクエストID
            
        戻り値:
            ステータス情報の辞書
        """
        response = await self._send_request("get_request_status", {"request_id": request_id})
        return response

    async def get_service_status(self) -> Dict[str, Any]:
        """
        サービスの状態を取得
        
        戻り値:
            サービスステータスの辞書
        """
        response = await self._send_request("status", {})
        return response.get("data", {}) 
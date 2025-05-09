import asyncio
import json
import os
import uuid
from typing import Dict, Optional, Union, List, Any
import logging
from logging import getLogger

logger = getLogger(__name__)

class BLERequestClient:
    def __init__(self, socket_path: Optional[str] = None, host: Optional[str] = None, port: Optional[int] = None, timeout: float = 10.0):
        self.socket_path = socket_path or os.environ.get("BLE_ORCHESTRATOR_SOCKET", "/tmp/ble-orchestrator.sock")
        self.host = host or os.environ.get("BLE_ORCHESTRATOR_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("BLE_ORCHESTRATOR_PORT", "8378"))
        self.timeout = timeout
        self.use_tcp = bool(host and port) or "BLE_ORCHESTRATOR_TCP" in os.environ
        self._reader = None
        self._writer = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._response_listener_task = None
        self._response_stop_event = asyncio.Event()

    async def connect(self) -> None:
        """サーバーに接続してレスポンスリスナーを開始"""
        if self._reader is not None and self._writer is not None:
            return
        try:
            if self.use_tcp:
                self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
            else:
                self._reader, self._writer = await asyncio.open_unix_connection(self.socket_path)
            
            # レスポンスリスナーを開始
            self._response_stop_event.clear()
            self._response_listener_task = asyncio.create_task(self._response_listener())
            logger.debug("Request client connected and listener started")
        except Exception as e:
            logger.error(f"Failed to connect for requests: {e}")
            raise

    async def _response_listener(self) -> None:
        """
        レスポンスリスナータスク
        サーバーからの応答を受信してFutureを完了させる
        """
        try:
            while not self._response_stop_event.is_set():
                if self._reader is None:
                    break
                    
                try:
                    # 応答受信
                    response_data = await self._reader.readline()
                    logger.debug(f"Received raw response: {response_data}")
                    if not response_data:
                        logger.warning("Request connection closed by server")
                        break
                        
                    # 応答をパース
                    try:
                        response = json.loads(response_data.decode())
                        logger.debug(f"Received response: {response}")
                        
                        # リクエストIDを取得
                        request_id = response.get("request_id")
                        if request_id and request_id in self._pending_requests:
                            # Futureを取得して結果をセット
                            future = self._pending_requests.pop(request_id)
                            logger.debug(f"Future for {request_id} exists: done={future.done()}")
                            if not future.done():
                                future.set_result(response)
                                logger.debug(f"Response received for request {request_id}")
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse response data: {e}")
                    
                except asyncio.CancelledError:
                    break
                    
                except Exception as e:
                    logger.error(f"Error in response listener: {e}")
                    await asyncio.sleep(1.0)  # エラー時は少し待機
                    
        except Exception as e:
            logger.error(f"Unexpected error in response listener: {e}")
        finally:
            logger.debug("Response listener terminated")

    async def _send_request(self, request: Dict[str, Any]) -> asyncio.Future:
        """
        リクエストを送信してFutureを返す
        """
        if self._writer is None or self._response_listener_task is None:
            await self.connect()
            
        # リクエストIDを生成（すでに存在する場合は使用）
        request_id = request.get("request_id", str(uuid.uuid4()))
        request["request_id"] = request_id
        logger.debug(f"&&&&&&&&&request: {request}")
        
        # Futureを作成
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future
        logger.debug(f"&&&&&&&&&pending_requests: {self._pending_requests}")
        
        # リクエスト送信
        request_json = json.dumps(request) + "\n"
        self._writer.write(request_json.encode())
        await self._writer.drain()
        logger.debug(f"Request sent: {request_id}")
        
        return future

    async def read_command(self, mac_address: str, service_uuid: str, characteristic_uuid: str, priority: str = "NORMAL", timeout: float = 10.0) -> asyncio.Future:
        """
        デバイスの特性値を読み取るコマンドをリクエスト
        Futureを返す
        """
        request = {
            "command": "read_sensor",  # 互換性のためサーバー側コマンド名はそのまま
            "mac_address": mac_address,
            "service_uuid": service_uuid,
            "characteristic_uuid": characteristic_uuid,
            "priority": priority,
            "timeout": timeout
        }
        return await self._send_request(request)

    async def scan_command(self, mac_address: str, service_uuid: Optional[str] = None, characteristic_uuid: Optional[str] = None) -> asyncio.Future:
        """
        スキャン済みデータからデバイスの情報を取得するコマンドをリクエスト
        デバイスに接続せずに、最後のスキャン結果からデータを返す
        Futureを返す
        """
        request = {
            "command": "get_scan_data",
            "mac_address": mac_address
        }
        
        # オプションでサービスとキャラクタリスティックを指定可能
        if service_uuid:
            request["service_uuid"] = service_uuid
        if characteristic_uuid:
            request["characteristic_uuid"] = characteristic_uuid
            
        return await self._send_request(request)

    async def send_command(self, mac_address: str, service_uuid: str, characteristic_uuid: str, data: Union[str, bytes, List[int]], response_required: bool = False, priority: str = "NORMAL", timeout: float = 10.0) -> asyncio.Future:
        """
        コマンド送信をリクエスト
        Futureを返す
        """
        if isinstance(data, str):
            data = data.encode().hex()
        elif isinstance(data, bytes):
            data = data.hex()
        elif isinstance(data, list):
            if not all(isinstance(x, int) for x in data):
                raise ValueError("List must contain only integers")
        else:
            raise ValueError("Data must be hex string, bytes or list of integers")
            
        request = {
            "command": "send_command",
            "mac_address": mac_address,
            "service_uuid": service_uuid,
            "characteristic_uuid": characteristic_uuid,
            "data": data,
            "response_required": response_required,
            "priority": priority,
            "timeout": timeout
        }
        return await self._send_request(request)

    async def disconnect(self) -> None:
        """
        接続を閉じる
        レスポンスリスナーを停止し、未完了のリクエストをキャンセル
        """
        # レスポンスリスナーを停止
        if self._response_listener_task:
            self._response_stop_event.set()
            try:
                await asyncio.wait_for(self._response_listener_task, timeout=2.0)
            except asyncio.TimeoutError:
                if not self._response_listener_task.done():
                    self._response_listener_task.cancel()
            self._response_listener_task = None
            
        # 保留中のリクエストをキャンセル
        for request_id, future in self._pending_requests.items():
            if not future.done():
                future.set_exception(ConnectionError("Connection closed"))
        self._pending_requests.clear()
        
        # 接続を閉じる
        if self._writer is None:
            return
            
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception as e:
            logger.error(f"Error closing request connection: {e}")
        finally:
            self._reader = None
            self._writer = None
            logger.debug("Request client disconnected") 
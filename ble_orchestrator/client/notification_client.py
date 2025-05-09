import asyncio
import json
import os
import uuid
from typing import Dict, Callable, Awaitable, Optional, Any
import logging
from logging import getLogger

logger = getLogger(__name__)

class BLENotificationClient:
    def __init__(self, socket_path: Optional[str] = None, host: Optional[str] = None, port: Optional[int] = None, timeout: float = 10.0):
        """
        通知クライアントの初期化
        """
        self.socket_path = socket_path or os.environ.get("BLE_ORCHESTRATOR_SOCKET", "/tmp/ble-orchestrator.sock")
        self.host = host or os.environ.get("BLE_ORCHESTRATOR_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("BLE_ORCHESTRATOR_PORT", "8378"))
        self.timeout = timeout
        self.use_tcp = bool(host and port) or "BLE_ORCHESTRATOR_TCP" in os.environ
        self._reader = None
        self._writer = None
        self._notification_callbacks: Dict[str, Callable[[Dict[str, Any]], Awaitable[None]]] = {}
        self._notification_task = None
        self._notification_stop_event = asyncio.Event()

    async def connect(self) -> None:
        """
        サーバーに接続して通知リスナーを開始
        """
        if self._reader is not None and self._writer is not None:
            return
        try:
            if self.use_tcp:
                self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
            else:
                self._reader, self._writer = await asyncio.open_unix_connection(self.socket_path)
            self._notification_stop_event.clear()
            self._notification_task = asyncio.create_task(self._notification_listener())
            logger.debug("通知クライアント接続完了、リスナー開始")
        except Exception as e:
            logger.error(f"通知クライアント接続失敗: {e}")
            raise

    async def _notification_listener(self) -> None:
        """
        通知リスナータスク
        サーバーからプッシュされる通知のみを受信して処理
        """
        try:
            while not self._notification_stop_event.is_set():
                if self._reader is None:
                    break
                try:
                    # 通知データを受信
                    response_data = await self._reader.readline()
                    if not response_data:
                        logger.warning("通知接続がサーバーによって閉じられました")
                        break
                    
                    # 受信データをパースして処理
                    data = json.loads(response_data.decode())
                    if data.get("type") == "notification":
                        await self._process_notification(data)
                    else:
                        logger.debug(f"通知ではないメッセージを受信: {data.get('type')}")
                except Exception as e:
                    logger.error(f"通知リスナーでエラー: {e}")
                    await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"通知リスナーで予期せぬエラー: {e}")
        finally:
            logger.debug("通知リスナー終了")

    async def _process_notification(self, notification_data: Dict[str, Any]) -> None:
        """
        受信した通知データを処理してコールバックを呼び出す
        """
        callback_id = notification_data.get("callback_id")
        if callback_id in self._notification_callbacks:
            try:
                callback = self._notification_callbacks[callback_id]
                await callback(notification_data)
                logger.debug(f"通知コールバック実行: {callback_id}")
            except Exception as e:
                logger.error(f"通知コールバック実行中にエラー: {e}")
        else:
            logger.warning(f"不明なcallback_idの通知を受信: {callback_id}")

    async def subscribe_notifications(self, mac_address: str, service_uuid: str, characteristic_uuid: str, callback: Callable[[Dict[str, Any]], Awaitable[None]], callback_id: Optional[str] = None) -> str:
        """
        BLE通知を購読登録する
        callback: 通知受信時に呼び出される非同期コールバック関数
        callback_id: コールバックの識別子（省略時は自動生成）
        """
        if callback_id is None:
            callback_id = f"{mac_address}_{characteristic_uuid}_{uuid.uuid4().hex[:8]}"
        
        # 購読リクエスト作成
        request = {
            "command": "subscribe_notifications",
            "mac_address": mac_address,
            "service_uuid": service_uuid,
            "characteristic_uuid": characteristic_uuid,
            "callback_id": callback_id
        }
        
        # コールバックを登録
        self._notification_callbacks[callback_id] = callback
        
        try:
            # 購読リクエストを送信
            await self._send_request(request)
            logger.info(f"通知購読開始: {mac_address} {characteristic_uuid}")
            return callback_id
        except Exception as e:
            # エラー時はコールバック登録を取り消し
            del self._notification_callbacks[callback_id]
            logger.error(f"通知購読失敗: {e}")
            raise

    async def unsubscribe_notifications(self, callback_id: str) -> bool:
        """
        通知購読を解除する
        """
        if callback_id not in self._notification_callbacks:
            logger.warning(f"コールバックID不明のため購読解除できません: {callback_id}")
            return False
        
        # 登録情報を取得
        callback = self._notification_callbacks[callback_id]
        mac_address = None
        characteristic_uuid = None
        
        # callback_idからデバイスとUUIDを解析（簡易的な実装）
        parts = callback_id.split('_')
        if len(parts) >= 2:
            mac_address = parts[0]
            characteristic_uuid = parts[1]
        
        if not mac_address or not characteristic_uuid:
            logger.error(f"購読解除に必要な情報が不足: {callback_id}")
            return False
        
        # 購読解除リクエスト作成
        request = {
            "command": "subscribe_notifications",
            "mac_address": mac_address,
            "service_uuid": "unknown",  # 解除時はサービスUUID不要
            "characteristic_uuid": characteristic_uuid,
            "callback_id": callback_id,
            "unsubscribe": True
        }
        
        try:
            # 購読解除リクエスト送信
            await self._send_request(request)
            # コールバック登録を削除
            del self._notification_callbacks[callback_id]
            logger.info(f"通知購読解除完了: {callback_id}")
            return True
        except Exception as e:
            logger.error(f"通知購読解除失敗: {e}")
            return False

    async def _send_request(self, request: Dict[str, Any]) -> None:
        """
        リクエストを送信する（レスポンスは期待しない）
        """
        if self._writer is None:
            await self.connect()
        
        # リクエスト送信
        request_json = json.dumps(request) + "\n"
        self._writer.write(request_json.encode())
        await self._writer.drain()
        logger.debug(f"通知関連リクエスト送信: {request.get('command')}")

    async def disconnect(self) -> None:
        """
        通知クライアントの接続を閉じる
        通知リスナーを停止してコールバックを全て解除
        """
        # 通知リスナーを停止
        if self._notification_task:
            self._notification_stop_event.set()
            try:
                await asyncio.wait_for(self._notification_task, timeout=2.0)
            except asyncio.TimeoutError:
                if not self._notification_task.done():
                    self._notification_task.cancel()
            self._notification_task = None
            logger.debug("通知リスナー停止")
        
        # 全てのコールバックを登録解除（実際の購読解除ではない）
        self._notification_callbacks.clear()
        
        # 接続を閉じる
        if self._writer is None:
            return
            
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception as e:
            logger.error(f"通知接続を閉じる際にエラー: {e}")
        finally:
            self._reader = None
            self._writer = None
            logger.debug("通知クライアント切断完了") 
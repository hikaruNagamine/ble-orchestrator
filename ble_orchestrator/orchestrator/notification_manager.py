"""
通知管理モジュール - BLE通知の購読と管理を行う
"""

import asyncio
import logging
import time
from typing import Dict, Set, Optional, Callable, Any, Tuple, Union

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice

from .config import BLE_CONNECT_TIMEOUT_SEC
from .types import NotificationRequest, NotificationData

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    BLE通知の管理クラス
    デバイスごとの接続と通知コールバックを管理
    """

    def __init__(self, get_device_func, notify_callback_func):
        """
        初期化
        get_device_func: BLEDeviceを取得する関数
        notify_callback_func: 通知時に呼び出すコールバック関数
        """
        self._get_device_func = get_device_func
        self._notify_callback_func = notify_callback_func
        self._active_connections: Dict[str, BleakClient] = {}  # MAC -> Client
        self._subscriptions: Dict[str, Set[str]] = {}  # MAC -> Set[characteristic_uuid]
        self._callback_map: Dict[str, str] = {}  # 'MAC:uuid' -> callback_id
        self._tasks: Dict[str, asyncio.Task] = {}  # MAC -> Task
        self._lock = asyncio.Lock()
        self._is_running = True

    async def start(self) -> None:
        """
        マネージャーを開始
        """
        logger.info("Starting notification manager")
        self._is_running = True

    async def stop(self) -> None:
        """
        マネージャーを停止し、すべての接続を切断
        """
        logger.info("Stopping notification manager...")
        self._is_running = False
        
        # すべてのタスクをキャンセル
        tasks_to_cancel = []
        for mac, task in self._tasks.items():
            if not task.done():
                # タスクの参照を保持
                tasks_to_cancel.append(task)
                # タスクをキャンセル
                task.cancel()
        
        # タスクの完了を待機（ただし再帰的なキャンセルを防止）
        if tasks_to_cancel:
            try:
                # 短いタイムアウトを設定して待機
                done, pending = await asyncio.wait(tasks_to_cancel, timeout=2.0)
                # 残りのタスクは無視（タイムアウト後も実行中のタスク）
                for task in pending:
                    logger.warning(f"Task {task} is still pending after timeout")
            except Exception as e:
                logger.error(f"Error waiting for tasks to cancel: {e}")
        
        # 接続を全て切断
        for mac in list(self._active_connections.keys()):
            try:
                await self._simple_disconnect(mac)
            except Exception as e:
                logger.error(f"Error disconnecting device {mac}: {e}")
        
        # 参照をクリア
        self._active_connections.clear()
        self._subscriptions.clear()
        self._callback_map.clear()
        self._tasks.clear()
        
        logger.info("Notification manager stopped")

    async def _simple_disconnect(self, mac: str) -> None:
        """
        デバイスから直接切断（シンプルな実装）
        """
        if mac in self._active_connections:
            client = self._active_connections[mac]
            try:
                if client.is_connected:
                    await client.disconnect()
                    logger.info(f"Disconnected from {mac}")
            except Exception as e:
                logger.error(f"Error disconnecting from {mac}: {e}")

    async def process_notification_request(self, request: NotificationRequest) -> None:
        """
        通知リクエストを処理
        """
        mac = request.mac_address
        char_uuid = request.characteristic_uuid
        key = f"{mac}:{char_uuid}"
        
        if request.unsubscribe:
            # サブスクリプション解除
            await self._unsubscribe(mac, char_uuid)
            logger.info(f"Unsubscribed from {char_uuid} on {mac}")
            return
        
        # サブスクリプション追加
        async with self._lock:
            # コールバックIDを記録
            self._callback_map[key] = request.callback_id
            
            # 既に接続済みでなければ接続
            if mac not in self._active_connections:
                # _get_device_funcは同期関数なのでawaitなしで呼び出し
                device = self._get_device_func(mac)
                if not device:
                    raise ValueError(f"Device {mac} not found")
                
                # デバイスへの接続を管理するタスク作成
                self._tasks[mac] = asyncio.create_task(
                    self._manage_device_connection(device, mac)
                )
                
                # サブスクリプション集合を初期化
                self._subscriptions[mac] = set()
            
            # サブスクリプション集合に特性UUIDを追加
            if mac in self._subscriptions:
                self._subscriptions[mac].add(char_uuid)
            
            logger.info(f"Subscribed to {char_uuid} notifications on {mac} with callback {request.callback_id}")

    async def _manage_device_connection(self, device: Union[BLEDevice, str], mac: str) -> None:
        """
        デバイス接続の管理タスク
        接続を維持しながら必要な通知を購読
        bleak 0.22.3ではデバイスにMACアドレス文字列を直接使用可能
        """
        retry_count = 0
        max_retry = 5
        retry_delay = 2.0  # 秒
        
        while self._is_running:
            try:
                logger.info(f"Connecting to {mac} for notifications")
                
                async with self._lock:
                    # BLEクライアント作成と接続
                    client = BleakClient(device, timeout=BLE_CONNECT_TIMEOUT_SEC)
                    await client.connect()
                    logger.info(f"Connected to {mac}")
                    
                    # 接続がうまくいったらリトライカウントをリセット
                    retry_count = 0
                    
                    # 接続を記録
                    self._active_connections[mac] = client
                    
                    # 必要な特性すべてをサブスクライブ
                    for char_uuid in self._subscriptions.get(mac, set()):
                        try:
                            await client.start_notify(
                                char_uuid, 
                                lambda sender, data: asyncio.create_task(
                                    self._notification_handler(mac, char_uuid, data)
                                )
                            )
                            logger.debug(f"Subscribed to {char_uuid} on {mac}")
                        except Exception as e:
                            logger.error(f"Failed to subscribe to {char_uuid} on {mac}: {e}")
                
                # 接続が切れるまで待機
                while self._is_running and client.is_connected:
                    await asyncio.sleep(1.0)
                
                logger.info(f"Connection to {mac} was dropped")
                
            except asyncio.CancelledError:
                logger.info(f"Connection task for {mac} cancelled")
                break
            except Exception as e:
                logger.error(f"Error in connection to {mac}: {e}")
                retry_count += 1
                
                if retry_count > max_retry:
                    logger.error(f"Max retry count reached for {mac}, giving up")
                    break
                
                await asyncio.sleep(retry_delay)
            finally:
                # 接続が切れたら情報をクリア
                if mac in self._active_connections:
                    try:
                        client = self._active_connections[mac]
                        if client.is_connected:
                            await client.disconnect()
                    except Exception as e:
                        logger.error(f"Error disconnecting from {mac}: {e}")
                    finally:
                        del self._active_connections[mac]
        
        logger.info(f"Connection management task for {mac} terminated")

    async def _notification_handler(self, mac: str, char_uuid: str, data: bytearray) -> None:
        """
        通知ハンドラー
        """
        key = f"{mac}:{char_uuid}"
        callback_id = self._callback_map.get(key)
        
        if not callback_id:
            logger.warning(f"Received notification for {key} but no callback ID registered")
            return
            
        try:
            # 通知データを作成
            notification = NotificationData(
                callback_id=callback_id,
                mac_address=mac,
                characteristic_uuid=char_uuid,
                value=bytes(data),
                timestamp=time.time()
            )
            
            # 通知コールバックを呼び出し
            await self._notify_callback_func(notification)
            
            logger.debug(
                f"Notification from {mac} characteristic {char_uuid}: "
                f"{data.hex() if data else 'None'}"
            )
        except Exception as e:
            logger.error(f"Error processing notification: {e}")

    async def _unsubscribe(self, mac: str, char_uuid: str) -> None:
        """
        特定の特性の通知をアンサブスクライブ
        """
        key = f"{mac}:{char_uuid}"
        
        async with self._lock:
            # コールバックマップから削除
            if key in self._callback_map:
                del self._callback_map[key]
            
            # サブスクリプションセットから削除
            if mac in self._subscriptions and char_uuid in self._subscriptions[mac]:
                self._subscriptions[mac].remove(char_uuid)
                
                # デバイスに接続中かつ特性を購読中なら停止
                if mac in self._active_connections:
                    client = self._active_connections[mac]
                    if client.is_connected:
                        try:
                            await client.stop_notify(char_uuid)
                            logger.debug(f"Unsubscribed from {char_uuid} on {mac}")
                        except Exception as e:
                            logger.error(f"Error unsubscribing from {char_uuid} on {mac}: {e}")
                
                # サブスクリプションがなくなったら接続も切断
                if mac in self._subscriptions and not self._subscriptions[mac]:
                    await self._disconnect_device(mac)

    async def _disconnect_device(self, mac: str) -> None:
        """
        デバイスから切断
        """
        # 接続タスクをキャンセル
        if mac in self._tasks:
            task = self._tasks[mac]
            if not task.done():
                task.cancel()
                try:
                    # タイムアウト付きで待機
                    await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for task cancellation for {mac}")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error cancelling task for {mac}: {e}")
            del self._tasks[mac]
        
        # BLE接続を切断
        if mac in self._active_connections:
            client = self._active_connections[mac]
            try:
                if client.is_connected:
                    await client.disconnect()
                    logger.info(f"Disconnected from {mac}")
            except Exception as e:
                logger.error(f"Error disconnecting from {mac}: {e}")
            finally:
                del self._active_connections[mac]
        
        # サブスクリプションを削除
        if mac in self._subscriptions:
            del self._subscriptions[mac]
            
        # このデバイスに関連するコールバックをすべて削除
        keys_to_delete = [key for key in self._callback_map.keys() if key.startswith(f"{mac}:")]
        for key in keys_to_delete:
            del self._callback_map[key]

    def get_active_subscriptions_count(self) -> int:
        """
        アクティブなサブスクリプション数を取得
        """
        count = 0
        for mac in self._subscriptions:
            count += len(self._subscriptions[mac])
        return count 
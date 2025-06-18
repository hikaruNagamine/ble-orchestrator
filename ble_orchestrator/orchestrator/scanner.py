"""
BLEスキャナーモジュール - BLEデバイスの常時スキャンとキャッシュ管理
"""

import asyncio
import logging
import time
import subprocess
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .config import SCAN_CACHE_TTL_SEC, SCAN_INTERVAL_SEC
from .types import ScanResult

logger = logging.getLogger(__name__)

# スキャナー再作成の最小間隔（秒）
MIN_SCANNER_RECREATE_INTERVAL = 300  # 5分
# デバイス未検出の許容時間（秒）
NO_DEVICES_THRESHOLD = 60

class ScanCache:
    """
    スキャン結果のキャッシュを管理するクラス
    各MACアドレスごとに最新のスキャン結果を指定秒数分保持
    """

    def __init__(self, ttl_seconds: float = SCAN_CACHE_TTL_SEC):
        self._cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def add_result(self, device: BLEDevice, adv_data: AdvertisementData) -> None:
        """
        スキャン結果をキャッシュに追加
        """
        result = ScanResult(
            address=device.address,
            name=device.name,
            rssi=adv_data.rssi,
            advertisement_data={
                "local_name": adv_data.local_name,
                "manufacturer_data": {
                    str(k) if isinstance(k, int) else k.hex(): list(v) for k, v in adv_data.manufacturer_data.items()
                },
                "service_data": {
                    k: list(v) for k, v in adv_data.service_data.items()
                },
                "service_uuids": adv_data.service_uuids,
            },
            timestamp=time.time(),
        )

        async with self._lock:
            self._cache[device.address].append(result)
        
        # logger.debug(f"Added scan result for {device.address} ({device.name}), RSSI: {adv_data.rssi}")

    def get_latest_result(self, address: str) -> Optional[ScanResult]:
        """
        指定MACアドレスの最新のスキャン結果を取得
        TTL切れの場合はNoneを返す
        """
        logger.debug(f"get_latest_result: {address}")
        # logger.debug(f"self._cache: {self._cache}")
        logger.debug(f"self._cache[address]: {self._cache[address]}")
        if address not in self._cache or not self._cache[address]:
            logger.debug(f"get_latest_result: {address} not in self._cache or not self._cache[address]")
            return None
        
        latest_result = self._cache[address][-1]
        logger.debug(f"latest_result: {latest_result}")
        logger.debug(f"latest_result.timestamp: {latest_result.timestamp}")
        logger.debug(f"latest_result type: {type(latest_result)}")
        
        # TTLチェック
        if time.time() - latest_result.timestamp > self._ttl_seconds:
            logger.debug(f"Scan result for {address} is expired")
            return None
            
        return latest_result

    def get_all_devices(self) -> List[str]:
        """
        アクティブなデバイスの一覧を取得
        TTL内のデバイスのみ返す
        """
        current_time = time.time()
        active_devices = []
        
        for address, results in self._cache.items():
            if results and current_time - results[-1].timestamp <= self._ttl_seconds:
                active_devices.append(address)
                
        return active_devices


class BLEScanner:
    """
    BLEデバイスの常時スキャンとキャッシュ管理
    """

    def __init__(self, notify_watchdog_func=None):
        self.is_running = False
        self.scanner = BleakScanner(adapter="hci0")
        self.cache = ScanCache()
        self._stop_event = asyncio.Event()
        self._task = None
        self._last_scan_time = time.time()
        self._last_device_count = 0
        self._no_devices_count = 0
        self._recreate_count = 0
        self._notify_watchdog_func = notify_watchdog_func
        self._last_recreate_time = 0
        self._recovery_in_progress = False
        
        # スキャン結果のコールバック設定
        self.scanner.register_detection_callback(self._detection_callback)

    async def _detection_callback(self, device: BLEDevice, adv_data: AdvertisementData) -> None:
        """
        スキャン結果のコールバック
        """
        self._last_scan_time = time.time()
        await self.cache.add_result(device, adv_data)

    async def _recreate_scanner(self) -> None:
        """
        スキャナーを完全に再作成
        """
        # 既に復旧処理中の場合は何もしない
        if self._recovery_in_progress:
            logger.info("Recovery already in progress, skipping scanner recreation")
            return
            
        # 最小再作成間隔をチェック
        current_time = time.time()
        if current_time - self._last_recreate_time < MIN_SCANNER_RECREATE_INTERVAL:
            logger.info("Skipping scanner recreation due to minimum interval restriction")
            return
            
        self._recovery_in_progress = True
        logger.info("Recreating scanner")
        
        try:
            # 現在のスキャナーを停止
            if self.scanner.is_scanning:
                await self.scanner.stop()
            await asyncio.sleep(1.0)
            
            # 再作成回数をカウント
            self._recreate_count += 1
            self._last_recreate_time = current_time
            
            # 3回連続で再作成が必要な場合はウォッチドッグに通知
            if self._recreate_count >= 3:
                logger.warning("Multiple scanner recreations required, notifying watchdog")
                if self._notify_watchdog_func:
                    try:
                        self._notify_watchdog_func()
                        logger.info("Watchdog notified of scanner issues")
                        # ウォッチドッグに任せて、しばらく再作成を試みない
                        await asyncio.sleep(60)  # ウォッチドッグの処理を待つ
                    except Exception as e:
                        logger.error(f"Failed to notify watchdog: {e}")
                self._recreate_count = 0
                return
            
            # 新しいスキャナーを作成
            self.scanner = BleakScanner(adapter="hci0")
            self.scanner.register_detection_callback(self._detection_callback)
            
            # スキャンを再開
            await self.scanner.start()
            self._last_scan_time = time.time()
            self._no_devices_count = 0
            logger.info("Scanner recreated successfully")
            
        except Exception as e:
            logger.error(f"Failed to recreate scanner: {e}")
            raise
        finally:
            self._recovery_in_progress = False

    async def _scan_loop(self) -> None:
        """
        スキャンループ
        """
        try:
            while not self._stop_event.is_set():
                # スキャナーはコールバック方式なので、待機するだけ
                await asyncio.sleep(SCAN_INTERVAL_SEC)
                
                # 定期的にアクティブデバイス数をログ出力
                active_devices = self.cache.get_all_devices()
                active_count = len(active_devices)
                logger.debug(f"Active BLE devices: {active_count}")
                
                # デバイス数が0の場合の処理
                if active_count == 0:
                    self._no_devices_count += 1
                    
                    # NO_DEVICES_THRESHOLD秒以上デバイスが検出されない場合のみ再作成
                    if self._no_devices_count >= NO_DEVICES_THRESHOLD:
                        logger.warning(f"No devices detected for {NO_DEVICES_THRESHOLD} seconds, recreating scanner")
                        await self._recreate_scanner()
                else:
                    self._no_devices_count = 0
                    self._last_device_count = active_count
                    # デバイスが検出された場合は再作成カウントをリセット
                    if self._recreate_count > 0:
                        logger.info("Devices detected, resetting recreation count")
                        self._recreate_count = 0
                
                # 最後のスキャンから一定時間経過している場合
                if time.time() - self._last_scan_time > NO_DEVICES_THRESHOLD:
                    logger.warning(f"No scan results for {NO_DEVICES_THRESHOLD} seconds, recreating scanner")
                    await self._recreate_scanner()
                    
        except asyncio.CancelledError:
            logger.info("Scan loop cancelled")
        except Exception as e:
            logger.error(f"Error in scan loop: {e}")
            # エラー発生時は即座に再作成せず、ウォッチドッグに任せる
            if self._notify_watchdog_func:
                self._notify_watchdog_func()
        finally:
            logger.info("Scan loop terminated")

    async def start(self) -> None:
        """
        スキャンを開始
        """
        if self.is_running:
            logger.warning("Scanner is already running")
            return

        self.is_running = True
        self._stop_event.clear()
        logger.info("Starting BLE scanner")
        
        try:
            await self.scanner.start()
            self._task = asyncio.create_task(self._scan_loop())
            logger.info("BLE scanner started successfully")
        except Exception as e:
            self.is_running = False
            logger.error(f"Failed to start BLE scanner: {e}")
            raise

    async def stop(self) -> None:
        """
        スキャンを停止
        """
        if not self.is_running:
            return

        logger.info("Stopping BLE scanner")
        self._stop_event.set()
        
        if self._task:
            try:
                # タスクをキャンセル
                self._task.cancel()
                # シールドしてタイムアウト付きで待機
                await asyncio.wait_for(asyncio.shield(asyncio.gather(self._task, return_exceptions=True)), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout while waiting for scanner task to cancel")
            except asyncio.CancelledError:
                logger.debug("Scanner task cancelled successfully")
            except Exception as e:
                logger.error(f"Error cancelling scanner task: {e}")
            
        try:
            await self.scanner.stop()
        except Exception as e:
            logger.error(f"Error while stopping scanner: {e}")
            
        self.is_running = False
        logger.info("BLE scanner stopped") 
"""
BLEスキャナーモジュール - BLEデバイスの常時スキャンとキャッシュ管理
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .config import SCAN_CACHE_TTL_SEC, SCAN_INTERVAL_SEC
from .types import ScanResult

logger = logging.getLogger(__name__)


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
                    k.hex(): list(v) for k, v in adv_data.manufacturer_data.items()
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
        
        logger.debug(f"Added scan result for {device.address} ({device.name}), RSSI: {adv_data.rssi}")

    def get_latest_result(self, address: str) -> Optional[ScanResult]:
        """
        指定MACアドレスの最新のスキャン結果を取得
        TTL切れの場合はNoneを返す
        """
        if address not in self._cache or not self._cache[address]:
            return None
        
        latest_result = self._cache[address][-1]
        
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

    def __init__(self):
        self.is_running = False
        self.scanner = BleakScanner()
        self.cache = ScanCache()
        self._stop_event = asyncio.Event()
        self._task = None
        
        # スキャン結果のコールバック設定
        self.scanner.register_detection_callback(self._detection_callback)

    async def _detection_callback(self, device: BLEDevice, adv_data: AdvertisementData) -> None:
        """
        スキャン結果のコールバック
        """
        await self.cache.add_result(device, adv_data)

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
                logger.debug(f"Active BLE devices: {len(active_devices)}")
        except asyncio.CancelledError:
            logger.info("Scan loop cancelled")
        except Exception as e:
            logger.error(f"Error in scan loop: {e}")
        finally:
            logger.info("Scan loop terminated")

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
                self._task.cancel()
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            
        try:
            await self.scanner.stop()
        except Exception as e:
            logger.error(f"Error while stopping scanner: {e}")
            
        self.is_running = False
        logger.info("BLE scanner stopped") 
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

    def __init__(self):
        self.is_running = False
        self.scanner = BleakScanner(adapter="hci0")
        self.cache = ScanCache()
        self._stop_event = asyncio.Event()
        self._task = None
        self._last_scan_time = time.time()
        self._last_device_count = 0
        self._no_devices_count = 0
        self._recreate_count = 0
        
        # スキャン結果のコールバック設定
        self.scanner.register_detection_callback(self._detection_callback)

    async def _restart_bluetooth_stack(self) -> None:
        """
        Bluetoothスタックを再起動
        """
        logger.info("Restarting Bluetooth stack")
        try:
            # Bluetoothサービスを再起動
            subprocess.run(["sudo", "systemctl", "restart", "bluetooth"], check=True)
            await asyncio.sleep(2.0)  # 再起動を待機
            
            # hci0アダプターをリセット
            subprocess.run(["sudo", "hciconfig", "hci0", "reset"], check=True)
            await asyncio.sleep(1.0)  # リセットを待機
            
            logger.info("Bluetooth stack restarted successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart Bluetooth stack: {e}")
            raise

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
        logger.info("Recreating scanner")
        try:
            # 現在のスキャナーを停止
            if self.scanner.is_scanning:
                await self.scanner.stop()
            await asyncio.sleep(1.0)
            
            # 再作成回数をカウント
            self._recreate_count += 1
            
            # 3回連続で再作成が必要な場合はBluetoothスタックを再起動
            if self._recreate_count >= 3:
                logger.warning("Multiple scanner recreations required, restarting Bluetooth stack")
                await self._restart_bluetooth_stack()
                self._recreate_count = 0
            
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
                    
                    # 30秒以上デバイスが検出されない場合（SCAN_INTERVAL_SECが1秒の場合、30回）
                    if self._no_devices_count >= 30:
                        logger.warning("No devices detected for 30 seconds, recreating scanner")
                        await self._recreate_scanner()
                else:
                    self._no_devices_count = 0
                    self._last_device_count = active_count
                    self._recreate_count = 0  # 正常に動作している場合はカウントをリセット
                
                # 最後のスキャンから一定時間経過している場合
                if time.time() - self._last_scan_time > 30.0:
                    logger.warning("No scan results for 30 seconds, recreating scanner")
                    await self._recreate_scanner()
                    
        except asyncio.CancelledError:
            logger.info("Scan loop cancelled")
        except Exception as e:
            logger.error(f"Error in scan loop: {e}")
            # エラー発生時もスキャナーを再作成
            try:
                await self._recreate_scanner()
            except Exception as recreate_error:
                logger.error(f"Failed to recreate scanner after error: {recreate_error}")
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
"""
BLEスキャナーモジュール - BLEデバイスの常時スキャンとキャッシュ管理
"""

import asyncio
import logging
import time
import subprocess
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .config import SCAN_CACHE_TTL_SEC, SCAN_INTERVAL_SEC, DEFAULT_SCAN_ADAPTER
from .types import ScanResult

logger = logging.getLogger(__name__)

# スキャナー再作成の最小間隔（秒）
MIN_SCANNER_RECREATE_INTERVAL = 180  # 3分
# デバイス未検出の許容時間（秒）
NO_DEVICES_THRESHOLD = 60

# BLE操作の排他制御用グローバルロック
_ble_operation_lock = asyncio.Lock()

# スキャナー排他制御用のグローバル変数
_scanner_stopping = False  # スキャナー停止フラグ
_client_connecting = False  # クライアント接続中フラグ
_scan_ready = asyncio.Event()  # スキャン準備完了イベント
_scan_completed = asyncio.Event()  # スキャン停止完了イベント
_client_completed = asyncio.Event()  # クライアント完了イベント

class ScanCache:
    """
    スキャン結果のキャッシュを管理するクラス
    各MACアドレスごとに最新のスキャン結果を指定秒数分保持
    """

    def __init__(self, ttl_seconds: float = SCAN_CACHE_TTL_SEC):
        self._cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5分ごとにクリーンアップ

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
            
            # 定期的なクリーンアップを実行
            await self._cleanup_expired_entries()
        
        # logger.debug(f"Added scan result for {device.address} ({device.name}), RSSI: {adv_data.rssi}")

    async def _cleanup_expired_entries(self) -> None:
        """
        期限切れのエントリを定期的にクリーンアップ
        """
        current_time = time.time()
        
        # クリーンアップ間隔をチェック
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
            
        self._last_cleanup = current_time
        
        # 期限切れのデバイスを特定
        expired_devices = []
        for address, results in self._cache.items():
            if not results:
                # 空のdequeは削除対象
                expired_devices.append(address)
                continue
                
            # 最新の結果が期限切れかチェック
            latest_result = results[-1]
            if current_time - latest_result.timestamp > self._ttl_seconds:
                expired_devices.append(address)
        
        # 期限切れのデバイスを削除
        for address in expired_devices:
            del self._cache[address]
            
        if expired_devices and logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Cleaned up {len(expired_devices)} expired device entries")

    def get_latest_result(self, address: str) -> Optional[ScanResult]:
        """
        指定MACアドレスの最新のスキャン結果を取得
        TTL切れの場合はNoneを返す
        """
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Getting latest scan result for {address}")
            
        if address not in self._cache or not self._cache[address]:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"No cached results found for {address}")
            return None
        
        latest_result = self._cache[address][-1]
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Latest result timestamp: {latest_result.timestamp}")
        
        # TTLチェック
        current_time = time.time()
        age = current_time - latest_result.timestamp
        if age > self._ttl_seconds:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Scan result for {address} is expired (age: {age:.1f}s, TTL: {self._ttl_seconds}s)")
            return None
            
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Returning valid scan result for {address} (age: {age:.1f}s)")
            
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

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        キャッシュの統計情報を取得
        """
        current_time = time.time()
        total_devices = len(self._cache)
        total_results = sum(len(results) for results in self._cache.values())
        
        # 有効なデバイス数を計算
        valid_devices = 0
        expired_devices = 0
        for address, results in self._cache.items():
            if results:
                latest_result = results[-1]
                age = current_time - latest_result.timestamp
                if age <= self._ttl_seconds:
                    valid_devices += 1
                else:
                    expired_devices += 1
        
        return {
            "total_devices": total_devices,
            "valid_devices": valid_devices,
            "expired_devices": expired_devices,
            "total_results": total_results,
            "last_cleanup": self._last_cleanup,
            "cleanup_interval": self._cleanup_interval,
            "ttl_seconds": self._ttl_seconds
        }


class BLEScanner:
    """
    BLEデバイスの常時スキャンとキャッシュ管理
    """

    def __init__(self, notify_watchdog_func=None):
        self.is_running = False
        self._scanner_active = False  # 独自のスキャン状態管理フラグ
        self.scanner = BleakScanner(
            adapter=DEFAULT_SCAN_ADAPTER,
            detection_callback=self._detection_callback
        )
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
        self._recreate_lock = asyncio.Lock()  # スキャナー再作成と停止処理の排他制御用
        
        # 排他制御用の状態管理
        self._exclusive_control_enabled = True  # 排他制御の有効/無効フラグ
        
        # デッドロック検出用
        self._exclusive_control_start_time = None  # 排他制御開始時刻
        self._deadlock_threshold = 90  # 90秒以上排他制御が続く場合はデッドロックとみなす

    async def _detection_callback(self, device: BLEDevice, adv_data: AdvertisementData) -> None:
        """
        スキャン結果のコールバック
        """
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Detection callback called for device: {device.address} ({device.name}), RSSI: {adv_data.rssi}")
        
        self._last_scan_time = time.time()
        await self.cache.add_result(device, adv_data)
        
        # 定期的に検出統計をログ出力（1分ごと）
        current_time = time.time()
        if hasattr(self, '_last_stats_log') and (current_time - self._last_stats_log) > 60:
            cache_stats = self.cache.get_cache_stats()
            logger.info(f"Scan statistics - Active devices: {cache_stats['valid_devices']}, "
                       f"Total cached: {cache_stats['total_devices']}, "
                       f"Expired: {cache_stats['expired_devices']}")
            self._last_stats_log = current_time
        elif not hasattr(self, '_last_stats_log'):
            self._last_stats_log = current_time

    async def _should_skip_recreation(self) -> bool:
        """
        スキャナー再作成をスキップすべきかチェック
        """
        # 既に復旧処理中の場合は何もしない
        if self._recovery_in_progress:
            logger.info("Recovery already in progress, skipping scanner recreation")
            return True
            
        # 最小再作成間隔をチェック
        current_time = time.time()
        if current_time - self._last_recreate_time < MIN_SCANNER_RECREATE_INTERVAL:
            # ただし、異常な長時間のスキャン停止の場合は強制再作成
            time_since_last_scan = current_time - self._last_scan_time
            if time_since_last_scan > 300:  # 5分以上
                logger.warning(f"Force recreation despite interval restriction - no scan for {time_since_last_scan:.1f}s")
                return False
            logger.info("Skipping scanner recreation due to minimum interval restriction")
            return True
            
        return False

    async def _stop_current_scanner(self) -> None:
        """
        現在のスキャナーを安全に停止
        """
        if not self._scanner_active:
            return
            
        try:
            logger.debug("Stopping scanner")
            # タイムアウト付きでスキャナー停止を試行
            await asyncio.wait_for(self.scanner.stop(), timeout=5.0)
            logger.debug("Scanner stopped successfully")
        except asyncio.TimeoutError:
            logger.warning("Timeout while stopping scanner, forcing stop")
        except Exception as e:
            error_msg = str(e)
            if "InProgress" in error_msg:
                logger.info("Scanner stop already in progress, waiting for completion")
                # InProgressエラーの場合は少し待機してから状態をクリア
                await asyncio.sleep(0.5)
            else:
                logger.warning(f"Error stopping scanner: {e}")
        finally:
            self._scanner_active = False  # スキャン状態フラグをクリア

    async def _notify_watchdog_if_needed(self) -> None:
        """
        必要に応じてウォッチドッグに通知
        """
            
        logger.warning("Multiple scanner recreations required, notifying watchdog")
        if self._notify_watchdog_func:
            try:
                # ウォッチドッグに通知（service.pyの改善された機能を使用）
                self._notify_watchdog_func()
                logger.info("Watchdog notification sent")
                
            except Exception as e:
                logger.error(f"Failed to notify watchdog: {e}")
        
        self._recreate_count = 0

    async def _create_new_scanner(self) -> None:
        """
        新しいスキャナーを作成して開始
        """
        logger.info("Creating new BleakScanner instance")
        
        # 新しいスキャナーを作成
        self.scanner = BleakScanner(
            adapter=DEFAULT_SCAN_ADAPTER,
            detection_callback=self._detection_callback
        )
        
        logger.info("Starting new scanner")
        # スキャンを再開
        await self.scanner.start()
        self._scanner_active = True  # スキャン状態フラグを設定
        self._last_scan_time = time.time()
        self._no_devices_count = 0
        logger.info("Scanner recreated successfully")
        logger.debug(f"Scanner active: {self._scanner_active}, last scan time: {self._last_scan_time}")

    async def _update_recreation_stats(self) -> None:
        """
        再作成統計情報を更新
        """
        current_time = time.time()
        self._recreate_count += 1
        self._last_recreate_time = current_time

    async def _recreate_scanner(self) -> None:
        """
        スキャナーを完全に再作成
        _recreate_lockにより、stop()メソッドとの競合を防ぐ
        """
        # スキャナー再作成と停止処理の排他制御
        # これにより、再作成中にstop()が呼ばれても安全に処理できる
        async with self._recreate_lock:
            # 事前チェック
            if await self._should_skip_recreation():
                return
                
            self._recovery_in_progress = True
            logger.info("Recreating scanner")
            
            # BLE操作の排他制御
            async with _ble_operation_lock:
                try:
                    # 現在のスキャナーを停止
                    await self._stop_current_scanner()
                    
                    await asyncio.sleep(1.0)
                    
                    # 再作成統計情報を更新
                    await self._update_recreation_stats()
                    
                    # ウォッチドッグ通知が必要な場合は処理を終了
                    await self._notify_watchdog_if_needed()
                    
                    # 新しいスキャナーを作成
                    await self._create_new_scanner()
                    
                    # 再作成後の状態をログ出力
                    logger.info("Scanner recreation completed, monitoring for detection callbacks")
                    
                except Exception as e:
                    logger.error(f"Failed to recreate scanner: {e}")
                    self._scanner_active = False  # エラーが発生した場合もフラグをクリア
                    raise
                finally:
                    self._recovery_in_progress = False

    def _check_recreation_needed(self) -> tuple[bool, str]:
        """
        スキャナー再作成が必要かどうかを判定
        返り値: (再作成が必要か, 理由)
        """
        # 定期的にアクティブデバイス数をログ出力
        active_devices = self.cache.get_all_devices()
        active_count = len(active_devices)
        current_time = time.time()
        time_since_last_scan = current_time - self._last_scan_time
        
        logger.debug(f"Active BLE devices: {active_count}, time since last scan: {time_since_last_scan:.1f}s")
        
        # デバイス数が0の場合の処理
        if active_count == 0:
            self._no_devices_count += 1
            logger.debug(f"No devices detected, count: {self._no_devices_count}/{NO_DEVICES_THRESHOLD}")
            
            # NO_DEVICES_THRESHOLD秒以上デバイスが検出されない場合
            if self._no_devices_count >= NO_DEVICES_THRESHOLD:
                logger.warning(f"Recreation needed: No devices detected for {NO_DEVICES_THRESHOLD} seconds")
                return True, f"No devices detected for {NO_DEVICES_THRESHOLD} seconds"
        else:
            if self._no_devices_count > 0:
                logger.info(f"Devices detected again, resetting no_devices_count from {self._no_devices_count} to 0")
            self._no_devices_count = 0
            self._last_device_count = active_count
            # デバイスが検出された場合は再作成カウントをリセット
            if self._recreate_count > 0:
                logger.info("Devices detected, resetting recreation count")
                self._recreate_count = 0
        
        # 最後のスキャンから一定時間経過している場合（デバイス検出条件と重複しない場合のみ）
        if time_since_last_scan > NO_DEVICES_THRESHOLD:
            logger.warning(f"Recreation needed: No scan results for {NO_DEVICES_THRESHOLD} seconds (last scan: {time_since_last_scan:.1f}s ago)")
            return True, f"No scan results for {NO_DEVICES_THRESHOLD} seconds (last scan: {time_since_last_scan:.1f}s ago)"
        
        # 異常な長時間のスキャン停止を検出（追加）
        if time_since_last_scan > 300:  # 5分以上
            logger.error(f"CRITICAL: Scanner appears to be completely stopped - no scan results for {time_since_last_scan:.1f}s")
            return True, f"Scanner appears stopped - no scan results for {time_since_last_scan:.1f}s"
        
        return False, ""

    async def _scan_loop(self) -> None:
        """
        スキャンループ
        """
        global _scanner_stopping, _client_connecting, _scan_completed, _client_completed, _scan_ready
        
        try:
            # スキャンループの開始　スキャンループの終了条件は、スキャン停止イベントが設定されている場合
            while not self._stop_event.is_set():
                # 排他制御が有効な場合、クライアント接続要求をチェック
                if self._exclusive_control_enabled and _scanner_stopping:
                    logger.info("Scanner stop requested for client connection")
                    
                    # スキャン停止前の統計をログ出力
                    active_devices = self.cache.get_all_devices()
                    logger.info(f"Stopping scanner - Active devices: {len(active_devices)}")
                    
                    # スキャナーを停止
                    await self._stop_current_scanner()
                    _scan_completed.set()  # スキャン停止完了を通知
                    
                    # クライアント完了を待機（タイムアウト付き）
                    try:
                        await asyncio.wait_for(_client_completed.wait(), timeout=60.0)  # 60秒タイムアウト
                    except asyncio.TimeoutError:
                        logger.warning("Timeout waiting for client completion, forcing scanner restart")
                        # タイムアウトした場合は強制的にスキャンを再開
                    except asyncio.CancelledError:
                        logger.warning("Scan loop cancelled")
                        break
                    _client_completed.clear()  # イベントをリセット
                    
                    # 停止イベントが設定されている場合は終了
                    if self._stop_event.is_set():
                        # スキャンループの終了　
                        logger.warning("Scan loop terminated due to stop event")
                        break
                    
                    # スキャンを再開
                    logger.info("Restarting scanner after client connection")
                    try:
                        await self.scanner.start()
                        self._scanner_active = True
                        logger.info("Scanner restarted successfully")
                    except Exception as e:
                        logger.error(f"Failed to restart scanner: {e}")
                        # 再開に失敗した場合は再作成を試行
                        await self._recreate_scanner()
                    
                    _scan_ready.set()  # スキャン準備完了を通知
                
                # スキャナーはコールバック方式なので、待機するだけ
                await asyncio.sleep(SCAN_INTERVAL_SEC)
                
                # デッドロック検出
                if self._exclusive_control_start_time:
                    current_time = time.time()
                    exclusive_duration = current_time - self._exclusive_control_start_time
                    if exclusive_duration > self._deadlock_threshold:
                        logger.error(f"POTENTIAL DEADLOCK DETECTED: Exclusive control active for {exclusive_duration:.1f}s")
                        # デッドロックを検出した場合は強制的にリセット
                        _scanner_stopping = False
                        _client_connecting = False
                        _client_completed.set()
                        self._exclusive_control_start_time = None
                        logger.warning("Forced reset of exclusive control due to potential deadlock")
                
                # スキャナー再作成が必要かどうかを判定
                need_recreation, recreation_reason = self._check_recreation_needed()
                
                # スキャナー再作成が必要な場合、一度だけ実行
                if need_recreation:
                    logger.warning(f"{recreation_reason}, recreating scanner")
                    await self._recreate_scanner()
                    
                    # 異常な長時間のスキャン停止の場合はウォッチドッグに通知
                    time_since_last_scan = time.time() - self._last_scan_time
                    if time_since_last_scan > 300:  # 5分以上
                        logger.error(f"CRITICAL: Scanner has been stopped for {time_since_last_scan:.1f}s, notifying watchdog")
                        if self._notify_watchdog_func:
                            self._notify_watchdog_func()
                    
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
        
        # 排他制御用イベントを初期化
        _scan_ready.clear()
        _scan_completed.clear()
        _client_completed.clear()
        
        try:
            await self.scanner.start()
            self._scanner_active = True  # スキャン状態フラグを設定
            self._task = asyncio.create_task(self._scan_loop())
            logger.info("BLE scanner started successfully")
            
            # スキャン準備完了を通知
            _scan_ready.set()
        except Exception as e:
            self.is_running = False
            self._scanner_active = False
            logger.error(f"Failed to start BLE scanner: {e}")
            raise

    def request_scanner_stop(self) -> None:
        """
        クライアント接続のためにスキャナー停止を要求
        """
        global _scanner_stopping, _client_connecting
        _scanner_stopping = True
        _client_connecting = True
        self._exclusive_control_start_time = time.time()  # 排他制御開始時刻を記録
        logger.info("Scanner stop requested for client connection")

    def notify_client_completed(self) -> None:
        """
        クライアント処理完了を通知
        """
        global _scanner_stopping, _client_connecting
        _client_connecting = False
        _scanner_stopping = False
        _client_completed.set()
        
        # 排他制御時間をログ出力
        if self._exclusive_control_start_time:
            duration = time.time() - self._exclusive_control_start_time
            logger.info(f"Client operation completed, scanner can resume (exclusive control duration: {duration:.1f}s)")
            self._exclusive_control_start_time = None  # リセット
        else:
            logger.info("Client operation completed, scanner can resume")

    def wait_for_scan_ready(self) -> asyncio.Event:
        """
        スキャン準備完了イベントを取得
        """
        return _scan_ready

    def wait_for_scan_completed(self) -> asyncio.Event:
        """
        スキャン停止完了イベントを取得
        """
        return _scan_completed

    def set_exclusive_control_enabled(self, enabled: bool) -> None:
        """
        排他制御の有効/無効を設定
        """
        self._exclusive_control_enabled = enabled
        logger.info(f"Exclusive control {'enabled' if enabled else 'disabled'}")

    def is_client_connecting(self) -> bool:
        """
        クライアントが接続中かどうかを確認
        """
        return _client_connecting

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
            
            # _recreate_scannerとの競合を防ぐため、Lockを使用
            # これにより、再作成中に停止処理が呼ばれても安全に処理できる
            async with self._recreate_lock:
                # BLE操作の排他制御
                async with _ble_operation_lock:
                    try:
                        # 既存のメソッドを再利用してスキャナーを停止
                        await self._stop_current_scanner()
                    except Exception as e:
                        logger.error(f"Error while stopping scanner: {e}")
                        self._scanner_active = False  # エラーが発生した場合もフラグをクリア
                
        self.is_running = False
        logger.info("BLE scanner stopped")

    def get_scanner_status(self) -> Dict[str, Any]:
        """
        スキャナーの詳細な状態を取得
        """
        current_time = time.time()
        time_since_last_scan = current_time - self._last_scan_time
        
        # キャッシュ統計を取得
        cache_stats = self.cache.get_cache_stats()
        
        return {
            "is_running": self.is_running,
            "scanner_active": self._scanner_active,
            "recovery_in_progress": self._recovery_in_progress,
            "last_scan_time": self._last_scan_time,
            "time_since_last_scan": time_since_last_scan,
            "no_devices_count": self._no_devices_count,
            "recreate_count": self._recreate_count,
            "last_device_count": self._last_device_count,
            "active_devices": cache_stats["valid_devices"],
            "total_cached_devices": cache_stats["total_devices"],
            "expired_devices": cache_stats["expired_devices"],
            "cache_stats": cache_stats,
            "scan_health": "healthy" if time_since_last_scan < 60 else "warning" if time_since_last_scan < 300 else "critical"
        } 
"""
ウォッチドッグモジュール - BLEハング検出と自動復旧機能
"""

import asyncio
import logging
import subprocess
import time
from typing import Callable, Optional

from .config import (
    ADAPTER_RESET_COMMAND,
    BLUETOOTH_RESTART_COMMAND,
    ADAPTER_STATUS_COMMAND,
    BLE_ADAPTERS,
    CONSECUTIVE_FAILURES_THRESHOLD,
    WATCHDOG_CHECK_INTERVAL_SEC,
)

logger = logging.getLogger(__name__)


class BLEWatchdog:
    """
    BLEアダプタの状態を監視し、必要に応じて復旧する
    """

    def __init__(
        self,
        get_failures_func: Callable[[], int],
        reset_failures_func: Callable[[], None],
        adapters: Optional[list] = None,
    ):
        """
        初期化
        get_failures_func: 連続失敗回数を取得する関数
        reset_failures_func: 失敗カウンタをリセットする関数
        adapters: BLEアダプタ名のリスト（デフォルト: config.BLE_ADAPTERS）
        """
        self._get_failures_func = get_failures_func
        self._reset_failures_func = reset_failures_func
        self._adapters = adapters or BLE_ADAPTERS
        self._stop_event = asyncio.Event()
        self._task = None
        self._recovery_in_progress = False
        self._start_time = time.time()
        self._component_issues = {}  # コンポーネントごとの問題を追跡
        self._adapter_status = {}  # 各アダプタの状態を追跡
        self._recovery_completion_event = asyncio.Event()  # 復旧完了通知用
        self._recovery_callbacks = []  # 復旧完了時のコールバック関数リスト

    async def notify_component_issue(self, component_name: str, issue_description: str) -> None:
        """
        コンポーネントから問題の通知を受け取る
        component_name: 問題を報告するコンポーネントの名前
        issue_description: 問題の説明
        """
        logger.warning(f"Component issue reported - {component_name}: {issue_description}")
        
        # コンポーネントの問題を記録
        self._component_issues[component_name] = {
            'description': issue_description,
            'timestamp': time.time()
        }
        
        # BleakClient失敗の場合は軽量なアダプタリセットのみ実行
        if component_name == "bleakclient_failure":
            if not self._recovery_in_progress:
                logger.info(f"Starting lightweight adapter reset due to BleakClient failure")
                asyncio.create_task(self._reset_adapters_only())
        else:
            # その他の問題の場合は通常の復旧プロセスを開始
            if not self._recovery_in_progress:
                logger.info(f"Starting recovery process due to {component_name} issue")
                asyncio.create_task(self._recover_ble_adapter())

    def add_recovery_completion_callback(self, callback: Callable[[], None]) -> None:
        """
        復旧完了時のコールバック関数を追加
        """
        self._recovery_callbacks.append(callback)
        logger.debug(f"Added recovery completion callback, total callbacks: {len(self._recovery_callbacks)}")

    def remove_recovery_completion_callback(self, callback: Callable[[], None]) -> None:
        """
        復旧完了時のコールバック関数を削除
        """
        if callback in self._recovery_callbacks:
            self._recovery_callbacks.remove(callback)
            logger.debug(f"Removed recovery completion callback, remaining callbacks: {len(self._recovery_callbacks)}")

    async def wait_for_recovery_completion(self, timeout: Optional[float] = None) -> bool:
        """
        復旧完了を待機
        timeout: 待機タイムアウト（秒）、Noneの場合は無制限
        返り値: 復旧が完了した場合はTrue、タイムアウトした場合はFalse
        """
        try:
            await asyncio.wait_for(self._recovery_completion_event.wait(), timeout=timeout)
            logger.info("Recovery completion event received")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for recovery completion after {timeout}s")
            return False

    async def check_bluetooth_service_status(self) -> str:
        """
        Bluetoothサービスの状態を確認
        返り値: サービスの状態（"active", "inactive", "failed", "unknown"）
        """
        try:
            # systemctlでBluetoothサービスの状態を確認
            result = await self._run_shell_command_with_output("systemctl is-active bluetooth")
            
            if result.strip() == "active":
                return "active"
            elif result.strip() == "inactive":
                return "inactive"
            elif result.strip() == "failed":
                return "failed"
            else:
                return "unknown"
        except Exception as e:
            logger.error(f"Error checking Bluetooth service status: {e}")
            return "unknown"

    async def wait_for_bluetooth_service_ready(self, timeout: float = 30.0) -> bool:
        """
        Bluetoothサービスが準備完了するまで待機
        timeout: 待機タイムアウト（秒）
        返り値: サービスが準備完了した場合はTrue、タイムアウトした場合はFalse
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = await self.check_bluetooth_service_status()
            
            if status == "active":
                logger.info("Bluetooth service is active and ready")
                return True
            elif status == "failed":
                logger.warning("Bluetooth service is in failed state")
                return False
            
            logger.debug(f"Bluetooth service status: {status}, waiting...")
            await asyncio.sleep(2.0)
        
        logger.warning(f"Timeout waiting for Bluetooth service to be ready after {timeout}s")
        return False

    async def start(self) -> None:
        """
        ウォッチドッグを開始
        """
        if self._task is not None:
            logger.warning("Watchdog is already running")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._watchdog_loop())
        self._start_time = time.time()
        logger.info("BLE watchdog started")

    async def stop(self) -> None:
        """
        ウォッチドッグを停止
        """
        if self._task is None:
            return

        logger.info("Stopping BLE watchdog...")
        self._stop_event.set()
        
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
            logger.warning("Watchdog task forcibly cancelled")
        except Exception as e:
            logger.error(f"Error while stopping watchdog: {e}")
            
        self._task = None
        logger.info("BLE watchdog stopped")

    async def _watchdog_loop(self) -> None:
        """
        ウォッチドッグループ
        """
        try:
            while not self._stop_event.is_set():
                try:
                    # 連続失敗回数をチェック
                    consecutive_failures = self._get_failures_func()
                    
                    if consecutive_failures >= CONSECUTIVE_FAILURES_THRESHOLD:
                        if not self._recovery_in_progress:
                            logger.warning(
                                f"Detected BLE issues: {consecutive_failures} consecutive failures. "
                                "Starting recovery process."
                            )
                            # 別タスクで復旧処理を実行
                            asyncio.create_task(self._recover_ble_adapter())
                    
                    # スキャナーの異常検出（追加）
                    await self._check_scanner_health()
                    
                    # 定期的にハートビートログを出力
                    uptime = time.time() - self._start_time
                    logger.debug(
                        f"Watchdog heartbeat: Uptime {uptime:.1f}s, "
                        f"Consecutive failures: {consecutive_failures}"
                    )
                    
                    # 次の確認まで待機
                    await asyncio.sleep(WATCHDOG_CHECK_INTERVAL_SEC)
                    
                except asyncio.CancelledError:
                    logger.info("Watchdog loop cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in watchdog loop: {e}")
                    await asyncio.sleep(WATCHDOG_CHECK_INTERVAL_SEC)
        finally:
            logger.info("Watchdog loop terminated")

    async def _check_scanner_health(self) -> None:
        """
        スキャナーの健全性をチェック
        """
        try:
            # スキャナーの状態を確認（サービスから取得する必要がある）
            # ここでは簡易的なチェックとして、BLEアダプタの状態を確認
            for adapter in self._adapters:
                status = await self._check_adapter_status(adapter)
                if status != "UP RUNNING":
                    logger.warning(f"Scanner health check: Adapter {adapter} has issues: {status}")
                    # アダプタに問題がある場合は復旧を開始
                    if not self._recovery_in_progress:
                        logger.warning(f"Starting recovery due to adapter {adapter} issues")
                        asyncio.create_task(self._recover_ble_adapter())
                        return
        except Exception as e:
            logger.error(f"Error in scanner health check: {e}")

    async def _recover_ble_adapter(self) -> None:
        """
        BLEアダプタの復旧を試みる
        1. 各アダプタの状態確認
        2. 問題のあるアダプタのリセット
        3. Bluetoothサービス再起動（必ず実行）
        """
        self._recovery_in_progress = True
        
        try:
            logger.info(f"Starting BLE adapter recovery for adapters: {self._adapters}")
            
            # 1. 各アダプタの状態を確認
            adapter_issues = []
            for adapter in self._adapters:
                status = await self._check_adapter_status(adapter)
                self._adapter_status[adapter] = status
                
                if status != "UP RUNNING":
                    adapter_issues.append(adapter)
                    logger.warning(f"Adapter {adapter} has issues: {status}")
            
            # 2. 問題のあるアダプタをリセット
            if adapter_issues:
                logger.info(f"Resetting problematic adapters: {adapter_issues}")
                for adapter in adapter_issues:
                    success = await self._reset_single_adapter(adapter)
                    if success:
                        logger.info(f"Successfully reset adapter {adapter}")
                    else:
                        logger.error(f"Failed to reset adapter {adapter}")
                
                # リセット後に少し待機
                await asyncio.sleep(3.0)
                
                # リセット後の状態を再確認
                still_problematic = []
                for adapter in adapter_issues:
                    status = await self._check_adapter_status(adapter)
                    self._adapter_status[adapter] = status
                    
                    if status != "UP RUNNING":
                        still_problematic.append(adapter)
                        logger.warning(f"Adapter {adapter} still has issues after reset: {status}")
            
            # 3. Bluetoothサービス再起動（必ず実行）
            logger.info("Performing Bluetooth service restart as part of recovery process")
            
            success = await self._run_shell_command(BLUETOOTH_RESTART_COMMAND)
            if success:
                logger.info("Successfully restarted Bluetooth service")
                # 再起動後に十分な待機時間
                await asyncio.sleep(10.0)
                
                # 再起動後の最終確認
                final_issues = []
                for adapter in self._adapters:
                    status = await self._check_adapter_status(adapter)
                    self._adapter_status[adapter] = status
                    
                    if status != "UP RUNNING":
                        final_issues.append(adapter)
                        logger.warning(f"Adapter {adapter} still has issues after service restart: {status}")
                
                if final_issues:
                    logger.error(
                        f"Failed to recover adapters {final_issues} after service restart. "
                        "Manual intervention may be required."
                    )
                else:
                    logger.info("All adapters recovered successfully after service restart")
                    self._reset_failures_func()
            else:
                logger.error("Failed to restart Bluetooth service")
                # サービス再起動に失敗した場合でも、アダプタリセットが成功していれば失敗カウンタをリセット
                if not adapter_issues or not still_problematic:
                    logger.info("Adapter reset was successful, resetting failure counter despite service restart failure")
                    self._reset_failures_func()
        
        except Exception as e:
            logger.error(f"Error during BLE adapter recovery: {e}")
        finally:
            self._recovery_in_progress = False
            # 復旧完了を通知
            self._recovery_completion_event.set()
            
            # コールバック関数を実行
            for callback in self._recovery_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in recovery completion callback: {e}")
            
            # イベントをリセット（次回の復旧に備えて）
            self._recovery_completion_event.clear()

    async def _check_adapter_status(self, adapter: str) -> str:
        """
        アダプタの状態を確認
        """
        try:
            cmd = ADAPTER_STATUS_COMMAND.format(adapter=adapter)
            result = await self._run_shell_command_with_output(cmd)
            
            if "UP RUNNING" in result:
                return "UP RUNNING"
            elif "DOWN" in result:
                return "DOWN"
            elif "No such device" in result:
                return "NOT_FOUND"
            else:
                return "UNKNOWN"
        except Exception as e:
            logger.error(f"Error checking status for adapter {adapter}: {e}")
            return "ERROR"

    async def _reset_single_adapter(self, adapter: str) -> bool:
        """
        単一アダプタをリセット
        """
        try:
            logger.info(f"Resetting adapter {adapter}")
            reset_cmd = ADAPTER_RESET_COMMAND.format(adapter=adapter)
            return await self._run_shell_command(reset_cmd)
        except Exception as e:
            logger.error(f"Error resetting adapter {adapter}: {e}")
            return False

    async def _run_shell_command_with_output(self, command: str) -> str:
        """
        シェルコマンドを実行して出力を取得
        """
        logger.debug(f"Running command: {command}")
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode().strip()
                logger.debug(f"Command succeeded: {output}")
                return output
            else:
                error_output = stderr.decode().strip()
                logger.error(f"Command failed with exit code {process.returncode}: {error_output}")
                return error_output
                
        except Exception as e:
            logger.error(f"Failed to execute command '{command}': {e}")
            return str(e)

    async def _run_shell_command(self, command: str) -> bool:
        """
        シェルコマンドを実行
        """
        logger.debug(f"Running command: {command}")
        
        try:
            # サブプロセスを非同期で実行
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.debug(f"Command succeeded: {stdout.decode().strip()}")
                return True
            else:
                logger.error(f"Command failed with exit code {process.returncode}: {stderr.decode().strip()}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to execute command '{command}': {e}")
            return False

    async def _reset_adapters_only(self) -> None:
        """
        BleakClient失敗時の軽量なアダプタリセットのみを実行
        Bluetoothサービス再起動は行わない
        """
        self._recovery_in_progress = True
        
        try:
            logger.info(f"Starting lightweight adapter reset for BleakClient failure, adapters: {self._adapters}")
            
            # 各アダプタをリセット
            reset_success_count = 0
            for adapter in self._adapters:
                logger.info(f"Resetting adapter {adapter} due to BleakClient failure")
                success = await self._reset_single_adapter(adapter)
                if success:
                    logger.info(f"Successfully reset adapter {adapter}")
                    reset_success_count += 1
                else:
                    logger.error(f"Failed to reset adapter {adapter}")
            
            # リセット後に少し待機
            await asyncio.sleep(2.0)
            
            # リセット後の状態を確認
            recovered_count = 0
            for adapter in self._adapters:
                status = await self._check_adapter_status(adapter)
                self._adapter_status[adapter] = status
                
                if status == "UP RUNNING":
                    recovered_count += 1
                    logger.info(f"Adapter {adapter} recovered successfully")
                else:
                    logger.warning(f"Adapter {adapter} still has issues after reset: {status}")
            
            if recovered_count == len(self._adapters):
                logger.info("All adapters recovered successfully after BleakClient failure")
                self._reset_failures_func()
            elif reset_success_count > 0:
                logger.info(f"Partial recovery: {recovered_count}/{len(self._adapters)} adapters recovered")
                self._reset_failures_func()
            else:
                logger.error("Failed to recover any adapters after BleakClient failure")
        
        except Exception as e:
            logger.error(f"Error during lightweight adapter reset: {e}")
        finally:
            self._recovery_in_progress = False
            # 復旧完了を通知
            self._recovery_completion_event.set()
            
            # コールバック関数を実行
            for callback in self._recovery_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in recovery completion callback: {e}")
            
            # イベントをリセット（次回の復旧に備えて）
            self._recovery_completion_event.clear() 
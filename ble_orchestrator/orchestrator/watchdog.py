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
        adapter_name: str = "hci0",
    ):
        """
        初期化
        get_failures_func: 連続失敗回数を取得する関数
        reset_failures_func: 失敗カウンタをリセットする関数
        adapter_name: BLEアダプタ名
        """
        self._get_failures_func = get_failures_func
        self._reset_failures_func = reset_failures_func
        self._adapter_name = adapter_name
        self._stop_event = asyncio.Event()
        self._task = None
        self._recovery_in_progress = False
        self._start_time = time.time()
        self._component_issues = {}  # コンポーネントごとの問題を追跡

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
        
        # 即座に復旧プロセスを開始
        if not self._recovery_in_progress:
            logger.info(f"Starting recovery process due to {component_name} issue")
            asyncio.create_task(self._recover_ble_adapter())

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

    async def _recover_ble_adapter(self) -> None:
        """
        BLEアダプタの復旧を試みる
        1. アダプタリセット
        2. Bluetoothサービス再起動
        """
        self._recovery_in_progress = True
        
        try:
            # まずアダプタリセットを試行
            logger.info(f"Attempting to reset BLE adapter {self._adapter_name}")
            reset_cmd = ADAPTER_RESET_COMMAND.format(adapter=self._adapter_name)
            
            success = await self._run_shell_command(reset_cmd)
            if success:
                logger.info(f"Successfully reset BLE adapter {self._adapter_name}")
                self._reset_failures_func()
                self._recovery_in_progress = False
                return
                
            # アダプタリセットが失敗した場合はBluetoothサービス再起動を試行
            logger.warning(
                f"Adapter reset failed. Attempting to restart Bluetooth service"
            )
            
            success = await self._run_shell_command(BLUETOOTH_RESTART_COMMAND)
            if success:
                logger.info("Successfully restarted Bluetooth service")
                # 再起動後に少し待機
                await asyncio.sleep(5.0)
                self._reset_failures_func()
            else:
                logger.error(
                    "Failed to recover BLE adapter. Manual intervention may be required."
                )
        
        except Exception as e:
            logger.error(f"Error during BLE adapter recovery: {e}")
        finally:
            self._recovery_in_progress = False

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
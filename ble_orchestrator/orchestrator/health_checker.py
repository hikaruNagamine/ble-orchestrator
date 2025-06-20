"""
ヘルスチェックモジュール - BLE Orchestratorの包括的な健全性監視
"""

import asyncio
import logging
import time
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Union
from .config import BLE_ADAPTERS

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """ヘルスステータス"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """コンポーネントの健全性情報"""
    name: str
    status: HealthStatus
    message: str
    last_check: float
    response_time_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class SystemHealth:
    """システム全体の健全性情報"""
    overall_status: HealthStatus
    components: Dict[str, ComponentHealth]
    timestamp: float
    uptime_sec: float
    version: str = "1.0.0"


class HealthChecker:
    """
    包括的なヘルスチェック機能を提供するクラス
    """

    def __init__(
        self,
        get_scanner_status_func: Callable[[], Dict[str, Any]],
        get_queue_status_func: Callable[[], Dict[str, Any]],
        get_handler_status_func: Callable[[], Dict[str, Any]],
        get_notification_status_func: Callable[[], Dict[str, Any]],
        get_ipc_status_func: Callable[[], Dict[str, Any]],
        start_time: float,
    ):
        """
        初期化
        """
        self._get_scanner_status = get_scanner_status_func
        self._get_queue_status = get_queue_status_func
        self._get_handler_status = get_handler_status_func
        self._get_notification_status = get_notification_status_func
        self._get_ipc_status = get_ipc_status_func
        self._start_time = start_time
        
        self._stop_event = asyncio.Event()
        self._task = None
        self._last_health_check = time.time()
        self._health_history: List[SystemHealth] = []
        self._max_history_size = 100

    async def start(self) -> None:
        """
        ヘルスチェックを開始
        """
        if self._task is not None:
            logger.warning("Health checker is already running")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._health_check_loop())
        logger.info("Health checker started")

    async def stop(self) -> None:
        """
        ヘルスチェックを停止
        """
        if self._task is None:
            return

        logger.info("Stopping health checker...")
        self._stop_event.set()
        
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
            logger.warning("Health checker task forcibly cancelled")
        except Exception as e:
            logger.error(f"Error while stopping health checker: {e}")
            
        self._task = None
        logger.info("Health checker stopped")

    async def _health_check_loop(self) -> None:
        """
        ヘルスチェックループ
        """
        try:
            while not self._stop_event.is_set():
                try:
                    # ヘルスチェック実行
                    health = await self._perform_health_check()
                    
                    # 履歴に追加
                    self._health_history.append(health)
                    if len(self._health_history) > self._max_history_size:
                        self._health_history.pop(0)
                    
                    # ステータスに応じたログ出力
                    if health.overall_status == HealthStatus.CRITICAL:
                        logger.error(f"System health is CRITICAL: {health}")
                    elif health.overall_status == HealthStatus.WARNING:
                        logger.warning(f"System health is WARNING: {health}")
                    else:
                        logger.debug(f"System health is HEALTHY: {health}")
                    
                    # 次のチェックまで待機（30秒間隔）
                    await asyncio.sleep(30.0)
                    
                except asyncio.CancelledError:
                    logger.info("Health check loop cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in health check loop: {e}")
                    await asyncio.sleep(30.0)
        finally:
            logger.info("Health check loop terminated")

    async def _perform_health_check(self) -> SystemHealth:
        """
        包括的なヘルスチェックを実行
        """
        start_time = time.time()
        components = {}
        
        # 各コンポーネントのヘルスチェック
        components["scanner"] = await self._check_scanner_health()
        components["queue"] = await self._check_queue_health()
        components["handler"] = await self._check_handler_health()
        components["notification"] = await self._check_notification_health()
        components["ipc"] = await self._check_ipc_health()
        components["bluetooth"] = await self._check_bluetooth_health()
        components["system"] = await self._check_system_health()
        
        # 全体のステータスを決定
        overall_status = self._determine_overall_status(components)
        
        self._last_health_check = time.time()
        
        return SystemHealth(
            overall_status=overall_status,
            components=components,
            timestamp=time.time(),
            uptime_sec=time.time() - self._start_time
        )

    async def _check_scanner_health(self) -> ComponentHealth:
        """
        スキャナーの健全性チェック
        """
        start_time = time.time()
        
        try:
            status = self._get_scanner_status()
            
            # スキャナーが動作しているかチェック
            if not status.get("is_running", False):
                return ComponentHealth(
                    name="scanner",
                    status=HealthStatus.CRITICAL,
                    message="Scanner is not running",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000
                )
            
            # アクティブデバイス数をチェック
            active_devices = status.get("active_devices", 0)
            if active_devices == 0:
                return ComponentHealth(
                    name="scanner",
                    status=HealthStatus.WARNING,
                    message=f"No active devices detected (0 devices)",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"active_devices": active_devices}
                )
            
            return ComponentHealth(
                name="scanner",
                status=HealthStatus.HEALTHY,
                message=f"Scanner is running with {active_devices} active devices",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={"active_devices": active_devices}
            )
            
        except Exception as e:
            return ComponentHealth(
                name="scanner",
                status=HealthStatus.CRITICAL,
                message=f"Scanner health check failed: {e}",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000
            )

    async def _check_queue_health(self) -> ComponentHealth:
        """
        キューの健全性チェック
        """
        start_time = time.time()
        
        try:
            status = self._get_queue_status()
            
            queue_size = status.get("queue_size", 0)
            
            # キューサイズが大きすぎる場合
            if queue_size > 100:
                return ComponentHealth(
                    name="queue",
                    status=HealthStatus.CRITICAL,
                    message=f"Queue size is too large: {queue_size}",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"queue_size": queue_size}
                )
            elif queue_size > 50:
                return ComponentHealth(
                    name="queue",
                    status=HealthStatus.WARNING,
                    message=f"Queue size is high: {queue_size}",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"queue_size": queue_size}
                )
            
            return ComponentHealth(
                name="queue",
                status=HealthStatus.HEALTHY,
                message=f"Queue is healthy with {queue_size} items",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={"queue_size": queue_size}
            )
            
        except Exception as e:
            return ComponentHealth(
                name="queue",
                status=HealthStatus.CRITICAL,
                message=f"Queue health check failed: {e}",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000
            )

    async def _check_handler_health(self) -> ComponentHealth:
        """
        ハンドラーの健全性チェック
        """
        start_time = time.time()
        
        try:
            status = self._get_handler_status()
            
            consecutive_failures = status.get("consecutive_failures", 0)
            
            if consecutive_failures >= 5:
                return ComponentHealth(
                    name="handler",
                    status=HealthStatus.CRITICAL,
                    message=f"Too many consecutive failures: {consecutive_failures}",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"consecutive_failures": consecutive_failures}
                )
            elif consecutive_failures >= 3:
                return ComponentHealth(
                    name="handler",
                    status=HealthStatus.WARNING,
                    message=f"Multiple consecutive failures: {consecutive_failures}",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"consecutive_failures": consecutive_failures}
                )
            
            return ComponentHealth(
                name="handler",
                status=HealthStatus.HEALTHY,
                message=f"Handler is healthy (failures: {consecutive_failures})",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={"consecutive_failures": consecutive_failures}
            )
            
        except Exception as e:
            return ComponentHealth(
                name="handler",
                status=HealthStatus.CRITICAL,
                message=f"Handler health check failed: {e}",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000
            )

    async def _check_notification_health(self) -> ComponentHealth:
        """
        通知マネージャーの健全性チェック
        """
        start_time = time.time()
        
        try:
            status = self._get_notification_status()
            
            active_subscriptions = status.get("active_subscriptions", 0)
            
            return ComponentHealth(
                name="notification",
                status=HealthStatus.HEALTHY,
                message=f"Notification manager is healthy with {active_subscriptions} subscriptions",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={"active_subscriptions": active_subscriptions}
            )
            
        except Exception as e:
            return ComponentHealth(
                name="notification",
                status=HealthStatus.CRITICAL,
                message=f"Notification health check failed: {e}",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000
            )

    async def _check_ipc_health(self) -> ComponentHealth:
        """
        IPCサーバーの健全性チェック
        """
        start_time = time.time()
        
        try:
            status = self._get_ipc_status()
            
            connections = status.get("connections", 0)
            
            return ComponentHealth(
                name="ipc",
                status=HealthStatus.HEALTHY,
                message=f"IPC server is healthy with {connections} connections",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={"connections": connections}
            )
            
        except Exception as e:
            return ComponentHealth(
                name="ipc",
                status=HealthStatus.CRITICAL,
                message=f"IPC health check failed: {e}",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000
            )

    async def _check_bluetooth_health(self) -> ComponentHealth:
        """
        Bluetoothスタックの健全性チェック
        """
        start_time = time.time()
        
        try:
            # 各アダプタの状態をチェック
            adapter_statuses = {}
            healthy_adapters = []
            problematic_adapters = []
            
            for adapter in BLE_ADAPTERS:
                try:
                    result = await self._run_command(f"hciconfig {adapter}")
                    
                    if "UP RUNNING" in result:
                        adapter_statuses[adapter] = "UP RUNNING"
                        healthy_adapters.append(adapter)
                    elif "DOWN" in result:
                        adapter_statuses[adapter] = "DOWN"
                        problematic_adapters.append(adapter)
                    elif "No such device" in result:
                        adapter_statuses[adapter] = "NOT_FOUND"
                        problematic_adapters.append(adapter)
                    else:
                        adapter_statuses[adapter] = "UNKNOWN"
                        problematic_adapters.append(adapter)
                except Exception as e:
                    adapter_statuses[adapter] = f"ERROR: {e}"
                    problematic_adapters.append(adapter)
            
            # 全アダプタが正常な場合
            if not problematic_adapters:
                return ComponentHealth(
                    name="bluetooth",
                    status=HealthStatus.HEALTHY,
                    message=f"All Bluetooth adapters are UP and RUNNING: {healthy_adapters}",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"adapter_statuses": adapter_statuses}
                )
            # 一部のアダプタに問題がある場合
            elif healthy_adapters:
                return ComponentHealth(
                    name="bluetooth",
                    status=HealthStatus.WARNING,
                    message=f"Some Bluetooth adapters have issues. Healthy: {healthy_adapters}, Problematic: {problematic_adapters}",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"adapter_statuses": adapter_statuses}
                )
            # 全アダプタに問題がある場合
            else:
                return ComponentHealth(
                    name="bluetooth",
                    status=HealthStatus.CRITICAL,
                    message=f"All Bluetooth adapters have issues: {problematic_adapters}",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={"adapter_statuses": adapter_statuses}
                )
                
        except Exception as e:
            return ComponentHealth(
                name="bluetooth",
                status=HealthStatus.CRITICAL,
                message=f"Bluetooth health check failed: {e}",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000
            )

    async def _check_system_health(self) -> ComponentHealth:
        """
        システムリソースの健全性チェック
        """
        start_time = time.time()
        
        try:
            # メモリ使用量をチェック
            memory_result = await self._run_command("free -m | grep Mem")
            memory_parts = memory_result.split()
            total_memory = int(memory_parts[1])
            used_memory = int(memory_parts[2])
            memory_usage_percent = (used_memory / total_memory) * 100
            
            # CPU使用率をチェック
            cpu_result = await self._run_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1")
            cpu_usage = float(cpu_result.strip())
            
            details = {
                "memory_usage_percent": round(memory_usage_percent, 1),
                "cpu_usage_percent": round(cpu_usage, 1),
                "total_memory_mb": total_memory,
                "used_memory_mb": used_memory
            }
            
            # リソース使用率が高い場合
            if memory_usage_percent > 90 or cpu_usage > 90:
                return ComponentHealth(
                    name="system",
                    status=HealthStatus.CRITICAL,
                    message=f"High resource usage - Memory: {memory_usage_percent:.1f}%, CPU: {cpu_usage:.1f}%",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details=details
                )
            elif memory_usage_percent > 80 or cpu_usage > 80:
                return ComponentHealth(
                    name="system",
                    status=HealthStatus.WARNING,
                    message=f"Moderate resource usage - Memory: {memory_usage_percent:.1f}%, CPU: {cpu_usage:.1f}%",
                    last_check=time.time(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details=details
                )
            
            return ComponentHealth(
                name="system",
                status=HealthStatus.HEALTHY,
                message=f"System resources are healthy - Memory: {memory_usage_percent:.1f}%, CPU: {cpu_usage:.1f}%",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                details=details
            )
            
        except Exception as e:
            return ComponentHealth(
                name="system",
                status=HealthStatus.UNKNOWN,
                message=f"System health check failed: {e}",
                last_check=time.time(),
                response_time_ms=(time.time() - start_time) * 1000
            )

    def _determine_overall_status(self, components: Dict[str, ComponentHealth]) -> HealthStatus:
        """
        全体のステータスを決定
        """
        if any(comp.status == HealthStatus.CRITICAL for comp in components.values()):
            return HealthStatus.CRITICAL
        elif any(comp.status == HealthStatus.WARNING for comp in components.values()):
            return HealthStatus.WARNING
        elif any(comp.status == HealthStatus.UNKNOWN for comp in components.values()):
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    async def _run_command(self, command: str) -> str:
        """
        シェルコマンドを実行
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Command failed: {stderr.decode().strip()}")
        
        return stdout.decode().strip()

    def get_current_health(self) -> Optional[SystemHealth]:
        """
        現在のヘルスステータスを取得
        """
        if self._health_history:
            return self._health_history[-1]
        return None

    def get_health_history(self) -> List[SystemHealth]:
        """
        ヘルスチェック履歴を取得
        """
        return self._health_history.copy()

    def get_component_health(self, component_name: str) -> Optional[ComponentHealth]:
        """
        特定コンポーネントのヘルスステータスを取得
        """
        current_health = self.get_current_health()
        if current_health:
            return current_health.components.get(component_name)
        return None 
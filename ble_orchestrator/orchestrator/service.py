"""
BLE Orchestratorのメインサービスモジュール
各コンポーネントを統括して動作を制御する
"""

import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Any, Union, cast

from bleak.backends.device import BLEDevice

from .config import LOG_DIR, LOG_FILE
from .handler import BLERequestHandler
from .ipc_server import IPCServer
from .queue_manager import RequestQueueManager
from .scanner import BLEScanner
from .types import BLERequest, ReadRequest, ScanRequest, ServiceStatus, WriteRequest, ScanResult
from .watchdog import BLEWatchdog

# ロガー設定
logger = logging.getLogger(__name__)


class BLEOrchestratorService:
    """
    BLE Orchestratorのメインサービスクラス
    各コンポーネントを管理し、サービス全体を制御する
    """

    def __init__(self):
        """
        サービスの初期化
        各コンポーネントのインスタンス化と連携設定
        """
        self._setup_logging()
        self._start_time = time.time()
        
        # スキャナー
        self.scanner = BLEScanner()
        
        # リクエストハンドラー
        self.handler = BLERequestHandler(self._get_ble_device)
        
        # リクエストキュー
        self.queue_manager = RequestQueueManager(self.handler.handle_request)
        
        # ウォッチドッグ
        self.watchdog = BLEWatchdog(
            self.handler.get_consecutive_failures,
            self.handler.reset_failure_count
        )
        
        # IPCサーバー
        self.ipc_server = IPCServer(
            self._get_scan_result,
            self._enqueue_request,
            self._get_service_status
        )
        
        logger.info("BLE Orchestrator service initialized")

    def _setup_logging(self) -> None:
        """
        ロギング設定
        """
        # ログディレクトリ作成
        os.makedirs(LOG_DIR, exist_ok=True)
        
        # ルートロガー設定
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # ファイルハンドラ
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
        root_logger.addHandler(file_handler)
        
        # コンソールハンドラ
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S"
            )
        )
        root_logger.addHandler(console_handler)
        
        # モジュール別ロガー設定
        logging.getLogger("bleak").setLevel(logging.WARNING)

    async def start(self) -> None:
        """
        サービスを開始
        各コンポーネントを順次起動
        """
        logger.info("Starting BLE Orchestrator service...")
        
        try:
            # スキャナー起動
            await self.scanner.start()
            
            # キューマネージャー起動
            await self.queue_manager.start()
            
            # ウォッチドッグ起動
            await self.watchdog.start()
            
            # IPCサーバー起動
            await self.ipc_server.start()
            
            logger.info("All components started successfully")
            logger.info("BLE Orchestrator service is running")
            
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """
        サービスを停止
        各コンポーネントを逆順で停止
        """
        logger.info("Stopping BLE Orchestrator service...")
        
        # IPCサーバー停止
        try:
            await self.ipc_server.stop()
        except Exception as e:
            logger.error(f"Error stopping IPC server: {e}")
        
        # ウォッチドッグ停止
        try:
            await self.watchdog.stop()
        except Exception as e:
            logger.error(f"Error stopping watchdog: {e}")
        
        # キューマネージャー停止
        try:
            await self.queue_manager.stop()
        except Exception as e:
            logger.error(f"Error stopping queue manager: {e}")
        
        # スキャナー停止
        try:
            await self.scanner.stop()
        except Exception as e:
            logger.error(f"Error stopping scanner: {e}")
        
        logger.info("BLE Orchestrator service stopped")

    def _get_ble_device(self, mac_address: str) -> Optional[BLEDevice]:
        """
        スキャン結果からBLEDeviceを取得
        """
        result = self.scanner.cache.get_latest_result(mac_address)
        if not result:
            return None
            
        # BLEDeviceっぽいものを作る（ScanResultからの変換）
        # 実際には実装はBLEDeviceに似せた独自クラスを作るべきかもしれない
        class SimpleBLEDevice:
            def __init__(self, address: str, name: Optional[str]):
                self.address = address
                self.name = name
                
        return SimpleBLEDevice(result.address, result.name)

    def _get_scan_result(self, mac_address: str) -> Optional[ScanResult]:
        """
        スキャン結果を取得
        """
        return self.scanner.cache.get_latest_result(mac_address)

    async def _enqueue_request(self, request: BLERequest) -> str:
        """
        リクエストをキューに追加
        """
        return await self.queue_manager.enqueue_request(request)

    def _get_service_status(self) -> Dict[str, Any]:
        """
        サービスステータスを取得
        """
        uptime = time.time() - self._start_time
        
        status = ServiceStatus(
            is_running=True,
            adapter_status="ok" if self.handler.get_consecutive_failures() == 0 else "warning",
            queue_size=self.queue_manager.get_queue_size(),
            last_error=None,  # TODO: 最後のエラーを保持する仕組み
            uptime_sec=uptime
        )
        
        # 辞書形式に変換
        return {
            "is_running": status.is_running,
            "adapter_status": status.adapter_status,
            "queue_size": status.queue_size,
            "last_error": status.last_error,
            "uptime_sec": round(status.uptime_sec, 1),
            "active_devices": len(self.scanner.cache.get_all_devices()),
        } 
"""
BLE Orchestratorのメインサービスモジュール
各コンポーネントを統括して動作を制御する
"""

import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Any, Union, cast
import uuid

from bleak.backends.device import BLEDevice

from .config import LOG_DIR, LOG_FILE, DEFAULT_REQUEST_TIMEOUT_SEC, BLE_ADAPTERS
from .handler import BLERequestHandler
from .ipc_server import IPCServer
from .queue_manager import RequestQueueManager
from .scanner import BLEScanner
from .types import (
    BLERequest, ReadRequest, ScanRequest, ServiceStatus, WriteRequest, 
    ScanResult, NotificationRequest, NotificationData, RequestPriority, RequestStatus
)
from .watchdog import BLEWatchdog
from .notification_manager import NotificationManager

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
        
        # リクエストハンドラー
        self.handler = BLERequestHandler(
            get_device_func=self._get_ble_device,
            get_scan_data_func=self._get_ble_device
        )
        
        # リクエストキュー
        self.queue_manager = RequestQueueManager(self.handler.handle_request)
        
        # ウォッチドッグ
        self.watchdog = BLEWatchdog(
            self.handler.get_consecutive_failures,
            self.handler.reset_failure_count,
            adapters=BLE_ADAPTERS
        )
        
        # スキャナー（ウォッチドッグ通知機能付き）
        self.scanner = BLEScanner(notify_watchdog_func=self._notify_watchdog)
        
        # 通知マネージャー
        self.notification_manager = NotificationManager(
            self._get_ble_device,
            self._handle_notification
        )
        
        # IPCサーバー
        self.ipc_server = IPCServer(
            self._get_scan_result,
            self._enqueue_request,
            self._get_service_status,
            queue_manager=self.queue_manager
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
        # root_logger.setLevel(logging.INFO)
        root_logger.setLevel(logging.DEBUG)
        
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
            
            # 通知マネージャー起動
            await self.notification_manager.start()
            
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
        errors = []
        
        # IPCサーバー停止
        try:
            await self.ipc_server.stop()
        except Exception as e:
            errors.append(f"IPC server: {e}")
            logger.error(f"Error stopping IPC server: {e}")
        
        # 通知マネージャー停止
        try:
            await self.notification_manager.stop()
        except Exception as e:
            errors.append(f"Notification manager: {e}")
            logger.error(f"Error stopping notification manager: {e}")
        
        # ウォッチドッグ停止
        try:
            await self.watchdog.stop()
        except Exception as e:
            errors.append(f"Watchdog: {e}")
            logger.error(f"Error stopping watchdog: {e}")
        
        # キューマネージャー停止
        try:
            await self.queue_manager.stop()
        except Exception as e:
            errors.append(f"Queue manager: {e}")
            logger.error(f"Error stopping queue manager: {e}")
        
        # スキャナー停止
        try:
            await self.scanner.stop()
        except Exception as e:
            errors.append(f"Scanner: {e}")
            logger.error(f"Error stopping scanner: {e}")
        
        if errors:
            logger.warning(f"Service stopped with {len(errors)} errors: {', '.join(errors)}")
        else:
            logger.info("BLE Orchestrator service stopped cleanly")

    def _get_ble_device(self, mac_address: str) -> Optional[Union[BLEDevice, str]]:
        """
        スキャン結果からBLEDeviceを取得
        bleak 0.22.3では文字列のMACアドレスを直接使用することも可能
        """
        result = self.scanner.cache.get_latest_result(mac_address)
        if not result:
            return None
            
        return result

    def _get_scan_result(self, mac_address: str) -> Optional[ScanResult]:
        """
        スキャン結果を取得
        """
        return self.scanner.cache.get_latest_result(mac_address)

    async def _enqueue_request(self, request: BLERequest) -> str:
        """
        リクエストをキューに入れるか、通知リクエストの場合は直接処理
        """
        # 通知リクエストは別途処理
        if isinstance(request, NotificationRequest):
            try:
                await self.notification_manager.process_notification_request(request)
                return request.request_id
            except Exception as e:
                logger.error(f"Error processing notification request: {e}")
                raise
                
        # 通常のリクエストはキューに追加
        return await self.queue_manager.enqueue_request(request)

    async def _handle_notification(self, notification: NotificationData) -> None:
        """
        通知を受信したときの処理
        IPCサーバー経由でクライアントに通知を送信
        """
        try:
            # IPCサーバーに通知を送信
            await self.ipc_server.send_notification(notification)
        except Exception as e:
            logger.error(f"Error sending notification to clients: {e}")

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
            uptime_sec=uptime,
            active_subscriptions=self.notification_manager.get_active_subscriptions_count()
        )
        
        # 辞書形式に変換
        return {
            "is_running": status.is_running,
            "adapter_status": status.adapter_status,
            "queue_size": status.queue_size,
            "last_error": status.last_error,
            "uptime_sec": round(status.uptime_sec, 1),
            "active_devices": len(self.scanner.cache.get_all_devices()),
            "active_subscriptions": status.active_subscriptions
        }

    def _notify_watchdog(self) -> None:
        """
        ウォッチドッグ通知機能
        スキャナーの問題をウォッチドッグに通知し、復旧完了を待機
        """
        logger.info("Notifying watchdog of scanner issues")
        # 非同期メソッドを同期的なコンテキストから呼び出すためのヘルパー
        async def _async_notify():
            try:
                # ウォッチドッグに通知
                await self.watchdog.notify_component_issue(
                    "scanner",
                    "Scanner detected potential Bluetooth stack issues"
                )
                
                # 復旧完了を待機（タイムアウト: 60秒）
                logger.info("Waiting for watchdog recovery completion...")
                recovery_completed = await self.watchdog.wait_for_recovery_completion(timeout=60.0)
                
                if recovery_completed:
                    logger.info("Watchdog recovery completed successfully")
                    
                    # Bluetoothサービスの準備完了を待機
                    logger.info("Waiting for Bluetooth service to be ready...")
                    service_ready = await self.watchdog.wait_for_bluetooth_service_ready(timeout=30.0)
                    
                    if service_ready:
                        logger.info("Bluetooth service is ready")
                        # サービス準備完了後、BLEアダプタの状態安定化を待機
                        await asyncio.sleep(5.0)
                    else:
                        logger.warning("Bluetooth service not ready, waiting for stabilization...")
                        await asyncio.sleep(10.0)
                else:
                    logger.warning("Watchdog recovery timeout, checking Bluetooth service status...")
                    # タイムアウトした場合でも、Bluetoothサービスの状態を確認
                    service_status = await self.watchdog.check_bluetooth_service_status()
                    logger.info(f"Bluetooth service status: {service_status}")
                    
                    if service_status == "active":
                        logger.info("Bluetooth service is active, proceeding...")
                        await asyncio.sleep(5.0)
                    else:
                        logger.warning("Bluetooth service not active, waiting longer...")
                        await asyncio.sleep(15.0)
                
                logger.info("Watchdog recovery wait completed")
                
            except Exception as e:
                logger.error(f"Error in watchdog notification: {e}")
                # エラーが発生した場合でも、BLEアダプタの状態安定化を待機
                await asyncio.sleep(15.0)
            
        # 非同期通知をイベントループで実行
        asyncio.create_task(_async_notify())

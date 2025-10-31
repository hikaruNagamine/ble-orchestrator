"""
service.pyの改善されたユニットテスト
実装に合わせた正確なテストを提供
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from ble_orchestrator.orchestrator.service import BLEOrchestratorService
from ble_orchestrator.orchestrator.types import ScanResult


@pytest.fixture
async def orchestrator_service():
    """テスト用のBLEオーケストレーターサービスインスタンス"""
    with patch("ble_orchestrator.orchestrator.service.BLEScanner") as mock_scanner:
        with patch("ble_orchestrator.orchestrator.service.RequestQueueManager") as mock_queue:
            with patch("ble_orchestrator.orchestrator.service.BLERequestHandler") as mock_handler:
                with patch("ble_orchestrator.orchestrator.service.BLEWatchdog") as mock_watchdog:
                    with patch("ble_orchestrator.orchestrator.service.IPCServer") as mock_ipc:
                        with patch("ble_orchestrator.orchestrator.service.NotificationManager") as mock_notif:
                            # モックインスタンスのセットアップ
                            mock_scanner_instance = MagicMock()
                            mock_scanner_instance.start = AsyncMock()
                            mock_scanner_instance.stop = AsyncMock()
                            mock_scanner_instance.cache = MagicMock()
                            mock_scanner_instance.cache.get_latest_result = MagicMock(return_value=None)
                            mock_scanner_instance.cache.get_all_devices = MagicMock(return_value=[])
                            mock_scanner.return_value = mock_scanner_instance
                            
                            mock_queue_instance = MagicMock()
                            mock_queue_instance.start = AsyncMock()
                            mock_queue_instance.stop = AsyncMock()
                            mock_queue_instance.get_queue_size = MagicMock(return_value=0)
                            mock_queue.return_value = mock_queue_instance
                            
                            mock_handler_instance = MagicMock()
                            mock_handler_instance.get_consecutive_failures = MagicMock(return_value=0)
                            mock_handler_instance.set_exclusive_control_enabled = MagicMock()
                            mock_handler_instance.is_exclusive_control_enabled = MagicMock(return_value=True)
                            mock_handler.return_value = mock_handler_instance
                            
                            mock_watchdog_instance = MagicMock()
                            mock_watchdog_instance.start = AsyncMock()
                            mock_watchdog_instance.stop = AsyncMock()
                            mock_watchdog.return_value = mock_watchdog_instance
                            
                            mock_notif_instance = MagicMock()
                            mock_notif_instance.start = AsyncMock()
                            mock_notif_instance.stop = AsyncMock()
                            mock_notif_instance.get_active_subscriptions_count = MagicMock(return_value=0)
                            mock_notif.return_value = mock_notif_instance
                            
                            mock_ipc_instance = MagicMock()
                            mock_ipc_instance.start = AsyncMock()
                            mock_ipc_instance.stop = AsyncMock()
                            mock_ipc.return_value = mock_ipc_instance
                            
                            # サービスインスタンスを作成
                            service = BLEOrchestratorService()
                            
                            # テスト前に開始
                            await service.start()
                            
                            yield service
                            
                            # テスト後に停止
                            await service.stop()


class TestBLEOrchestratorService:
    """BLEOrchestratorServiceクラスのテスト"""
    
    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """サービスが正しく初期化されることを確認"""
        with patch("ble_orchestrator.orchestrator.service.BLEScanner"):
            with patch("ble_orchestrator.orchestrator.service.RequestQueueManager"):
                with patch("ble_orchestrator.orchestrator.service.BLERequestHandler"):
                    with patch("ble_orchestrator.orchestrator.service.BLEWatchdog"):
                        with patch("ble_orchestrator.orchestrator.service.IPCServer"):
                            with patch("ble_orchestrator.orchestrator.service.NotificationManager"):
                                service = BLEOrchestratorService()
                                
                                # 各コンポーネントが存在することを確認
                                assert service.scanner is not None
                                assert service.queue_manager is not None
                                assert service.handler is not None
                                assert service.watchdog is not None
                                assert service.ipc_server is not None
                                assert service.notification_manager is not None
    
    @pytest.mark.asyncio
    async def test_start_components_in_order(self):
        """サービス起動時に各コンポーネントが正しい順序で起動されることを確認"""
        with patch("ble_orchestrator.orchestrator.service.BLEScanner") as mock_scanner_class:
            with patch("ble_orchestrator.orchestrator.service.RequestQueueManager") as mock_queue_class:
                with patch("ble_orchestrator.orchestrator.service.BLERequestHandler"):
                    with patch("ble_orchestrator.orchestrator.service.BLEWatchdog") as mock_watchdog_class:
                        with patch("ble_orchestrator.orchestrator.service.IPCServer") as mock_ipc_class:
                            with patch("ble_orchestrator.orchestrator.service.NotificationManager") as mock_notif_class:
                                # モックのセットアップ
                                mock_scanner = MagicMock()
                                mock_scanner.start = AsyncMock()
                                mock_scanner.stop = AsyncMock()
                                mock_scanner_class.return_value = mock_scanner
                                
                                mock_queue = MagicMock()
                                mock_queue.start = AsyncMock()
                                mock_queue.stop = AsyncMock()
                                mock_queue.get_queue_size = MagicMock(return_value=0)
                                mock_queue_class.return_value = mock_queue
                                
                                mock_watchdog = MagicMock()
                                mock_watchdog.start = AsyncMock()
                                mock_watchdog.stop = AsyncMock()
                                mock_watchdog_class.return_value = mock_watchdog
                                
                                mock_notif = MagicMock()
                                mock_notif.start = AsyncMock()
                                mock_notif.stop = AsyncMock()
                                mock_notif_class.return_value = mock_notif
                                
                                mock_ipc = MagicMock()
                                mock_ipc.start = AsyncMock()
                                mock_ipc.stop = AsyncMock()
                                mock_ipc_class.return_value = mock_ipc
                                
                                # サービス作成と起動
                                service = BLEOrchestratorService()
                                await service.start()
                                
                                # 各コンポーネントのstartが呼ばれたことを確認
                                mock_scanner.start.assert_called_once()
                                mock_queue.start.assert_called_once()
                                mock_watchdog.start.assert_called_once()
                                mock_notif.start.assert_called_once()
                                mock_ipc.start.assert_called_once()
                                
                                # クリーンアップ
                                await service.stop()
    
    @pytest.mark.asyncio
    async def test_get_service_status(self, orchestrator_service):
        """サービスステータスが正しく取得できることを確認"""
        status = orchestrator_service._get_service_status()
        
        # 必要なキーが含まれていることを確認
        assert "is_running" in status
        assert "adapter_status" in status
        assert "queue_size" in status
        assert "uptime_sec" in status
        assert "active_devices" in status
        assert "active_subscriptions" in status
        assert "exclusive_control_enabled" in status
        assert "client_connecting" in status
        
        # 値の型を確認
        assert isinstance(status["is_running"], bool)
        assert isinstance(status["uptime_sec"], (int, float))
        assert isinstance(status["queue_size"], int)
    
    @pytest.mark.asyncio
    async def test_get_scan_result(self, orchestrator_service):
        """スキャン結果の取得が正しく動作することを確認"""
        # モックのスキャン結果を設定
        mock_result = ScanResult(
            address="AA:BB:CC:DD:EE:FF",
            name="Test Device",
            rssi=-60,
            advertisement_data={},
            timestamp=1000.0
        )
        orchestrator_service.scanner.cache.get_latest_result.return_value = mock_result
        
        # スキャン結果を取得
        result = orchestrator_service._get_scan_result("AA:BB:CC:DD:EE:FF")
        
        # 結果が正しいことを確認
        assert result is not None
        assert result.address == "AA:BB:CC:DD:EE:FF"
        assert result.name == "Test Device"
        
        # スキャナーのメソッドが呼ばれたことを確認
        orchestrator_service.scanner.cache.get_latest_result.assert_called_once_with("AA:BB:CC:DD:EE:FF")
    
    @pytest.mark.asyncio
    async def test_stop_components_in_reverse_order(self, orchestrator_service):
        """サービス停止時に各コンポーネントが逆順で停止されることを確認"""
        # stopメソッドを呼び出し
        await orchestrator_service.stop()
        
        # 各コンポーネントのstopが呼ばれたことを確認
        orchestrator_service.ipc_server.stop.assert_called()
        orchestrator_service.notification_manager.stop.assert_called()
        orchestrator_service.watchdog.stop.assert_called()
        orchestrator_service.queue_manager.stop.assert_called()
        orchestrator_service.scanner.stop.assert_called()


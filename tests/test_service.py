import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from ble_orchestrator.orchestrator.service import BLEOrchestratorService
from ble_orchestrator.orchestrator.types import ScanResult


@pytest.fixture
async def orchestrator_service():
    """テスト用のBLEオーケストレーターサービスインスタンス"""
    # 各コンポーネントをモック化
    with patch("ble_orchestrator.orchestrator.service.BLEScanner") as mock_scanner:
        with patch("ble_orchestrator.orchestrator.service.RequestQueueManager") as mock_queue_manager:
            with patch("ble_orchestrator.orchestrator.service.BLERequestHandler") as mock_handler:
                with patch("ble_orchestrator.orchestrator.service.BLEWatchdog") as mock_watchdog:
                    with patch("ble_orchestrator.orchestrator.service.IPCServer") as mock_ipc_server:
                        # モックインスタンスを設定
                        mock_scanner_instance = MagicMock()
                        mock_scanner_instance.get_latest_result = MagicMock()
                        mock_scanner_instance.get_all_devices = MagicMock(return_value=[
                            ScanResult(
                                address="AA:BB:CC:DD:EE:FF",
                                name="TestDevice",
                                rssi=-60,
                                advertisement_data={},
                                timestamp=1000.0
                            )
                        ])
                        mock_scanner.return_value = mock_scanner_instance
                        
                        mock_queue_manager_instance = MagicMock()
                        mock_queue_manager_instance.enqueue_request = AsyncMock()
                        mock_queue_manager_instance.get_request_status = MagicMock()
                        mock_queue_manager_instance.get_queue_size = MagicMock(return_value=0)
                        mock_queue_manager.return_value = mock_queue_manager_instance
                        
                        mock_handler_instance = MagicMock()
                        mock_handler_instance.get_consecutive_failures = MagicMock(return_value=0)
                        mock_handler_instance.reset_consecutive_failures = MagicMock()
                        mock_handler.return_value = mock_handler_instance
                        
                        mock_watchdog_instance = MagicMock()
                        mock_watchdog.return_value = mock_watchdog_instance
                        
                        mock_ipc_server_instance = MagicMock()
                        mock_ipc_server_instance.start = AsyncMock()
                        mock_ipc_server_instance.stop = AsyncMock()
                        mock_ipc_server.return_value = mock_ipc_server_instance
                        
                        # サービスインスタンスを作成
                        service = BLEOrchestratorService()
                        
                        # テストの前に開始する
                        await service.start()
                        
                        yield service
                        
                        # テストの後に停止する
                        await service.stop()


class TestBLEOrchestratorService:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        """サービスの起動と停止のテスト"""
        # 各コンポーネントをモック化
        with patch("ble_orchestrator.orchestrator.service.BLEScanner") as mock_scanner:
            with patch("ble_orchestrator.orchestrator.service.RequestQueueManager") as mock_queue_manager:
                with patch("ble_orchestrator.orchestrator.service.BLERequestHandler") as mock_handler:
                    with patch("ble_orchestrator.orchestrator.service.BLEWatchdog") as mock_watchdog:
                        with patch("ble_orchestrator.orchestrator.service.IPCServer") as mock_ipc_server:
                            # モックのセットアップ
                            mock_scanner_instance = MagicMock()
                            mock_scanner_instance.start = AsyncMock()
                            mock_scanner_instance.stop = AsyncMock()
                            mock_scanner.return_value = mock_scanner_instance
                            
                            mock_queue_manager_instance = MagicMock()
                            mock_queue_manager_instance.start = AsyncMock()
                            mock_queue_manager_instance.stop = AsyncMock()
                            mock_queue_manager.return_value = mock_queue_manager_instance
                            
                            mock_watchdog_instance = MagicMock()
                            mock_watchdog_instance.start = AsyncMock()
                            mock_watchdog_instance.stop = AsyncMock()
                            mock_watchdog.return_value = mock_watchdog_instance
                            
                            mock_ipc_server_instance = MagicMock()
                            mock_ipc_server_instance.start = AsyncMock()
                            mock_ipc_server_instance.stop = AsyncMock()
                            mock_ipc_server.return_value = mock_ipc_server_instance
                            
                            # サービスインスタンスを作成
                            service = BLEOrchestratorService()
                            
                            # 初期状態の確認
                            assert service._is_running is False
                            
                            # サービスを起動
                            await service.start()
                            
                            # 各コンポーネントのstart()が呼ばれたか確認
                            mock_scanner_instance.start.assert_called_once()
                            mock_queue_manager_instance.start.assert_called_once()
                            mock_watchdog_instance.start.assert_called_once()
                            mock_ipc_server_instance.start.assert_called_once()
                            
                            # 状態が更新されたか確認
                            assert service._is_running is True
                            
                            # サービスを停止
                            await service.stop()
                            
                            # 各コンポーネントのstop()が呼ばれたか確認（逆順）
                            mock_ipc_server_instance.stop.assert_called_once()
                            mock_watchdog_instance.stop.assert_called_once()
                            mock_queue_manager_instance.stop.assert_called_once()
                            mock_scanner_instance.stop.assert_called_once()
                            
                            # 状態が更新されたか確認
                            assert service._is_running is False

    @pytest.mark.asyncio
    async def test_handle_scan_func(self, orchestrator_service):
        """スキャン結果ハンドリング関数のテスト"""
        # 存在するデバイスのスキャン結果を取得
        result = orchestrator_service._handle_scan_func("AA:BB:CC:DD:EE:FF")
        
        # スキャナーのget_latest_resultが呼ばれたことを確認
        orchestrator_service._scanner.get_latest_result.assert_called_once_with("AA:BB:CC:DD:EE:FF")
        
        # 存在しないデバイスのスキャン結果を取得
        orchestrator_service._scanner.get_latest_result.reset_mock()
        orchestrator_service._scanner.get_latest_result.return_value = None
        
        result = orchestrator_service._handle_scan_func("11:22:33:44:55:66")
        
        # スキャナーのget_latest_resultが呼ばれたことを確認
        orchestrator_service._scanner.get_latest_result.assert_called_once_with("11:22:33:44:55:66")
        
        # 結果がNoneであることを確認
        assert result is None

    @pytest.mark.asyncio
    async def test_enqueue_request_func(self, orchestrator_service):
        """リクエストエンキュー関数のテスト"""
        # モックリクエスト
        mock_request = MagicMock()
        mock_request.mac_address = "AA:BB:CC:DD:EE:FF"
        
        # リクエストIDを設定
        orchestrator_service._queue_manager.enqueue_request.return_value = "test-request-id"
        
        # リクエストをエンキュー
        request_id = await orchestrator_service._enqueue_request_func(mock_request)
        
        # キューマネージャーのenqueue_requestが呼ばれたことを確認
        orchestrator_service._queue_manager.enqueue_request.assert_called_once_with(mock_request)
        
        # 正しいリクエストIDが返されることを確認
        assert request_id == "test-request-id"

    @pytest.mark.asyncio
    async def test_get_status_func(self, orchestrator_service):
        """ステータス取得関数のテスト"""
        # 起動時間を調整
        orchestrator_service._start_time = orchestrator_service._start_time - 60.0
        
        # ステータスを取得
        status = orchestrator_service._get_status_func()
        
        # 戻り値の構造を確認
        assert "is_running" in status
        assert status["is_running"] is True
        
        assert "adapter_status" in status
        assert status["adapter_status"] == "ok"
        
        assert "queue_size" in status
        assert status["queue_size"] == 0
        
        assert "last_error" in status
        
        assert "uptime_sec" in status
        assert status["uptime_sec"] >= 60.0
        
        assert "active_devices" in status
        assert status["active_devices"] == 1
        
        # 必要なメソッドが呼ばれたことを確認
        orchestrator_service._handler.get_consecutive_failures.assert_called_once()
        orchestrator_service._queue_manager.get_queue_size.assert_called_once()
        orchestrator_service._scanner.get_all_devices.assert_called_once()

    @pytest.mark.asyncio
    async def test_double_start(self, orchestrator_service):
        """二重起動のテスト"""
        # すでに起動状態なので、start()は内部コンポーネントを再起動しないはず
        with patch.object(orchestrator_service._scanner, "start") as mock_scanner_start:
            with patch.object(orchestrator_service._queue_manager, "start") as mock_queue_manager_start:
                with patch.object(orchestrator_service._watchdog, "start") as mock_watchdog_start:
                    with patch.object(orchestrator_service._ipc_server, "start") as mock_ipc_server_start:
                        # 二回目の起動を試行
                        await orchestrator_service.start()
                        
                        # 内部コンポーネントのstart()が呼ばれていないことを確認
                        mock_scanner_start.assert_not_called()
                        mock_queue_manager_start.assert_not_called()
                        mock_watchdog_start.assert_not_called()
                        mock_ipc_server_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_double_stop(self, orchestrator_service):
        """二重停止のテスト"""
        # 一度停止させる
        await orchestrator_service.stop()
        
        # すでに停止状態なので、stop()は内部コンポーネントを再停止しないはず
        with patch.object(orchestrator_service._scanner, "stop") as mock_scanner_stop:
            with patch.object(orchestrator_service._queue_manager, "stop") as mock_queue_manager_stop:
                with patch.object(orchestrator_service._watchdog, "stop") as mock_watchdog_stop:
                    with patch.object(orchestrator_service._ipc_server, "stop") as mock_ipc_server_stop:
                        # 二回目の停止を試行
                        await orchestrator_service.stop()
                        
                        # 内部コンポーネントのstop()が呼ばれていないことを確認
                        mock_scanner_stop.assert_not_called()
                        mock_queue_manager_stop.assert_not_called()
                        mock_watchdog_stop.assert_not_called()
                        mock_ipc_server_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_error_adapter_reset(self, orchestrator_service):
        """アダプターリセット後のエラーハンドリングのテスト"""
        # リセット関数をモック化
        with patch.object(orchestrator_service, "_reset_after_adapter_restart") as mock_reset:
            # エラーハンドリング関数を呼び出す
            await orchestrator_service._handle_error("Bluetooth adapter has been reset")
            
            # リセット関数が呼ばれたことを確認
            mock_reset.assert_called_once()
            
            # エラーメッセージが設定されたことを確認
            assert orchestrator_service._last_error == "Bluetooth adapter has been reset"

    @pytest.mark.asyncio
    async def test_handle_error_general(self, orchestrator_service):
        """一般的なエラーハンドリングのテスト"""
        # リセット関数をモック化
        with patch.object(orchestrator_service, "_reset_after_adapter_restart") as mock_reset:
            # エラーハンドリング関数を呼び出す
            await orchestrator_service._handle_error("General error")
            
            # リセット関数が呼ばれないことを確認（アダプターリセットエラーではないため）
            mock_reset.assert_not_called()
            
            # エラーメッセージが設定されたことを確認
            assert orchestrator_service._last_error == "General error"

    @pytest.mark.asyncio
    async def test_reset_after_adapter_restart(self, orchestrator_service):
        """アダプターリスタート後のリセット処理のテスト"""
        # リセット処理
        await orchestrator_service._reset_after_adapter_restart()
        
        # 各コンポーネントの必要なメソッドが呼ばれたことを確認
        orchestrator_service._handler.reset_consecutive_failures.assert_called_once()
        orchestrator_service._scanner.stop.assert_called_once()
        orchestrator_service._scanner.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_execution(self):
        """メイン実行フローのテスト"""
        # サービスクラスをモック化
        with patch("ble_orchestrator.orchestrator.service.BLEOrchestratorService") as mock_service_class:
            # シグナルハンドラーをモック化
            with patch("asyncio.get_event_loop") as mock_get_loop:
                # モックインスタンスを設定
                mock_service_instance = MagicMock()
                mock_service_instance.start = AsyncMock()
                mock_service_instance.stop = AsyncMock()
                
                mock_service_class.return_value = mock_service_instance
                
                mock_loop = MagicMock()
                mock_get_loop.return_value = mock_loop
                
                # 再度モジュールをインポートして実行関数を取得
                from ble_orchestrator.orchestrator.service import main as service_main
                
                # KeyboardInterrupt例外を発生させる
                mock_loop.run_until_complete.side_effect = KeyboardInterrupt()
                
                # メイン関数を実行
                service_main()
                
                # サービスのstart()とstop()が呼ばれたことを確認
                mock_service_instance.start.assert_called_once()
                mock_service_instance.stop.assert_called_once() 
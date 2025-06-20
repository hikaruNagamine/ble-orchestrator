"""
watchdog.pyのユニットテスト
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call

from ble_orchestrator.orchestrator.watchdog import BLEWatchdog


@pytest.fixture
def mock_get_failures():
    """失敗回数取得関数のモック"""
    return MagicMock(return_value=0)


@pytest.fixture
def mock_reset_failures():
    """失敗カウンタリセット関数のモック"""
    return MagicMock()


@pytest.fixture
def watchdog(mock_get_failures, mock_reset_failures):
    """テスト用のウォッチドッグインスタンス"""
    return BLEWatchdog(
        get_failures_func=mock_get_failures,
        reset_failures_func=mock_reset_failures,
        adapters=["hci0", "hci1"]
    )


class TestBLEWatchdog:
    """BLEWatchdogクラスのテスト"""

    @pytest.mark.asyncio
    async def test_start_stop(self, watchdog):
        """起動と停止の基本テスト"""
        # 起動
        await watchdog.start()
        assert watchdog._task is not None
        
        # 二重起動（警告ログが出るだけで問題なし）
        await watchdog.start()
        
        # 停止
        await watchdog.stop()
        assert watchdog._task is None
        
        # 二重停止（問題なし）
        await watchdog.stop()

    @pytest.mark.asyncio
    async def test_failure_detection_no_failures(self, watchdog, mock_get_failures):
        """失敗がない場合のテスト"""
        # 失敗回数を0に設定
        mock_get_failures.return_value = 0
        
        # ウォッチドッグ起動
        await watchdog.start()
        
        # 少し待機してチェックが実行されるようにする
        await asyncio.sleep(0.2)
        
        # 失敗回数取得が呼ばれたことを確認
        assert mock_get_failures.called
        
        # 停止
        await watchdog.stop()

    @pytest.mark.asyncio
    async def test_failure_detection_below_threshold(self, watchdog, mock_get_failures):
        """しきい値以下の失敗の場合のテスト"""
        # しきい値未満の失敗回数を設定
        with patch('ble_orchestrator.orchestrator.watchdog.CONSECUTIVE_FAILURES_THRESHOLD', 3):
            mock_get_failures.return_value = 2  # しきい値は3
            
            # ウォッチドッグ起動
            await watchdog.start()
            
            # 少し待機してチェックが実行されるようにする
            await asyncio.sleep(0.2)
            
            # 失敗回数取得が呼ばれたことを確認
            assert mock_get_failures.called
            
            # リカバリプロセスが開始されないことを確認
            assert not watchdog._recovery_in_progress
            
            # 停止
            await watchdog.stop()

    @pytest.mark.asyncio
    async def test_failure_detection_at_threshold(self, watchdog, mock_get_failures, mock_reset_failures):
        """しきい値ちょうどの失敗の場合のテスト"""
        # しきい値と同じ失敗回数を設定
        with patch('ble_orchestrator.orchestrator.watchdog.CONSECUTIVE_FAILURES_THRESHOLD', 3):
            mock_get_failures.return_value = 3  # しきい値は3
            
            # _recover_ble_adapterをモック
            with patch.object(watchdog, '_recover_ble_adapter', new_callable=AsyncMock) as mock_recover:
                # ウォッチドッグ起動
                await watchdog.start()
                
                # 少し待機してチェックが実行されるようにする
                await asyncio.sleep(0.2)
                
                # 失敗回数取得が呼ばれたことを確認
                assert mock_get_failures.called
                
                # リカバリプロセスが開始されたことを確認
                mock_recover.assert_called_once()
                
                # 停止
                await watchdog.stop()

    @pytest.mark.asyncio
    async def test_failure_detection_above_threshold(self, watchdog, mock_get_failures, mock_reset_failures):
        """しきい値を超える失敗の場合のテスト"""
        # しきい値を超える失敗回数を設定
        with patch('ble_orchestrator.orchestrator.watchdog.CONSECUTIVE_FAILURES_THRESHOLD', 3):
            mock_get_failures.return_value = 4  # しきい値は3
            
            # _recover_ble_adapterをモック
            with patch.object(watchdog, '_recover_ble_adapter', new_callable=AsyncMock) as mock_recover:
                # ウォッチドッグ起動
                await watchdog.start()
                
                # 少し待機してチェックが実行されるようにする
                await asyncio.sleep(0.2)
                
                # 失敗回数取得が呼ばれたことを確認
                assert mock_get_failures.called
                
                # リカバリプロセスが開始されたことを確認
                mock_recover.assert_called_once()
                
                # 停止
                await watchdog.stop()

    @pytest.mark.asyncio
    async def test_recover_ble_adapter_success(self, watchdog, mock_reset_failures):
        """BLEアダプタの復旧が成功するケース"""
        # _run_shell_commandのモック（成功）
        with patch.object(watchdog, '_run_shell_command', new_callable=AsyncMock) as mock_run_cmd:
            mock_run_cmd.return_value = True  # コマンドは成功
            
            # 復旧処理を実行
            await watchdog._recover_ble_adapter()
            
            # シェルコマンドが実行されたことを確認
            assert mock_run_cmd.called
            
            # 失敗カウンタがリセットされたことを確認
            mock_reset_failures.assert_called_once()
            
            # 復旧プロセスが終了していることを確認
            assert not watchdog._recovery_in_progress

    @pytest.mark.asyncio
    async def test_recover_ble_adapter_failure_retry(self, watchdog, mock_reset_failures):
        """BLEアダプタの復旧が失敗し、Bluetoothサービス再起動を試みるケース"""
        # _run_shell_commandのモック（最初は失敗、次は成功）
        with patch.object(watchdog, '_run_shell_command', new_callable=AsyncMock) as mock_run_cmd:
            # 1回目は失敗、2回目は成功
            mock_run_cmd.side_effect = [False, True]
            
            # asyncio.sleepをモック
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                # 復旧処理を実行
                await watchdog._recover_ble_adapter()
                
                # シェルコマンドが2回呼ばれたことを確認
                assert mock_run_cmd.call_count == 2
                
                # 失敗カウンタがリセットされたことを確認
                mock_reset_failures.assert_called_once()
                
                # 復旧後に待機したことを確認
                mock_sleep.assert_called_once()
                
                # 復旧プロセスが終了していることを確認
                assert not watchdog._recovery_in_progress

    @pytest.mark.asyncio
    async def test_recover_ble_adapter_complete_failure(self, watchdog, mock_reset_failures):
        """BLEアダプタの復旧が完全に失敗するケース"""
        # _run_shell_commandのモック（すべて失敗）
        with patch.object(watchdog, '_run_shell_command', new_callable=AsyncMock) as mock_run_cmd:
            mock_run_cmd.return_value = False  # コマンドはすべて失敗
            
            # 復旧処理を実行
            await watchdog._recover_ble_adapter()
            
            # シェルコマンドが2回呼ばれたことを確認
            assert mock_run_cmd.call_count == 2
            
            # 失敗カウンタがリセットされていないことを確認
            assert not mock_reset_failures.called
            
            # 復旧プロセスが終了していることを確認
            assert not watchdog._recovery_in_progress

    @pytest.mark.asyncio
    async def test_recover_ble_adapter_error(self, watchdog, mock_reset_failures):
        """復旧処理中に例外が発生するケース"""
        # _run_shell_commandのモック（例外発生）
        with patch.object(watchdog, '_run_shell_command', new_callable=AsyncMock) as mock_run_cmd:
            mock_run_cmd.side_effect = Exception("Command execution failed")
            
            # 復旧処理を実行（例外がキャッチされ、終了すること）
            await watchdog._recover_ble_adapter()
            
            # シェルコマンドの呼び出しが試行されたことを確認
            assert mock_run_cmd.called
            
            # 復旧プロセスが終了していることを確認
            assert not watchdog._recovery_in_progress

    @pytest.mark.asyncio
    async def test_run_shell_command_success(self, watchdog):
        """シェルコマンド実行成功のテスト"""
        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_subprocess:
            # プロセスのモック設定
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"success output", b""))
            mock_subprocess.return_value = mock_process
            
            # コマンド実行
            result = await watchdog._run_shell_command("test command")
            
            # 成功したことを確認
            assert result is True
            # サブプロセスが作成されたことを確認
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_shell_command_failure(self, watchdog):
        """シェルコマンド実行失敗のテスト"""
        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_subprocess:
            # プロセスのモック設定
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(b"", b"error output"))
            mock_subprocess.return_value = mock_process
            
            # コマンド実行
            result = await watchdog._run_shell_command("test command")
            
            # 失敗したことを確認
            assert result is False
            # サブプロセスが作成されたことを確認
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_shell_command_exception(self, watchdog):
        """シェルコマンド実行中の例外発生テスト"""
        with patch('asyncio.create_subprocess_shell', side_effect=Exception("Subprocess error")) as mock_subprocess:
            # コマンド実行
            result = await watchdog._run_shell_command("test command")
            
            # 失敗したことを確認
            assert result is False
            # サブプロセスの作成が試行されたことを確認
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_watchdog_loop_cancellation(self, watchdog):
        """ウォッチドッグループのキャンセル処理テスト"""
        with patch.object(watchdog, '_get_failures_func') as mock_get_failures:
            # ウォッチドッグ起動
            await watchdog.start()
            
            # 強制的にタスクをキャンセル
            watchdog._task.cancel()
            
            # タスクが完了するのを待つ
            try:
                await asyncio.wait_for(watchdog._task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            
            # タスクが完了したことを確認
            assert watchdog._task.done()

    @pytest.mark.asyncio
    async def test_watchdog_loop_exception(self, watchdog, mock_get_failures):
        """ウォッチドッグループのエラー処理テスト"""
        # 失敗回数取得関数でエラーを発生させる
        mock_get_failures.side_effect = Exception("Test error in get_failures")
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # ウォッチドッグ起動
            await watchdog.start()
            
            # 少し待機してチェックが実行されるようにする
            await asyncio.sleep(0.2)
            
            # sleep が呼ばれたことを確認 (エラー後にスリープ)
            mock_sleep.assert_called()
            
            # 停止
            await watchdog.stop() 
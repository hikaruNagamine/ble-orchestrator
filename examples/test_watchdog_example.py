#!/usr/bin/env python3
"""
BLEWatchdogのテスト例

このスクリプトはBLEWatchdogクラスの単体テスト方法を示します。
pytest-asyncioを使用して非同期テストを実行しています。
"""

import asyncio
import unittest
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# ble_orchestratorパッケージをインポート
import sys
sys.path.append('..')
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
        adapter_name="hci0"
    )


@pytest.mark.asyncio
async def test_watchdog_basic_functionality(watchdog, mock_get_failures, mock_reset_failures):
    """ウォッチドッグの基本機能テスト"""
    # 起動
    await watchdog.start()
    assert watchdog._task is not None
    
    # 連続失敗回数のテスト
    # ウォッチドッグ動作中に失敗カウンタを変更
    with patch('ble_orchestrator.orchestrator.watchdog.CONSECUTIVE_FAILURES_THRESHOLD', 3):
        # しきい値より小さい場合
        mock_get_failures.return_value = 2
        await asyncio.sleep(0.1)  # ウォッチドッグループが実行される時間を確保
        
        # リカバリが開始されないことを確認
        assert not watchdog._recovery_in_progress
        
        # しきい値以上の場合
        mock_get_failures.return_value = 3
        
        # _recover_ble_adapterをモック
        with patch.object(watchdog, '_recover_ble_adapter', new_callable=AsyncMock) as mock_recover:
            await asyncio.sleep(0.1)  # ウォッチドッグループが実行される時間を確保
            
            # リカバリプロセスが開始されることを確認
            mock_recover.assert_called_once()
    
    # 停止
    await watchdog.stop()
    assert watchdog._task is None


@pytest.mark.asyncio
async def test_watchdog_recovery_process(watchdog, mock_reset_failures):
    """ウォッチドッグの復旧プロセステスト"""
    # _run_shell_commandをモック
    with patch.object(watchdog, '_run_shell_command', new_callable=AsyncMock) as mock_run_cmd:
        # 成功ケース
        mock_run_cmd.return_value = True
        
        # 復旧プロセスを実行
        await watchdog._recover_ble_adapter()
        
        # シェルコマンドが実行され、失敗カウンタがリセットされることを確認
        mock_run_cmd.assert_called_once()
        mock_reset_failures.assert_called_once()
        
        # 復旧フラグがリセットされることを確認
        assert not watchdog._recovery_in_progress
        
        # 失敗→成功のケース
        mock_run_cmd.reset_mock()
        mock_reset_failures.reset_mock()
        mock_run_cmd.side_effect = [False, True]
        
        # 復旧プロセスを実行
        await watchdog._recover_ble_adapter()
        
        # シェルコマンドが2回実行され、失敗カウンタがリセットされることを確認
        assert mock_run_cmd.call_count == 2
        mock_reset_failures.assert_called_once()


if __name__ == "__main__":
    # コマンドラインから実行する場合
    pytest.main(["-v", __file__]) 
"""
scanner.pyのユニットテスト
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from ble_orchestrator.orchestrator.scanner import ScanCache, BLEScanner


class TestScanCache:
    """ScanCacheクラスのテスト"""

    @pytest.mark.asyncio
    async def test_add_result(self, mock_ble_device, mock_advertisement_data):
        """add_resultメソッドが正しく動作することを確認"""
        cache = ScanCache(ttl_seconds=10.0)
        await cache.add_result(mock_ble_device, mock_advertisement_data)
        
        # キャッシュに追加されたことを確認
        result = cache.get_latest_result(mock_ble_device.address)
        assert result is not None
        assert result.address == mock_ble_device.address
        assert result.name == mock_ble_device.name
        assert result.rssi == mock_advertisement_data.rssi

    def test_get_latest_result_existing(self, sample_scan_result):
        """存在するアドレスのget_latest_resultが正しく動作することを確認"""
        cache = ScanCache(ttl_seconds=10.0)
        
        # キャッシュに直接追加
        address = sample_scan_result.address
        cache._cache[address].append(sample_scan_result)
        
        # 取得できることを確認
        result = cache.get_latest_result(address)
        assert result is not None
        assert result.address == address
        assert result.name == sample_scan_result.name
        assert result.rssi == sample_scan_result.rssi

    def test_get_latest_result_nonexistent(self):
        """存在しないアドレスのget_latest_resultがNoneを返すことを確認"""
        cache = ScanCache(ttl_seconds=10.0)
        result = cache.get_latest_result("11:22:33:44:55:66")
        assert result is None

    def test_get_latest_result_expired(self, sample_scan_result):
        """期限切れのget_latest_resultがNoneを返すことを確認"""
        cache = ScanCache(ttl_seconds=5.0)
        
        # 過去のタイムスタンプを設定
        expired_result = sample_scan_result
        expired_result.timestamp = time.time() - 10.0  # 10秒前
        
        # キャッシュに直接追加
        address = expired_result.address
        cache._cache[address].append(expired_result)
        
        # 期限切れでNoneが返ることを確認
        result = cache.get_latest_result(address)
        assert result is None

    def test_get_all_devices(self, sample_scan_result):
        """get_all_devicesが正しく動作することを確認"""
        cache = ScanCache(ttl_seconds=10.0)
        
        # 現在のタイムスタンプを設定
        current_result = sample_scan_result
        current_result.timestamp = time.time()
        
        # 過去のタイムスタンプを設定した別のデバイス
        expired_result = sample_scan_result
        expired_result.address = "11:22:33:44:55:66"
        expired_result.timestamp = time.time() - 20.0  # 20秒前
        
        # キャッシュに直接追加
        cache._cache[current_result.address].append(current_result)
        cache._cache[expired_result.address].append(expired_result)
        
        # アクティブなデバイスのみ取得できることを確認
        devices = cache.get_all_devices()
        assert len(devices) == 1
        assert current_result.address in devices
        assert expired_result.address not in devices


class TestBLEScanner:
    """BLEScannerクラスのテスト"""

    @pytest.mark.asyncio
    async def test_detection_callback(self, mock_ble_device, mock_advertisement_data):
        """_detection_callbackが正しく動作することを確認"""
        scanner = BLEScanner()
        await scanner._detection_callback(mock_ble_device, mock_advertisement_data)
        
        # キャッシュに追加されたことを確認
        result = scanner.cache.get_latest_result(mock_ble_device.address)
        assert result is not None
        assert result.address == mock_ble_device.address
        assert result.name == mock_ble_device.name
        assert result.rssi == mock_advertisement_data.rssi

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """start/stopメソッドが正しく動作することを確認"""
        with patch('ble_orchestrator.orchestrator.scanner.BleakScanner') as mock_bleak_scanner:
            # BleakScannerのモック
            mock_instance = mock_bleak_scanner.return_value
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            
            # スキャナーインスタンス作成
            scanner = BLEScanner()
            assert not scanner.is_running
            
            # 開始
            await scanner.start()
            assert scanner.is_running
            mock_instance.start.assert_called_once()
            
            # 停止
            await scanner.stop()
            assert not scanner.is_running
            mock_instance.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_loop(self):
        """_scan_loopが正しく動作することを確認"""
        scanner = BLEScanner()
        
        # 現在のキャッシュを保存
        original_cache = scanner.cache
        
        # キャッシュをモック化
        mock_cache = MagicMock()
        mock_cache.get_all_devices.return_value = ["AA:BB:CC:DD:EE:FF"]
        scanner.cache = mock_cache
        
        # スキャンループを短時間実行
        scanner._stop_event.clear()
        task = asyncio.create_task(scanner._scan_loop())
        
        # 少し待ってから停止
        await asyncio.sleep(0.1)
        scanner._stop_event.set()
        await task
        
        # キャッシュのget_all_devicesが呼ばれたことを確認
        mock_cache.get_all_devices.assert_called()
        
        # 元のキャッシュに戻す
        scanner.cache = original_cache 
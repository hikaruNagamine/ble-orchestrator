"""
handler.pyのユニットテスト
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from ble_orchestrator.orchestrator.types import ReadRequest, ScanRequest, WriteRequest, RequestStatus
from ble_orchestrator.orchestrator.handler import BLERequestHandler


@pytest.fixture
def mock_get_device_func():
    """デバイス取得関数のモック"""
    mock_func = MagicMock()
    
    # 存在するデバイスの場合
    mock_device = MagicMock()
    mock_device.address = "AA:BB:CC:DD:EE:FF"
    mock_device.name = "Test Device"
    
    # 関数が呼ばれたときの挙動を設定
    mock_func.return_value = mock_device
    
    return mock_func


@pytest.fixture
def handler(mock_get_device_func):
    """BLERequestHandlerのインスタンス"""
    return BLERequestHandler(mock_get_device_func)


@pytest.fixture
def scan_request():
    """ScanRequest のインスタンス"""
    return ScanRequest(
        request_id="scan-1234",
        mac_address="AA:BB:CC:DD:EE:FF"
    )


@pytest.fixture
def read_request():
    """ReadRequest のインスタンス"""
    return ReadRequest(
        request_id="read-1234",
        mac_address="AA:BB:CC:DD:EE:FF",
        service_uuid="0000180f-0000-1000-8000-00805f9b34fb",
        characteristic_uuid="00002a19-0000-1000-8000-00805f9b34fb"
    )


@pytest.fixture
def write_request():
    """WriteRequest のインスタンス"""
    return WriteRequest(
        request_id="write-1234",
        mac_address="AA:BB:CC:DD:EE:FF",
        service_uuid="0000180f-0000-1000-8000-00805f9b34fb",
        characteristic_uuid="00002a19-0000-1000-8000-00805f9b34fb",
        data=b'\x01\x00',
        response_required=False
    )


class TestBLERequestHandler:
    """BLERequestHandlerクラスのテスト"""

    @pytest.mark.asyncio
    async def test_handle_scan_request(self, handler, scan_request):
        """スキャンリクエストが正しく処理されることを確認"""
        # スキャンリクエストの処理
        await handler.handle_request(scan_request)
        
        # スキャンリクエストはキャッシュから取得するだけなので特に検証なし
        # 例外が発生しなければOK
        assert handler._consecutive_failures == 0
        assert scan_request.status == RequestStatus.PENDING  # 変更されない

    @pytest.mark.asyncio
    async def test_handle_unknown_request_type(self, handler):
        """未知のリクエストタイプが正しくエラー処理されることを確認"""
        # 未知のリクエストタイプ
        unknown_request = MagicMock()
        unknown_request.request_id = "unknown-1234"
        unknown_request.mac_address = "AA:BB:CC:DD:EE:FF"
        
        # エラーが発生することを確認
        with pytest.raises(ValueError):
            await handler.handle_request(unknown_request)
            
        # 連続失敗回数が増えることを確認
        assert handler._consecutive_failures == 1
        assert unknown_request.status == RequestStatus.FAILED

    @pytest.mark.asyncio
    async def test_handle_device_not_found(self, handler, read_request):
        """存在しないデバイスへのリクエストが正しくエラー処理されることを確認"""
        # デバイスが見つからない場合
        handler._get_device_func.return_value = None
        
        # エラーが発生することを確認
        with pytest.raises(ValueError):
            await handler.handle_request(read_request)
            
        # 連続失敗回数が増えることを確認
        assert handler._consecutive_failures == 1
        assert read_request.status == RequestStatus.FAILED
        assert "not found" in read_request.error_message.lower()

    @pytest.mark.asyncio
    async def test_handle_read_request_success(self, handler, read_request):
        """読み取りリクエストが正しく処理されることを確認"""
        # BleakClientのモック
        with patch('ble_orchestrator.orchestrator.handler.BleakClient') as MockClient:
            # クライアントのインスタンスをモック
            mock_client = AsyncMock()
            
            # read_gatt_charメソッドの戻り値を設定
            mock_client.read_gatt_char.return_value = b'\x42'
            
            # コンテキストマネージャーが返すインスタンスを設定
            MockClient.return_value.__aenter__.return_value = mock_client
            
            # 読み取りリクエストの処理
            await handler.handle_request(read_request)
            
            # read_gatt_charが呼ばれたことを確認
            mock_client.read_gatt_char.assert_called_once_with(read_request.characteristic_uuid)
            
            # レスポンスが設定されていることを確認
            assert read_request.response_data == b'\x42'
            
            # 連続失敗回数がリセットされていることを確認
            assert handler._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_handle_write_request_success(self, handler, write_request):
        """書き込みリクエストが正しく処理されることを確認"""
        # BleakClientのモック
        with patch('ble_orchestrator.orchestrator.handler.BleakClient') as MockClient:
            # クライアントのインスタンスをモック
            mock_client = AsyncMock()
            
            # コンテキストマネージャーが返すインスタンスを設定
            MockClient.return_value.__aenter__.return_value = mock_client
            
            # 書き込みリクエストの処理
            await handler.handle_request(write_request)
            
            # write_gatt_charが呼ばれたことを確認
            mock_client.write_gatt_char.assert_called_once_with(
                write_request.characteristic_uuid,
                write_request.data,
                response=write_request.response_required
            )
            
            # 連続失敗回数がリセットされていることを確認
            assert handler._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_handle_write_request_with_response(self, handler, write_request):
        """レスポンスを要求する書き込みリクエストが正しく処理されることを確認"""
        # レスポンスが必要な書き込みリクエスト
        write_request.response_required = True
        
        # BleakClientのモック
        with patch('ble_orchestrator.orchestrator.handler.BleakClient') as MockClient:
            # クライアントのインスタンスをモック
            mock_client = AsyncMock()
            
            # read_gatt_charメソッドの戻り値を設定
            mock_client.read_gatt_char.return_value = b'\x43'
            
            # コンテキストマネージャーが返すインスタンスを設定
            MockClient.return_value.__aenter__.return_value = mock_client
            
            # 書き込みリクエストの処理
            await handler.handle_request(write_request)
            
            # write_gatt_charが呼ばれたことを確認
            mock_client.write_gatt_char.assert_called_once_with(
                write_request.characteristic_uuid,
                write_request.data,
                response=True
            )
            
            # read_gatt_charが呼ばれたことを確認
            mock_client.read_gatt_char.assert_called_once_with(write_request.characteristic_uuid)
            
            # レスポンスが設定されていることを確認
            assert write_request.response_data == b'\x43'

    @pytest.mark.asyncio
    async def test_handle_read_request_connection_error(self, handler, read_request):
        """接続エラー時の読み取りリクエストが正しく処理されることを確認"""
        # BleakClientのモック
        with patch('ble_orchestrator.orchestrator.handler.BleakClient') as MockClient:
            # 接続エラーを発生させる
            from bleak import BleakError
            MockClient.return_value.__aenter__.side_effect = BleakError("Connection failed")
            
            # エラーが発生することを確認
            with pytest.raises(BleakError):
                await handler.handle_request(read_request)
                
            # 連続失敗回数が増えることを確認
            assert handler._consecutive_failures == 1
            assert read_request.status == RequestStatus.FAILED
            assert "connection failed" in read_request.error_message.lower()

    @pytest.mark.asyncio
    async def test_consecutive_failures_and_reset(self, handler, read_request):
        """連続失敗カウンタが正しく機能することを確認"""
        # 初期状態
        assert handler.get_consecutive_failures() == 0
        
        # デバイスが見つからない場合のエラー
        handler._get_device_func.return_value = None
        
        # 1回目の失敗
        with pytest.raises(ValueError):
            await handler.handle_request(read_request)
        assert handler.get_consecutive_failures() == 1
        
        # 2回目の失敗
        with pytest.raises(ValueError):
            await handler.handle_request(read_request)
        assert handler.get_consecutive_failures() == 2
        
        # カウンタのリセット
        handler.reset_failure_count()
        assert handler.get_consecutive_failures() == 0 
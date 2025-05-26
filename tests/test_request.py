import uuid
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ble_orchestrator.orchestrator.request import (
    Request, BLERequest, ReadSensorRequest, SendCommandRequest, 
    BLERequestHandler, RequestStatus, RequestTimeoutError,
    RequestQueueManager
)


@pytest.fixture
def read_sensor_request():
    """ReadSensorRequestのテスト用フィクスチャ"""
    return ReadSensorRequest(
        mac_address="AA:BB:CC:DD:EE:FF", 
        sensor_name="temperature"
    )


@pytest.fixture
def send_command_request():
    """SendCommandRequestのテスト用フィクスチャ"""
    return SendCommandRequest(
        mac_address="AA:BB:CC:DD:EE:FF",
        command_name="set_led",
        parameters={"color": "red", "brightness": 100}
    )


@pytest.fixture
async def ble_adapter():
    """モック化されたBLEAdapterのフィクスチャ"""
    with patch("ble_orchestrator.orchestrator.request.BLEAdapter") as mock_adapter_class:
        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()
        mock_adapter.read_characteristic = AsyncMock(return_value=b'{"temperature": 25.5}')
        mock_adapter.write_characteristic = AsyncMock()
        mock_adapter_class.return_value = mock_adapter
        
        yield mock_adapter


@pytest.fixture
async def request_handler(ble_adapter):
    """BLERequestHandlerのテスト用フィクスチャ"""
    # エラーハンドリング関数をモック化
    error_handler = AsyncMock()
    
    # ハンドラーインスタンスを作成
    handler = BLERequestHandler(error_handler=error_handler)
    
    yield handler


@pytest.fixture
async def queue_manager(request_handler):
    """RequestQueueManagerのテスト用フィクスチャ"""
    # キューマネージャーインスタンスを作成
    manager = RequestQueueManager(request_handler)
    
    yield manager
    
    # テスト後にクリーンアップ
    await manager.stop()


class TestRequest:
    def test_request_init(self, read_sensor_request):
        """Test that a Request object can be initialized with correct attributes."""
        assert read_sensor_request.device_id == "test_device"
        assert read_sensor_request.sensor_id == "temperature"
        assert isinstance(read_sensor_request.request_id, str)
        assert read_sensor_request.status == "pending"
        assert read_sensor_request.result is None

    def test_request_update_status(self, read_sensor_request):
        """Test that a request status can be updated."""
        read_sensor_request.update_status("processing")
        assert read_sensor_request.status == "processing"

    def test_request_update_result(self, read_sensor_request):
        """Test that a request result can be updated."""
        result = {"temperature": 25.0}
        read_sensor_request.update_result(result)
        assert read_sensor_request.result == result
        assert read_sensor_request.status == "completed"

    def test_request_update_error(self, read_sensor_request):
        """Test that a request error can be updated."""
        error_msg = "Device not found"
        read_sensor_request.update_error(error_msg)
        assert read_sensor_request.error == error_msg
        assert read_sensor_request.status == "failed"

    def test_execute_not_implemented(self, read_sensor_request):
        """Test that execute method raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            asyncio.run(read_sensor_request.execute(None))


class TestBLERequest:
    def test_ble_request_creation(self):
        """BLERequestクラスのテスト"""
        request = BLERequest(
            mac_address="AA:BB:CC:DD:EE:FF",
            service_uuid="1800",
            characteristic_uuid="2A00"
        )
        
        # 基本属性の確認
        assert request.mac_address == "AA:BB:CC:DD:EE:FF"
        assert request.service_uuid == "1800"
        assert request.characteristic_uuid == "2A00"
        
        # dict表現の確認
        request_dict = request.to_dict()
        assert request_dict["service_uuid"] == "1800"
        assert request_dict["characteristic_uuid"] == "2A00"


class TestReadSensorRequest:
    def test_read_sensor_request_creation(self, read_sensor_request):
        """ReadSensorRequestクラスのテスト"""
        # 基本属性の確認
        assert read_sensor_request.mac_address == "AA:BB:CC:DD:EE:FF"
        assert read_sensor_request.sensor_name == "temperature"
        
        # dict表現の確認
        request_dict = read_sensor_request.to_dict()
        assert request_dict["sensor_name"] == "temperature"
        assert request_dict["request_type"] == "read_sensor"


class TestSendCommandRequest:
    def test_send_command_request_creation(self, send_command_request):
        """SendCommandRequestクラスのテスト"""
        # 基本属性の確認
        assert send_command_request.mac_address == "AA:BB:CC:DD:EE:FF"
        assert send_command_request.command_name == "set_led"
        assert send_command_request.parameters == {"color": "red", "brightness": 100}
        
        # dict表現の確認
        request_dict = send_command_request.to_dict()
        assert request_dict["command_name"] == "set_led"
        assert request_dict["parameters"] == {"color": "red", "brightness": 100}
        assert request_dict["request_type"] == "send_command"


class TestBLERequestHandler:
    @pytest.mark.asyncio
    async def test_read_sensor_request(self, request_handler, read_sensor_request, ble_adapter):
        """ReadSensorRequestの処理テスト"""
        # リクエスト処理
        await request_handler.handle_request(read_sensor_request)
        
        # 接続と切断が行われたことを確認
        ble_adapter.connect.assert_called_once_with("AA:BB:CC:DD:EE:FF")
        ble_adapter.disconnect.assert_called_once()
        
        # リクエストのステータスとリザルトを確認
        assert read_sensor_request.status == RequestStatus.COMPLETED
        assert read_sensor_request.result == {"temperature": 25.5}
    
    @pytest.mark.asyncio
    async def test_send_command_request(self, request_handler, send_command_request, ble_adapter):
        """SendCommandRequestの処理テスト"""
        # リクエスト処理
        await request_handler.handle_request(send_command_request)
        
        # 接続と切断が行われたことを確認
        ble_adapter.connect.assert_called_once_with("AA:BB:CC:DD:EE:FF")
        ble_adapter.disconnect.assert_called_once()
        
        # コマンド送信が行われたことを確認
        ble_adapter.write_characteristic.assert_called_once()
        
        # リクエストのステータスを確認
        assert send_command_request.status == RequestStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_request_handling_error(self, request_handler, read_sensor_request, ble_adapter):
        """リクエスト処理中のエラーハンドリングテスト"""
        # BLEAdapterの接続でエラーを発生させる
        ble_adapter.connect.side_effect = Exception("Connection error")
        
        # リクエスト処理
        await request_handler.handle_request(read_sensor_request)
        
        # エラーハンドラーが呼ばれたことを確認
        request_handler._error_handler.assert_called_once()
        
        # リクエストのステータスを確認
        assert read_sensor_request.status == RequestStatus.FAILED
        assert "error" in read_sensor_request.result
    
    @pytest.mark.asyncio
    async def test_consecutive_failures(self, request_handler, read_sensor_request, ble_adapter):
        """連続失敗カウントのテスト"""
        # 初期状態を確認
        assert request_handler.get_consecutive_failures() == 0
        
        # BLEAdapterの接続でエラーを発生させる
        ble_adapter.connect.side_effect = Exception("Connection error")
        
        # リクエストを複数回処理
        for _ in range(3):
            await request_handler.handle_request(read_sensor_request)
        
        # 連続失敗カウントが増えていることを確認
        assert request_handler.get_consecutive_failures() == 3
        
        # カウントをリセット
        request_handler.reset_consecutive_failures()
        
        # リセット後のカウントを確認
        assert request_handler.get_consecutive_failures() == 0


class TestRequestQueueManager:
    @pytest.mark.asyncio
    async def test_enqueue_request(self, queue_manager, read_sensor_request):
        """リクエストのエンキューテスト"""
        # Queue Managerを起動
        await queue_manager.start()
        
        # リクエストをエンキュー
        request_id = await queue_manager.enqueue_request(read_sensor_request)
        
        # 返却されたIDがリクエストのIDと一致することを確認
        assert request_id == read_sensor_request.id
        
        # キューサイズが増えたことを確認
        assert queue_manager.get_queue_size() > 0
    
    @pytest.mark.asyncio
    async def test_get_request_status(self, queue_manager, read_sensor_request):
        """リクエストステータス取得テスト"""
        # Queue Managerを起動
        await queue_manager.start()
        
        # リクエストをエンキューして一意なIDを取得
        request_id = await queue_manager.enqueue_request(read_sensor_request)
        
        # ステータスを取得
        status = queue_manager.get_request_status(request_id)
        
        # ステータス情報の構造を確認
        assert "id" in status
        assert "status" in status
        assert "mac_address" in status
        
        # 値が正しいことを確認
        assert status["id"] == request_id
        assert status["status"] == "pending"
        assert status["mac_address"] == "AA:BB:CC:DD:EE:FF"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_request_status(self, queue_manager):
        """存在しないリクエストのステータス取得テスト"""
        # Queue Managerを起動
        await queue_manager.start()
        
        # 存在しないIDでステータスを取得
        status = queue_manager.get_request_status(str(uuid.uuid4()))
        
        # ステータスがNoneであることを確認
        assert status is None
    
    @pytest.mark.asyncio
    async def test_request_processing(self, queue_manager, read_sensor_request, request_handler):
        """リクエスト処理フローのテスト"""
        # RequestHandlerのhandle_requestメソッドをモック化
        request_handler.handle_request = AsyncMock()
        
        # Queue Managerを起動
        await queue_manager.start()
        
        # リクエストをエンキュー
        await queue_manager.enqueue_request(read_sensor_request)
        
        # リクエスト処理タスクを手動でスケジュール
        await queue_manager._process_next_request()
        
        # ハンドラーのhandle_requestが呼ばれたことを確認
        request_handler.handle_request.assert_called_once_with(read_sensor_request)
    
    @pytest.mark.asyncio
    async def test_stop_while_processing(self, queue_manager, read_sensor_request, request_handler):
        """処理中のキューマネージャー停止テスト"""
        # 長時間実行されるハンドル処理をシミュレート
        async def slow_handler(request):
            await asyncio.sleep(1)
            request.status = RequestStatus.COMPLETED
        
        request_handler.handle_request = slow_handler
        
        # Queue Managerを起動
        await queue_manager.start()
        
        # リクエストをエンキュー
        await queue_manager.enqueue_request(read_sensor_request)
        
        # キューマネージャーを停止
        await queue_manager.stop()
        
        # キューマネージャーが停止していることを確認
        assert queue_manager._running is False 
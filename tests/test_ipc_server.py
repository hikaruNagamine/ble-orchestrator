import asyncio
import json
import os
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

from ble_orchestrator.orchestrator.ipc_server import IPCServer
from ble_orchestrator.orchestrator.types import (
    ScanResult, ReadRequest, WriteRequest, RequestPriority
)


@pytest.fixture
def mock_handlers():
    """モック化されたハンドラー関数セット"""
    scan_result = ScanResult(
        address="AA:BB:CC:DD:EE:FF",
        name="TestDevice",
        rssi=-60,
        advertisement_data={
            "local_name": "TestDevice",
            "manufacturer_data": {"0102": [3, 4]},
            "service_data": {"0000180f-0000-1000-8000-00805f9b34fb": [5, 6]},
            "service_uuids": ["0000180f-0000-1000-8000-00805f9b34fb"]
        },
        timestamp=1000.0
    )
    
    # スキャンハンドラー
    def handle_scan_func(mac_address):
        if mac_address == "AA:BB:CC:DD:EE:FF":
            return scan_result
        return None
    
    # キューイングハンドラー
    enqueue_request_func = AsyncMock(return_value=str(uuid.uuid4()))
    
    # ステータスハンドラー
    get_status_func = MagicMock(return_value={
        "is_running": True,
        "adapter_status": "ok",
        "queue_size": 0,
        "last_error": None,
        "uptime_sec": 123.4,
        "active_devices": 1
    })
    
    return handle_scan_func, enqueue_request_func, get_status_func


@pytest.fixture
async def ipc_server(mock_handlers):
    """テスト用のIPCサーバーインスタンス"""
    handle_scan_func, enqueue_request_func, get_status_func = mock_handlers
    
    with patch.object(IPCServer, "_serve_forever", AsyncMock()):
        with patch("os.unlink"):
            with patch("os.path.exists", return_value=False):
                with patch("os.chmod"):
                    with patch("asyncio.start_unix_server", AsyncMock()):
                        server = IPCServer(
                            handle_scan_func,
                            enqueue_request_func,
                            get_status_func
                        )
                        yield server
                        
                        if server._task is not None:
                            await server.stop()


@pytest.fixture
def mock_reader_writer():
    """モック化されたStreamReaderとStreamWriter"""
    reader = AsyncMock()
    writer = AsyncMock()
    writer.get_extra_info.return_value = ("127.0.0.1", 12345)
    return reader, writer


class TestIPCServer:
    @pytest.mark.asyncio
    async def test_start_stop_unix_socket(self, ipc_server):
        """UNIXソケットモードでの起動と停止のテスト"""
        # 環境変数をクリア
        with patch.dict(os.environ, {}, clear=True):
            # サーバーを起動
            await ipc_server.start()
            assert ipc_server._task is not None
            
            # サーバーを停止
            await ipc_server.stop()
            assert ipc_server._task is None

    @pytest.mark.asyncio
    async def test_start_stop_tcp_socket(self, ipc_server):
        """TCPソケットモードでの起動と停止のテスト"""
        # 環境変数にTCP指定
        with patch.dict(os.environ, {"BLE_ORCHESTRATOR_TCP": "1"}):
            with patch("asyncio.start_server", AsyncMock()):
                # サーバーを起動
                await ipc_server.start()
                assert ipc_server._task is not None
                
                # サーバーを停止
                await ipc_server.stop()
                assert ipc_server._task is None

    @pytest.mark.asyncio
    async def test_process_command_get_scan_result_success(self, ipc_server, mock_handlers):
        """get_scan_resultコマンドの成功テスト"""
        # リクエスト
        request = {
            "mac_address": "AA:BB:CC:DD:EE:FF"
        }
        
        # コマンド処理
        response = await ipc_server._process_command("get_scan_result", request)
        
        # レスポンスの確認
        assert response["status"] == "success"
        assert "data" in response
        assert response["data"]["address"] == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_process_command_get_scan_result_not_found(self, ipc_server):
        """get_scan_resultコマンドで存在しないデバイスのテスト"""
        # リクエスト
        request = {
            "mac_address": "11:22:33:44:55:66"  # 存在しないMACアドレス
        }
        
        # コマンド処理
        response = await ipc_server._process_command("get_scan_result", request)
        
        # レスポンスの確認
        assert response["status"] == "error"
        assert "error" in response

    @pytest.mark.asyncio
    async def test_process_command_read_sensor(self, ipc_server, mock_handlers):
        """read_sensorコマンドのテスト"""
        _, enqueue_request_func, _ = mock_handlers
        
        # リクエスト
        request = {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "service_uuid": "0000180f-0000-1000-8000-00805f9b34fb",
            "characteristic_uuid": "00002a19-0000-1000-8000-00805f9b34fb",
            "priority": "HIGH",
            "timeout": 5.0
        }
        
        # コマンド処理
        response = await ipc_server._process_command("read_sensor", request)
        
        # レスポンスの確認
        assert response["status"] == "success"
        assert "request_id" in response
        
        # enqueue_request_funcが呼ばれたことを確認
        enqueue_request_func.assert_called_once()
        args, _ = enqueue_request_func.call_args
        read_request = args[0]
        
        # 渡されたリクエストオブジェクトの確認
        assert isinstance(read_request, ReadRequest)
        assert read_request.mac_address == "AA:BB:CC:DD:EE:FF"
        assert read_request.service_uuid == "0000180f-0000-1000-8000-00805f9b34fb"
        assert read_request.characteristic_uuid == "00002a19-0000-1000-8000-00805f9b34fb"
        assert read_request.priority == RequestPriority.HIGH
        assert read_request.timeout_sec == 5.0

    @pytest.mark.asyncio
    async def test_process_command_send_command(self, ipc_server, mock_handlers):
        """send_commandコマンドのテスト"""
        _, enqueue_request_func, _ = mock_handlers
        
        # リクエスト
        request = {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "service_uuid": "0000180f-0000-1000-8000-00805f9b34fb",
            "characteristic_uuid": "00002a19-0000-1000-8000-00805f9b34fb",
            "data": "0102",  # 16進文字列
            "response_required": True,
            "priority": "LOW",
            "timeout": 15.0
        }
        
        # コマンド処理
        response = await ipc_server._process_command("send_command", request)
        
        # レスポンスの確認
        assert response["status"] == "success"
        assert "request_id" in response
        
        # enqueue_request_funcが呼ばれたことを確認
        enqueue_request_func.assert_called_once()
        args, _ = enqueue_request_func.call_args
        write_request = args[0]
        
        # 渡されたリクエストオブジェクトの確認
        assert isinstance(write_request, WriteRequest)
        assert write_request.mac_address == "AA:BB:CC:DD:EE:FF"
        assert write_request.service_uuid == "0000180f-0000-1000-8000-00805f9b34fb"
        assert write_request.characteristic_uuid == "00002a19-0000-1000-8000-00805f9b34fb"
        assert write_request.data == bytes([0x01, 0x02])
        assert write_request.response_required is True
        assert write_request.priority == RequestPriority.LOW
        assert write_request.timeout_sec == 15.0

    @pytest.mark.asyncio
    async def test_process_command_get_request_status(self, ipc_server):
        """get_request_statusコマンドのテスト"""
        # リクエスト
        request = {
            "request_id": "test-request-id"
        }
        
        # コマンド処理
        response = await ipc_server._process_command("get_request_status", request)
        
        # レスポンスの確認（まだ実装されていないので"pending"が返る）
        assert response["status"] == "pending"

    @pytest.mark.asyncio
    async def test_process_command_status(self, ipc_server, mock_handlers):
        """statusコマンドのテスト"""
        _, _, get_status_func = mock_handlers
        
        # コマンド処理
        response = await ipc_server._process_command("status", {})
        
        # レスポンスの確認
        assert response["status"] == "success"
        assert "data" in response
        assert response["data"]["is_running"] is True
        assert response["data"]["adapter_status"] == "ok"
        
        # get_status_funcが呼ばれたことを確認
        get_status_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_command_unknown(self, ipc_server):
        """未知のコマンドのテスト"""
        # コマンド処理
        response = await ipc_server._process_command("unknown_command", {})
        
        # レスポンスの確認
        assert response["status"] == "error"
        assert "error" in response
        assert "Unknown command" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_client(self, ipc_server, mock_reader_writer):
        """クライアント接続ハンドリングのテスト"""
        reader, writer = mock_reader_writer
        
        # クライアントからのリクエスト
        request = {
            "command": "status"
        }
        
        # 1回目の読み取りでリクエストを返し、2回目の読み取りで接続終了を示す
        reader.readline.side_effect = [
            json.dumps(request).encode() + b"\n",
            b""  # 空のレスポンスで接続終了を示す
        ]
        
        # クライアント処理を実行
        await ipc_server._handle_client(reader, writer)
        
        # writeが呼ばれたことを確認
        assert writer.write.called
        
        # 接続が閉じられたことを確認
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_client_invalid_json(self, ipc_server, mock_reader_writer):
        """不正なJSONを受け取った場合のテスト"""
        reader, writer = mock_reader_writer
        
        # 不正なJSON
        reader.readline.side_effect = [
            b"invalid json\n",
            b""  # 空のレスポンスで接続終了を示す
        ]
        
        # クライアント処理を実行
        await ipc_server._handle_client(reader, writer)
        
        # エラーレスポンスが送信されたことを確認
        args, _ = writer.write.call_args_list[0]
        response_bytes = args[0]
        response = json.loads(response_bytes.decode().strip())
        assert response["status"] == "error"
        assert "Invalid JSON" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_client_exception(self, ipc_server, mock_reader_writer):
        """処理中に例外が発生した場合のテスト"""
        reader, writer = mock_reader_writer
        
        # 正しいJSONだが処理中に例外
        request = {
            "command": "get_scan_result"
            # mac_addressが欠けているので処理中にエラー
        }
        
        reader.readline.side_effect = [
            json.dumps(request).encode() + b"\n",
            b""  # 空のレスポンスで接続終了を示す
        ]
        
        # クライアント処理を実行
        await ipc_server._handle_client(reader, writer)
        
        # エラーレスポンスが送信されたことを確認
        args, _ = writer.write.call_args_list[0]
        response_bytes = args[0]
        response = json.loads(response_bytes.decode().strip())
        assert response["status"] == "error"
        assert "error" in response 
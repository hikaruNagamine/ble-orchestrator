"""
pytestのフィクスチャ定義
"""

import asyncio
import logging
import os
import pytest
from unittest.mock import MagicMock, AsyncMock

from ble_orchestrator.orchestrator.types import ScanResult, RequestPriority, RequestStatus
from ble_orchestrator.orchestrator.scanner import ScanCache, BLEScanner
from ble_orchestrator.orchestrator.queue_manager import RequestQueueManager
from ble_orchestrator.orchestrator.handler import BLERequestHandler
from ble_orchestrator.orchestrator.watchdog import BLEWatchdog
from ble_orchestrator.orchestrator.ipc_server import IPCServer
from ble_orchestrator.orchestrator.service import BLEOrchestratorService


# ロギングを無効化
@pytest.fixture(autouse=True)
def disable_logging():
    """テスト中はロギングを無効化"""
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def event_loop():
    """
    非同期テスト用のイベントループを提供
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_ble_device():
    """
    モック化されたBLEDeviceを提供
    """
    device = MagicMock()
    device.address = "AA:BB:CC:DD:EE:FF"
    device.name = "Test Device"
    return device


@pytest.fixture
def mock_advertisement_data():
    """
    モック化されたAdvertisementDataを提供
    """
    adv_data = MagicMock()
    adv_data.rssi = -70
    adv_data.local_name = "Test Device"
    adv_data.manufacturer_data = {b'\x00\x01': b'test'}
    adv_data.service_data = {"service1": b'test'}
    adv_data.service_uuids = ["uuid1", "uuid2"]
    return adv_data


@pytest.fixture
def sample_scan_result():
    """
    サンプルのスキャン結果を提供
    """
    return ScanResult(
        address="AA:BB:CC:DD:EE:FF",
        name="Test Device",
        rssi=-70,
        advertisement_data={
            "local_name": "Test Device",
            "manufacturer_data": {"0001": [116, 101, 115, 116]},
            "service_data": {"service1": [116, 101, 115, 116]},
            "service_uuids": ["uuid1", "uuid2"],
        },
        timestamp=1000.0
    )


@pytest.fixture
def mock_scan_cache(sample_scan_result):
    """
    モック化されたScanCacheを提供
    """
    cache = MagicMock(spec=ScanCache)
    cache.get_latest_result.return_value = sample_scan_result
    cache.get_all_devices.return_value = ["AA:BB:CC:DD:EE:FF"]
    return cache


@pytest.fixture
def mock_ble_scanner(mock_scan_cache):
    """
    モック化されたBLEScannerを提供
    """
    scanner = MagicMock(spec=BLEScanner)
    scanner.cache = mock_scan_cache
    scanner.start = AsyncMock()
    scanner.stop = AsyncMock()
    scanner.is_running = True
    return scanner


@pytest.fixture
def mock_request_handler():
    """
    モック化されたBLERequestHandlerを提供
    """
    handler = MagicMock(spec=BLERequestHandler)
    handler.handle_request = AsyncMock()
    handler.get_consecutive_failures.return_value = 0
    handler.reset_failure_count = MagicMock()
    return handler


@pytest.fixture
def mock_queue_manager():
    """
    モック化されたRequestQueueManagerを提供
    """
    queue_manager = MagicMock(spec=RequestQueueManager)
    queue_manager.start = AsyncMock()
    queue_manager.stop = AsyncMock()
    queue_manager.enqueue_request = AsyncMock(return_value="request-id-1234")
    queue_manager.get_queue_size.return_value = 0
    return queue_manager


@pytest.fixture
def mock_watchdog():
    """
    モック化されたBLEWatchdogを提供
    """
    watchdog = MagicMock(spec=BLEWatchdog)
    watchdog.start = AsyncMock()
    watchdog.stop = AsyncMock()
    return watchdog


@pytest.fixture
def mock_ipc_server():
    """
    モック化されたIPCServerを提供
    """
    server = MagicMock(spec=IPCServer)
    server.start = AsyncMock()
    server.stop = AsyncMock()
    return server


@pytest.fixture
def mock_service(mock_ble_scanner, mock_request_handler, 
                mock_queue_manager, mock_watchdog, mock_ipc_server):
    """
    モック化されたBLEOrchestratorServiceを提供
    すべてのコンポーネントがモック化されている
    """
    service = MagicMock(spec=BLEOrchestratorService)
    service.scanner = mock_ble_scanner
    service.handler = mock_request_handler
    service.queue_manager = mock_queue_manager
    service.watchdog = mock_watchdog
    service.ipc_server = mock_ipc_server
    service.start = AsyncMock()
    service.stop = AsyncMock()
    return service 
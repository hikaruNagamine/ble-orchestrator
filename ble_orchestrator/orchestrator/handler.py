"""
BLEリクエスト処理ハンドラー
各種リクエストの具体的な処理ロジックを実装
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, cast

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice

from .config import BLE_CONNECT_TIMEOUT_SEC, BLE_RETRY_COUNT, BLE_RETRY_INTERVAL_SEC
from .types import BLERequest, ReadRequest, ScanRequest, WriteRequest, RequestStatus

logger = logging.getLogger(__name__)


class BLERequestHandler:
    """
    BLEリクエスト処理ハンドラー
    """

    def __init__(self, get_device_func):
        """
        初期化
        get_device_func: BLEDeviceを取得する関数
        """
        self._get_device_func = get_device_func
        self._connection_lock = asyncio.Lock()
        self._last_error = None
        self._consecutive_failures = 0

    async def handle_request(self, request: BLERequest) -> None:
        """
        リクエストの種類に応じた処理を実行
        """
        try:
            if isinstance(request, ScanRequest):
                await self._handle_scan_request(request)
            elif isinstance(request, ReadRequest):
                await self._handle_read_request(request)
            elif isinstance(request, WriteRequest):
                await self._handle_write_request(request)
            else:
                raise ValueError(f"Unknown request type: {type(request)}")
                
            # 成功したらエラーカウンタをリセット
            self._consecutive_failures = 0
            
        except Exception as e:
            self._last_error = str(e)
            self._consecutive_failures += 1
            logger.error(f"Error handling request {request.request_id}: {e}")
            request.status = RequestStatus.FAILED
            request.error_message = str(e)
            raise

    async def _handle_scan_request(self, request: ScanRequest) -> None:
        """
        スキャン結果を返す
        """
        # すでにキャッシュが管理しているので特に処理なし
        # メインサービスでキャッシュから取得している
        logger.debug(f"Scan request {request.request_id} for {request.mac_address} processed")

    async def _handle_read_request(self, request: ReadRequest) -> None:
        """
        特性値を読み取る
        """
        device = await self._get_device(request.mac_address)
        if not device:
            raise ValueError(f"Device {request.mac_address} not found")

        async with self._connection_lock:
            for retry in range(BLE_RETRY_COUNT):
                try:
                    logger.debug(
                        f"Connecting to {device.address} to read characteristic "
                        f"{request.characteristic_uuid} (attempt {retry+1}/{BLE_RETRY_COUNT})"
                    )
                    
                    async with BleakClient(device, timeout=BLE_CONNECT_TIMEOUT_SEC) as client:
                        logger.debug(f"Connected to {device.address}")
                        
                        value = await client.read_gatt_char(request.characteristic_uuid)
                        request.response_data = value
                        
                        logger.info(
                            f"Successfully read characteristic {request.characteristic_uuid} "
                            f"from {device.address}: {value.hex() if value else 'None'}"
                        )
                        return
                        
                except (BleakError, asyncio.TimeoutError) as e:
                    logger.warning(
                        f"Failed to read from {device.address} (attempt {retry+1}): {e}"
                    )
                    if retry < BLE_RETRY_COUNT - 1:
                        await asyncio.sleep(BLE_RETRY_INTERVAL_SEC)
                    else:
                        raise BleakError(f"Failed to read after {BLE_RETRY_COUNT} attempts: {e}")

    async def _handle_write_request(self, request: WriteRequest) -> None:
        """
        特性値を書き込む
        """
        device = await self._get_device(request.mac_address)
        if not device:
            raise ValueError(f"Device {request.mac_address} not found")

        async with self._connection_lock:
            for retry in range(BLE_RETRY_COUNT):
                try:
                    logger.debug(
                        f"Connecting to {device.address} to write characteristic "
                        f"{request.characteristic_uuid} (attempt {retry+1}/{BLE_RETRY_COUNT})"
                    )
                    
                    async with BleakClient(device, timeout=BLE_CONNECT_TIMEOUT_SEC) as client:
                        logger.debug(f"Connected to {device.address}")
                        
                        await client.write_gatt_char(
                            request.characteristic_uuid, 
                            request.data,
                            response=request.response_required
                        )
                        
                        # レスポンスが必要な場合は読み取り
                        if request.response_required:
                            response = await client.read_gatt_char(request.characteristic_uuid)
                            request.response_data = response
                            logger.debug(f"Response received: {response.hex() if response else 'None'}")
                        
                        logger.info(
                            f"Successfully wrote to characteristic {request.characteristic_uuid} "
                            f"on {device.address}: {request.data.hex() if request.data else 'None'}"
                        )
                        return
                        
                except (BleakError, asyncio.TimeoutError) as e:
                    logger.warning(
                        f"Failed to write to {device.address} (attempt {retry+1}): {e}"
                    )
                    if retry < BLE_RETRY_COUNT - 1:
                        await asyncio.sleep(BLE_RETRY_INTERVAL_SEC)
                    else:
                        raise BleakError(f"Failed to write after {BLE_RETRY_COUNT} attempts: {e}")

    async def _get_device(self, address: str) -> Optional[BLEDevice]:
        """
        スキャン結果からデバイスを取得
        """
        device = self._get_device_func(address)
        if not device:
            logger.warning(f"Device {address} not found in scan cache")
            return None
            
        return device

    def get_consecutive_failures(self) -> int:
        """
        連続失敗回数を取得
        """
        return self._consecutive_failures

    def reset_failure_count(self) -> None:
        """
        失敗カウンタをリセット
        """
        self._consecutive_failures = 0 
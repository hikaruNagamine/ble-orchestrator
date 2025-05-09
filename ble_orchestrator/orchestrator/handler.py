"""
BLEリクエスト処理ハンドラー
各種リクエストの具体的な処理ロジックを実装
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, cast, Union

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice

from .config import BLE_CONNECT_TIMEOUT_SEC, BLE_RETRY_COUNT, BLE_RETRY_INTERVAL_SEC
from .types import (
    BLERequest, ReadRequest, ScanRequest, WriteRequest, RequestStatus, 
    NotificationRequest
)

logger = logging.getLogger(__name__)


class BLERequestHandler:
    """
    BLEリクエスト処理ハンドラー
    """

    def __init__(self, get_device_func, get_scan_data_func=None):
        """
        初期化
        get_device_func: BLEDeviceを取得する関数
        get_scan_data_func: スキャン済みデータを取得する関数
        """
        self._get_device_func = get_device_func
        self._get_scan_data_func = get_scan_data_func
        self._connection_lock = asyncio.Lock()
        self._last_error = None
        self._consecutive_failures = 0

    async def handle_request(self, request: BLERequest) -> None:
        """
        リクエストの種類に応じた処理を実行
        """
        try:
            logger.debug(f"&&&&&&&&&handle_request: {request}")
            if isinstance(request, ScanRequest):
                await self._handle_scan_request(request)
            elif isinstance(request, ReadRequest):
                await self._handle_read_request(request)
            elif isinstance(request, WriteRequest):
                logger.debug(f"&&&&&&&&&handle_request: WriteRequest")
                await self._handle_write_request(request)
                logger.debug(f"&&&&&&&&&handle_request: WriteRequest done")
            elif isinstance(request, NotificationRequest):
                # 通知リクエストはメインサービスで直接処理されるので何もしない
                logger.debug(f"Notification request {request.request_id} will be handled by notification manager")
            else:
                raise ValueError(f"Unknown request type: {type(request)}")
                
            # 成功したらエラーカウンタをリセット
            self._consecutive_failures = 0
            
            # リクエスト完了をマーク
            request.mark_as_done()
            logger.debug(f"&&&&&&&&&handle_request: done")
            
        except Exception as e:
            self._last_error = str(e)
            self._consecutive_failures += 1
            logger.error(f"Error handling request {request.request_id}: {e}")
            request.status = RequestStatus.FAILED
            request.error_message = str(e)
            
            # エラー時もリクエスト完了をマーク
            request.mark_as_done()
            
            raise

    async def _handle_scan_request(self, request: ScanRequest) -> None:
        """
        スキャン済みデータを取得して返す（デバイスに接続せずに）
        """
        # スキャン関数が設定されていない場合はエラー
        if not self._get_scan_data_func:
            logger.error("Scan data function not configured")
            raise ValueError("Scan data function not configured")
            
        logger.debug(f"Getting scan data for {request.mac_address}")
        
        # スキャン済みデータを取得
        scan_data = self._get_scan_data_func(request.mac_address)
        if not scan_data:
            logger.error(f"No scan data found for device {request.mac_address}")
            raise ValueError(f"No scan data found for device {request.mac_address}")
        
        logger.debug(f"scan_data: {scan_data}")

        # レスポンスデータを設定
        scan_result = {}
        
        # デバイスの基本情報
        if hasattr(scan_data, "name"):
            scan_result["name"] = scan_data.name
        if hasattr(scan_data, "rssi"):
            scan_result["rssi"] = scan_data.rssi
        if hasattr(scan_data, "address"):
            scan_result["address"] = scan_data.address
            
        # アドバタイズメントデータ
        if hasattr(scan_data, "advertisement_data"):
            scan_result["advertisement_data"] = scan_data.advertisement_data
            # manufacturer_dataを明示的に取り出して含める
            if "manufacturer_data" in scan_data.advertisement_data:
                scan_result["manufacturer_data"] = scan_data.advertisement_data["manufacturer_data"]
        # 旧スタイルのアドバタイズメントデータ（advertisementプロパティを使用）
        elif hasattr(scan_data, "advertisement"):
            adv_data = scan_data.advertisement
            # アドバタイズデータをJSON化できる形式に変換
            adv_dict = {}
            for key, value in adv_data.__dict__.items():
                if key.startswith("_"):
                    continue
                    
                # バイト型データは16進数文字列に変換
                if isinstance(value, bytes):
                    adv_dict[key] = value.hex()
                # リスト型のバイトデータも変換
                elif isinstance(value, list) and all(isinstance(x, bytes) for x in value):
                    adv_dict[key] = [x.hex() for x in value]
                # その他の型はそのまま
                else:
                    adv_dict[key] = value
                    
            scan_result["advertisement_data"] = adv_dict
            
            # manufacturer_dataを明示的に取り出して含める
            if hasattr(adv_data, "manufacturer_data"):
                manufacturer_data = {}
                for key, value in adv_data.manufacturer_data.items():
                    if isinstance(key, int):
                        str_key = str(key)
                    elif isinstance(key, bytes):
                        str_key = key.hex()
                    else:
                        str_key = str(key)
                        
                    if isinstance(value, bytes):
                        manufacturer_data[str_key] = list(value)
                    elif isinstance(value, list):
                        manufacturer_data[str_key] = value
                    else:
                        manufacturer_data[str_key] = str(value)
                        
                scan_result["manufacturer_data"] = manufacturer_data
            
        # サービスUUIDリスト
        if hasattr(scan_data, "metadata") and "uuids" in scan_data.metadata:
            scan_result["services"] = scan_data.metadata["uuids"]
            
        # サービスデータ
        if request.service_uuid:
            # 特定のサービスに関するデータのみを抽出
            service_data = {}
            if hasattr(scan_data, "metadata") and "service_data" in scan_data.metadata:
                service_data = scan_data.metadata["service_data"].get(request.service_uuid, {})
            scan_result["service_data"] = {request.service_uuid: service_data}
        
        # レスポンスデータを設定    
        request.response_data = scan_result
        
        # リクエスト完了
        request.status = RequestStatus.COMPLETED
        
        logger.info(f"Scan request {request.request_id} for {request.mac_address} processed")
        logger.debug(f"Scan result: {scan_result}")

    async def _handle_read_request(self, request: ReadRequest) -> None:
        """
        特性値を読み取る
        """
        device = await self._get_device(request.mac_address)
        logger.debug(f"read_request: {request.mac_address}")
        logger.debug(f"read_request: {device}")
        if not device:
            raise ValueError(f"Device {request.mac_address} not found")

        async with self._connection_lock:
            for retry in range(BLE_RETRY_COUNT):
                try:
                    logger.debug(
                        f"Connecting to {device} to read characteristic "
                        f"{request.characteristic_uuid} (attempt {retry+1}/{BLE_RETRY_COUNT})"
                    )
                    
                    async with BleakClient(device.address, timeout=BLE_CONNECT_TIMEOUT_SEC, adapter="hci1") as client:
                        logger.debug(f"Connected to {device}")
                        
                        value = await client.read_gatt_char(request.characteristic_uuid)
                        request.response_data = value
                        request.status = RequestStatus.COMPLETED
                        
                        logger.info(
                            f"Successfully read characteristic {request.characteristic_uuid} "
                            f"from {device}: {value.hex() if value else 'None'}"
                        )
                        return
                        
                except (BleakError, asyncio.TimeoutError) as e:
                    logger.warning(
                        f"Failed to read from {device} (attempt {retry+1}): {e}"
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
                    
                    async with BleakClient(device.address, timeout=BLE_CONNECT_TIMEOUT_SEC, adapter="hci1") as client:
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
                        else:
                            logger.debug(f"Response not required")
                            request.response_data = {}
                        
                        # リクエスト完了
                        request.status = RequestStatus.COMPLETED
                        
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

    async def _get_device(self, mac_address: str) -> Optional[Union[BLEDevice, str]]:
        """
        BLEデバイスを取得
        bleak 0.22.3では文字列のMACアドレスをそのまま使用可能
        """
        device = self._get_device_func(mac_address)
        logger.debug(f"get_device: {device}")
        logger.debug(f"get_device: {type(device)}")
        if not device:
            raise ValueError(f"Device {mac_address} not found")
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
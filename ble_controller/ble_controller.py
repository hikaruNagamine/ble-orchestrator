import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from .services.request_queue import RequestQueue
from .types.request_task import RequestTask, CommandType, BLEDeviceData
from .exceptions import DeviceConnectionError

logger = logging.getLogger(__name__)

class BLEController:
    """BLEデバイスコントローラー

    BLEデバイスのスキャンと制御を行う。
    リクエストキューを使用して非同期処理を管理する。
    """

    def __init__(self):
        self.scanner = None
        self.scan_data: List[BLEDeviceData] = []
        self.scan_task = None
        self.is_scanning = False
        self.request_queue = RequestQueue(max_size=1000)

    async def start(self):
        """BLEコントローラーを開始"""
        logger.info("Starting BLE controller")
        try:
            self.scanner = BleakScanner(adapter='hci0')
            self.scan_task = asyncio.create_task(self._continuous_scan())
            await self.request_queue.start()
            self.is_scanning = True
        except Exception as e:
            logger.error(f"Failed to start BLE controller: {e}", exc_info=True)
            raise

    async def stop(self):
        """BLEコントローラーを停止"""
        logger.info("Stopping BLE controller")
        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
            try:
                await self.scan_task
            except asyncio.CancelledError:
                pass
        await self.request_queue.stop()
        self.scan_data = []

    async def _continuous_scan(self):
        """継続的なBLEスキャン処理"""
        while self.is_scanning:
            try:
                devices = await self.scanner.discover(timeout=1.0)
                current_time = datetime.now()
                
                # 新しいスキャンデータを追加
                for device in devices:
                    scan_entry = {
                        'address': device.address,
                        'name': device.name,
                        'rssi': device.rssi,
                        'timestamp': current_time.isoformat(),
                        'manufacturer_data': device.metadata.get('manufacturer_data', {})
                    }
                    self.scan_data.append(scan_entry)

                # 10秒より古いデータを削除
                cutoff_time = current_time - timedelta(seconds=10)
                self.scan_data = [
                    entry for entry in self.scan_data
                    if datetime.fromisoformat(entry['timestamp']) > cutoff_time
                ]

            except Exception as e:
                print(f"Scan error: {e}")
                await asyncio.sleep(1)

    async def get_scan_data(self, timestamp: Optional[str] = None) -> List[Dict]:
        """スキャンデータ取得リクエストをキューに追加"""
        task = RequestTask(
            id=f"get_{datetime.now().timestamp()}",
            type=CommandType.GET,
            url="/scan_data",
            priority=1,
            payload={"timestamp": timestamp},
            timestamp=datetime.now().timestamp()
        )
        self.request_queue.enqueue(task)
        return await self._get_scan_data_internal(timestamp)

    async def _get_scan_data_internal(self, timestamp: Optional[str] = None) -> List[Dict]:
        """内部的なスキャンデータ取得処理"""
        if not timestamp:
            return self.scan_data

        start_time = datetime.fromisoformat(timestamp)
        return [
            entry for entry in self.scan_data
            if datetime.fromisoformat(entry['timestamp']) >= start_time
        ]

    async def send_command(self, device_address: str, command: str, parameters: Dict = None) -> Dict:
        """コマンド送信リクエストをキューに追加"""
        task = RequestTask(
            id=f"send_{datetime.now().timestamp()}",
            type=CommandType.SEND,
            url="/command",
            priority=2,
            payload={
                "address": device_address,
                "command": command,
                "parameters": parameters
            },
            timestamp=datetime.now().timestamp()
        )
        self.request_queue.enqueue(task)
        return await self._send_command_internal(device_address, command, parameters)

    async def _send_command_internal(self, device_address: str, command: str, parameters: Dict = None) -> Dict:
        """内部的なコマンド送信処理"""
        try:
            async with BleakClient(device_address, adapter='hci1') as client:
                if command == "turn_on":
                    result = await self._execute_turn_on(client, parameters)
                else:
                    raise ValueError(f"Unknown command: {command}")

                return {
                    "status": "success",
                    "result": result
                }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def _execute_turn_on(self, client: BleakClient, parameters: Dict) -> Dict:
        """turn_onコマンドの実装例"""
        # ここにデバイス固有の実装を追加
        return {"message": "Command executed successfully"}

    async def wait_for_queue_completion(self) -> None:
        """キューの処理完了を待機"""
        while self.request_queue._is_processing or self.request_queue._queue:
            await asyncio.sleep(0.1) 

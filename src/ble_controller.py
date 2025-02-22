import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

class BLEController:
    def __init__(self):
        self.scanner = None
        self.scan_data = []
        self.scan_task = None
        self.is_scanning = False

    async def start(self):
        """BLEコントローラーを開始"""
        # スキャナーの初期化
        self.scanner = BleakScanner(adapter='hci0')
        # スキャンの開始
        self.scan_task = asyncio.create_task(self._continuous_scan())
        self.is_scanning = True

    async def stop(self):
        """BLEコントローラーを停止"""
        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
            try:
                await self.scan_task
            except asyncio.CancelledError:
                pass
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
        """
        指定された時刻以降のスキャンデータを取得
        
        Args:
            timestamp: 取得開始時刻（ISO形式）
        """
        if not timestamp:
            return self.scan_data

        start_time = datetime.fromisoformat(timestamp)
        return [
            entry for entry in self.scan_data
            if datetime.fromisoformat(entry['timestamp']) >= start_time
        ]

    async def send_command(self, device_address: str, command: str, parameters: Dict = None) -> Dict:
        """
        BLEデバイスにコマンドを送信
        
        Args:
            device_address: デバイスのMACアドレス
            command: 実行するコマンド
            parameters: コマンドのパラメータ
        """
        try:
            async with BleakClient(device_address, adapter='hci1') as client:
                # コマンドの実行
                if command == "turn_on":
                    # ここに実際のBLEコマンド実装を追加
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
        """
        turn_onコマンドの実装例
        実際のデバイスに応じて実装を追加
        """
        # ここにデバイス固有の実装を追加
        return {"message": "Command executed successfully"} 
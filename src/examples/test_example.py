import asyncio
import pytest
from datetime import datetime
from ble_controller import BLEController

@pytest.mark.asyncio
async def test_scan_data():
    controller = BLEController()
    await controller.start()

    try:
        # スキャンデータが取得できることを確認
        await asyncio.sleep(2)  # スキャンデータが蓄積されるまで待機
        
        data = await controller.get_scan_data()
        assert isinstance(data, list)
        
        # タイムスタンプ指定での取得を確認
        timestamp = datetime.now().isoformat()
        filtered_data = await controller.get_scan_data(timestamp)
        assert isinstance(filtered_data, list)
        
    finally:
        await controller.stop()

@pytest.mark.asyncio
async def test_send_command():
    controller = BLEController()
    await controller.start()

    try:
        # コマンド送信のテスト
        result = await controller.send_command(
            device_address="00:11:22:33:44:55",  # テスト用アドレス
            command="turn_on"
        )
        
        assert isinstance(result, dict)
        assert "status" in result
        
    finally:
        await controller.stop()

if __name__ == "__main__":
    pytest.main([__file__]) 
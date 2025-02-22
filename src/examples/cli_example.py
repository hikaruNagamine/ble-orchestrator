import asyncio
import json
from datetime import datetime

from ble_controller import BLEController

async def main():
    # BLEコントローラーの初期化と開始
    controller = BLEController()
    await controller.start()

    try:
        while True:
            print("\nBLE Controller CLI Example")
            print("1: Get scan data")
            print("2: Send command")
            print("q: Quit")
            
            choice = input("Choose an option: ")

            if choice == "1":
                # スキャンデータの取得
                timestamp = (datetime.now()).isoformat()
                print(f"Getting scan data from {timestamp}")
                
                data = await controller.get_scan_data(timestamp)
                print("\nScan Results:")
                print(json.dumps(data, indent=2))

            elif choice == "2":
                # コマンド送信
                address = input("Enter device address (e.g. XX:XX:XX:XX:XX:XX): ")
                command = input("Enter command (e.g. turn_on): ")
                
                result = await controller.send_command(
                    device_address=address,
                    command=command
                )
                print("\nCommand Result:")
                print(json.dumps(result, indent=2))

            elif choice.lower() == 'q':
                break

            await asyncio.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        await controller.stop()

if __name__ == "__main__":
    asyncio.run(main()) 
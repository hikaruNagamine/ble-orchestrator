import aiohttp
import asyncio
import json
from datetime import datetime

async def main():
    async with aiohttp.ClientSession() as session:
        while True:
            print("\nBLE Controller HTTP Client Example")
            print("1: Get scan data")
            print("2: Send command")
            print("q: Quit")
            
            choice = input("Choose an option: ")

            if choice == "1":
                # スキャンデータの取得
                timestamp = datetime.now().isoformat()
                data = {
                    "command": "get",
                    "timestamp": timestamp
                }
                
                async with session.post('http://localhost:8080/ble', json=data) as response:
                    result = await response.json()
                    print("\nScan Results:")
                    print(json.dumps(result, indent=2))

            elif choice == "2":
                # コマンド送信
                address = input("Enter device address (e.g. XX:XX:XX:XX:XX:XX): ")
                command = input("Enter command (e.g. turn_on): ")
                
                data = {
                    "command": "send",
                    "device": {
                        "address": address,
                        "command": command
                    }
                }
                
                async with session.post('http://localhost:8080/ble', json=data) as response:
                    result = await response.json()
                    print("\nCommand Result:")
                    print(json.dumps(result, indent=2))

            elif choice.lower() == 'q':
                break

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main()) 
import asyncio
from .service import BLEService

async def main():
    service = BLEService()
    await service.start()
    
    try:
        # サービスを実行し続ける
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await service.stop()

if __name__ == '__main__':
    asyncio.run(main()) 
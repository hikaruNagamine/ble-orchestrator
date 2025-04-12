#!/usr/bin/env python3
"""
BLE Orchestrator - メインスクリプト
"""

import asyncio
import logging
import signal
import sys

from orchestrator.service import BLEOrchestratorService

logger = logging.getLogger(__name__)


async def main():
    """
    メインエントリーポイント
    """
    service = BLEOrchestratorService()
    
    # シグナルハンドラ設定
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(shutdown(service))
        )
    
    try:
        # サービス開始
        await service.start()
        
        # 無限ループで待機（シグナルで停止されるまで）
        while True:
            await asyncio.sleep(3600)  # 1時間待機
            
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
        return 1
    finally:
        await shutdown(service)
    
    return 0


async def shutdown(service):
    """
    正常にシャットダウン
    """
    logger.info("Shutdown initiated")
    await service.stop()
    
    # 現在のタスクを取得
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    # 残りのタスクをキャンセルして待機
    for task in tasks:
        task.cancel()
    
    if tasks:
        logger.info(f"Waiting for {len(tasks)} tasks to complete...")
        await asyncio.gather(*tasks, return_exceptions=True)
    
    logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        # Pythonバージョンチェック
        if sys.version_info < (3, 9):
            print("Error: Python 3.9 or higher is required")
            sys.exit(1)
            
        # メイン実行
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1) 
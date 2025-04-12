#!/usr/bin/env python3
"""
BLEWatchdogの使用例

このスクリプトはBLEWatchdogクラスの基本的な使い方と設定方法を示します。
実際のアプリケーションでは、このクラスはBLEOrchestratorServiceによって管理されます。
"""

import asyncio
import logging
import signal
import sys
import time
from typing import Optional

# ble_orchestratorパッケージをインポート
sys.path.append('..')
from ble_orchestrator.orchestrator.watchdog import BLEWatchdog


# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("watchdog_example")


# シミュレーション用の連続失敗カウンタ
consecutive_failures = 0


def get_failures() -> int:
    """
    連続失敗回数を取得する関数
    実際のアプリケーションではBLERequestHandlerから提供されます
    """
    global consecutive_failures
    return consecutive_failures


def reset_failures() -> None:
    """
    連続失敗カウンタをリセットする関数
    実際のアプリケーションではBLERequestHandlerから提供されます
    """
    global consecutive_failures
    logger.info("失敗カウンタをリセットします")
    consecutive_failures = 0


class ExampleApplication:
    """
    BLEWatchdogを使用するアプリケーション例
    """
    
    def __init__(self):
        self.watchdog: Optional[BLEWatchdog] = None
        self.running = False
        self._stop_event = asyncio.Event()
        
    async def start(self) -> None:
        """
        アプリケーションとウォッチドッグを起動
        """
        logger.info("アプリケーションを起動します")
        self.running = True
        
        # ウォッチドッグの初期化と起動
        self.watchdog = BLEWatchdog(
            get_failures_func=get_failures,
            reset_failures_func=reset_failures,
            adapter_name="hci0"  # 実際のBLEアダプタ名を指定
        )
        await self.watchdog.start()
        
        # メインループの開始
        asyncio.create_task(self._main_loop())
    
    async def stop(self) -> None:
        """
        アプリケーションとウォッチドッグを停止
        """
        logger.info("アプリケーションを停止します")
        self.running = False
        self._stop_event.set()
        
        # ウォッチドッグの停止
        if self.watchdog:
            await self.watchdog.stop()
    
    async def _main_loop(self) -> None:
        """
        アプリケーションのメインループ
        テスト用に定期的に失敗カウンタを増加させます
        """
        global consecutive_failures
        
        try:
            counter = 0
            
            while not self._stop_event.is_set():
                # 10秒ごとに失敗カウンタを増加
                counter += 1
                if counter % 10 == 0:
                    consecutive_failures += 1
                    logger.info(f"BLE操作の失敗をシミュレート: 連続失敗回数 = {consecutive_failures}")
                
                # アプリケーションの状態を出力
                logger.debug(f"アプリケーション実行中... 連続失敗回数: {consecutive_failures}")
                
                # 1秒待機
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("メインループがキャンセルされました")
        except Exception as e:
            logger.error(f"メインループでエラーが発生しました: {e}")
        finally:
            logger.info("メインループを終了します")


async def shutdown(app: ExampleApplication, sig: signal.Signals = None) -> None:
    """
    シャットダウン処理
    """
    if sig:
        logger.info(f"シグナル {sig.name} を受信しました")
    await app.stop()


async def main() -> None:
    """
    メイン関数
    """
    # シグナルハンドラの設定
    app = ExampleApplication()
    loop = asyncio.get_running_loop()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(app, s))
        )
    
    try:
        # アプリケーション起動
        await app.start()
        
        # メインスレッドがシグナルを受け取るまで待機
        while app.running:
            await asyncio.sleep(0.1)
            
    except Exception as e:
        logger.error(f"アプリケーション実行中にエラーが発生しました: {e}")
    finally:
        # クリーンアップ
        await app.stop()
        logger.info("アプリケーションを終了します")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("キーボード割り込みを受信しました")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
    finally:
        print("終了しました") 
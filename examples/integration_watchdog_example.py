#!/usr/bin/env python3
"""
BLEWatchdogの統合例

このスクリプトはBLEWatchdogをBLERequestHandlerと一緒に使用する方法を示します。
実際のアプリケーションでは、これらはBLEOrchestratorServiceによって管理されます。
"""

import asyncio
import logging
import signal
import sys
from typing import Optional, Dict, Any

# ble_orchestratorパッケージをインポート
sys.path.append('..')
from ble_orchestrator.orchestrator.watchdog import BLEWatchdog
from ble_orchestrator.orchestrator.types import BLERequest, RequestStatus, ReadRequest
from ble_orchestrator.orchestrator.config import CONSECUTIVE_FAILURES_THRESHOLD


# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("integration_example")


class MockBLEHandler:
    """
    BLERequestHandlerのモック
    実際のハンドラーと同様のインターフェースを提供し、エラーをシミュレート
    """
    
    def __init__(self):
        self._consecutive_failures = 0
        self._simulate_errors = False
    
    async def handle_request(self, request: BLERequest) -> None:
        """リクエスト処理をシミュレート"""
        if self._simulate_errors:
            self._consecutive_failures += 1
            request.status = RequestStatus.FAILED
            request.error_message = f"シミュレートされたエラー (連続 {self._consecutive_failures}回目)"
            logger.error(f"リクエスト処理エラー: {request.error_message}")
            return
        
        # 正常処理
        self._consecutive_failures = 0
        request.status = RequestStatus.COMPLETED
        
        if isinstance(request, ReadRequest):
            # 読み取りリクエストの場合はレスポンスを設定
            request.response_data = b'\x42'
        
        logger.info(f"リクエスト {request.request_id} 正常処理完了")
    
    def get_consecutive_failures(self) -> int:
        """連続失敗回数を取得"""
        return self._consecutive_failures
    
    def reset_failure_count(self) -> None:
        """失敗カウンタをリセット"""
        logger.info(f"失敗カウンタをリセット: {self._consecutive_failures} → 0")
        self._consecutive_failures = 0
    
    def set_simulate_errors(self, simulate: bool) -> None:
        """エラーシミュレーション設定"""
        self._simulate_errors = simulate
        logger.info(f"エラーシミュレーション: {'有効' if simulate else '無効'}")


class IntegrationExample:
    """
    BLEWatchdogとBLEHandlerの統合例
    """
    
    def __init__(self):
        self.handler = MockBLEHandler()
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
            get_failures_func=self.handler.get_consecutive_failures,
            reset_failures_func=self.handler.reset_failure_count,
            adapter_name="hci0"
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
        テスト用に一定時間後にエラーをシミュレート
        """
        try:
            counter = 0
            
            while not self._stop_event.is_set():
                counter += 1
                
                # 10秒後にエラーをシミュレート開始
                if counter == 10:
                    logger.warning("BLE操作のエラーシミュレーションを開始します")
                    self.handler.set_simulate_errors(True)
                
                # 30秒後にエラーシミュレーションを停止
                if counter == 30:
                    logger.warning("BLE操作のエラーシミュレーションを停止します")
                    self.handler.set_simulate_errors(False)
                
                # リクエスト処理をシミュレート
                request = ReadRequest(
                    request_id=f"read-{counter}",
                    mac_address="AA:BB:CC:DD:EE:FF",
                    service_uuid="0000180f-0000-1000-8000-00805f9b34fb",
                    characteristic_uuid="00002a19-0000-1000-8000-00805f9b34fb"
                )
                
                try:
                    await self.handler.handle_request(request)
                    
                    # 処理結果を表示
                    if request.status == RequestStatus.COMPLETED:
                        logger.info(f"リクエスト成功: id={request.request_id}")
                    else:
                        logger.warning(f"リクエスト失敗: id={request.request_id}, status={request.status}")
                        
                except Exception as e:
                    logger.error(f"リクエスト処理で例外が発生: {e}")
                
                # ステータス表示
                failures = self.handler.get_consecutive_failures()
                threshold = CONSECUTIVE_FAILURES_THRESHOLD
                logger.info(f"現在のステータス: 連続失敗={failures}/{threshold}")
                
                # 1秒待機
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("メインループがキャンセルされました")
        except Exception as e:
            logger.error(f"メインループでエラーが発生しました: {e}")
        finally:
            logger.info("メインループを終了します")


async def shutdown(app: IntegrationExample, sig: signal.Signals = None) -> None:
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
    app = IntegrationExample()
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
#!/usr/bin/env python3
"""
BLEWatchdogをサーキットブレーカーパターンとして使用する例

このスクリプトは、BLEWatchdogクラスを使用して、サーキットブレーカーパターンを
実装する方法を示します。サーキットブレーカーパターンは、障害が発生した場合に
システムを保護し、自動復旧を試みるデザインパターンです。
"""

import asyncio
import logging
import signal
import sys
import time
import random
from typing import Optional, Callable, Awaitable, Dict, Any
from enum import Enum, auto

# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("circuit_breaker_example")


class CircuitState(Enum):
    """サーキットブレーカーの状態"""
    CLOSED = auto()  # 正常状態（リクエスト許可）
    OPEN = auto()    # 障害状態（リクエスト拒否）
    HALF_OPEN = auto()  # 回復試行状態（限定的なリクエスト許可）


class BLECircuitBreaker:
    """
    BLEオペレーションのためのサーキットブレーカー実装
    連続失敗を監視し、しきい値を超えると回路を開いてリクエストを拒否します
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 10.0,
        reset_command: str = "sudo hciconfig hci0 reset"
    ):
        """
        初期化
        
        Args:
            failure_threshold: 回路を開くための連続失敗のしきい値
            recovery_timeout: 回路が開いた後に半開状態に移行するまでの秒数
            reset_command: 回復時に実行するコマンド
        """
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._reset_command = reset_command
        self._state = CircuitState.CLOSED
        self._last_failure_time = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """現在の回路状態を取得"""
        return self._state
    
    @property
    def failure_count(self) -> int:
        """現在の連続失敗回数"""
        return self._failure_count
    
    async def execute(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        """
        操作を実行し、サーキットブレーカーロジックを適用
        
        Args:
            operation: 実行する非同期操作
            
        Returns:
            操作の結果
            
        Raises:
            CircuitOpenError: 回路が開いている場合
            その他の例外: 操作自体が失敗した場合
        """
        async with self._lock:
            # 回路が開いている場合は即時拒否
            if self._state == CircuitState.OPEN:
                # 回復タイムアウトを確認
                current_time = time.time()
                if current_time - self._last_failure_time >= self._recovery_timeout:
                    logger.info("回復タイムアウトに達しました。回路を半開状態に移行します")
                    self._state = CircuitState.HALF_OPEN
                else:
                    remaining = self._recovery_timeout - (current_time - self._last_failure_time)
                    raise CircuitOpenError(
                        f"サーキットブレーカーが開いています。残り約{remaining:.1f}秒で回復試行"
                    )
        
        try:
            # CLOSED または HALF_OPEN 状態では操作を許可
            logger.debug(f"操作を実行します (状態: {self._state.name})")
            result = await operation()
            
            # 成功した場合
            async with self._lock:
                if self._state == CircuitState.HALF_OPEN:
                    logger.info("回復テスト成功。回路を閉じます")
                    self._state = CircuitState.CLOSED
                
                self._failure_count = 0
            
            return result
            
        except Exception as e:
            # 失敗した場合
            async with self._lock:
                self._failure_count += 1
                logger.warning(f"操作が失敗しました。連続失敗回数: {self._failure_count}/{self._failure_threshold}")
                
                # しきい値を超えた場合は回路を開く
                if self._failure_count >= self._failure_threshold:
                    if self._state != CircuitState.OPEN:
                        logger.error(f"連続失敗しきい値({self._failure_threshold})を超えました。回路を開きます")
                        self._state = CircuitState.OPEN
                        self._last_failure_time = time.time()
                        
                        # 自動回復プロセスを開始
                        asyncio.create_task(self._attempt_recovery())
                
                # 例外を再送出
                raise
    
    async def _attempt_recovery(self) -> None:
        """
        回復プロセスを試行
        """
        logger.info("回復プロセスを開始します")
        try:
            # リセットコマンドを実行
            logger.info(f"リセットコマンドを実行: {self._reset_command}")
            process = await asyncio.create_subprocess_shell(
                self._reset_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"リセット成功: {stdout.decode().strip()}")
            else:
                logger.error(f"リセット失敗 (コード: {process.returncode}): {stderr.decode().strip()}")
        
        except Exception as e:
            logger.error(f"回復プロセス中にエラーが発生: {e}")
    
    def reset(self) -> None:
        """
        サーキットブレーカーをリセットして閉じた状態に戻す
        """
        logger.info("サーキットブレーカーを手動でリセットします")
        self._failure_count = 0
        self._state = CircuitState.CLOSED


class CircuitOpenError(Exception):
    """サーキットブレーカーが開いている場合に発生する例外"""
    pass


class BLEDeviceSimulator:
    """
    BLEデバイスシミュレータ
    ランダムな障害を生成
    """
    
    def __init__(self, failure_rate: float = 0.3):
        """
        初期化
        
        Args:
            failure_rate: 操作が失敗する確率 (0.0～1.0)
        """
        self.failure_rate = failure_rate
        self.device_id = "AA:BB:CC:DD:EE:FF"
    
    async def read_characteristic(self, characteristic_id: str) -> bytes:
        """
        特性値の読み取りをシミュレート
        
        Args:
            characteristic_id: 読み取る特性のID
            
        Returns:
            読み取ったデータ
            
        Raises:
            ConnectionError: 接続エラーが発生した場合
            TimeoutError: タイムアウトが発生した場合
        """
        # シミュレートされた処理時間
        await asyncio.sleep(0.2)
        
        # 障害をシミュレート
        if random.random() < self.failure_rate:
            error_type = random.choice([ConnectionError, TimeoutError])
            logger.debug(f"シミュレートされた障害: {error_type.__name__}")
            raise error_type(f"デバイス {self.device_id} との通信中にエラーが発生しました")
        
        # 成功した場合はダミーデータを返す
        return bytes([random.randint(0, 255) for _ in range(4)])


class CircuitBreakerExample:
    """
    サーキットブレーカーの使用例
    """
    
    def __init__(self):
        self.device = BLEDeviceSimulator(failure_rate=0.4)
        self.circuit_breaker = BLECircuitBreaker(
            failure_threshold=3,
            recovery_timeout=5.0,
            reset_command="echo 'Simulating BLE adapter reset'"
        )
        self.running = False
        self._stop_event = asyncio.Event()
    
    async def start(self) -> None:
        """アプリケーションを開始"""
        logger.info("サーキットブレーカー例を開始します")
        self.running = True
        asyncio.create_task(self._main_loop())
    
    async def stop(self) -> None:
        """アプリケーションを停止"""
        logger.info("サーキットブレーカー例を停止します")
        self.running = False
        self._stop_event.set()
    
    async def _main_loop(self) -> None:
        """メインアプリケーションループ"""
        try:
            counter = 0
            battery_characteristic = "00002a19-0000-1000-8000-00805f9b34fb"
            
            while not self._stop_event.is_set():
                counter += 1
                logger.info(f"==== リクエスト #{counter} ====")
                logger.info(f"現在の状態: {self.circuit_breaker.state.name}, "
                           f"失敗カウント: {self.circuit_breaker.failure_count}")
                
                try:
                    # サーキットブレーカーを通して操作を実行
                    result = await self.circuit_breaker.execute(
                        lambda: self.device.read_characteristic(battery_characteristic)
                    )
                    logger.info(f"読取り成功: {result.hex()}")
                    
                except CircuitOpenError as e:
                    logger.warning(f"リクエスト拒否: {e}")
                    
                except (ConnectionError, TimeoutError) as e:
                    logger.error(f"BLE操作エラー: {e}")
                    
                except Exception as e:
                    logger.error(f"未知のエラー: {e}")
                
                # 次のリクエストまで待機
                await asyncio.sleep(1.0)
        
        except asyncio.CancelledError:
            logger.info("メインループがキャンセルされました")
        except Exception as e:
            logger.error(f"メインループでエラーが発生: {e}")
        finally:
            logger.info("メインループを終了します")


async def shutdown(app: CircuitBreakerExample, sig: signal.Signals = None) -> None:
    """シャットダウン処理"""
    if sig:
        logger.info(f"シグナル {sig.name} を受信しました")
    await app.stop()


async def main() -> None:
    """メイン関数"""
    # シグナルハンドラの設定
    app = CircuitBreakerExample()
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
        print("プログラムを終了します") 
# BLE Orchestrator リファクタリング提案

## 🎯 目標
グローバル変数を除去し、より保守性の高いコード構造にする

## 📋 現在の問題点

### 1. グローバル変数の多用
`scanner.py`と`handler.py`で以下のグローバル変数が共有されている：

```python
# scanner.py
_ble_operation_lock = asyncio.Lock()
_scanner_stopping = False
_client_connecting = False
_scan_ready = asyncio.Event()
_scan_completed = asyncio.Event()
_client_completed = asyncio.Event()
```

**問題：**
- テストが困難（グローバル状態のリセットが必要）
- マルチインスタンス実行が不可能
- 状態管理が分散している

## 🔧 提案される解決策

### 解決策1: ExclusiveControlManagerクラスの導入

```python
# ble_orchestrator/orchestrator/exclusive_control.py

"""
BLE操作の排他制御を管理するモジュール
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class ExclusiveControlManager:
    """
    BLEスキャナーとクライアント操作の排他制御を管理するクラス
    
    スキャナーとクライアントが同時にBLEアダプタにアクセスすることによる
    競合を防ぐための排他制御メカニズムを提供します。
    """
    
    def __init__(
        self,
        enabled: bool = True,
        deadlock_threshold: float = 90.0,
        client_completion_timeout: float = 60.0
    ):
        """
        初期化
        
        Args:
            enabled: 排他制御を有効にするかどうか
            deadlock_threshold: デッドロック検出のしきい値（秒）
            client_completion_timeout: クライアント完了待機のタイムアウト（秒）
        """
        self._enabled = enabled
        self._deadlock_threshold = deadlock_threshold
        self._client_completion_timeout = client_completion_timeout
        
        # 排他制御用のロックとイベント
        self._ble_operation_lock = asyncio.Lock()
        self._scanner_stopping = False
        self._client_connecting = False
        self._scan_ready = asyncio.Event()
        self._scan_completed = asyncio.Event()
        self._client_completed = asyncio.Event()
        
        # デッドロック検出用
        self._exclusive_control_start_time: Optional[float] = None
        
        # 初期状態を設定
        self._scan_ready.set()
    
    def is_enabled(self) -> bool:
        """排他制御が有効かどうかを返す"""
        return self._enabled
    
    def set_enabled(self, enabled: bool) -> None:
        """排他制御の有効/無効を設定"""
        self._enabled = enabled
        logger.info(f"Exclusive control {'enabled' if enabled else 'disabled'}")
    
    def is_client_connecting(self) -> bool:
        """クライアントが接続中かどうかを返す"""
        return self._client_connecting
    
    def request_scanner_stop(self) -> None:
        """
        クライアント接続のためにスキャナー停止を要求
        """
        if not self._enabled:
            return
            
        self._scanner_stopping = True
        self._client_connecting = True
        self._exclusive_control_start_time = time.time()
        self._scan_ready.clear()
        logger.info("Scanner stop requested for client connection")
    
    def notify_client_completed(self) -> None:
        """
        クライアント処理完了を通知
        """
        if not self._enabled:
            return
            
        self._client_connecting = False
        self._scanner_stopping = False
        self._client_completed.set()
        
        if self._exclusive_control_start_time:
            duration = time.time() - self._exclusive_control_start_time
            logger.info(
                f"Client operation completed, scanner can resume "
                f"(exclusive control duration: {duration:.1f}s)"
            )
            self._exclusive_control_start_time = None
        else:
            logger.info("Client operation completed, scanner can resume")
    
    def get_wait_events(self):
        """
        待機用のイベントオブジェクトを返す
        
        Returns:
            tuple: (scan_ready, scan_completed, client_completed)
        """
        return (
            self._scan_ready,
            self._scan_completed,
            self._client_completed
        )
    
    def is_scanner_stopping(self) -> bool:
        """スキャナーが停止中かどうかを返す"""
        return self._scanner_stopping
    
    def notify_scan_completed(self) -> None:
        """スキャン停止完了を通知"""
        self._scan_completed.set()
        logger.debug("Scanner stop completed")
    
    def notify_scan_ready(self) -> None:
        """スキャン準備完了を通知"""
        self._scan_ready.set()
        logger.debug("Scanner ready")
    
    def get_operation_lock(self) -> asyncio.Lock:
        """BLE操作用のロックを返す"""
        return self._ble_operation_lock
    
    def check_deadlock(self) -> bool:
        """
        デッドロックの可能性をチェック
        
        Returns:
            bool: デッドロックの可能性がある場合はTrue
        """
        if not self._exclusive_control_start_time:
            return False
            
        current_time = time.time()
        exclusive_duration = current_time - self._exclusive_control_start_time
        
        if exclusive_duration > self._deadlock_threshold:
            logger.error(
                f"POTENTIAL DEADLOCK DETECTED: "
                f"Exclusive control active for {exclusive_duration:.1f}s"
            )
            return True
            
        return False
    
    def force_reset(self) -> None:
        """
        デッドロック検出時に排他制御を強制リセット
        
        注意: この操作は危険です。実際にクライアントが動作中の場合、
        状態が不整合になる可能性があります。
        """
        logger.warning("Forcing reset of exclusive control due to potential deadlock")
        
        self._scanner_stopping = False
        self._client_connecting = False
        self._client_completed.set()
        self._scan_ready.set()
        self._exclusive_control_start_time = None
    
    async def wait_for_scan_ready(self, timeout: Optional[float] = None) -> bool:
        """
        スキャン準備完了を待機
        
        Args:
            timeout: タイムアウト（秒）
            
        Returns:
            bool: 準備完了した場合はTrue、タイムアウトした場合はFalse
        """
        try:
            await asyncio.wait_for(self._scan_ready.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for scan ready after {timeout}s")
            return False
    
    async def wait_for_scan_completed(self, timeout: Optional[float] = None) -> bool:
        """
        スキャン停止完了を待機
        
        Args:
            timeout: タイムアウト（秒）
            
        Returns:
            bool: 停止完了した場合はTrue、タイムアウトした場合はFalse
        """
        try:
            await asyncio.wait_for(self._scan_completed.wait(), timeout=timeout)
            self._scan_completed.clear()
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for scan completion after {timeout}s")
            return False
    
    async def wait_for_client_completed(self, timeout: Optional[float] = None) -> bool:
        """
        クライアント処理完了を待機
        
        Args:
            timeout: タイムアウト（秒）
            
        Returns:
            bool: 完了した場合はTrue、タイムアウトした場合はFalse
        """
        try:
            await asyncio.wait_for(
                self._client_completed.wait(),
                timeout=timeout or self._client_completion_timeout
            )
            self._client_completed.clear()
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for client completion after {timeout}s")
            return False
    
    def get_status(self) -> dict:
        """
        排他制御の現在の状態を取得
        
        Returns:
            dict: 状態情報
        """
        return {
            "enabled": self._enabled,
            "scanner_stopping": self._scanner_stopping,
            "client_connecting": self._client_connecting,
            "scan_ready": self._scan_ready.is_set(),
            "exclusive_control_duration": (
                time.time() - self._exclusive_control_start_time
                if self._exclusive_control_start_time
                else None
            ),
        }
```

### 解決策2: リファクタリング後のコード構造

#### service.py の変更

```python
class BLEOrchestratorService:
    def __init__(self):
        # 排他制御マネージャーを作成
        self.exclusive_control = ExclusiveControlManager(
            enabled=EXCLUSIVE_CONTROL_ENABLED,
            deadlock_threshold=90.0,
            client_completion_timeout=60.0
        )
        
        # スキャナー（排他制御マネージャーを渡す）
        self.scanner = BLEScanner(
            notify_watchdog_func=self._notify_watchdog,
            exclusive_control=self.exclusive_control
        )
        
        # ハンドラー（排他制御マネージャーを渡す）
        self.handler = BLERequestHandler(
            get_device_func=self._get_ble_device,
            scanner=self.scanner,
            exclusive_control=self.exclusive_control,
            notify_watchdog_func=notify_bleakclient_failure
        )
```

#### scanner.py の変更

```python
class BLEScanner:
    def __init__(
        self,
        notify_watchdog_func=None,
        exclusive_control: Optional[ExclusiveControlManager] = None
    ):
        self.exclusive_control = exclusive_control or ExclusiveControlManager()
        # ... 他の初期化
    
    async def _scan_loop(self) -> None:
        """スキャンループ"""
        try:
            while not self._stop_event.is_set():
                self._update_loop_activity()
                
                # 排他制御をチェック
                if self.exclusive_control.is_scanner_stopping():
                    logger.info("Scanner stop requested for client connection")
                    
                    await self._stop_current_scanner()
                    self.exclusive_control.notify_scan_completed()
                    
                    # クライアント完了を待機
                    completed = await self.exclusive_control.wait_for_client_completed(
                        timeout=60.0
                    )
                    
                    if not completed:
                        logger.warning("Timeout waiting for client, forcing scanner restart")
                    
                    # スキャンを再開
                    await self._restart_scanner()
                    self.exclusive_control.notify_scan_ready()
                
                await asyncio.sleep(SCAN_INTERVAL_SEC)
                
                # デッドロックチェック
                if self.exclusive_control.check_deadlock():
                    self.exclusive_control.force_reset()
```

#### handler.py の変更

```python
class BLERequestHandler:
    def __init__(
        self,
        get_device_func,
        scanner=None,
        exclusive_control: Optional[ExclusiveControlManager] = None,
        notify_watchdog_func=None
    ):
        self._exclusive_control = exclusive_control or ExclusiveControlManager()
        # ... 他の初期化
    
    async def _handle_write_request(self, request: WriteRequest) -> None:
        """特性値を書き込む"""
        device = await self._get_device(request.mac_address)
        
        async with self._connection_lock:
            # 排他制御が有効な場合
            if self._exclusive_control.is_enabled():
                # スキャナー停止を要求
                self._exclusive_control.request_scanner_stop()
                
                # スキャン停止完了を待機
                completed = await self._exclusive_control.wait_for_scan_completed(
                    timeout=10.0
                )
                
                if not completed:
                    logger.warning("Timeout waiting for scanner stop, proceeding anyway")
            
            try:
                # BLE操作（ロック取得）
                async with self._exclusive_control.get_operation_lock():
                    # ... 実際の書き込み処理 ...
                    pass
            finally:
                # 排他制御が有効な場合、クライアント処理完了を通知
                if self._exclusive_control.is_enabled():
                    self._exclusive_control.notify_client_completed()
```

## ✅ この変更のメリット

1. **テストが容易**: ExclusiveControlManagerをモックできる
2. **状態管理が明確**: すべての排他制御状態が1つのクラスに集約
3. **マルチインスタンス対応**: グローバル変数がないため複数のインスタンスが可能
4. **デバッグが容易**: `get_status()`で状態を確認できる
5. **保守性向上**: 排他制御のロジックが1箇所に集約

## 📝 実装手順

1. `exclusive_control.py`を作成
2. `service.py`でExclusiveControlManagerをインスタンス化
3. `scanner.py`をリファクタリング
4. `handler.py`をリファクタリング
5. テストを書き直し
6. 統合テストで動作確認

## ⚠️ 注意事項

- 後方互換性のため、グローバル変数を段階的に除去することも検討
- 実機テストで動作確認が必須
- パフォーマンスへの影響を測定


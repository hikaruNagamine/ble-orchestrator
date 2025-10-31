# ログメンテナンス機能の統合例

## 📝 概要

`log_utils.py`で作成したログメンテナンス機能を、BLE Orchestratorサービスに統合する方法を説明します。

---

## 🔧 統合方法

### 方法1: service.pyに統合（推奨）

`service.py`を以下のように修正して、定期的にログメンテナンスを実行します。

#### 変更箇所1: インポートの追加

```python
# service.py の先頭に追加
from .log_utils import LogDirectoryManager, LogMaintenanceScheduler
```

#### 変更箇所2: __init__メソッドにログマネージャーを追加

```python
class BLEOrchestratorService:
    def __init__(self):
        self._setup_logging()
        self._start_time = time.time()
        
        # ログメンテナンス機能を初期化（追加）
        self._log_manager = None
        self._log_scheduler = None
        if LOG_TO_FILE:
            self._log_manager = LogDirectoryManager(
                log_dir=LOG_DIR,
                max_total_size_mb=100.0,  # 100MBまで
                max_age_days=30,           # 30日以上古いファイルを削除
                enable_compression=True,   # 圧縮を有効化
                compression_age_days=7     # 7日以上古いファイルを圧縮
            )
            self._log_scheduler = LogMaintenanceScheduler(
                manager=self._log_manager,
                interval_hours=24.0  # 24時間ごとに実行
            )
            logger.info("Log maintenance enabled")
        
        # ... 以下、既存のコード
```

#### 変更箇所3: startメソッドにログメンテナンスタスクを追加

```python
async def start(self) -> None:
    """
    サービスを開始
    各コンポーネントを順次起動
    """
    logger.info("Starting BLE Orchestrator service...")
    
    try:
        # スキャナー起動
        await self.scanner.start()
        
        # キューマネージャー起動
        await self.queue_manager.start()
        
        # ウォッチドッグ起動
        await self.watchdog.start()
        
        # 通知マネージャー起動
        await self.notification_manager.start()
        
        # IPCサーバー起動
        await self.ipc_server.start()
        
        # ログメンテナンスタスクを開始（追加）
        if self._log_scheduler:
            asyncio.create_task(self._log_maintenance_loop())
            logger.info("Log maintenance task started")
        
        logger.info("All components started successfully")
        logger.info("BLE Orchestrator service is running")
        
    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        await self.stop()
        raise
```

#### 変更箇所4: ログメンテナンスループの追加

```python
async def _log_maintenance_loop(self) -> None:
    """
    定期的にログメンテナンスを実行するループ
    """
    logger.info("Log maintenance loop started")
    
    # 初回は起動から1時間後に実行
    await asyncio.sleep(3600)
    
    while True:
        try:
            # メンテナンスが必要かチェック
            result = self._log_scheduler.run_if_needed()
            
            if result:
                logger.info(
                    f"Log maintenance executed: "
                    f"compressed={result['compressed_files']}, "
                    f"deleted={result['deleted_by_age'] + result['deleted_by_size']}, "
                    f"freed={result['space_freed_mb']:.1f}MB"
                )
            
            # 1時間ごとにチェック
            await asyncio.sleep(3600)
            
        except asyncio.CancelledError:
            logger.info("Log maintenance loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in log maintenance loop: {e}", exc_info=True)
            # エラーが発生しても継続
            await asyncio.sleep(3600)
```

#### 変更箇所5: get_service_statusにログ情報を追加

```python
def _get_service_status(self) -> Dict[str, Any]:
    """
    サービスステータスを取得
    """
    uptime = time.time() - self._start_time
    
    status = ServiceStatus(
        is_running=True,
        adapter_status="ok" if self.handler.get_consecutive_failures() == 0 else "warning",
        queue_size=self.queue_manager.get_queue_size(),
        last_error=None,
        uptime_sec=uptime,
        active_subscriptions=self.notification_manager.get_active_subscriptions_count()
    )
    
    # 辞書形式に変換
    result = {
        "is_running": status.is_running,
        "adapter_status": status.adapter_status,
        "queue_size": status.queue_size,
        "last_error": status.last_error,
        "uptime_sec": round(status.uptime_sec, 1),
        "active_devices": len(self.scanner.cache.get_all_devices()),
        "active_subscriptions": status.active_subscriptions,
        "exclusive_control_enabled": self.handler.is_exclusive_control_enabled(),
        "client_connecting": self.scanner.is_client_connecting()
    }
    
    # ログ情報を追加（追加）
    if self._log_manager:
        log_status = self._log_manager.get_status()
        result["log_status"] = {
            "total_files": log_status["total_files"],
            "total_size_mb": round(log_status["total_size_mb"], 2),
            "usage_percent": round(log_status["usage_percent"], 1)
        }
    
    return result
```

---

### 方法2: 独立したメンテナンススクリプト（シンプル）

サービスに統合せず、cronで定期実行する方法：

#### 1. cronの設定

```bash
# crontabを編集
crontab -e

# 毎日午前3時に実行
0 3 * * * /home/nagamine/project/ble-orchestrator/scripts/cleanup_logs.sh /var/log/ble-orchestrator 100 30 >> /var/log/ble-orchestrator-cleanup.log 2>&1
```

#### 2. systemd timerの使用（より推奨）

`/etc/systemd/system/ble-orchestrator-log-cleanup.service`:
```ini
[Unit]
Description=BLE Orchestrator Log Cleanup
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/home/nagamine/project/ble-orchestrator/scripts/cleanup_logs.sh /var/log/ble-orchestrator 100 30
User=root
StandardOutput=journal
StandardError=journal
```

`/etc/systemd/system/ble-orchestrator-log-cleanup.timer`:
```ini
[Unit]
Description=BLE Orchestrator Log Cleanup Timer
Requires=ble-orchestrator-log-cleanup.service

[Timer]
OnCalendar=daily
OnCalendar=03:00
Persistent=true

[Install]
WantedBy=timers.target
```

有効化：
```bash
sudo systemctl daemon-reload
sudo systemctl enable ble-orchestrator-log-cleanup.timer
sudo systemctl start ble-orchestrator-log-cleanup.timer

# 確認
sudo systemctl list-timers
```

---

## 🧪 テスト方法

### 手動テスト

```python
# Pythonインタプリタで実行
from ble_orchestrator.orchestrator.log_utils import LogDirectoryManager

# マネージャーを作成
manager = LogDirectoryManager(
    log_dir="/var/log/ble-orchestrator",
    max_total_size_mb=50.0,
    max_age_days=7
)

# 現在の状態を確認
status = manager.get_status()
print(f"Total files: {status['total_files']}")
print(f"Total size: {status['total_size_mb']:.2f}MB")
print(f"Usage: {status['usage_percent']:.1f}%")

# メンテナンスを実行
result = manager.run_maintenance()
print(f"Compressed: {result['compressed_files']}")
print(f"Deleted: {result['deleted_by_age'] + result['deleted_by_size']}")
print(f"Space freed: {result['space_freed_mb']:.1f}MB")
```

### シェルスクリプトのテスト

```bash
# ドライラン（実際には削除しない）
bash -x /home/nagamine/project/ble-orchestrator/scripts/cleanup_logs.sh

# 実行
./scripts/cleanup_logs.sh /var/log/ble-orchestrator 50 7
```

---

## 📊 監視とアラート

### ログサイズの監視

Nagios/Icinga/Zabbixなどの監視ツールで使用できるスクリプト：

```bash
#!/bin/bash
# check_log_size.sh

LOG_DIR="/var/log/ble-orchestrator"
WARN_SIZE_MB=70
CRIT_SIZE_MB=90

CURRENT_SIZE=$(du -sm "$LOG_DIR" 2>/dev/null | cut -f1)

if [ -z "$CURRENT_SIZE" ]; then
    echo "OK: Log directory is empty or does not exist"
    exit 0
fi

if [ "$CURRENT_SIZE" -ge "$CRIT_SIZE_MB" ]; then
    echo "CRITICAL: Log size is ${CURRENT_SIZE}MB (>= ${CRIT_SIZE_MB}MB)"
    exit 2
elif [ "$CURRENT_SIZE" -ge "$WARN_SIZE_MB" ]; then
    echo "WARNING: Log size is ${CURRENT_SIZE}MB (>= ${WARN_SIZE_MB}MB)"
    exit 1
else
    echo "OK: Log size is ${CURRENT_SIZE}MB"
    exit 0
fi
```

### Prometheusメトリクスの公開

将来的な拡張として、メトリクスをPrometheusで監視：

```python
# metrics.py (将来的な拡張例)
from prometheus_client import Gauge

log_size_bytes = Gauge('ble_orchestrator_log_size_bytes', 'Total log directory size in bytes')
log_file_count = Gauge('ble_orchestrator_log_file_count', 'Total number of log files')

def update_log_metrics(log_manager):
    status = log_manager.get_status()
    log_size_bytes.set(status['total_size_mb'] * 1024 * 1024)
    log_file_count.set(status['total_files'])
```

---

## ⚙️ 設定のカスタマイズ

### config.pyに設定を追加

```python
# config.py に追加

# ログメンテナンス設定
LOG_MAINTENANCE_ENABLED = os.environ.get("BLE_ORCHESTRATOR_LOG_MAINTENANCE", "1") == "1"
LOG_MAX_TOTAL_SIZE_MB = float(os.environ.get("BLE_ORCHESTRATOR_LOG_MAX_TOTAL_SIZE", "100"))
LOG_MAX_AGE_DAYS = int(os.environ.get("BLE_ORCHESTRATOR_LOG_MAX_AGE_DAYS", "30"))
LOG_COMPRESSION_ENABLED = os.environ.get("BLE_ORCHESTRATOR_LOG_COMPRESSION", "1") == "1"
LOG_COMPRESSION_AGE_DAYS = int(os.environ.get("BLE_ORCHESTRATOR_LOG_COMPRESSION_AGE", "7"))
LOG_MAINTENANCE_INTERVAL_HOURS = float(os.environ.get("BLE_ORCHESTRATOR_LOG_MAINTENANCE_INTERVAL", "24"))
```

### 環境変数による制御

```bash
# systemd環境変数設定
Environment="BLE_ORCHESTRATOR_LOG_MAINTENANCE=1"
Environment="BLE_ORCHESTRATOR_LOG_MAX_TOTAL_SIZE=50"
Environment="BLE_ORCHESTRATOR_LOG_MAX_AGE_DAYS=14"
Environment="BLE_ORCHESTRATOR_LOG_COMPRESSION=1"
Environment="BLE_ORCHESTRATOR_LOG_COMPRESSION_AGE=3"
Environment="BLE_ORCHESTRATOR_LOG_MAINTENANCE_INTERVAL=12"
```

---

## 🔍 トラブルシューティング

### ログメンテナンスが実行されない

**確認項目:**
1. `LOG_MAINTENANCE_ENABLED`が有効か
2. ログディレクトリが存在するか
3. 権限が適切か

**デバッグ:**
```python
# サービス内でデバッグログを追加
logger.debug(f"Log maintenance enabled: {LOG_MAINTENANCE_ENABLED}")
logger.debug(f"Log directory: {LOG_DIR}")
logger.debug(f"Log scheduler: {self._log_scheduler}")
```

### ファイルの削除に失敗する

**原因:**
- 権限不足
- ファイルが使用中

**解決:**
```bash
# 権限確認
ls -la /var/log/ble-orchestrator/

# プロセスの確認
lsof /var/log/ble-orchestrator/ble_orchestrator.log
```

---

## 📈 パフォーマンスへの影響

### メンテナンス実行時の負荷

- CPU: ファイル圧縮時に一時的に上昇（通常1-2%）
- ディスクI/O: ファイル操作時に増加
- メモリ: 影響は最小限

### 推奨事項

- 負荷の低い時間帯（深夜）に実行
- interval_hoursを適切に設定（24時間推奨）
- 大量のファイルがある場合は分割実行を検討

---

## 💡 ベストプラクティス

1. **本番環境**: systemd timer + 圧縮有効
2. **開発環境**: サービス統合 + 短い保持期間
3. **テスト環境**: cronで毎週実行

4. **監視**: ログサイズを定期的に確認
5. **アラート**: 80%到達時に警告
6. **バックアップ**: 重要なログは別途保存

---

**関連ファイル:**
- `log_utils.py`: ログメンテナンス機能の実装
- `scripts/cleanup_logs.sh`: シェルスクリプト版
- `LOG_MANAGEMENT_GUIDE.md`: 詳細な管理ガイド


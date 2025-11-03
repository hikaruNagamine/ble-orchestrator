# ログ管理ガイド

## 📋 現在のログ設定

### 基本設定

| 項目 | デフォルト値 | 環境変数 |
|------|------------|---------|
| ログディレクトリ（開発） | `ble_orchestrator/logs/` | `BLE_ORCHESTRATOR_LOG_DIR` |
| ログディレクトリ（本番） | `/var/log/ble-orchestrator/` | `BLE_ORCHESTRATOR_LOG_DIR` |
| ログファイル名 | `ble_orchestrator.log` | - |
| ファイルサイズ上限 | 10MB | `BLE_ORCHESTRATOR_LOG_MAX_BYTES` |
| バックアップ世代数 | 5世代 | `BLE_ORCHESTRATOR_LOG_BACKUP_COUNT` |
| ファイル出力の有効/無効 | 有効 | `BLE_ORCHESTRATOR_LOG_TO_FILE` |
| ログレベル | INFO | `BLE_ORCHESTRATOR_LOG_LEVEL` |

### 現在のローテーション動作

```
ble_orchestrator.log         ← 現在のログ（10MBまで）
ble_orchestrator.log.1       ← 1世代前（10MB）
ble_orchestrator.log.2       ← 2世代前（10MB）
ble_orchestrator.log.3       ← 3世代前（10MB）
ble_orchestrator.log.4       ← 4世代前（10MB）
ble_orchestrator.log.5       ← 5世代前（10MB）
```

**合計最大サイズ: 約60MB**

---

## ✅ ログがたまらないようにする方法

### 方法1: 環境変数で設定を調整（推奨）

#### より少ないディスク容量で運用する

```bash
# ファイルサイズを5MBに、世代数を3に減らす
export BLE_ORCHESTRATOR_LOG_MAX_BYTES=5242880      # 5MB
export BLE_ORCHESTRATOR_LOG_BACKUP_COUNT=3         # 3世代
# 合計: 約20MB
```

#### ログレベルを上げて出力量を減らす

```bash
# WARNINGレベル以上のみログ出力（INFO/DEBUGを無効化）
export BLE_ORCHESTRATOR_LOG_LEVEL=WARNING
```

#### ファイル出力を無効化（コンソールのみ）

```bash
# systemdがログを管理する場合
export BLE_ORCHESTRATOR_LOG_TO_FILE=0
```

### 方法2: logrotateの設定（本番環境推奨）

systemdで運用する場合、logrotateを使用して古いログを自動削除・圧縮できます。

#### `/etc/logrotate.d/ble-orchestrator`を作成

```bash
/var/log/ble-orchestrator/*.log {
    daily                    # 毎日ローテーション
    rotate 7                 # 7日分保持
    compress                 # gzip圧縮
    delaycompress           # 最新のバックアップは圧縮しない
    missingok               # ファイルがなくてもエラーにしない
    notifempty              # 空ファイルはローテーションしない
    create 0644 root root   # 新規ファイルのパーミッション
    sharedscripts
    postrotate
        # サービスにログ再オープンを通知（必要に応じて）
        systemctl reload ble-orchestrator >/dev/null 2>&1 || true
    endscript
}
```

#### 設定例の比較

| 設定 | ディスク使用量 | 保持期間 | 推奨環境 |
|------|--------------|---------|---------|
| デフォルト | 60MB | 無制限 | 開発 |
| 軽量設定 | 20MB | 無制限 | 小規模 |
| logrotate（日次） | 15MB（圧縮後） | 7日 | 本番 |
| logrotate（週次） | 40MB（圧縮後） | 4週 | 本番 |

### 方法3: cronでの定期クリーンアップ

logrotateを使用しない場合、cronで古いログファイルを削除できます。

```bash
# crontabを編集
crontab -e

# 30日以上古いログファイルを毎日深夜2時に削除
0 2 * * * find /var/log/ble-orchestrator/ -name "*.log.*" -mtime +30 -delete

# または、合計サイズが100MBを超えたら古いファイルから削除
0 2 * * * /path/to/cleanup-logs.sh
```

`cleanup-logs.sh`の例：

```bash
#!/bin/bash

LOG_DIR="/var/log/ble-orchestrator"
MAX_SIZE_MB=100
CURRENT_SIZE=$(du -sm "$LOG_DIR" | cut -f1)

if [ "$CURRENT_SIZE" -gt "$MAX_SIZE_MB" ]; then
    echo "Log directory size ($CURRENT_SIZE MB) exceeds limit ($MAX_SIZE_MB MB)"
    # 最も古いバックアップファイルから削除
    find "$LOG_DIR" -name "*.log.*" -type f -printf '%T+ %p\n' | sort | head -n 5 | cut -d' ' -f2- | xargs rm -f
    echo "Cleaned up old log files"
fi
```

---

## 🔧 推奨設定

### 開発環境

```bash
# .env または ~/.bashrc に追加
export BLE_ORCHESTRATOR_LOG_LEVEL=DEBUG
export BLE_ORCHESTRATOR_LOG_MAX_BYTES=5242880    # 5MB
export BLE_ORCHESTRATOR_LOG_BACKUP_COUNT=3       # 3世代
```

### 本番環境（systemd運用）

#### オプション1: Pythonのログローテーション + logrotate

```bash
# systemd環境変数設定
# /etc/systemd/system/ble-orchestrator.service に追加
[Service]
Environment="BLE_ORCHESTRATOR_LOG_LEVEL=INFO"
Environment="BLE_ORCHESTRATOR_LOG_MAX_BYTES=10485760"
Environment="BLE_ORCHESTRATOR_LOG_BACKUP_COUNT=5"
```

`/etc/logrotate.d/ble-orchestrator`:
```
/var/log/ble-orchestrator/*.log* {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
}
```

#### オプション2: journaldに統合（最小ディスク使用）

```bash
# systemd環境変数設定
Environment="BLE_ORCHESTRATOR_LOG_TO_FILE=0"  # ファイル出力無効

# journaldの設定を確認
journalctl -u ble-orchestrator -f

# journaldのログサイズ制限
# /etc/systemd/journald.conf
SystemMaxUse=100M
MaxRetentionSec=7day
```

---

## 📊 ログサイズの監視

### 手動確認

```bash
# ログディレクトリのサイズ確認
du -sh /var/log/ble-orchestrator/

# ファイル別サイズ確認
ls -lh /var/log/ble-orchestrator/

# ログファイル数の確認
ls -1 /var/log/ble-orchestrator/ | wc -l
```

### 自動監視スクリプト

```bash
#!/bin/bash
# check-log-size.sh

LOG_DIR="/var/log/ble-orchestrator"
WARN_SIZE_MB=50
CRIT_SIZE_MB=100

CURRENT_SIZE=$(du -sm "$LOG_DIR" 2>/dev/null | cut -f1)

if [ -z "$CURRENT_SIZE" ]; then
    echo "OK: Log directory does not exist or is empty"
    exit 0
fi

if [ "$CURRENT_SIZE" -ge "$CRIT_SIZE_MB" ]; then
    echo "CRITICAL: Log directory size is ${CURRENT_SIZE}MB (>= ${CRIT_SIZE_MB}MB)"
    exit 2
elif [ "$CURRENT_SIZE" -ge "$WARN_SIZE_MB" ]; then
    echo "WARNING: Log directory size is ${CURRENT_SIZE}MB (>= ${WARN_SIZE_MB}MB)"
    exit 1
else
    echo "OK: Log directory size is ${CURRENT_SIZE}MB"
    exit 0
fi
```

---

## 🛠️ トラブルシューティング

### ログファイルが作成されない

**原因:**
1. ログディレクトリのパーミッション不足
2. 環境変数で無効化されている

**解決策:**
```bash
# ディレクトリの作成と権限設定
sudo mkdir -p /var/log/ble-orchestrator
sudo chown $USER:$USER /var/log/ble-orchestrator
sudo chmod 755 /var/log/ble-orchestrator

# 設定確認
echo $BLE_ORCHESTRATOR_LOG_TO_FILE  # 1または未設定であること
```

### ログがローテーションされない

**原因:**
1. ファイルサイズが上限に達していない
2. `RotatingFileHandler`が正しく動作していない

**確認方法:**
```python
# テスト用に大量のログを出力
import logging
logger = logging.getLogger()
for i in range(1000000):
    logger.info(f"Test log message {i}")
```

### ディスク容量が逼迫している

**緊急対応:**
```bash
# 古いログファイルを手動削除
cd /var/log/ble-orchestrator
ls -lt  # 日付順に表示
rm ble_orchestrator.log.5
rm ble_orchestrator.log.4

# または圧縮
gzip ble_orchestrator.log.*
```

**恒久対策:**
- より小さい設定に変更
- logrotateの導入
- 定期クリーンアップスクリプトの設定

---

## 📝 設定変更の手順

### 1. 環境変数による設定変更

#### systemd環境での変更

```bash
# サービスファイルを編集
sudo vim /etc/systemd/system/ble-orchestrator.service

# [Service] セクションに追加
[Service]
Environment="BLE_ORCHESTRATOR_LOG_MAX_BYTES=5242880"
Environment="BLE_ORCHESTRATOR_LOG_BACKUP_COUNT=3"

# 変更を反映
sudo systemctl daemon-reload
sudo systemctl restart ble-orchestrator

# 確認
sudo systemctl status ble-orchestrator
```

#### 手動実行の場合

```bash
# 環境変数を設定してから起動
export BLE_ORCHESTRATOR_LOG_MAX_BYTES=5242880
export BLE_ORCHESTRATOR_LOG_BACKUP_COUNT=3
python -m ble_orchestrator
```

### 2. logrotateの設定

```bash
# 設定ファイルを作成
sudo vim /etc/logrotate.d/ble-orchestrator

# 文法チェック
sudo logrotate -d /etc/logrotate.d/ble-orchestrator

# 手動実行（テスト）
sudo logrotate -f /etc/logrotate.d/ble-orchestrator

# 自動実行の確認（通常は毎日実行される）
cat /etc/cron.daily/logrotate
```

---

## 💡 ベストプラクティス

### 開発環境
- ファイルサイズ: 5MB
- 世代数: 2-3
- ログレベル: DEBUG
- 手動クリーンアップ

### ステージング環境
- ファイルサイズ: 10MB
- 世代数: 3-5
- ログレベル: INFO
- logrotate週次実行

### 本番環境
- **推奨1**: journaldに統合（`LOG_TO_FILE=0`）
- **推奨2**: logrotate日次実行 + 圧縮
- ファイルサイズ: 10MB
- 世代数: 5
- ログレベル: INFO または WARNING
- 監視アラート設定

---

## 📈 ログ分析のヒント

### 重要なログメッセージを見つける

```bash
# エラーのみ抽出
grep "ERROR" /var/log/ble-orchestrator/ble_orchestrator.log

# 特定デバイスのログ
grep "AA:BB:CC:DD:EE:FF" /var/log/ble-orchestrator/ble_orchestrator.log

# 接続エラーの統計
grep "Failed to connect" /var/log/ble-orchestrator/ble_orchestrator.log | wc -l

# 最新の警告
tail -n 100 /var/log/ble-orchestrator/ble_orchestrator.log | grep "WARNING"
```

### ログサイズの時系列分析

```bash
# 1時間ごとのログ出力量
grep "$(date +%Y-%m-%d\ %H)" /var/log/ble-orchestrator/ble_orchestrator.log | wc -l

# 日別ログサイズ
for i in {1..7}; do
    date -d "$i days ago" +%Y-%m-%d
    journalctl -u ble-orchestrator --since "$i days ago" --until "$(($i-1)) days ago" | wc -l
done
```

---

## 🔒 セキュリティとプライバシー

### ログファイルのパーミッション

```bash
# 推奨設定
chmod 644 /var/log/ble-orchestrator/ble_orchestrator.log
chown root:root /var/log/ble-orchestrator/ble_orchestrator.log

# より厳格な設定（読み取りを制限）
chmod 640 /var/log/ble-orchestrator/ble_orchestrator.log
chown root:adm /var/log/ble-orchestrator/ble_orchestrator.log
```

### 機密情報の除外

ログに機密情報が含まれないよう注意：
- MACアドレスは含まれる（必要に応じて難読化を検討）
- パスワードやトークンは含めない
- 個人識別情報（PII）に注意

---

## 📞 よくある質問

### Q: ログが急に増えた場合の対処法は？

**A:** 以下を確認：
1. ログレベルがDEBUGになっていないか
2. スキャナーのエラーループが発生していないか
3. 一時的にログレベルをWARNINGに変更

```bash
export BLE_ORCHESTRATOR_LOG_LEVEL=WARNING
sudo systemctl restart ble-orchestrator
```

### Q: 古いログを完全に削除したい

**A:**
```bash
# すべてのログファイルを削除（注意！）
sudo rm -f /var/log/ble-orchestrator/ble_orchestrator.log*

# サービスを再起動して新しいログファイルを作成
sudo systemctl restart ble-orchestrator
```

### Q: ログをリアルタイムで監視したい

**A:**
```bash
# ファイル出力を有効にしている場合
tail -f /var/log/ble-orchestrator/ble_orchestrator.log

# journaldに出力している場合
journalctl -u ble-orchestrator -f

# 特定のレベルのみ
journalctl -u ble-orchestrator -f -p warning
```

---


**最終更新**: 2025-10-24  
**関連ドキュメント**: `REVIEW_SUMMARY.md`, `config.py`

---

## ⚠️ 緊急対応: 巨大なログファイル（例: 1.8GB）がある場合の安全な対処

起動時に巨大なログファイルが残っているとディスクを圧迫します。サービスを止められるかどうかで対応を選んでください。

1) サービスを止せない、または即時ディスクを開放したい場合（プロセスを停止せずに空にする）

```bash
# ファイルを空にしてディスクを開放（sudoが必要な場合あり）
sudo truncate -s 0 /var/speedbeesynapse/projects/project1/dynlibs/pyvenv/lib/python3.11/site-packages/ble_orchestrator/logs/ble_orchestrator.log
# もしくは
sudo sh -c '> /var/speedbeesynapse/projects/project1/dynlibs/pyvenv/lib/python3.11/site-packages/ble_orchestrator/logs/ble_orchestrator.log'
```

注意: truncate はファイルを空にしますが、直近のログ内容を保存したい場合は次の「サービス停止」手順を使用してください。

2) サービスを停止してログを保存・圧縮したい場合（推奨）

```bash
# systemd の例
sudo systemctl stop ble-orchestrator.service

# ログを移動して圧縮
sudo mv /var/speedbeesynapse/projects/project1/dynlibs/pyvenv/lib/python3.11/site-packages/ble_orchestrator/logs/ble_orchestrator.log /tmp/ble_orchestrator.log
sudo gzip /tmp/ble_orchestrator.log   # -> /tmp/ble_orchestrator.log.gz

# サービスを再起動して新しいログを作らせる
sudo systemctl start ble-orchestrator.service
```

3) どのプロセスがファイルを開いているか確認する

```bash
sudo lsof /var/speedbeesynapse/projects/project1/dynlibs/pyvenv/lib/python3.11/site-packages/ble_orchestrator/logs/ble_orchestrator.log
```

上記で PID がわかれば、そのプロセスを停止/再起動してログを切り替えられます。

---

## 🧾 リポジトリ内の logrotate 設定例

リポジトリの `systemd/ble-orchestrator.logrotate` に運用例を追加しています。実運用では `/etc/logrotate.d/ble-orchestrator` として配置してください。

基本例（`/etc/logrotate.d/ble-orchestrator` に配置）:

```text
/var/log/ble-orchestrator/*.log {
        daily
        rotate 14
        compress
        delaycompress
        missingok
        notifempty
        create 0640 root root
        sharedscripts
        postrotate
                # ログファイルを再オープンする方法。サービスに応じて reload / restart を選択
                systemctl restart ble-orchestrator.service >/dev/null 2>&1 || true
        endscript
}
```

---

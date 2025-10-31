# ログ処理のレビューサマリー

## ✅ 現在の実装状況

### 既に実装されている機能

BLE Orchestratorには**既にログローテーション機能が実装されています**：

```python
# service.py
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,      # デフォルト: 10MB
    backupCount=LOG_BACKUP_COUNT, # デフォルト: 5世代
    encoding="utf-8"
)
```

**現在の動作:**
- ログファイルが10MBに達すると自動的にローテーション
- 最大6ファイル（現在+バックアップ5世代）を保持
- 合計最大約60MBのディスク使用量

### 環境変数による制御

| 環境変数 | デフォルト | 説明 |
|---------|----------|------|
| `BLE_ORCHESTRATOR_LOG_MAX_BYTES` | 10485760 (10MB) | ファイルサイズ上限 |
| `BLE_ORCHESTRATOR_LOG_BACKUP_COUNT` | 5 | バックアップ世代数 |
| `BLE_ORCHESTRATOR_LOG_TO_FILE` | 1 (有効) | ファイル出力の有効/無効 |
| `BLE_ORCHESTRATOR_LOG_LEVEL` | INFO | ログレベル |

---

## 📝 作成したドキュメントとツール

### 1. LOG_MANAGEMENT_GUIDE.md
**内容:**
- 現在のログ設定の詳細説明
- ログがたまらないようにする具体的な方法
- 環境変数による設定調整
- logrotateの設定例
- cronによる定期クリーンアップ
- トラブルシューティング
- ベストプラクティス

**すぐに使える設定例:**
```bash
# より少ないディスク容量で運用
export BLE_ORCHESTRATOR_LOG_MAX_BYTES=5242880    # 5MB
export BLE_ORCHESTRATOR_LOG_BACKUP_COUNT=3       # 3世代
# 合計: 約20MB
```

### 2. log_utils.py
**内容:**
Pythonによる高度なログ管理機能：

- `LogDirectoryManager`: ログディレクトリの包括的な管理
  - 古いログファイルの自動削除
  - サイズ制限による削除
  - gzip圧縮
  - ステータス取得

- `LogMaintenanceScheduler`: 定期メンテナンスのスケジューラー
  - 指定間隔でメンテナンスを実行
  - 自動的に必要性を判断

**使用例:**
```python
manager = LogDirectoryManager(
    log_dir="/var/log/ble-orchestrator",
    max_total_size_mb=100.0,    # 100MB上限
    max_age_days=30,             # 30日で削除
    enable_compression=True,     # 圧縮有効
    compression_age_days=7       # 7日後に圧縮
)

# メンテナンス実行
result = manager.run_maintenance()
```

### 3. scripts/cleanup_logs.sh
**内容:**
シェルスクリプトによるログクリーンアップ：

- 古いログファイルの削除
- サイズ制限による削除
- 自動圧縮
- 実行結果のレポート

**使用方法:**
```bash
# 手動実行
./scripts/cleanup_logs.sh /var/log/ble-orchestrator 100 30

# cronで自動実行（毎日午前3時）
0 3 * * * /path/to/cleanup_logs.sh /var/log/ble-orchestrator 100 30
```

### 4. LOG_INTEGRATION_EXAMPLE.md
**内容:**
ログメンテナンス機能をサービスに統合する方法：

- service.pyへの統合手順
- コード例（そのまま使える）
- systemd timerの設定例
- テスト方法
- 監視とアラート

---

## 🎯 推奨される対応

### 短期的な対応（今すぐ実施可能）

#### オプション1: 環境変数で設定を調整（最も簡単）

```bash
# systemd環境の場合
sudo vim /etc/systemd/system/ble-orchestrator.service

# [Service]セクションに追加
Environment="BLE_ORCHESTRATOR_LOG_MAX_BYTES=5242880"
Environment="BLE_ORCHESTRATOR_LOG_BACKUP_COUNT=3"

sudo systemctl daemon-reload
sudo systemctl restart ble-orchestrator
```

**結果**: 合計約20MBに削減

#### オプション2: ログレベルを上げる

```bash
# INFO/DEBUGを減らしてWARNING以上のみ
Environment="BLE_ORCHESTRATOR_LOG_LEVEL=WARNING"
```

**結果**: ログ出力量が大幅に削減

#### オプション3: cronでクリーンアップ

```bash
# crontabを編集
crontab -e

# 毎週日曜日午前2時に実行
0 2 * * 0 /home/nagamine/project/ble-orchestrator/scripts/cleanup_logs.sh /var/log/ble-orchestrator 50 14
```

**結果**: 自動的に古いログを削除

### 中期的な対応（本番運用時）

#### logrotateの導入（推奨）

`/etc/logrotate.d/ble-orchestrator`:
```
/var/log/ble-orchestrator/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 root root
}
```

**結果**: 
- 自動的に毎日ローテーション
- gzip圧縮で容量削減（約70%削減）
- 7日分のみ保持

### 長期的な対応（将来の改善）

#### log_utils.pyの統合

`service.py`にログメンテナンス機能を統合：
- 自動的な古いファイル削除
- 自動圧縮
- サイズ監視

詳細は`LOG_INTEGRATION_EXAMPLE.md`を参照

---

## 📊 設定の比較

| 設定 | ディスク使用量 | 保持期間 | 設定の複雑さ | 推奨環境 |
|------|--------------|---------|------------|---------|
| **現在のデフォルト** | 60MB | 無制限 | 簡単 | 開発 |
| **環境変数調整** | 20MB | 無制限 | 簡単 | 小規模本番 |
| **cronクリーンアップ** | 50MB | 14-30日 | 中 | 本番 |
| **logrotate** | 15MB（圧縮） | 7日 | 中 | 本番（推奨） |
| **log_utils統合** | 100MB | カスタマイズ可 | 高 | 大規模本番 |
| **journaldのみ** | systemd管理 | systemd設定次第 | 低 | コンテナ/クラウド |

---

## 🚀 今すぐ実施できること

### ステップ1: 現在のログサイズを確認

```bash
# ログディレクトリのサイズ確認
du -sh /home/nagamine/project/ble-orchestrator/ble_orchestrator/logs/
# または
du -sh /var/log/ble-orchestrator/
```

### ステップ2: ログファイルを確認

```bash
# ファイル一覧と日時
ls -lh /home/nagamine/project/ble-orchestrator/ble_orchestrator/logs/
```

### ステップ3: 必要に応じて設定変更

#### 開発環境の場合

```bash
# .bashrc または .zshrc に追加
export BLE_ORCHESTRATOR_LOG_MAX_BYTES=5242880
export BLE_ORCHESTRATOR_LOG_BACKUP_COUNT=2
export BLE_ORCHESTRATOR_LOG_LEVEL=INFO
```

#### 本番環境の場合

オプションA: logrotateを設定（推奨）
```bash
sudo cp /home/nagamine/project/ble-orchestrator/docs/logrotate.conf /etc/logrotate.d/ble-orchestrator
```

オプションB: cronスクリプトを設定
```bash
crontab -e
# 以下を追加
0 3 * * * /home/nagamine/project/ble-orchestrator/scripts/cleanup_logs.sh /var/log/ble-orchestrator 100 30
```

---

## 💡 重要なポイント

### ✅ 安心してください

1. **既にローテーション機能は実装済み**
   - ログファイルが10MBを超えると自動的にローテーション
   - 最大6ファイル（60MB）までしか使用しない

2. **無限にたまることはない**
   - `RotatingFileHandler`が古いファイルを自動削除
   - バックアップ数を超えるファイルは上書きされる

3. **簡単に調整可能**
   - 環境変数で設定を変更するだけ
   - サービスの再起動で反映

### ⚠️ 注意点

1. **手動で削除したファイルは除外される**
   - RotatingHandlerが管理するのは自動生成されたファイルのみ

2. **設定変更で残ったファイル**
   - 世代数を減らした場合、古いバックアップは残る
   - 手動削除またはクリーンアップスクリプトで対応

3. **複数インスタンス実行**
   - 同じログディレクトリを複数プロセスで使用する場合は注意
   - 通常は1インスタンスのみなので問題なし

---

## 📞 次のアクション

### 最小限の対応（5分）

```bash
# 現在のログサイズを確認
du -sh /var/log/ble-orchestrator/ 2>/dev/null || \
du -sh /home/nagamine/project/ble-orchestrator/ble_orchestrator/logs/

# 問題がなければ何もしなくてOK
# 気になる場合は環境変数で調整
```

### 推奨される対応（30分）

1. `LOG_MANAGEMENT_GUIDE.md`を読む
2. 環境に合わせた設定を選択
3. 環境変数を設定してサービスを再起動

### 本番運用での対応（1-2時間）

1. `LOG_MANAGEMENT_GUIDE.md`を熟読
2. logrotateを設定
3. cronまたはsystemd timerでクリーンアップ自動化
4. 監視設定（オプション）

---

## 📚 参考ドキュメント

作成したドキュメント：
1. **LOG_MANAGEMENT_GUIDE.md** - 詳細なログ管理ガイド
2. **LOG_INTEGRATION_EXAMPLE.md** - サービス統合の例
3. **log_utils.py** - 高度なログ管理ツール
4. **scripts/cleanup_logs.sh** - クリーンアップスクリプト

---

## ✨ まとめ

### 現状
- ✅ ログローテーション機能は既に実装済み
- ✅ 無限にログがたまることはない
- ✅ 最大60MB程度で自動的に管理される

### 改善可能な点
- 🔧 環境変数で容量をさらに削減可能
- 🔧 logrotateで圧縮・自動削除を追加可能
- 🔧 高度な管理機能（log_utils.py）の統合可能

### 推奨アクション
1. **今すぐ**: 現在のログサイズを確認
2. **必要に応じて**: 環境変数で調整
3. **本番運用時**: logrotate導入

---

**レビュー日**: 2025-10-24  
**レビュアー**: AI Code Reviewer


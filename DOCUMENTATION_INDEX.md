# BLE Orchestrator ドキュメント一覧

## 📚 利用可能なドキュメント

このリポジトリには、以下のドキュメントが含まれています。目的に応じて適切なドキュメントをご参照ください。

---

## 🚀 はじめに

### 1. [README.md](README.md)
**対象**: すべてのユーザー  
**内容**:
- プロジェクトの概要
- 背景と目的
- システム構成図
- インストール手順
- 基本的な使い方

**こんなときに**:
- 初めてBLE Orchestratorを使う
- プロジェクトの全体像を知りたい

---

### 2. [QUICK_START.md](QUICK_START.md) ⭐ 初心者向け
**対象**: 初めて使うユーザー  
**内容**:
- インストール手順
- 基本的な使い方
- 実用的なサンプルコード
- トラブルシューティング
- よく使うコマンド集

**こんなときに**:
- すぐに動かしてみたい
- 実際のコード例が見たい
- エラーが出たときの対処法を知りたい

---

## 📖 詳細仕様

### 3. [SPECIFICATION.md](SPECIFICATION.md) ⭐ 開発者必読
**対象**: 開発者、システム管理者  
**内容**:
- システムアーキテクチャ
- 各コンポーネントの詳細仕様
- API仕様（全コマンド）
- データ型定義
- 通信プロトコル
- 設定項目一覧
- エラー処理
- 排他制御メカニズム

**こんなときに**:
- システムの内部動作を理解したい
- APIの詳細を知りたい
- 独自のクライアントを開発したい
- 設定をカスタマイズしたい

---

## 🔍 コードレビューと改善提案

### 4. [REVIEW_SUMMARY.md](REVIEW_SUMMARY.md)
**対象**: 開発者、メンテナー  
**内容**:
- コードレビューの総合評価
- 良い点と改善点
- 優先順位付き改善提案
- アクションアイテム
- 推奨ツールとライブラリ

**こんなときに**:
- コードの品質を確認したい
- 改善すべき点を知りたい
- リファクタリング計画を立てたい

---

### 5. [REFACTORING_PROPOSAL.md](REFACTORING_PROPOSAL.md)
**対象**: 上級開発者  
**内容**:
- グローバル変数の問題点
- `ExclusiveControlManager`クラスの提案
- 詳細な実装例
- リファクタリング手順

**こんなときに**:
- グローバル変数を除去したい
- より保守性の高いコードにしたい
- テスト可能な設計にしたい

---

### 6. [QUICK_FIXES.md](QUICK_FIXES.md)
**対象**: 開発者  
**内容**:
- すぐに実施可能な改善項目
- チェックリスト形式
- 具体的なコマンド
- 進捗トラッキング

**こんなときに**:
- 簡単な改善から始めたい
- 何から手をつけるべきか知りたい
- 開発環境のセットアップをしたい

---

## 📝 ログ管理

### 7. [LOG_REVIEW_SUMMARY.md](LOG_REVIEW_SUMMARY.md) ⭐ ログ管理の要約
**対象**: システム管理者、開発者  
**内容**:
- 現在のログ設定の確認
- ログがたまらないようにする方法
- 推奨される設定
- すぐに実施できる対応

**こんなときに**:
- ログ管理の全体像を知りたい
- ログがたまらないか心配
- 設定を調整したい

---

### 8. [LOG_MANAGEMENT_GUIDE.md](LOG_MANAGEMENT_GUIDE.md)
**対象**: システム管理者  
**内容**:
- 現在のログ設定の詳細
- 環境変数による調整方法
- logrotateの設定例
- cronによる自動クリーンアップ
- トラブルシューティング

**こんなときに**:
- 詳細なログ管理方法を知りたい
- 本番環境の設定を最適化したい
- ログサイズを監視したい

---

### 9. [LOG_INTEGRATION_EXAMPLE.md](LOG_INTEGRATION_EXAMPLE.md)
**対象**: 上級開発者  
**内容**:
- `log_utils.py`の統合方法
- サービスへの組み込み手順
- systemd timerの設定
- テスト方法

**こんなときに**:
- 高度なログ管理機能を追加したい
- 自動メンテナンス機能を実装したい

---

## 🛠️ テストとサンプル

### 10. tests/ ディレクトリ
**対象**: 開発者  
**内容**:
- ユニットテスト
- 統合テスト
- テストスクリプト

**主要なテストファイル**:
- `test_service_improved.py` - 改善されたサービステスト
- `test_handler.py` - ハンドラーのテスト
- `test_scanner.py` - スキャナーのテスト
- `test_queue_manager.py` - キューマネージャーのテスト

---

### 11. examples/ ディレクトリ
**対象**: すべてのユーザー  
**内容**:
- 実装例
- サンプルスクリプト

**こんなときに**:
- 実際の使用例を見たい
- サンプルコードを参考にしたい

---

## 🔧 ツールとスクリプト

### 12. scripts/ ディレクトリ
**対象**: システム管理者  
**内容**:
- `cleanup_logs.sh` - ログクリーンアップスクリプト
- その他のユーティリティスクリプト

---

## 📦 パッケージング

### 13. [PACKAGING.md](PACKAGING.md)
**対象**: 開発者、配布担当者  
**内容**:
- パッケージングの詳細
- インストール方法の詳細
- トラブルシューティング

---

## 🎯 目的別ドキュメントガイド

### 初めて使う場合
1. [README.md](README.md) - 概要を理解
2. [QUICK_START.md](QUICK_START.md) - 実際に動かしてみる

### 開発する場合
1. [SPECIFICATION.md](SPECIFICATION.md) - 仕様を理解
2. [QUICK_START.md](QUICK_START.md) - サンプルコードを参照
3. [REVIEW_SUMMARY.md](REVIEW_SUMMARY.md) - コード品質を確認

### 本番環境に導入する場合
1. [README.md](README.md) - インストール方法
2. [LOG_MANAGEMENT_GUIDE.md](LOG_MANAGEMENT_GUIDE.md) - ログ設定
3. [SPECIFICATION.md](SPECIFICATION.md) - 設定項目を確認

### コードを改善する場合
1. [REVIEW_SUMMARY.md](REVIEW_SUMMARY.md) - 改善点を確認
2. [QUICK_FIXES.md](QUICK_FIXES.md) - 簡単な修正から開始
3. [REFACTORING_PROPOSAL.md](REFACTORING_PROPOSAL.md) - 大規模な改善計画

### トラブルシューティング
1. [QUICK_START.md](QUICK_START.md) - よくある問題と解決策
2. [LOG_MANAGEMENT_GUIDE.md](LOG_MANAGEMENT_GUIDE.md) - ログの確認方法
3. [SPECIFICATION.md](SPECIFICATION.md) - エラー処理の仕様

---

## 📊 ドキュメントの関係図

```
README.md (出発点)
    ├─ QUICK_START.md (すぐ動かす)
    │   └─ examples/ (サンプルコード)
    │
    ├─ SPECIFICATION.md (詳細仕様)
    │   ├─ API仕様
    │   ├─ 設定項目
    │   └─ エラー処理
    │
    ├─ ログ管理
    │   ├─ LOG_REVIEW_SUMMARY.md (要約)
    │   ├─ LOG_MANAGEMENT_GUIDE.md (詳細)
    │   └─ LOG_INTEGRATION_EXAMPLE.md (統合)
    │
    └─ コード改善
        ├─ REVIEW_SUMMARY.md (レビュー)
        ├─ QUICK_FIXES.md (簡単な修正)
        └─ REFACTORING_PROPOSAL.md (大規模改善)
```

---

## 💡 推奨される読む順序

### 🌟 初心者向け
1. **README.md** - 5分
2. **QUICK_START.md** - 20分
3. **LOG_REVIEW_SUMMARY.md** - 5分

### 🔧 開発者向け
1. **README.md** - 5分
2. **QUICK_START.md** - 20分
3. **SPECIFICATION.md** - 60分
4. **REVIEW_SUMMARY.md** - 30分

### 🚀 システム管理者向け
1. **README.md** - 5分
2. **QUICK_START.md** - 20分
3. **LOG_MANAGEMENT_GUIDE.md** - 30分
4. **SPECIFICATION.md** の設定項目 - 20分

---

## 🔄 ドキュメントの更新履歴

| ドキュメント | 最終更新 | バージョン |
|------------|---------|-----------|
| README.md | - | - |
| QUICK_START.md | 2025-10-24 | 1.0 |
| SPECIFICATION.md | 2025-10-24 | 1.0 |
| REVIEW_SUMMARY.md | 2025-10-24 | 1.0 |
| LOG_REVIEW_SUMMARY.md | 2025-10-24 | 1.0 |
| LOG_MANAGEMENT_GUIDE.md | 2025-10-24 | 1.0 |
| REFACTORING_PROPOSAL.md | 2025-10-24 | 1.0 |
| QUICK_FIXES.md | 2025-10-24 | 1.0 |

---

## 📞 サポート

ドキュメントに関する質問や改善提案は、Issueで報告してください。

---

**ドキュメント一覧の最終更新**: 2025-10-24


# クイックフィックス チェックリスト

このドキュメントは、今すぐ実施できる簡単な修正項目のリストです。

## ✅ すぐに実施可能な改善（30分以内）

### 1. デバッグログの整理
- [x] `handler.py`のデバッグ記号（`&&&&&&&&&`）を削除 ✓
- [ ] `scanner.py`のログメッセージを整理
- [ ] `queue_manager.py`のログメッセージを整理

### 2. docstringの追加
- [x] `BLEScanner.__init__`にdocstringを追加 ✓
- [x] `BLERequestHandler.handle_request`を改善 ✓
- [ ] `BLEWatchdog.__init__`にdocstringを追加
- [ ] `IPCServer.__init__`にdocstringを追加

### 3. 開発ツールの設定
- [x] `.pre-commit-config.yaml`を作成 ✓
- [ ] pre-commitフックをインストール: `pre-commit install`
- [ ] 初回実行: `pre-commit run --all-files`

### 4. テストコードの即座の修正
- [ ] `test_service.py`の`_is_running`を削除または修正
- [ ] `test_handler.py`のモック設定を実装に合わせる

---

## ⚡ 1時間以内で実施可能な改善

### 5. 型ヒントの追加
以下のファイルに型ヒントを追加：

```python
# handler.py
from typing import Optional, Callable, Union
from bleak.backends.device import BLEDevice

def __init__(
    self, 
    get_device_func: Callable[[str], Optional[Union[BLEDevice, str]]],
    get_scan_data_func: Optional[Callable[[str], Optional[ScanResult]]] = None,
    scanner: Optional['BLEScanner'] = None,
    notify_watchdog_func: Optional[Callable[[], None]] = None
):
```

ファイル別チェックリスト：
- [ ] `handler.py`
- [ ] `scanner.py`
- [ ] `queue_manager.py`
- [ ] `watchdog.py`
- [ ] `ipc_server.py`

### 6. 定数の移動
以下の定数を`config.py`に移動：

```python
# scanner.pyから移動
MIN_SCANNER_RECREATE_INTERVAL = 180
NO_DEVICES_THRESHOLD = 90
CLIENT_COMPLETION_TIMEOUT = 60.0
SCANNER_START_TIMEOUT = 10.0
SCANNER_STOP_TIMEOUT = 10.0
```

- [ ] `scanner.py`の定数を`config.py`に移動
- [ ] `handler.py`の定数を確認
- [ ] インポートを更新

---

## 📦 半日で実施可能な改善

### 7. 静的解析ツールの導入と初回実行

```bash
# インストール
pip install ruff mypy black isort pytest-cov

# pyproject.tomlに設定を追加（既にある場合は確認）
# 実行
black ble_orchestrator/
isort ble_orchestrator/
ruff check ble_orchestrator/ --fix
mypy ble_orchestrator/
```

チェックリスト：
- [ ] ツールのインストール
- [ ] blackでフォーマット
- [ ] isortでインポート整理
- [ ] ruffで問題点チェック
- [ ] mypyで型チェック
- [ ] 検出された問題を修正

### 8. カバレッジ測定

```bash
# テスト実行とカバレッジ測定
pytest --cov=ble_orchestrator --cov-report=html --cov-report=term

# HTMLレポートを確認
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

- [ ] pytest-covをインストール
- [ ] カバレッジを測定
- [ ] カバレッジ30%未満のモジュールをリストアップ
- [ ] 優先順位を決定

---

## 🔧 具体的な修正コマンド

### セットアップコマンド

```bash
# 開発環境のセットアップ
cd /home/nagamine/project/ble-orchestrator

# 仮想環境をアクティベート（既存の場合）
source venv/bin/activate

# または新規作成
python3 -m venv venv
source venv/bin/activate

# 開発用パッケージのインストール
pip install -e ".[dev]"

# または個別にインストール
pip install pytest pytest-asyncio pytest-cov black isort ruff mypy

# pre-commitのインストール
pip install pre-commit
pre-commit install

# 初回実行
pre-commit run --all-files
```

### コードフォーマット

```bash
# すべてのコードをフォーマット
black ble_orchestrator/
isort ble_orchestrator/

# 特定のファイルのみ
black ble_orchestrator/orchestrator/handler.py
isort ble_orchestrator/orchestrator/handler.py
```

### 静的解析

```bash
# ruffでチェック（自動修正付き）
ruff check ble_orchestrator/ --fix

# mypyで型チェック
mypy ble_orchestrator/

# 特定のファイルのみ
mypy ble_orchestrator/orchestrator/handler.py
```

### テスト実行

```bash
# すべてのテストを実行
pytest tests/

# カバレッジ付きで実行
pytest --cov=ble_orchestrator --cov-report=html --cov-report=term

# 特定のテストファイルのみ
pytest tests/test_handler.py -v

# 特定のテストケースのみ
pytest tests/test_handler.py::TestBLERequestHandler::test_handle_scan_request -v
```

---

## 📝 修正後の確認項目

各修正後に以下を確認：

### コードフォーマット後
- [ ] 黒でフォーマットされている（`black --check .`）
- [ ] インポートが整理されている（`isort --check .`）
- [ ] ruffの警告がない（`ruff check .`）

### 型ヒント追加後
- [ ] mypyエラーがない（`mypy ble_orchestrator/`）
- [ ] IDEで型推論が動作する

### テスト修正後
- [ ] すべてのテストが通る（`pytest tests/`）
- [ ] カバレッジが改善している

---

## 🚀 継続的改善のための習慣

以下を開発フローに組み込む：

### 1. コミット前
```bash
# pre-commitフックが自動実行（設定済みの場合）
git commit -m "..."

# 手動実行する場合
black ble_orchestrator/
isort ble_orchestrator/
ruff check ble_orchestrator/ --fix
pytest tests/
```

### 2. PR作成前
```bash
# フルチェック
black --check ble_orchestrator/
isort --check ble_orchestrator/
ruff check ble_orchestrator/
mypy ble_orchestrator/
pytest --cov=ble_orchestrator --cov-report=term
```

### 3. 週次レビュー
- [ ] カバレッジレポートを確認
- [ ] 新たな技術的負債をリスト化
- [ ] 改善項目の優先順位を更新

---

## 📊 進捗トラッキング

以下のメトリクスを定期的に測定：

| メトリクス | 現在 | 目標 | 期限 |
|-----------|------|------|------|
| テストカバレッジ | ??% | 70% | 1ヶ月 |
| 型ヒントカバレッジ | ??% | 80% | 2週間 |
| ruff警告数 | ?? | 0 | 1週間 |
| mypy警告数 | ?? | 50以下 | 2週間 |
| 平均メソッド長 | ??行 | 50行以下 | 1ヶ月 |
| 重複コード率 | ??% | 5%以下 | 1ヶ月 |

---

## 🎯 今週の優先タスク

### 今日中に実施
1. [x] デバッグログの整理
2. [ ] pre-commitフックのインストール
3. [ ] 初回静的解析の実行

### 今週中に実施
1. [ ] テストコードの修正（`test_service.py`）
2. [ ] 型ヒントの追加（主要3ファイル）
3. [ ] カバレッジ測定と分析

### 来週以降
1. [ ] グローバル変数のリファクタリング計画
2. [ ] 統合テストの作成
3. [ ] ドキュメントの充実

---

## 💡 Tips

### VSCodeを使用している場合
`.vscode/settings.json`に以下を追加：

```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "python.sortImports.provider": "isort",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  },
  "python.analysis.typeCheckingMode": "basic"
}
```

### PyCharmを使用している場合
1. Settings → Tools → Black → Enable Black on save
2. Settings → Tools → External Tools でruffを設定
3. Settings → Editor → Code Style → Python でisortを設定

---

**最終更新**: 2025-10-24  
**次回確認**: 週次（毎週金曜日）


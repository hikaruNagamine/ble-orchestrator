# BLE Orchestrator パッケージ化ガイド

## 概要

BLE Orchestratorは、Pythonパッケージとして配布可能な形式で構築されています。このドキュメントでは、パッケージのビルド、インストール、配布方法について説明します。

## システム管理環境について

### Raspberry Pi OSでの制限

Raspberry Pi OS（Bullseye以降）では、PEP 668に準拠してシステム管理環境が保護されています。これにより、システム全体にPythonパッケージをインストールしようとすると以下のエラーが発生します：

```
error: externally-managed-environment
× This environment is externally managed
```

### 解決策

1. **仮想環境を使用（推奨）**
2. **--break-system-packagesフラグを使用（非推奨）**
3. **システムパッケージマネージャーを使用**

## パッケージ構造

```
ble-orchestrator/
├── pyproject.toml          # パッケージ設定（現代的な標準）
├── setup.py               # 従来のsetuptools互換性
├── MANIFEST.in            # 含めるファイルの指定
├── requirements.txt       # 依存関係（開発用）
├── build_and_install.sh   # 自動ビルド・インストールスクリプト
├── install_venv.sh        # 仮想環境専用インストールスクリプト
├── ble_orchestrator/      # メインパッケージ
│   ├── __init__.py
│   ├── __main__.py        # エントリーポイント
│   ├── main.py           # メインロジック
│   └── ...
└── tests/                # テストファイル
```

## インストール方法

### 1. 仮想環境を使用したインストール（推奨）

#### 簡易インストール
```bash
# 仮想環境を作成してインストール
./install_venv.sh
```

#### 詳細インストール
```bash
# 自動ビルド・インストールスクリプトを実行
./build_and_install.sh
# 選択肢1または2を選択（仮想環境内にインストール）
```

#### 手動インストール
```bash
# 仮想環境を作成
python3 -m venv venv

# 仮想環境をアクティベート
source venv/bin/activate

# 依存関係のインストール
pip install -r requirements.txt

# 開発モードでインストール
pip install -e .

# 実行
python -m ble_orchestrator
```

### 2. システム全体へのインストール（非推奨）

⚠️ **警告**: システム全体にインストールすると、システムの安定性に影響を与える可能性があります。

```bash
# システム全体にインストール
sudo pip install --break-system-packages .

# または
sudo ./build_and_install.sh
# 選択肢3を選択
```

### 3. 特定の仮想環境へのインストール

```bash
# 特定の仮想環境のPythonを使用
/path/to/venv/bin/pip install .

# 実行
/path/to/venv/bin/python -m ble_orchestrator
```

## 使用方法

### 仮想環境での実行

```bash
# 仮想環境をアクティベート
source venv/bin/activate

# 実行
python -m ble_orchestrator

# 非アクティベート
deactivate
```

### 直接実行

```bash
# 仮想環境をアクティベートせずに直接実行
venv/bin/python -m ble_orchestrator
```

### systemdサービスでの使用

```bash
# systemdユニットファイルを編集
sed -i "s|/path/to/ble_orchestrator|$(pwd)|g" ble_orchestrator/systemd/ble-orchestrator.service
sed -i "s|python3|$(pwd)/venv/bin/python|g" ble_orchestrator/systemd/ble-orchestrator.service

# systemdにユニットファイルをコピー
sudo cp ble_orchestrator/systemd/ble-orchestrator.service /etc/systemd/system/

# systemdを再読み込み
sudo systemctl daemon-reload

# サービスを有効化・開始
sudo systemctl enable ble-orchestrator.service
sudo systemctl start ble-orchestrator.service
```

## パッケージの配布

### 1. ローカル配布

```bash
# パッケージをビルド
python -m build

# 生成されたファイル
ls dist/
# ble_orchestrator-0.1.0.tar.gz
# ble_orchestrator-0.1.0-py3-none-any.whl
```

### 2. PyPI配布

```bash
# ビルドツールのインストール
pip install build twine

# パッケージをビルド
python -m build

# PyPIにアップロード（初回のみ）
twine upload dist/*

# テストPyPIにアップロード（テスト用）
twine upload --repository testpypi dist/*
```

### 3. GitHub Releases

```bash
# パッケージをビルド
python -m build

# GitHub Releasesに手動でアップロード
# dist/ ディレクトリのファイルをアップロード
```

## パッケージ設定の詳細

### pyproject.toml

現代的なPythonパッケージ設定ファイルです：

- **メタデータ**: 名前、バージョン、説明、ライセンス
- **依存関係**: 必要なPythonパッケージとバージョン
- **エントリーポイント**: `ble-orchestrator`コマンドの定義
- **開発依存関係**: テスト・開発用のパッケージ

### エントリーポイント

パッケージは以下の方法で実行できます：

1. **モジュール実行**: `python -m ble_orchestrator`
2. **コマンドライン**: `ble-orchestrator`（インストール後）

### 依存関係管理

- **メイン依存関係**: `pyproject.toml`の`dependencies`セクション
- **開発依存関係**: `pyproject.toml`の`optional-dependencies.dev`
- **requirements.txt**: 開発時の簡易インストール用

## トラブルシューティング

### よくある問題

1. **externally-managed-environmentエラー**
   ```bash
   # 解決策: 仮想環境を使用
   python3 -m venv venv
   source venv/bin/activate
   pip install .
   ```

2. **パッケージが見つからない**
   ```bash
   # 仮想環境がアクティベートされているか確認
   echo $VIRTUAL_ENV
   
   # パッケージ情報を確認
   pip show ble-orchestrator
   
   # 再インストール
   pip uninstall ble-orchestrator
   pip install .
   ```

3. **権限エラー**
   ```bash
   # 仮想環境を使用（推奨）
   python3 -m venv venv
   source venv/bin/activate
   pip install .
   
   # またはユーザーインストール
   pip install --user .
   ```

4. **依存関係の競合**
   ```bash
   # 新しい仮想環境を作成
   python3 -m venv fresh_venv
   source fresh_venv/bin/activate
   pip install .
   ```

### デバッグ

```bash
# 仮想環境の確認
echo $VIRTUAL_ENV

# パッケージの詳細情報
pip show ble-orchestrator

# インストールされたファイル
pip show -f ble-orchestrator

# パッケージの検証
python -c "import ble_orchestrator; print(ble_orchestrator.__file__)"
```

## 開発者向け情報

### パッケージの更新

1. バージョンを更新（`pyproject.toml`と`__init__.py`）
2. 変更履歴を更新
3. テストを実行
4. パッケージをビルド・インストール

### テスト

```bash
# 仮想環境をアクティベート
source venv/bin/activate

# 開発依存関係をインストール
pip install -e ".[dev]"

# テストを実行
pytest

# コードフォーマット
black .

# 型チェック
mypy ble_orchestrator/
```

## 参考リンク

- [Python Packaging User Guide](https://packaging.python.org/)
- [setuptools Documentation](https://setuptools.pypa.io/)
- [PyPA Build](https://pypa-build.readthedocs.io/)
- [PEP 668 - External Environment Management](https://peps.python.org/pep-0668/) 
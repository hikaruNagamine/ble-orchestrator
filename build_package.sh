#!/bin/bash
# BLE Orchestrator パッケージビルドスクリプト

set -e

echo "=== BLE Orchestrator パッケージビルド ==="

# 仮想環境の確認
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ エラー: 仮想環境が見つかりません"
    echo "まず ./install_venv.sh を実行して仮想環境を作成してください"
    exit 1
fi

# 仮想環境が正常かチェック
if [ ! -f "$VENV_DIR/bin/activate" ] || [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "❌ エラー: 仮想環境が破損しています"
    echo "rm -rf $VENV_DIR && ./install_venv.sh を実行してください"
    exit 1
fi

# 仮想環境をアクティベート
echo "1. 仮想環境をアクティベート..."
source "$VENV_DIR/bin/activate"

# ビルドツールの確認とインストール
echo "2. ビルドツールを確認..."
if ! python -c "import build" 2>/dev/null; then
    echo "ビルドツールをインストール..."
    pip install build
else
    echo "✅ ビルドツールは既にインストールされています"
fi

# クリーンアップ
echo "3. 既存のビルドファイルをクリーンアップ..."
rm -rf build/ dist/ *.egg-info/

# パッケージをビルド
echo "4. パッケージをビルド..."
python -m build

# ビルド結果の確認
echo ""
echo "=== ビルド完了 ==="
echo "生成されたファイル:"
ls -la dist/

echo ""
echo "=== 配布ファイルの詳細 ==="
for file in dist/*; do
    echo "ファイル: $(basename "$file")"
    echo "サイズ: $(du -h "$file" | cut -f1)"
    echo "---"
done

echo ""
echo "=== 次のステップ ==="
echo "1. ローカルインストール: pip install dist/*.whl"
echo "2. PyPI配布: python -m twine upload dist/*"
echo "3. GitHub Releases: dist/ ディレクトリのファイルをアップロード" 
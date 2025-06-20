#!/bin/bash
# BLE Orchestrator 仮想環境インストールスクリプト

set -e

echo "=== BLE Orchestrator 仮想環境インストール ==="

# 仮想環境の確認と作成
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "1. 仮想環境を作成..."
    python3 -m venv "$VENV_DIR"
    echo "✅ 仮想環境を作成しました: $VENV_DIR"
else
    echo "1. 既存の仮想環境を確認..."
    # 仮想環境が正常かチェック
    if [ ! -f "$VENV_DIR/bin/activate" ] || [ ! -f "$VENV_DIR/bin/python" ]; then
        echo "⚠️  仮想環境が破損しているため、再作成します..."
        rm -rf "$VENV_DIR"
        python3 -m venv "$VENV_DIR"
        echo "✅ 仮想環境を再作成しました: $VENV_DIR"
    else
        echo "✅ 既存の仮想環境を使用: $VENV_DIR"
    fi
fi

# 仮想環境をアクティベート
echo "2. 仮想環境をアクティベート..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "❌ エラー: 仮想環境のactivateスクリプトが見つかりません"
    echo "仮想環境を再作成してください: rm -rf $VENV_DIR && python3 -m venv $VENV_DIR"
    exit 1
fi

source "$VENV_DIR/bin/activate"

# 仮想環境が正常にアクティベートされたか確認
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ エラー: 仮想環境のアクティベートに失敗しました"
    exit 1
fi

echo "✅ 仮想環境がアクティベートされました: $VIRTUAL_ENV"

# 依存関係のインストール
echo "3. 依存関係をインストール..."
pip install --upgrade pip
pip install -r requirements.txt

# パッケージを開発モードでインストール
echo "4. パッケージを開発モードでインストール..."
pip install -e .

echo ""
echo "=== インストール完了 ==="
echo ""
echo "使用方法:"
echo "  アクティベート: source $VENV_DIR/bin/activate"
echo "  実行: python -m ble_orchestrator"
echo "  非アクティベート: deactivate"
echo ""
echo "または直接実行:"
echo "  $VENV_DIR/bin/python -m ble_orchestrator" 
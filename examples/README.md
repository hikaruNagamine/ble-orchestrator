# BLEWatchdog の使用例

このディレクトリには、BLEWatchdogクラスの様々な使用例が含まれています。
これらの例は、実際のアプリケーションでウォッチドッグを使用する方法を示すためのものです。

## ファイル一覧

### 1. watchdog_example.py

基本的なBLEWatchdogの使用例です。
シンプルなアプリケーションでウォッチドッグを起動し、定期的にステータスをチェックする方法を示します。
連続失敗をシミュレートし、自動復旧機能の動作を確認できます。

**実行方法:**
```bash
python3 watchdog_example.py
```

### 2. test_watchdog_example.py

ウォッチドッグのユニットテスト方法を示す例です。
pytest-asyncioを使用して非同期テストを記述する方法を学べます。

**実行方法:**
```bash
pytest -v test_watchdog_example.py
```

### 3. integration_watchdog_example.py

BLEWatchdogとBLERequestHandlerを統合した例です。
実際のアプリケーションに近い形で、ハンドラーからの連続失敗を監視し、
自動復旧する方法を示します。

**実行方法:**
```bash
python3 integration_watchdog_example.py
```

### 4. watchdog_circuit_breaker.py

BLEWatchdogをサーキットブレーカーパターンとして実装した高度な例です。
障害検出と自動復旧のメカニズムをより洗練された形で示しています。
状態管理（CLOSED/OPEN/HALF-OPEN）を持つ回路遮断機として実装されています。

**実行方法:**
```bash
python3 watchdog_circuit_breaker.py
```

## 実行時の注意点

- これらの例はテスト環境用に設計されています。実際のBLEアダプタは必須ではありません。
- シミュレーションモードでは実際のBLEハードウェアにアクセスしません。
- 実機で試す場合は、root権限が必要な操作があります。

## 学習ポイント

- 非同期プログラミング（asyncio）の使用方法
- BLEエラー検出と自動復旧の実装パターン
- 状態管理と例外処理
- ユニットテストの書き方
- サーキットブレーカーパターンの実装 
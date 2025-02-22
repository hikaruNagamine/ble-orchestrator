# BLE Controller Examples

BLE Controller の使用例を示すサンプルスクリプト集です。

## 準備

1. 必要なパッケージのインストール:
```bash
pip install aiohttp pytest pytest-asyncio
```

2. BLE Controller サービスの起動:
```bash
python -m ble_controller
```

## サンプルの実行

### CLIサンプル

直接BLEControllerクラスを使用する例:
```bash
python cli_example.py
```

### HTTPクライアントサンプル

BLE Controller サービスにHTTPリクエストを送信する例:
```bash
python http_client_example.py
```

### テストサンプル

単体テストの実行例:
```bash
pytest test_example.py
```

## 使用例

1. スキャンデータの取得:
```python
controller = BLEController()
await controller.start()
data = await controller.get_scan_data()
print(json.dumps(data, indent=2))
```

2. コマンドの送信:
```python
result = await controller.send_command(
    device_address="XX:XX:XX:XX:XX:XX",
    command="turn_on"
)
print(json.dumps(result, indent=2))
```

## 注意点

- BLEデバイスとの通信には適切な権限が必要です
- 実際のデバイスに合わせてコマンドの実装を調整してください
- テスト時は適切なモックを使用することを推奨します 
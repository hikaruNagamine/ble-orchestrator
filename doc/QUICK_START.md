# BLE Orchestrator クイックスタートガイド

## 📋 目次

1. [インストール](#インストール)
2. [基本的な使い方](#基本的な使い方)
3. [実用例](#実用例)
4. [トラブルシューティング](#トラブルシューティング)

---

## インストール

### 1. リポジトリのクローン

```bash
git clone https://github.com/username/ble-orchestrator.git
cd ble-orchestrator
```

### 2. 仮想環境のセットアップ

```bash
# 仮想環境の作成
python3 -m venv venv

# 仮想環境の有効化
source venv/bin/activate

# 依存パッケージのインストール
pip install -r requirements.txt

# パッケージのインストール（開発モード）
pip install -e .
```

### 3. サービスの起動

```bash
# 手動起動
python -m ble_orchestrator

# またはコマンドとして
ble-orchestrator
```

### 4. systemdでの自動起動（オプション）

```bash
# サービスファイルの編集
sed -i "s|/path/to/ble_orchestrator|$(pwd)|g" ble_orchestrator/systemd/ble-orchestrator.service
sed -i "s|python3|$(pwd)/venv/bin/python|g" ble_orchestrator/systemd/ble-orchestrator.service

# systemdにコピー
sudo cp ble_orchestrator/systemd/ble-orchestrator.service /etc/systemd/system/

# サービスの有効化と起動
sudo systemctl daemon-reload
sudo systemctl enable ble-orchestrator
sudo systemctl start ble-orchestrator

# ステータス確認
sudo systemctl status ble-orchestrator
```

---

## 基本的な使い方

### 1. デバイスのスキャン

```python
import asyncio
from ble_orchestrator.client import BLEOrchestratorClient

async def scan_device():
    client = BLEOrchestratorClient()
    
    async with client:
        # デバイス情報を取得（接続不要）
        result_future = await client.scan_command(
            mac_address="AA:BB:CC:DD:EE:FF"
        )
        
        # 結果を待機
        result = await result_future
        
        print(f"Device Name: {result.get('name')}")
        print(f"RSSI: {result.get('rssi')}dBm")
        print(f"Address: {result.get('address')}")

# 実行
asyncio.run(scan_device())
```

### 2. Characteristicの読み取り

```python
import asyncio
from ble_orchestrator.client import BLEOrchestratorClient

async def read_battery():
    client = BLEOrchestratorClient()
    
    async with client:
        # バッテリーレベルを読み取る
        result_future = await client.read_command(
            mac_address="AA:BB:CC:DD:EE:FF",
            service_uuid="0000180f-0000-1000-8000-00805f9b34fb",  # Battery Service
            characteristic_uuid="00002a19-0000-1000-8000-00805f9b34fb"  # Battery Level
        )
        
        result = await result_future
        battery_level = result['data'][0]
        
        print(f"Battery Level: {battery_level}%")

asyncio.run(read_battery())
```

### 3. Characteristicへの書き込み

```python
import asyncio
from ble_orchestrator.client import BLEOrchestratorClient

async def control_led():
    client = BLEOrchestratorClient()
    
    async with client:
        # LEDをONにする
        result_future = await client.send_command(
            mac_address="AA:BB:CC:DD:EE:FF",
            service_uuid="12345678-1234-5678-1234-56789abcdef0",
            characteristic_uuid="12345678-1234-5678-1234-56789abcdef1",
            data="01",  # ON
            response_required=False
        )
        
        result = await result_future
        print("LED turned ON")

asyncio.run(control_led())
```

### 4. 通知の購読

```python
import asyncio
from ble_orchestrator.client import BLEOrchestratorClient

async def notification_callback(data):
    """通知を受信したときのコールバック"""
    print(f"Received notification: {data['value']}")
    print(f"Timestamp: {data['timestamp']}")

async def monitor_temperature():
    client = BLEOrchestratorClient()
    
    async with client:
        # 温度センサーの通知を購読
        callback_id = await client.subscribe_notifications(
            mac_address="AA:BB:CC:DD:EE:FF",
            service_uuid="0000181a-0000-1000-8000-00805f9b34fb",  # Environmental Sensing
            characteristic_uuid="00002a6e-0000-1000-8000-00805f9b34fb",  # Temperature
            callback=notification_callback
        )
        
        print(f"Subscribed with ID: {callback_id}")
        print("Monitoring temperature... (Press Ctrl+C to stop)")
        
        # 60秒間監視
        await asyncio.sleep(60)
        
        # 購読解除
        await client.unsubscribe_notifications(callback_id)
        print("Unsubscribed")

asyncio.run(monitor_temperature())
```

---

## 実用例

### 例1: SwitchBot温湿度計の読み取り

```python
import asyncio
from ble_orchestrator.client import BLEOrchestratorClient

async def read_switchbot_meter():
    client = BLEOrchestratorClient()
    
    async with client:
        # スキャンデータから温湿度を取得
        result_future = await client.scan_command(
            mac_address="XX:XX:XX:XX:XX:XX"  # SwitchBotのMACアドレス
        )
        
        result = await result_future
        
        # Manufacturer Dataから温湿度を解析
        mfg_data = result.get('manufacturer_data', {})
        
        # SwitchBotのManufacturer ID: 0x0969
        if '2425' in mfg_data:  # 0x0969 = 2425
            data = mfg_data['2425']
            
            # データ形式: [deviceType, ..., battery, temp, humidity, ...]
            if len(data) >= 6:
                battery = data[2] & 0x7F
                temp_sign = 1 if (data[4] & 0x80) == 0 else -1
                temp = temp_sign * ((data[4] & 0x7F) + (data[3] & 0x0F) / 10.0)
                humidity = data[5] & 0x7F
                
                print(f"Temperature: {temp}°C")
                print(f"Humidity: {humidity}%")
                print(f"Battery: {battery}%")

asyncio.run(read_switchbot_meter())
```

### 例2: スマートプラグの制御

```python
import asyncio
from ble_orchestrator.client import BLEOrchestratorClient

class SmartPlug:
    """スマートプラグ制御クラス"""
    
    # SwitchBot Plugmini の例
    SERVICE_UUID = "cba20d00-224d-11e6-9fb8-0002a5d5c51b"
    CHAR_WRITE = "cba20002-224d-11e6-9fb8-0002a5d5c51b"
    CHAR_NOTIFY = "cba20003-224d-11e6-9fb8-0002a5d5c51b"
    
    def __init__(self, mac_address: str):
        self.mac_address = mac_address
        self.client = BLEOrchestratorClient()
    
    async def turn_on(self):
        """プラグをONにする"""
        async with self.client:
            cmd = "570f500101"  # ON command
            result_future = await self.client.send_command(
                mac_address=self.mac_address,
                service_uuid=self.SERVICE_UUID,
                characteristic_uuid=self.CHAR_WRITE,
                data=cmd,
                response_required=False,
                priority="HIGH"
            )
            await result_future
            print("Plug turned ON")
    
    async def turn_off(self):
        """プラグをOFFにする"""
        async with self.client:
            cmd = "570f500102"  # OFF command
            result_future = await self.client.send_command(
                mac_address=self.mac_address,
                service_uuid=self.SERVICE_UUID,
                characteristic_uuid=self.CHAR_WRITE,
                data=cmd,
                response_required=False,
                priority="HIGH"
            )
            await result_future
            print("Plug turned OFF")
    
    async def toggle(self):
        """プラグのON/OFFを切り替える"""
        async with self.client:
            cmd = "570f500180"  # Toggle command
            result_future = await self.client.send_command(
                mac_address=self.mac_address,
                service_uuid=self.SERVICE_UUID,
                characteristic_uuid=self.CHAR_WRITE,
                data=cmd,
                response_required=False,
                priority="HIGH"
            )
            await result_future
            print("Plug toggled")

# 使用例
async def main():
    plug = SmartPlug("XX:XX:XX:XX:XX:XX")
    
    await plug.turn_on()
    await asyncio.sleep(5)
    
    await plug.turn_off()

asyncio.run(main())
```

### 例3: 複数デバイスの監視

```python
import asyncio
from ble_orchestrator.client import BLEOrchestratorClient
from typing import List, Dict

class MultiDeviceMonitor:
    """複数デバイスを監視するクラス"""
    
    def __init__(self, devices: List[Dict[str, str]]):
        """
        Args:
            devices: [{"name": "Device1", "mac": "XX:XX:XX:XX:XX:XX"}, ...]
        """
        self.devices = devices
        self.client = BLEOrchestratorClient()
    
    async def scan_all(self):
        """全デバイスをスキャン"""
        async with self.client:
            tasks = []
            
            for device in self.devices:
                task = self.client.scan_command(
                    mac_address=device["mac"]
                )
                tasks.append(task)
            
            # 並行実行
            futures = await asyncio.gather(*tasks)
            results = await asyncio.gather(*futures)
            
            # 結果を表示
            for device, result in zip(self.devices, results):
                name = device["name"]
                rssi = result.get("rssi", "N/A")
                print(f"{name}: RSSI={rssi}dBm")
    
    async def monitor_loop(self, interval: float = 10.0):
        """定期的に全デバイスを監視"""
        while True:
            print(f"\n=== Scan at {asyncio.get_event_loop().time()} ===")
            await self.scan_all()
            await asyncio.sleep(interval)

# 使用例
async def main():
    devices = [
        {"name": "Sensor1", "mac": "AA:BB:CC:DD:EE:01"},
        {"name": "Sensor2", "mac": "AA:BB:CC:DD:EE:02"},
        {"name": "Sensor3", "mac": "AA:BB:CC:DD:EE:03"},
    ]
    
    monitor = MultiDeviceMonitor(devices)
    
    try:
        await monitor.monitor_loop(interval=30.0)
    except KeyboardInterrupt:
        print("\nMonitoring stopped")

asyncio.run(main())
```

### 例4: エラーハンドリング

```python
import asyncio
from ble_orchestrator.client import BLEOrchestratorClient

async def robust_read():
    client = BLEOrchestratorClient()
    
    async with client:
        try:
            result_future = await client.read_command(
                mac_address="AA:BB:CC:DD:EE:FF",
                service_uuid="0000180f-0000-1000-8000-00805f9b34fb",
                characteristic_uuid="00002a19-0000-1000-8000-00805f9b34fb",
                timeout=5.0
            )
            
            result = await result_future
            print(f"Success: {result}")
            
        except asyncio.TimeoutError:
            print("Error: Request timed out")
        except ConnectionError:
            print("Error: Could not connect to device")
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(robust_read())
```

---

## トラブルシューティング

### 1. サービスが起動しない

**症状**: `python -m ble_orchestrator`でエラー

**確認事項**:
```bash
# Pythonバージョン確認
python --version  # 3.9以上が必要

# 依存パッケージ確認
pip list | grep bleak

# Bluetoothアダプタ確認
hciconfig
```

**解決策**:
```bash
# 依存パッケージの再インストール
pip install -r requirements.txt --force-reinstall

# Bluetoothサービスの確認
sudo systemctl status bluetooth

# 必要に応じて再起動
sudo systemctl restart bluetooth
```

### 2. デバイスが見つからない

**症状**: `"Device not found"`エラー

**確認事項**:
```bash
# 手動でスキャン
sudo hcitool lescan

# または
bluetoothctl
[bluetooth]# scan on
```

**解決策**:
1. デバイスの電源とBluetooth有効化を確認
2. デバイスが範囲内にあるか確認
3. MACアドレスが正しいか確認
4. スキャンキャッシュのTTL（5分）を待つ

### 3. 接続がタイムアウトする

**症状**: `"Connection timeout"`エラー

**確認事項**:
```bash
# アダプタの状態
hciconfig hci0

# 他のプロセスが使用していないか
sudo lsof | grep hci
```

**解決策**:
```bash
# アダプタのリセット
sudo hciconfig hci0 down
sudo hciconfig hci0 up

# Bluetoothサービスの再起動
sudo systemctl restart bluetooth

# ble-orchestratorの再起動
sudo systemctl restart ble-orchestrator
```

### 4. 権限エラー

**症状**: `"Permission denied"`エラー

**解決策**:
```bash
# ユーザーをbluetoothグループに追加
sudo usermod -a -G bluetooth $USER

# 再ログインして反映
# または
newgrp bluetooth

# capabilityを付与（推奨）
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(which python3)
```

### 5. ログの確認方法

```bash
# ファイルログ
tail -f /var/log/ble-orchestrator/ble_orchestrator.log

# または開発環境
tail -f ble_orchestrator/logs/ble_orchestrator.log

# systemd journal
journalctl -u ble-orchestrator -f

# 特定のエラーを検索
grep "ERROR" /var/log/ble-orchestrator/ble_orchestrator.log
```

---

## 便利なコマンド集

### サービス管理

```bash
# サービスの状態確認
sudo systemctl status ble-orchestrator

# サービスの起動
sudo systemctl start ble-orchestrator

# サービスの停止
sudo systemctl stop ble-orchestrator

# サービスの再起動
sudo systemctl restart ble-orchestrator

# ログの表示
sudo journalctl -u ble-orchestrator -f --lines=100
```

### デバッグ

```bash
# 詳細ログで起動
export BLE_ORCHESTRATOR_LOG_LEVEL=DEBUG
python -m ble_orchestrator

# Bluetoothデバイスの一覧
bluetoothctl devices

# BLEスキャン
sudo hcitool lescan

# アダプタ情報
hciconfig -a
```

### 開発

```bash
# テストの実行
pytest tests/ -v

# カバレッジ測定
pytest --cov=ble_orchestrator --cov-report=html

# コードフォーマット
black ble_orchestrator/
isort ble_orchestrator/

# 静的解析
ruff check ble_orchestrator/
mypy ble_orchestrator/
```

---

## 次のステップ

1. **SPECIFICATION.md**を読んで詳細仕様を理解
2. **examples/**ディレクトリの実装例を確認
3. 独自のアプリケーションを開発

---

**参考ドキュメント**:
- [SPECIFICATION.md](SPECIFICATION.md) - 技術仕様書
- [README.md](README.md) - プロジェクト概要
- [LOG_MANAGEMENT_GUIDE.md](LOG_MANAGEMENT_GUIDE.md) - ログ管理ガイド
- [REVIEW_SUMMARY.md](REVIEW_SUMMARY.md) - コードレビューサマリー


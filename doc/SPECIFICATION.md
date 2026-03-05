# BLE Orchestrator 技術仕様書

バージョン: 0.1.2  
最終更新: 2026-3-5

---

## 📋 目次

1. [概要](#概要)
2. [システムアーキテクチャ](#システムアーキテクチャ)
3. [コンポーネント仕様](#コンポーネント仕様)
4. [API仕様](#api仕様)
5. [データ型定義](#データ型定義)
6. [通信プロトコル](#通信プロトコル)
7. [設定項目](#設定項目)
8. [エラー処理](#エラー処理)
9. [排他制御メカニズム](#排他制御メカニズム)
10. [ログ仕様](#ログ仕様)

---

## 概要

### システムの目的

BLE Orchestratorは、複数のPythonスクリプトから安全にBLE（Bluetooth Low Energy）デバイスを操作するための常駐型サービスです。

### 主要機能

1. **BLEデバイスの集約制御**
   - 複数クライアントからのBLE操作を集約
   - デバイススキャンとキャッシュ管理
   - 接続処理の一元化

2. **スキャンキャッシュ**
   - BLEデバイスのアドバタイズメントデータを5分間キャッシュ
   - 接続不要でデバイス情報を高速取得

3. **優先度付きリクエストキュー**
   - HIGH/NORMAL/LOWの3段階優先度
   - タイムアウト監視
   - 古いリクエストの自動スキップ

4. **自動復旧機能**
   - BLE接続失敗時の自動リトライ
   - アダプタリセット
   - Bluetoothサービス再起動

5. **排他制御**
   - スキャナーとクライアント接続の競合回避
   - BlueZレベルでのリソース管理

6. **通知サブスクリプション**
   - BLE Notificationのリアルタイム受信
   - 複数クライアントへの配信

### 技術スタック

- **言語**: Python 3.9以上
- **BLEライブラリ**: Bleak 0.21.1-0.22.x
- **非同期処理**: asyncio
- **IPC**: Unix Domain Socket / TCP Socket
- **データシリアライゼーション**: JSON
- **ログ**: Python logging (RotatingFileHandler)
- **プロセス管理**: systemd

---

## システムアーキテクチャ

### 全体構成

```
┌─────────────────────────────────────────────────────────┐
│                  Client Applications                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Sensor   │  │ Control  │  │ Monitor  │             │
│  │ Script   │  │ Script   │  │ Script   │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
└───────┼─────────────┼─────────────┼────────────────────┘
        │             │             │
        │   IPC (Unix Socket / TCP) │
        └─────────────┼─────────────┘
                      │
┌─────────────────────┼─────────────────────────────────┐
│  BLE Orchestrator Service                              │
│  ┌───────────────────────────────────────────────────┐│
│  │              IPC Server                            ││
│  │  - Request Handler                                 ││
│  │  - Notification Distributor                        ││
│  └────┬──────────────────────────────────────┬────────┘│
│       │                                       │         │
│  ┌────┴─────────┐                   ┌────────┴───────┐│
│  │ Queue Manager│                   │ Notification   ││
│  │              │                   │ Manager        ││
│  └────┬─────────┘                   └────────────────┘│
│       │                                                │
│  ┌────┴──────────────────────────────────────────────┐│
│  │         Request Handler                            ││
│  │  - Read/Write/Scan Request Processing             ││
│  │  - BleakClient Management                          ││
│  └────┬───────────────────────────────────────┬───────┘│
│       │                                       │         │
│  ┌────┴─────────┐                   ┌────────┴───────┐│
│  │ BLE Scanner  │                   │   Watchdog     ││
│  │ - Continuous │                   │ - Health Check ││
│  │   Scanning   │                   │ - Auto Recovery││
│  │ - Cache Mgmt │                   │                ││
│  └──────┬───────┘                   └────────────────┘│
└─────────┼──────────────────────────────────────────────┘
          │
          │ Bleak API
          │
┌─────────┼──────────────────────────────────────────────┐
│         │      Operating System (Linux)                 │
│  ┌──────┴───────┐                                       │
│  │    BlueZ     │  Bluetooth Stack                      │
│  └──────┬───────┘                                       │
│         │                                                │
│  ┌──────┴───────┐                                       │
│  │ BLE Adapter  │  Hardware (hci0, hci1)                │
│  │   (HCI)      │                                       │
│  └──────────────┘                                       │
└────────────────────────────────────────────────────────┘
```

### データフロー

#### 1. スキャンデータの流れ

```
BLE Device → Adapter → BlueZ → Bleak → Scanner → Cache → Client
            (Advertisement)     (Callback)  (Store)   (Query)
```

#### 2. コマンド送信の流れ

```
Client → IPC → Queue → Handler → BleakClient → Adapter → BLE Device
       (Request) (Enqueue) (Process) (Connect)   (HCI)
```

#### 3. 通知の流れ

```
BLE Device → Adapter → BleakClient → Notification Manager → IPC → Client
           (Notify)    (Callback)     (Distribute)          (Push)
```

---

## コンポーネント仕様

### 1. BLEScanner

**ファイル**: `ble_orchestrator/orchestrator/scanner.py`

**責務**:
- BLEデバイスの常時スキャン
- アドバタイズメントデータのキャッシュ管理
- スキャナーの自動再作成

**主要メソッド**:

```python
class BLEScanner:
    async def start() -> None
        """スキャンを開始"""
    
    async def stop() -> None
        """スキャンを停止"""
    
    def request_scanner_stop() -> None
        """排他制御用: スキャナー停止を要求"""
    
    def notify_client_completed() -> None
        """排他制御用: クライアント処理完了を通知"""
```

**スキャンキャッシュ**:
- TTL: 300秒（5分）
- 最大デバイス数: 制限なし
- 各デバイスの履歴: 最新10件まで

**自動再作成条件**:
- デバイス未検出が90秒以上継続
- 最終スキャンから90秒以上経過
- 再作成間隔: 最短180秒（3分）

### 2. BLERequestHandler

**ファイル**: `ble_orchestrator/orchestrator/handler.py`

**責務**:
- BLEリクエストの処理
- BleakClientによるデバイス接続
- 読み取り/書き込み操作

**主要メソッド**:

```python
class BLERequestHandler:
    async def handle_request(request: BLERequest) -> None
        """リクエストを処理"""
    
    async def _handle_scan_request(request: ScanRequest) -> None
        """スキャンリクエスト処理（キャッシュから取得）"""
    
    async def _handle_read_request(request: ReadRequest) -> None
        """読み取りリクエスト処理"""
    
    async def _handle_write_request(request: WriteRequest) -> None
        """書き込みリクエスト処理"""
```

**接続仕様**:
- タイムアウト: 10秒
- リトライ回数: 2回
- リトライ間隔: 1秒
- 使用アダプタ: hci1（デフォルト）

### 3. RequestQueueManager

**ファイル**: `ble_orchestrator/orchestrator/queue_manager.py`

**責務**:
- リクエストキューの管理
- 優先度付き処理
- タイムアウト監視

**キュー仕様**:

| キュー種別 | 処理方式 | ワーカー数 | タイムアウト |
|----------|---------|-----------|------------|
| メインキュー | 逐次処理 | 1 | リクエスト毎 |
| スキャンキュー | 並行処理 | 3 | 5秒 |

**優先度**:
```python
class RequestPriority(Enum):
    HIGH = 0      # 最優先
    NORMAL = 1    # 通常
    LOW = 2       # 低優先度
```

**古いリクエストのスキップ**:
- 有効/無効: `SKIP_OLD_REQUESTS` (デフォルト: True)
- 最大待機時間: 30秒
- スキップ後のステータス: FAILED

### 4. BLEWatchdog

**ファイル**: `ble_orchestrator/orchestrator/watchdog.py`

**責務**:
- BLE接続失敗の監視
- アダプタの自動復旧
- サービス再起動

**監視間隔**: 30秒

**復旧シーケンス**:

1. **軽量リセット（BleakClient失敗時）**
   ```bash
   sudo hciconfig hci0 down
   sudo hciconfig hci0 up
   ```

2. **通常リセット（連続失敗3回以上）**
   ```bash
   sudo hciconfig hci0 reset
   ```

3. **重度障害（リセット失敗時）**
   ```bash
   sudo systemctl restart bluetooth
   ```

### 5. IPCServer

**ファイル**: `ble_orchestrator/orchestrator/ipc_server.py`

**責務**:
- クライアントとの通信
- リクエストの受付
- 通知の配信

**通信方式**:
- Unix Domain Socket: `/tmp/ble-orchestrator.sock`（デフォルト）
- TCP Socket: `127.0.0.1:8378`（環境変数で切替）

**プロトコル**: JSON over line-delimited text

**最大接続数**: 10

### 6. NotificationManager

**ファイル**: `ble_orchestrator/orchestrator/notification_manager.py`

**責務**:
- BLE Notificationのサブスクリプション管理
- 複数クライアントへの配信
- 接続管理

**サブスクリプション仕様**:
- タイムアウト: 0（無限）または指定秒数
- 自動再接続: あり
- 排他制御: 有効

---

## API仕様

### クライアントAPI

**ファイル**: `ble_orchestrator/client/client.py`

#### 1. scan_command

**説明**: スキャンキャッシュからデバイス情報を取得（接続不要）

**リクエスト**:
```json
{
  "command": "scan_command",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "service_uuid": "optional",
  "characteristic_uuid": "optional",
  "request_id": "uuid4-string"
}
```

**レスポンス**:
```json
{
  "status": "success",
  "request_id": "uuid4-string",
  "result": {
    "address": "AA:BB:CC:DD:EE:FF",
    "name": "Device Name",
    "rssi": -60,
    "advertisement_data": {...},
    "manufacturer_data": {...}
  }
}
```

**特徴**:
- 即座にレスポンス（キャッシュから取得）
- 接続不要のため高速
- 並行処理（3ワーカー）

#### 2. read_command

**説明**: デバイスに接続してCharacteristicの値を読み取る

**リクエスト**:
```json
{
  "command": "read_command",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "service_uuid": "0000180f-0000-1000-8000-00805f9b34fb",
  "characteristic_uuid": "00002a19-0000-1000-8000-00805f9b34fb",
  "priority": "NORMAL",
  "timeout": 10.0,
  "request_id": "uuid4-string"
}
```

**レスポンス**:
```json
{
  "status": "success",
  "request_id": "uuid4-string",
  "result": {
    "data": [0x42, 0x4C, 0x45],
    "hex": "424c45"
  }
}
```

**タイムアウト**: 10秒（デフォルト）

#### 3. send_command

**説明**: デバイスに接続してCharacteristicに値を書き込む

**リクエスト**:
```json
{
  "command": "send_command",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "service_uuid": "0000180f-0000-1000-8000-00805f9b34fb",
  "characteristic_uuid": "00002a19-0000-1000-8000-00805f9b34fb",
  "data": "0100",
  "response_required": false,
  "priority": "NORMAL",
  "timeout": 10.0,
  "request_id": "uuid4-string"
}
```

**データフォーマット**:
- 16進数文字列: "0100" → bytes([0x01, 0x00])
- バイト配列: [1, 0]
- bytes型: b'\x01\x00'

**レスポンス**:
```json
{
  "status": "success",
  "request_id": "uuid4-string",
  "result": {
    "response_data": [0x01, 0x00]  // response_required=trueの場合
  }
}
```

#### 4. subscribe_notifications

**説明**: BLE Notificationを購読

**リクエスト**:
```json
{
  "command": "subscribe_notifications",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "service_uuid": "0000180f-0000-1000-8000-00805f9b34fb",
  "characteristic_uuid": "00002a19-0000-1000-8000-00805f9b34fb",
  "callback_id": "optional-callback-id",
  "notification_timeout": 0,
  "request_id": "uuid4-string"
}
```

**通知データ**（プッシュ）:
```json
{
  "type": "notification",
  "callback_id": "callback-id",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "characteristic_uuid": "00002a19-0000-1000-8000-00805f9b34fb",
  "value": [0x42, 0x4C, 0x45],
  "timestamp": 1234567890.123
}
```

#### 5. unsubscribe_notifications

**説明**: BLE Notificationの購読を解除

**リクエスト**:
```json
{
  "command": "unsubscribe_notifications",
  "callback_id": "callback-id",
  "request_id": "uuid4-string"
}
```

#### 6. get_service_status

**説明**: サービスの状態を取得

**リクエスト**:
```json
{
  "command": "get_service_status",
  "request_id": "uuid4-string"
}
```

**レスポンス**:
```json
{
  "status": "success",
  "result": {
    "is_running": true,
    "adapter_status": "ok",
    "queue_size": 0,
    "uptime_sec": 3600.5,
    "active_devices": 5,
    "active_subscriptions": 2,
    "exclusive_control_enabled": true,
    "client_connecting": false,
    "log_status": {
      "total_files": 3,
      "total_size_mb": 25.6,
      "usage_percent": 42.7
    }
  }
}
```

---

## データ型定義

**ファイル**: `ble_orchestrator/orchestrator/types.py`

### RequestPriority

```python
class RequestPriority(Enum):
    HIGH = 0
    NORMAL = 1
    LOW = 2
```

### RequestStatus

```python
class RequestStatus(Enum):
    PENDING = auto()       # キューで待機中
    PROCESSING = auto()    # 処理中
    COMPLETED = auto()     # 完了
    FAILED = auto()        # 失敗
    TIMEOUT = auto()       # タイムアウト
```

### ScanResult

```python
@dataclass
class ScanResult:
    address: str                              # MACアドレス
    name: Optional[str] = None                # デバイス名
    rssi: Optional[int] = None                # 信号強度
    advertisement_data: Dict[str, Any] = {}   # アドバタイズメントデータ
    timestamp: float = 0.0                    # 取得時刻（UNIXタイム）
```

### BLERequest

```python
@dataclass
class BLERequest:
    request_id: str                           # リクエストID（UUID）
    mac_address: str                          # MACアドレス
    priority: RequestPriority = NORMAL        # 優先度
    timeout_sec: float = 10.0                 # タイムアウト
    status: RequestStatus = PENDING           # ステータス
    error_message: Optional[str] = None       # エラーメッセージ
    response_data: Any = None                 # レスポンスデータ
    created_at: float = time.time()           # 作成時刻
```

### ReadRequest

```python
@dataclass
class ReadRequest(BLERequest):
    service_uuid: str = ""                    # Service UUID
    characteristic_uuid: str = ""             # Characteristic UUID
    response_data: Optional[bytearray] = None # 読み取りデータ
```

### WriteRequest

```python
@dataclass
class WriteRequest(BLERequest):
    service_uuid: str = ""                    # Service UUID
    characteristic_uuid: str = ""             # Characteristic UUID
    data: bytes = bytes()                     # 書き込みデータ
    response_required: bool = False           # レスポンス要求
    response_data: Optional[bytearray] = None # レスポンスデータ
```

### NotificationRequest

```python
@dataclass
class NotificationRequest(BLERequest):
    service_uuid: str = ""                    # Service UUID
    characteristic_uuid: str = ""             # Characteristic UUID
    callback_id: str = ""                     # コールバックID
    notification_timeout_sec: float = 0.0     # タイムアウト（0=無限）
    unsubscribe: bool = False                 # 解除フラグ
```

---

## 通信プロトコル

### メッセージフォーマット

**形式**: JSON（1行1メッセージ）

**改行コード**: `\n` (LF)

**エンコーディング**: UTF-8

### リクエスト構造

```json
{
  "command": "コマンド名",
  "request_id": "UUID",
  "...": "コマンド固有のパラメータ"
}
```

### レスポンス構造

**成功時**:
```json
{
  "status": "success",
  "request_id": "UUID",
  "result": {...}
}
```

**失敗時**:
```json
{
  "status": "error",
  "request_id": "UUID",
  "error": "エラーメッセージ"
}
```

### エラーコード

| エラーメッセージ | 原因 |
|----------------|------|
| "Device not found" | デバイスが見つからない |
| "Connection timeout" | 接続タイムアウト |
| "Request timed out" | リクエスト処理タイムアウト |
| "Request skipped due to age" | 古いリクエストがスキップされた |
| "Unknown request type" | 不明なリクエストタイプ |
| "Invalid command" | 無効なコマンド |

---

## 設定項目

**ファイル**: `ble_orchestrator/orchestrator/config.py`

### BLE設定

| 設定項目 | 環境変数 | デフォルト | 説明 |
|---------|---------|-----------|------|
| `SCAN_INTERVAL_SEC` | - | 0.5 | スキャン間隔（秒） |
| `SCAN_CACHE_TTL_SEC` | - | 300.0 | キャッシュTTL（秒） |
| `BLE_CONNECT_TIMEOUT_SEC` | `BLE_ORCHESTRATOR_CONNECT_TIMEOUT` | 20.0 | 接続タイムアウト（秒） |
| `BLE_RETRY_COUNT` | `BLE_ORCHESTRATOR_RETRY_COUNT` | 2 | リトライ回数 |
| `BLE_RETRY_INTERVAL_SEC` | `BLE_ORCHESTRATOR_RETRY_INTERVAL` | 1.0 | リトライ間隔（秒） |
| `BLE_POST_CONNECT_WAIT_SEC` | `BLE_ORCHESTRATOR_POST_CONNECT_WAIT` | 0.5 | 接続直後のサービス発見完了待機時間（秒） |
| `ENABLE_PRECONNECT_FIND` | `BLE_ORCHESTRATOR_ENABLE_PRECONNECT_FIND` | False | 接続前に簡易スキャンで到達可能性をチェックするか |
| `PRECONNECT_FIND_TIMEOUT_SEC` | `BLE_ORCHESTRATOR_PRECONNECT_FIND_TIMEOUT` | 2.0 | preconnect find のタイムアウト（秒） |
| `DEFAULT_SCAN_ADAPTER` | - | "hci0" | スキャン用アダプタ |
| `DEFAULT_CONNECT_ADAPTER` | - | "hci1" | 接続用アダプタ |

### ログ設定

| 設定項目 | 環境変数 | デフォルト | 説明 |
|---------|---------|-----------|------|
| `LOG_DIR` | `BLE_ORCHESTRATOR_LOG_DIR` | `logs/` または `/var/log/ble-orchestrator/` | ログディレクトリ |
| `LOG_LEVEL` | `BLE_ORCHESTRATOR_LOG_LEVEL` | "INFO" | ログレベル |
| `LOG_TO_FILE` | `BLE_ORCHESTRATOR_LOG_TO_FILE` | "1" | ファイル出力 |
| `LOG_MAX_BYTES` | `BLE_ORCHESTRATOR_LOG_MAX_BYTES` | 10485760 (10MB) | ファイルサイズ上限 |
| `LOG_BACKUP_COUNT` | `BLE_ORCHESTRATOR_LOG_BACKUP_COUNT` | 5 | バックアップ世代数 |

### IPC設定

| 設定項目 | 環境変数 | デフォルト | 説明 |
|---------|---------|-----------|------|
| `IPC_SOCKET_PATH` | `BLE_ORCHESTRATOR_SOCKET` | "/tmp/ble-orchestrator.sock" | Unixソケットパス |
| `IPC_LISTEN_HOST` | `BLE_ORCHESTRATOR_HOST` | "127.0.0.1" | TCPホスト |
| `IPC_LISTEN_PORT` | `BLE_ORCHESTRATOR_PORT` | 8378 | TCPポート |
| `IPC_MAX_CONNECTIONS` | - | 10 | 最大接続数 |

### キュー設定

| 設定項目 | 環境変数 | デフォルト | 説明 |
|---------|---------|-----------|------|
| `REQUEST_MAX_AGE_SEC` | - | 30.0 | リクエスト最大待機時間 |
| `SKIP_OLD_REQUESTS` | - | True | 古いリクエストスキップ |
| `SCAN_COMMAND_PARALLEL_WORKERS` | - | 3 | scan_commandワーカー数 |
| `SCAN_COMMAND_TIMEOUT_SEC` | - | 5.0 | scan_commandタイムアウト |

### 排他制御設定

| 設定項目 | 環境変数 | デフォルト | 説明 |
|---------|---------|-----------|------|
| `EXCLUSIVE_CONTROL_ENABLED` | - | True | 排他制御有効/無効 |
| `EXCLUSIVE_CONTROL_TIMEOUT_SEC` | - | 30.0 | 排他制御タイムアウト |

### ウォッチドッグ設定

| 設定項目 | 環境変数 | デフォルト | 説明 |
|---------|---------|-----------|------|
| `WATCHDOG_CHECK_INTERVAL_SEC` | - | 30.0 | チェック間隔 |
| `CONSECUTIVE_FAILURES_THRESHOLD` | - | 3 | 連続失敗しきい値 |

---

## エラー処理

### エラーの種類

#### 1. 接続エラー

**原因**:
- デバイスが範囲外
- デバイスの電源オフ
- Bluetoothアダプタの問題

**処理**:
1. 自動リトライ（2回）
2. リトライ失敗後、ウォッチドッグに通知
3. アダプタリセット

**クライアントへの通知**:
```json
{
  "status": "error",
  "error": "Failed to connect after 2 attempts: ..."
}
```

#### 2. タイムアウトエラー

**原因**:
- リクエスト処理時間超過
- キュー待機時間超過

**処理**:
- リクエストをFAILEDステータスに更新
- クライアントにエラーレスポンス

**クライアントへの通知**:
```json
{
  "status": "error",
  "error": "Request timed out after 10.0 seconds"
}
```

#### 3. デバイス未発見エラー

**原因**:
- デバイスがスキャンキャッシュに存在しない
- キャッシュの有効期限切れ

**処理**:
- エラーレスポンス返却
- スキャンは継続（自動的に発見される）

**クライアントへの通知**:
```json
{
  "status": "error",
  "error": "Device AA:BB:CC:DD:EE:FF not found or scan data expired"
}
```

### リカバリーシーケンス

#### レベル1: リトライ（自動）

```
接続失敗 → 1秒待機 → 再試行 → 成功/失敗
```

#### レベル2: アダプタリセット（自動）

```
連続失敗3回 → hciconfig reset → 5秒待機 → 再開
```

#### レベル3: サービス再起動（自動）

```
リセット失敗 → systemctl restart bluetooth → 10秒待機 → 再開
```

---

## 排他制御メカニズム

### 目的

BLEスキャナーとクライアント接続を同時実行すると、BlueZレベルでリソース競合が発生する問題を回避。

### 動作シーケンス

#### クライアント接続時

```
1. Client: read_command / send_command 要求
2. Handler: scanner.request_scanner_stop() 呼び出し
3. Scanner: スキャンを停止
4. Scanner: scan_completed イベントを設定
5. Handler: BleakClient で接続・処理
6. Handler: scanner.notify_client_completed() 呼び出し
7. Scanner: スキャンを再開
8. Scanner: scan_ready イベントを設定
```

#### タイムアウト

- スキャン停止待機: 10秒
- クライアント処理: リクエストのタイムアウト設定次第
- クライアント完了待機: 60秒

#### デッドロック検出

- 排他制御が90秒以上継続した場合、デッドロックと判定
- 強制的に排他制御をリセット（警告ログ出力）

### 無効化

排他制御は環境変数または設定で無効化可能：

```python
EXCLUSIVE_CONTROL_ENABLED = False
```

---

## ログ仕様

### ログレベル

| レベル | 用途 |
|-------|------|
| DEBUG | 詳細なデバッグ情報 |
| INFO | 通常の動作情報 |
| WARNING | 警告（処理は継続） |
| ERROR | エラー（処理失敗） |

### ログローテーション

- **方式**: `RotatingFileHandler`
- **ファイルサイズ上限**: 10MB（デフォルト）
- **バックアップ世代数**: 5（デフォルト）
- **合計最大サイズ**: 約60MB

### ログファイル

- **現在のログ**: `ble_orchestrator.log`
- **バックアップ**: `ble_orchestrator.log.1` 〜 `.5`

### 主要ログメッセージ

| メッセージ | レベル | 意味 |
|----------|-------|------|
| "BLE Orchestrator service initialized" | INFO | サービス初期化完了 |
| "All components started successfully" | INFO | 全コンポーネント起動完了 |
| "Enqueued request XXX" | INFO | リクエストがキューに追加 |
| "Processing request XXX" | DEBUG | リクエスト処理開始 |
| "Request XXX completed successfully" | INFO | リクエスト処理完了 |
| "Failed to connect after N attempts" | WARNING | 接続失敗 |
| "Recreation needed: No devices detected" | WARNING | スキャナー再作成必要 |
| "Scanner stopped for client connection" | INFO | 排他制御でスキャン停止 |
| "POTENTIAL DEADLOCK DETECTED" | ERROR | デッドロック検出 |

---

## パフォーマンス特性

### レイテンシ

| 操作 | 標準 | 最大 |
|-----|------|------|
| scan_command | <10ms | 100ms |
| read_command | 100-500ms | 10秒 |
| send_command | 100-500ms | 10秒 |
| subscribe_notifications | 1-3秒 | 10秒 |

### スループット

- **scan_command**: 並行3リクエスト/秒以上
- **read/send_command**: 逐次処理、1リクエスト/秒程度
- **通知**: リアルタイム（遅延<100ms）

### リソース使用量

| リソース | 通常時 | ピーク時 |
|---------|-------|---------|
| CPU | 1-3% | 10% |
| メモリ | 30-50MB | 100MB |
| ディスク（ログ） | 60MB | 100MB |

---

## セキュリティ考慮事項

### アクセス制御

- **Unixソケット**: ファイルパーミッション（0666）
- **TCPソケット**: localhostのみ（デフォルト）
- **認証**: なし（ローカル通信のみを想定）

### データ保護

- **ログ**: MACアドレスを含む（機密性注意）
- **IPC通信**: 暗号化なし（ローカル通信のみ）

### 推奨事項

1. 本番環境ではファイアウォール設定
2. ログファイルのパーミッション制限
3. Unixソケットの使用（TCPより安全）

---

## 制限事項

### システム要件

- **OS**: Linux（BlueZ必須）
- **Python**: 3.9以上
- **権限**: Bluetooth操作にはroot権限またはcap_net_admin

### BLE仕様

- **同時接続デバイス数**: ハードウェア依存（通常1-7台）
- **スキャン対象**: BLE 4.0以上のデバイス
- **通信距離**: 約10-30m（環境依存）

### 既知の問題

1. **複数アダプタ使用時の競合**
   - 排他制御で回避可能
   - 推奨: スキャン用とメイン接続用で分離

2. **長時間接続の安定性**
   - Notification購読は安定
   - 通常の接続は短時間推奨

3. **大量デバイスのスキャン**
   - キャッシュが大きくなる
   - TTLで自動削除

---

## 今後の拡張予定

1. **認証機能**: クライアント認証
2. **メトリクス**: Prometheus対応
3. **Web UI**: 管理画面
4. **マルチアダプタ**: 負荷分散

---

**ドキュメントバージョン**: 1.0  
**最終更新**: 2025-10-24


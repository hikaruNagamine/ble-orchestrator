"""
BLE Orchestrator設定ファイル
"""

import os
from pathlib import Path

# 基本設定
DEBUG = os.environ.get("BLE_ORCHESTRATOR_DEBUG", "0") == "1"
LOG_LEVEL = os.environ.get("BLE_ORCHESTRATOR_LOG_LEVEL", "INFO")

# パス設定
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = os.environ.get("BLE_ORCHESTRATOR_LOG_DIR", str(BASE_DIR / "logs"))
LOG_FILE = os.path.join(LOG_DIR, "ble_orchestrator.log")

# BLE設定
SCAN_INTERVAL_SEC = 0.5  # スキャン間隔（秒）
SCAN_CACHE_TTL_SEC = 300.0  # スキャン結果キャッシュ保持時間（秒）- 5分に延長
BLE_CONNECT_TIMEOUT_SEC = 10.0  # 接続タイムアウト（秒）
BLE_RETRY_COUNT = 2  # 接続リトライ回数
BLE_RETRY_INTERVAL_SEC = 1.0  # リトライ間隔（秒）

# BLEアダプタ設定
BLE_ADAPTERS = ["hci0", "hci1"]  # 使用するBLEアダプタのリスト
DEFAULT_SCAN_ADAPTER = "hci0"  # スキャン用のデフォルトアダプタ
DEFAULT_CONNECT_ADAPTER = "hci1"  # 接続用のデフォルトアダプタ

# ハング検出・復旧設定
WATCHDOG_CHECK_INTERVAL_SEC = 30.0  # ウォッチドッグ確認間隔（秒）
CONSECUTIVE_FAILURES_THRESHOLD = 3  # 連続失敗しきい値
ADAPTER_RESET_COMMAND = "sudo hciconfig {adapter} reset"  # アダプタリセットコマンド
BLUETOOTH_RESTART_COMMAND = "sudo systemctl restart bluetooth"  # Bluetooth再起動コマンド
ADAPTER_STATUS_COMMAND = "hciconfig {adapter}"  # アダプタ状態確認コマンド

# IPCサーバー設定
IPC_SOCKET_PATH = os.environ.get(
    "BLE_ORCHESTRATOR_SOCKET", 
    "/tmp/ble-orchestrator.sock"
)
IPC_LISTEN_HOST = os.environ.get("BLE_ORCHESTRATOR_HOST", "127.0.0.1")
IPC_LISTEN_PORT = int(os.environ.get("BLE_ORCHESTRATOR_PORT", "8378"))  # BLE on phone keypad
IPC_MAX_CONNECTIONS = 10

# リクエストのデフォルトタイムアウト (秒)
DEFAULT_REQUEST_TIMEOUT_SEC = 10.0

# リクエストキュー設定
REQUEST_MAX_AGE_SEC = 30.0  # リクエストの最大待機時間（秒）- 60秒から30秒に短縮
SKIP_OLD_REQUESTS = True  # 古いリクエストのスキップ機能の有効/無効

# 並行処理設定
SCAN_COMMAND_PARALLEL_WORKERS = 3  # scan_command専用の並行ワーカー数
SCAN_COMMAND_TIMEOUT_SEC = 5.0  # scan_command専用のタイムアウト（秒）

# 排他制御設定
EXCLUSIVE_CONTROL_ENABLED = True  # スキャナーとクライアントの排他制御の有効/無効
EXCLUSIVE_CONTROL_TIMEOUT_SEC = 30.0  # 排他制御のタイムアウト（秒） 
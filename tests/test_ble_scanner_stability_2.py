import asyncio
import signal
import time
from bleak import BleakScanner, BleakClient

# ---------- 変更してください ----------
TARGET_MAC = "34:85:18:18:57:C2"  # 実機のBLEデバイスアドレス
CHARACTERISTIC_UUID = "cba20002-224d-11e6-9fb8-0002a5d5c51b"  # 書き込み先UUID
WRITE_DATA_ON = bytearray.fromhex("570101")  # 例：ONコマンド
WRITE_DATA_OFF = bytearray.fromhex("570102")  # 例：OFFコマンド
REPEAT_COUNT = 10000  # 接続・write回数
SLEEP_BETWEEN_ATTEMPTS = 5  # 接続試行間隔（秒）
SCAN_DURATION = 8  # スキャン実行時間（秒）
CLIENT_DELAY = 3  # クライアント処理開始までの遅延（秒）
# ----------------------------------------

# グローバル変数
last_seen = time.time()
detection_count = 0
running = True
test_start_time = None
scanner = None  # スキャナーインスタンス
scanner_stopping = False  # スキャナー停止フラグ
client_connecting = False  # クライアント接続中フラグ
connection_lock = asyncio.Lock()  # 接続処理用ロック

# デバイス統計用のデータ構造
device_stats = {}  # {address: {'name': name, 'count': count, 'last_seen': timestamp, 'rssi_avg': avg_rssi}}
last_stats_time = time.time()
stats_interval = 5  # 統計計算間隔（秒）

# 累積統計用の変数（device_statsリセット後も保持）
cumulative_stats = {
    'total_unique_devices': 0,  # 累積ユニークデバイス数
    'total_detections': 0,      # 累積検出回数
    'no_detection_count': 0,    # No detection警告回数
    'no_detection_duration': 0  # No detection累積時間（秒）
}

# No detection記録用
no_detection_start_time = None

def signal_handler(signum, frame):
    """Ctrl+Cのシグナルハンドラー"""
    global running
    print("\n[Main] Received Ctrl+C, shutting down gracefully...", flush=True)
    running = False

def detection_callback(device, adv_data):
    """デバイス検出時のコールバック"""
    global last_seen, detection_count, device_stats, cumulative_stats, no_detection_start_time
    last_seen = time.time()
    detection_count += 1
    
    # No detection状態をリセット
    if no_detection_start_time is not None:
        no_detection_duration = time.time() - no_detection_start_time
        cumulative_stats['no_detection_duration'] += no_detection_duration
        no_detection_start_time = None
    
    # デバイスアドレスごとの統計を更新
    address = device.address
    if address not in device_stats:
        device_stats[address] = {
            'name': device.name or 'Unknown',
            'count': 0,
            'last_seen': last_seen,
            'rssi_sum': 0,
            'rssi_count': 0,
            'first_seen': last_seen  # 初回検出時刻を追加
        }
        # 新しいデバイスを累積統計に追加
        cumulative_stats['total_unique_devices'] += 1
    
    # 統計データを更新
    device_stats[address]['count'] += 1
    device_stats[address]['last_seen'] = last_seen
    cumulative_stats['total_detections'] += 1
    if adv_data.rssi is not None:
        device_stats[address]['rssi_sum'] += adv_data.rssi
        device_stats[address]['rssi_count'] += 1
    
    # 100回に1回の統計ログ（ログ過多を防ぐ）
    if detection_count % 100 == 0:
        print(f"[Scanner] 📊 Total detections: {detection_count}, Current unique devices: {len(device_stats)}", flush=True)

def calculate_device_stats():
    """デバイス統計を計算"""
    global device_stats, cumulative_stats
    
    if not device_stats:
        return 0, 0, 0, 0, cumulative_stats
    
    total_devices = len(device_stats)
    total_detections = sum(dev['count'] for dev in device_stats.values())
    
    # 平均RSSIを計算
    total_rssi = 0
    total_rssi_count = 0
    for dev in device_stats.values():
        if dev['rssi_count'] > 0:
            total_rssi += dev['rssi_sum']
            total_rssi_count += dev['rssi_count']
    
    avg_rssi = total_rssi / total_rssi_count if total_rssi_count > 0 else 0
    
    # 最も検出されたデバイスを特定
    most_detected = max(device_stats.items(), key=lambda x: x[1]['count'])
    
    return total_devices, total_detections, avg_rssi, most_detected, cumulative_stats

async def bluez_resource_manager():
    """BlueZリソース管理"""
    try:
        import subprocess
        
        print("[BlueZ] Managing BlueZ resources...", flush=True)
        
        # BlueZデーモンの再起動（必要に応じて）
        result = subprocess.run(['systemctl', 'is-active', 'bluetooth'], capture_output=True, text=True)
        if result.stdout.strip() != 'active':
            print("[BlueZ] 🔄 Restarting bluetooth service...", flush=True)
            subprocess.run(['sudo', 'systemctl', 'restart', 'bluetooth'], capture_output=True)
            await asyncio.sleep(3)
        
        print("[BlueZ] ✅ Resource management completed", flush=True)
        
    except Exception as e:
        print(f"[BlueZ] ❌ Resource management error: {e}", flush=True)

async def scan_task(duration):
    """スキャンタスク - 並行実行用"""
    global scanner, last_seen, detection_count, device_stats, cumulative_stats, no_detection_start_time
    
    print(f"[ScanTask] Starting {duration}s scan...", flush=True)
    
    # スキャナー設定
    scanner = BleakScanner(
        adapter="hci0", 
        detection_callback=detection_callback,
    )
    
    try:
        await scanner.start()
        print("[ScanTask] ✅ Scanner started", flush=True)
        
        # 指定時間だけスキャン
        start_time = time.time()
        while time.time() - start_time < duration and running and not scanner_stopping:
            await asyncio.sleep(1)
            
            # 5秒ごとに進捗表示
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0:
                print(f"[ScanTask] Progress: {elapsed}/{duration}s, Detections: {detection_count}", flush=True)
        
        print(f"[ScanTask] ✅ Scan completed ({duration}s)", flush=True)
        
    except Exception as e:
        print(f"[ScanTask] ❌ Error: {e}", flush=True)
    finally:
        try:
            if scanner and not scanner_stopping:
                await scanner.stop()
                print("[ScanTask] Scanner stopped normally", flush=True)
        except Exception as e:
            print(f"[ScanTask] Stop error: {e}", flush=True)

async def client_task(round_num):
    """クライアントタスク - 接続とwrite処理"""
    global scanner, scanner_stopping, client_connecting
    
    print(f"[ClientTask] Round {round_num}: Starting client task...", flush=True)
    
    # クライアント処理開始前に少し待機
    await asyncio.sleep(CLIENT_DELAY)
    
    # スキャナー停止フラグを設定
    scanner_stopping = True
    client_connecting = True
    
    print(f"[ClientTask] Round {round_num}: Stopping scanner for connection...", flush=True)
    
    # スキャナーを停止
    if scanner:
        try:
            await scanner.stop()
            print(f"[ClientTask] Round {round_num}: Scanner stopped", flush=True)
        except Exception as e:
            print(f"[ClientTask] Round {round_num}: Scanner stop error: {e}", flush=True)
    
    # 接続とwrite処理
    print(f"[ClientTask] Round {round_num}: Attempting connection...", flush=True)
    try:
        async with BleakClient(TARGET_MAC, adapter="hci1", timeout=10.0) as client:
            if client.is_connected:
                print(f"[ClientTask] Round {round_num}: ✅ Connected", flush=True)
                write_data = WRITE_DATA_ON if round_num % 2 == 0 else WRITE_DATA_OFF
                await client.write_gatt_char(CHARACTERISTIC_UUID, write_data)
                print(f"[ClientTask] Round {round_num}: ✅ Write succeeded ({write_data.hex()})", flush=True)
                result = True
            else:
                print(f"[ClientTask] Round {round_num}: ❌ Connection failed", flush=True)
                result = False
    except Exception as e:
        print(f"[ClientTask] Round {round_num}: ❌ Connection exception: {e}", flush=True)
        result = False
    
    # フラグをリセット
    client_connecting = False
    scanner_stopping = False
    
    return result

async def parallel_test():
    """スキャンとクライアント処理を並行実行するテスト"""
    global running, test_start_time, scanner_stopping, client_connecting
    
    print("=== BLE Parallel Test (Scan + Client) ===", flush=True)
    print(f"Target: {TARGET_MAC}", flush=True)
    print(f"Scanner: hci0, Client: hci1", flush=True)
    print(f"Repeat count: {REPEAT_COUNT}", flush=True)
    print(f"Scan duration: {SCAN_DURATION}s", flush=True)
    print(f"Client delay: {CLIENT_DELAY}s", flush=True)
    print("Press Ctrl+C to stop", flush=True)
    print("=" * 50, flush=True)
    
    # BlueZリソース管理
    await bluez_resource_manager()
    
    success_count = 0
    fail_count = 0
    
    for i in range(REPEAT_COUNT):
        if not running:
            break
            
        print(f"\n[Test] Round {i+1}/{REPEAT_COUNT}", flush=True)
        
        # スキャンタスクとクライアントタスクを並行実行
        scan_task_obj = asyncio.create_task(scan_task(SCAN_DURATION))
        client_task_obj = asyncio.create_task(client_task(i+1))
        
        # 両方のタスクが完了するまで待機
        scan_result, client_result = await asyncio.gather(
            scan_task_obj, 
            client_task_obj,
            return_exceptions=True
        )
        
        # 結果を処理
        if isinstance(client_result, Exception):
            print(f"[Test] Round {i+1}: ❌ Client task exception: {client_result}", flush=True)
            fail_count += 1
        elif client_result:
            success_count += 1
        else:
            fail_count += 1
        
        # クリーンアップ
        await cleanup_scanner()
        
        # 間隔待機
        if i < REPEAT_COUNT - 1:  # 最後のループ以外
            print(f"[Test] Round {i+1}: Waiting {SLEEP_BETWEEN_ATTEMPTS} seconds...", flush=True)
            await asyncio.sleep(SLEEP_BETWEEN_ATTEMPTS)
    
    print(f"\n[Test] Final Results - Success: {success_count}, Failed: {fail_count}", flush=True)
    print_final_report(success_count, fail_count)

async def cleanup_scanner():
    """スキャナーのクリーンアップ"""
    try:
        import subprocess
        
        # BlueZレベルでのクリーンアップ
        print("[Cleanup] Cleaning up BlueZ resources...", flush=True)
        
        # hci0のリセット
        subprocess.run(['hciconfig', 'hci0', 'down'], capture_output=True)
        await asyncio.sleep(1)
        subprocess.run(['hciconfig', 'hci0', 'up'], capture_output=True)
        await asyncio.sleep(2)
        
        print("[Cleanup] ✅ BlueZ cleanup completed", flush=True)
        
    except Exception as e:
        print(f"[Cleanup] ❌ Cleanup error: {e}", flush=True)

async def main():
    """メイン関数"""
    global test_start_time
    
    # シグナルハンドラーを設定
    signal.signal(signal.SIGINT, signal_handler)
    
    # テスト開始時刻を記録
    test_start_time = time.time()
    
    print("=== BLE Parallel Stability Test ===", flush=True)
    print(f"Target: {TARGET_MAC}", flush=True)
    print(f"Scanner: hci0, Client: hci1", flush=True)
    print(f"Repeat count: {REPEAT_COUNT}", flush=True)
    print("Press Ctrl+C to stop", flush=True)
    print("=" * 30, flush=True)
    
    try:
        await parallel_test()
    except asyncio.CancelledError:
        print("[Main] Tasks cancelled", flush=True)
    finally:
        print("[Main] Test completed", flush=True)

def print_final_report(success_count, fail_count):
    """最終結果レポートを出力"""
    global test_start_time, detection_count, device_stats, cumulative_stats, no_detection_start_time
    
    if test_start_time:
        total_time = time.time() - test_start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
    else:
        total_time = 0
        minutes = 0
        seconds = 0
    
    # 最終的なNo detection時間を計算
    if no_detection_start_time is not None:
        final_no_detection_duration = time.time() - no_detection_start_time
        cumulative_stats['no_detection_duration'] += final_no_detection_duration
    
    # デバイス統計を計算
    total_devices, total_detections, avg_rssi, most_detected, cum_stats = calculate_device_stats()
    
    print("\n" + "=" * 50, flush=True)
    print("🎯 BLE PARALLEL STABILITY TEST - FINAL REPORT", flush=True)
    print("=" * 50, flush=True)
    print(f"⏱️  Total Test Time: {minutes}m {seconds}s", flush=True)
    print(f"🎯 Target Device: {TARGET_MAC}", flush=True)
    print(f"🔄 Repeat Count: {REPEAT_COUNT}", flush=True)
    print(f"⏳ Interval: {SLEEP_BETWEEN_ATTEMPTS}s", flush=True)
    print(f"📡 Scan Duration: {SCAN_DURATION}s", flush=True)
    print(f"⏰ Client Delay: {CLIENT_DELAY}s", flush=True)
    print(flush=True)
    print("📊 CLIENT RESULTS (hci1):", flush=True)
    print(f"   ✅ Success: {success_count}", flush=True)
    print(f"   ❌ Failed: {fail_count}", flush=True)
    print(f"   📈 Success Rate: {(success_count/(success_count+fail_count)*100):.1f}%", flush=True)
    print(flush=True)
    print("📡 SCANNER RESULTS (hci0):", flush=True)
    print(f"   📱 Total Devices Detected: {detection_count}", flush=True)
    print(f"   🔍 Current Unique Devices: {total_devices}", flush=True)
    print(f"   📊 Current Total Detections: {total_detections}", flush=True)
    print(f"   📈 Average Detection Rate: {detection_count/(total_time/60):.1f} devices/min", flush=True)
    print(f"   📶 Average RSSI: {avg_rssi:.1f}dBm", flush=True)
    print(flush=True)
    print("📈 CUMULATIVE STATISTICS:", flush=True)
    print(f"   🔍 Total Unique Devices (All Time): {cum_stats['total_unique_devices']}", flush=True)
    print(f"   📊 Total Detections (All Time): {cum_stats['total_detections']}", flush=True)
    print(f"   ⚠️  No Detection Warnings: {cum_stats['no_detection_count']}", flush=True)
    print(f"   ⏱️  Total No Detection Time: {cum_stats['no_detection_duration']:.1f}s ({(cum_stats['no_detection_duration']/total_time*100):.1f}% of test time)", flush=True)
    if most_detected:
        addr, stats = most_detected
        print(f"   🏆 Most Detected Device: {stats['name']} ({addr})", flush=True)
        print(f"      - Detected {stats['count']} times", flush=True)
        if stats['rssi_count'] > 0:
            print(f"      - Average RSSI: {stats['rssi_sum']/stats['rssi_count']:.1f}dBm", flush=True)
    print(flush=True)
    print("🔧 TEST CONFIGURATION:", flush=True)
    print(f"   📝 ON Command: {WRITE_DATA_ON.hex()}", flush=True)
    print(f"   📝 OFF Command: {WRITE_DATA_OFF.hex()}", flush=True)
    print(f"   🔗 Characteristic UUID: {CHARACTERISTIC_UUID}", flush=True)
    print("=" * 50, flush=True)

if __name__ == "__main__":
    asyncio.run(main()) 
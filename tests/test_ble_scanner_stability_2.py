import asyncio
import signal
import time
from bleak import BleakScanner, BleakClient

# ---------- 変更してください ----------
TARGET_MAC = "34:85:18:18:57:C2"  # 実機のBLEデバイスアドレス
CHARACTERISTIC_UUID = "cba20002-224d-11e6-9fb8-0002a5d5c51b"  # 書き込み先UUID
WRITE_DATA_ON = bytearray.fromhex("570101")  # 例：ONコマンド
WRITE_DATA_OFF = bytearray.fromhex("570102")  # 例：OFFコマンド
REPEAT_COUNT = 1000  # 接続・write回数
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

# 並行継続実行用の制御変数
scan_ready = asyncio.Event()  # スキャン準備完了イベント
client_ready = asyncio.Event()  # クライアント準備完了イベント
scan_completed = asyncio.Event()  # スキャン完了イベント
client_completed = asyncio.Event()  # クライアント完了イベント
current_round = 0  # 現在のラウンド番号
success_count = 0  # 成功回数
fail_count = 0  # 失敗回数

# デバイス統計用のデータ構造
device_stats = {}  # {address: {'name': name, 'count': count, 'last_seen': timestamp, 'rssi_avg': avg_rssi}}
last_stats_time = time.time()
stats_interval = 5  # 統計計算間隔（秒）

# スキャン統計用のデータ構造（ループごとに初期化）
scan_device_stats = {}  # 現在のスキャンセッション用
scan_detection_count = 0  # 現在のスキャンセッションの検出回数
scan_start_time = None  # 現在のスキャンセッション開始時刻

# スキャン検出監視用の変数
scan_last_detection_time = None  # 最後の検出時刻
scan_no_detection_warning_time = 30  # 検出なし警告時間（秒）
scan_no_detection_warning_interval = 10  # 警告表示間隔（秒）
scan_last_warning_time = 0  # 最後の警告時刻

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
    try:
        print("\n[Main] Received Ctrl+C, shutting down gracefully...", flush=True)
    except BrokenPipeError:
        # パイプが切断されている場合は無視
        pass
    running = False

def detection_callback(device, adv_data):
    """デバイス検出時のコールバック"""
    global last_seen, detection_count, device_stats, cumulative_stats, no_detection_start_time
    global scan_device_stats, scan_detection_count, scan_last_detection_time
    
    last_seen = time.time()
    detection_count += 1
    scan_detection_count += 1  # スキャンセッション用カウンター
    scan_last_detection_time = time.time()  # 最後の検出時刻を更新
    
    # No detection状態をリセット
    if no_detection_start_time is not None:
        no_detection_duration = time.time() - no_detection_start_time
        cumulative_stats['no_detection_duration'] += no_detection_duration
        no_detection_start_time = None
    
    # 全体統計用のデバイス情報を更新
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
    
    # 全体統計データを更新
    device_stats[address]['count'] += 1
    device_stats[address]['last_seen'] = last_seen
    cumulative_stats['total_detections'] += 1
    if adv_data.rssi is not None:
        device_stats[address]['rssi_sum'] += adv_data.rssi
        device_stats[address]['rssi_count'] += 1
    
    # スキャンセッション用のデバイス情報を更新
    if address not in scan_device_stats:
        scan_device_stats[address] = {
            'name': device.name or 'Unknown',
            'count': 0,
            'last_seen': last_seen,
            'rssi_sum': 0,
            'rssi_count': 0,
            'first_seen': last_seen
        }
    
    # スキャンセッション統計データを更新
    scan_device_stats[address]['count'] += 1
    scan_device_stats[address]['last_seen'] = last_seen
    if adv_data.rssi is not None:
        scan_device_stats[address]['rssi_sum'] += adv_data.rssi
        scan_device_stats[address]['rssi_count'] += 1

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

def calculate_scan_stats():
    """スキャンセッション統計を計算"""
    global scan_device_stats, scan_detection_count, scan_start_time
    
    if not scan_device_stats:
        return 0, 0, 0, None
    
    total_devices = len(scan_device_stats)
    total_detections = scan_detection_count
    
    # 平均RSSIを計算
    total_rssi = 0
    total_rssi_count = 0
    for dev in scan_device_stats.values():
        if dev['rssi_count'] > 0:
            total_rssi += dev['rssi_sum']
            total_rssi_count += dev['rssi_count']
    
    avg_rssi = total_rssi / total_rssi_count if total_rssi_count > 0 else 0
    
    # 最も検出されたデバイスを特定
    most_detected = max(scan_device_stats.items(), key=lambda x: x[1]['count']) if scan_device_stats else None
    
    return total_devices, total_detections, avg_rssi, most_detected

def reset_scan_stats():
    """スキャン統計をリセット"""
    global scan_device_stats, scan_detection_count, scan_start_time
    global scan_last_detection_time, scan_last_warning_time
    scan_device_stats = {}
    scan_detection_count = 0
    scan_start_time = time.time()
    scan_last_detection_time = time.time()  # リセット時に現在時刻を設定
    scan_last_warning_time = 0  # 警告時刻をリセット

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

async def scan_task():
    """スキャンタスク - 継続実行用"""
    global scanner, last_seen, detection_count, device_stats, cumulative_stats, no_detection_start_time, scan_ready, scan_completed, running
    global scan_device_stats, scan_detection_count, scan_start_time, scan_last_detection_time, scan_last_warning_time
    
    try:
        print("[ScanTask] Starting continuous scan...", flush=True)
    except BrokenPipeError:
        return
    
    # スキャナー設定
    scanner = BleakScanner(
        adapter="hci0", 
        detection_callback=detection_callback,
    )
    
    try:
        await scanner.start()
        try:
            print("[ScanTask] ✅ Scanner started", flush=True)
        except BrokenPipeError:
            pass
        scan_ready.set()  # スキャン準備完了を通知
        
        # 初回スキャン統計をリセット
        reset_scan_stats()
        
        # 継続的にスキャンを実行
        while running:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            
            # runningフラグがFalseになったら終了
            if not running:
                try:
                    print("[ScanTask] Test completion detected. Stopping scan...", flush=True)
                except BrokenPipeError:
                    pass
                break
            
            # クライアントからの停止要求をチェック
            if scanner_stopping:
                # スキャン停止前の統計を表示
                scan_devices, scan_detections, scan_avg_rssi, scan_most_detected = calculate_scan_stats()
                scan_duration = time.time() - scan_start_time if scan_start_time else 0
                try:
                    print(f"[ScanTask] 📊 Scan Session Stats - Duration: {scan_duration:.1f}s, Devices: {scan_devices}, Detections: {scan_detections}, Avg RSSI: {scan_avg_rssi:.1f}dBm", flush=True)
                except BrokenPipeError:
                    pass
                
                try:
                    print("[ScanTask] Stopping scanner for client connection...", flush=True)
                except BrokenPipeError:
                    pass
                await scanner.stop()
                try:
                    print("[ScanTask] Scanner stopped for client", flush=True)
                except BrokenPipeError:
                    pass
                scan_completed.set()  # スキャン停止完了を通知
                
                # クライアント完了を待機
                try:
                    await client_completed.wait()
                except asyncio.CancelledError:
                    break
                client_completed.clear()  # イベントをリセット
                
                # runningフラグがFalseになったら終了
                if not running:
                    try:
                        print("[ScanTask] Test completion detected. Not restarting scan...", flush=True)
                    except BrokenPipeError:
                        pass
                    break
                
                # スキャンを再開
                try:
                    print("[ScanTask] Restarting scanner...", flush=True)
                except BrokenPipeError:
                    pass
                await scanner.start()
                try:
                    print("[ScanTask] Scanner restarted", flush=True)
                except BrokenPipeError:
                    pass
                
                # スキャン統計をリセット
                reset_scan_stats()
                
                scan_ready.set()  # スキャン準備完了を通知
            
            # 検出なし警告のチェック
            current_time = time.time()
            if scan_last_detection_time and (current_time - scan_last_detection_time) > scan_no_detection_warning_time:
                # 警告間隔をチェック（連続警告を防ぐ）
                if (current_time - scan_last_warning_time) > scan_no_detection_warning_interval:
                    no_detection_duration = current_time - scan_last_detection_time
                    try:
                        print(f"[ScanTask] ⚠️  WARNING: No device detection for {no_detection_duration:.1f}s", flush=True)
                    except BrokenPipeError:
                        pass
                    cumulative_stats['no_detection_count'] += 1  # 警告カウントをインクリメント
                    scan_last_warning_time = current_time
            
            # 5秒ごとにスキャン稼働状況を表示
            if scan_start_time and (time.time() - scan_start_time) % 5 < 1:
                scan_devices, scan_detections, scan_avg_rssi, _ = calculate_scan_stats()
                scan_duration = time.time() - scan_start_time
                try:
                    print(f"[ScanTask] 🔍 Scan Active - Duration: {scan_duration:.1f}s, Devices: {scan_devices}, Detections: {scan_detections}, Avg RSSI: {scan_avg_rssi:.1f}dBm", flush=True)
                except BrokenPipeError:
                    pass
        
        try:
            print("[ScanTask] Continuous scan completed", flush=True)
        except BrokenPipeError:
            pass
        
    except asyncio.CancelledError:
        try:
            print("[ScanTask] Scan task cancelled", flush=True)
        except BrokenPipeError:
            pass
    except Exception as e:
        try:
            print(f"[ScanTask] ❌ Error: {e}", flush=True)
        except BrokenPipeError:
            pass
    finally:
        try:
            if scanner:
                await scanner.stop()
                try:
                    print("[ScanTask] Scanner stopped normally", flush=True)
                except BrokenPipeError:
                    pass
        except Exception as e:
            try:
                print(f"[ScanTask] Stop error: {e}", flush=True)
            except BrokenPipeError:
                pass

async def client_task():
    """クライアントタスク - 継続実行用"""
    global scanner, scanner_stopping, client_connecting, current_round, success_count, fail_count, scan_ready, client_completed, running
    
    try:
        print("[ClientTask] Starting continuous client task...", flush=True)
    except BrokenPipeError:
        return
    
    # スキャン準備完了を待機
    try:
        await scan_ready.wait()
    except asyncio.CancelledError:
        return
    scan_ready.clear()  # イベントをリセット
    
    while running and current_round < REPEAT_COUNT:
        current_round += 1
        try:
            print(f"[ClientTask] Round {current_round}/{REPEAT_COUNT}: Starting client task...", flush=True)
        except BrokenPipeError:
            break
        
        # クライアント処理開始前に少し待機
        try:
            await asyncio.sleep(CLIENT_DELAY)
        except asyncio.CancelledError:
            break
        
        # スキャナー停止フラグを設定
        scanner_stopping = True
        client_connecting = True
        
        try:
            print(f"[ClientTask] Round {current_round}: Stopping scanner for connection...", flush=True)
        except BrokenPipeError:
            break
        
        # スキャン停止完了を待機
        try:
            await scan_completed.wait()
        except asyncio.CancelledError:
            break
        scan_completed.clear()  # イベントをリセット
        
        # 接続とwrite処理
        try:
            print(f"[ClientTask] Round {current_round}: Attempting connection...", flush=True)
        except BrokenPipeError:
            break
        try:
            async with BleakClient(TARGET_MAC, adapter="hci1", timeout=10.0) as client:
                if client.is_connected:
                    try:
                        print(f"[ClientTask] Round {current_round}: ✅ Connected", flush=True)
                    except BrokenPipeError:
                        pass
                    write_data = WRITE_DATA_ON if current_round % 2 == 0 else WRITE_DATA_OFF
                    await client.write_gatt_char(CHARACTERISTIC_UUID, write_data)
                    try:
                        print(f"[ClientTask] Round {current_round}: ✅ Write succeeded ({write_data.hex()})", flush=True)
                    except BrokenPipeError:
                        pass
                    success_count += 1
                    result = True
                else:
                    try:
                        print(f"[ClientTask] Round {current_round}: ❌ Connection failed", flush=True)
                    except BrokenPipeError:
                        pass
                    fail_count += 1
                    result = False
        except asyncio.CancelledError:
            break
        except Exception as e:
            try:
                print(f"[ClientTask] Round {current_round}: ❌ Connection exception: {e}", flush=True)
            except BrokenPipeError:
                pass
            fail_count += 1
            result = False
        
        # フラグをリセット
        client_connecting = False
        scanner_stopping = False
        
        # クライアント完了を通知（スキャン再開のトリガー）
        client_completed.set()
        
        # REPEAT_COUNTに達したらテスト終了
        if current_round >= REPEAT_COUNT:
            try:
                print(f"[ClientTask] ✅ All {REPEAT_COUNT} rounds completed. Terminating test...", flush=True)
            except BrokenPipeError:
                pass
            running = False
            break
        
        # 間隔待機
        if current_round < REPEAT_COUNT:
            try:
                print(f"[ClientTask] Round {current_round}: Waiting {SLEEP_BETWEEN_ATTEMPTS} seconds...", flush=True)
            except BrokenPipeError:
                break
            try:
                await asyncio.sleep(SLEEP_BETWEEN_ATTEMPTS)
            except asyncio.CancelledError:
                break
    
    try:
        print("[ClientTask] Continuous client task completed", flush=True)
    except BrokenPipeError:
        pass

async def parallel_test():
    """スキャンとクライアント処理を並行継続実行するテスト"""
    global running, test_start_time, scanner_stopping, client_connecting, success_count, fail_count
    
    try:
        print("=== BLE Parallel Continuous Test (Scan + Client) ===", flush=True)
        print(f"Target: {TARGET_MAC}", flush=True)
        print(f"Scanner: hci0, Client: hci1", flush=True)
        print(f"Repeat count: {REPEAT_COUNT}", flush=True)
        print(f"Client delay: {CLIENT_DELAY}s", flush=True)
        print(f"Interval: {SLEEP_BETWEEN_ATTEMPTS}s", flush=True)
        print("Press Ctrl+C to stop", flush=True)
        print("=" * 50, flush=True)
    except BrokenPipeError:
        return
    
    # BlueZリソース管理
    await bluez_resource_manager()
    
    # スキャンタスクとクライアントタスクを並行継続実行
    scan_task_obj = asyncio.create_task(scan_task())
    client_task_obj = asyncio.create_task(client_task())
    
    # 両方のタスクが完了するまで待機
    try:
        await asyncio.gather(
            scan_task_obj, 
            client_task_obj,
            return_exceptions=True
        )
    except asyncio.CancelledError:
        # タスクをキャンセル
        scan_task_obj.cancel()
        client_task_obj.cancel()
        try:
            await asyncio.gather(scan_task_obj, client_task_obj, return_exceptions=True)
        except Exception:
            pass
    except Exception as e:
        try:
            print(f"[Test] Exception in parallel execution: {e}", flush=True)
        except BrokenPipeError:
            pass
    
    try:
        print(f"\n[Test] ✅ Test completed successfully!", flush=True)
        print(f"[Test] Final Results - Success: {success_count}, Failed: {fail_count}", flush=True)
        print_final_report(success_count, fail_count)
    except BrokenPipeError:
        pass

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
    
    try:
        print("=== BLE Parallel Continuous Stability Test ===", flush=True)
        print(f"Target: {TARGET_MAC}", flush=True)
        print(f"Scanner: hci0, Client: hci1", flush=True)
        print(f"Repeat count: {REPEAT_COUNT}", flush=True)
        print("Press Ctrl+C to stop", flush=True)
        print("=" * 30, flush=True)
    except BrokenPipeError:
        return
    
    try:
        await parallel_test()
    except asyncio.CancelledError:
        try:
            print("[Main] Tasks cancelled", flush=True)
        except BrokenPipeError:
            pass
    except Exception as e:
        try:
            print(f"[Main] Exception: {e}", flush=True)
        except BrokenPipeError:
            pass
    finally:
        try:
            print("[Main] Test completed", flush=True)
        except BrokenPipeError:
            pass

def print_final_report(success_count, fail_count):
    """最終結果レポートを出力"""
    global test_start_time, detection_count, device_stats, cumulative_stats, no_detection_start_time
    
    try:
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
        print("🎯 BLE PARALLEL CONTINUOUS STABILITY TEST - FINAL REPORT", flush=True)
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
        print("📊 SCAN SESSION STATISTICS:", flush=True)
        scan_devices, scan_detections, scan_avg_rssi, scan_most_detected = calculate_scan_stats()
        print(f"   🔍 Current Session Devices: {scan_devices}", flush=True)
        print(f"   📊 Current Session Detections: {scan_detections}", flush=True)
        print(f"   📶 Current Session Avg RSSI: {scan_avg_rssi:.1f}dBm", flush=True)
        if scan_most_detected:
            addr, stats = scan_most_detected
            print(f"   🏆 Current Session Most Detected: {stats['name']} ({addr})", flush=True)
            print(f"      - Detected {stats['count']} times", flush=True)
            if stats['rssi_count'] > 0:
                print(f"      - Average RSSI: {stats['rssi_sum']/stats['rssi_count']:.1f}dBm", flush=True)
        print(flush=True)
        print("🔧 TEST CONFIGURATION:", flush=True)
        print(f"   📝 ON Command: {WRITE_DATA_ON.hex()}", flush=True)
        print(f"   📝 OFF Command: {WRITE_DATA_OFF.hex()}", flush=True)
        print(f"   🔗 Characteristic UUID: {CHARACTERISTIC_UUID}", flush=True)
        print("=" * 50, flush=True)
    except BrokenPipeError:
        # パイプが切断されている場合は無視
        pass
    except Exception as e:
        try:
            print(f"[Report] Error generating report: {e}", flush=True)
        except BrokenPipeError:
            pass

if __name__ == "__main__":
    asyncio.run(main()) 
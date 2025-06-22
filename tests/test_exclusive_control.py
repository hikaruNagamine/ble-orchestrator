#!/usr/bin/env python3
"""
BLE Orchestrator 排他制御機能テスト
検証スクリプトの排他制御メカニズムを参考に、ble-orchestratorの排他制御機能をテスト
"""

import asyncio
import signal
import time
import sys
import os

# ble-orchestratorのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bleak import BleakClient
from ble_orchestrator.orchestrator.service import BLEOrchestratorService

# ---------- 変更してください ----------
TARGET_MAC = "34:85:18:18:57:C2"  # 実機のBLEデバイスアドレス
CHARACTERISTIC_UUID = "cba20002-224d-11e6-9fb8-0002a5d5c51b"  # 書き込み先UUID
WRITE_DATA_ON = bytearray.fromhex("570101")  # 例：ONコマンド
WRITE_DATA_OFF = bytearray.fromhex("570102")  # 例：OFFコマンド
REPEAT_COUNT = 100  # 接続・write回数
SLEEP_BETWEEN_ATTEMPTS = 3  # 接続試行間隔（秒）
# ----------------------------------------

# グローバル変数
running = True
test_start_time = None
success_count = 0
fail_count = 0

def signal_handler(signum, frame):
    """Ctrl+Cのシグナルハンドラー"""
    global running
    print("\n[Main] Received Ctrl+C, shutting down gracefully...", flush=True)
    running = False

async def test_exclusive_control():
    """排他制御機能のテスト"""
    global running, test_start_time, success_count, fail_count
    
    print("=== BLE Orchestrator Exclusive Control Test ===", flush=True)
    print(f"Target: {TARGET_MAC}", flush=True)
    print(f"Repeat count: {REPEAT_COUNT}", flush=True)
    print(f"Interval: {SLEEP_BETWEEN_ATTEMPTS}s", flush=True)
    print("Press Ctrl+C to stop", flush=True)
    print("=" * 50, flush=True)
    
    # BLE Orchestratorサービスを開始
    service = BLEOrchestratorService()
    
    try:
        await service.start()
        print("[Test] ✅ BLE Orchestrator service started", flush=True)
        
        # サービスステータスを確認
        status = service._get_service_status()
        print(f"[Test] Service status: {status}", flush=True)
        
        # 排他制御が有効かどうかを確認
        if not status.get('exclusive_control_enabled', False):
            print("[Test] ⚠️  Exclusive control is disabled", flush=True)
        else:
            print("[Test] ✅ Exclusive control is enabled", flush=True)
        
        # 連続テスト実行
        for i in range(REPEAT_COUNT):
            if not running:
                break
                
            print(f"\n[Test] Round {i+1}/{REPEAT_COUNT}", flush=True)
            
            try:
                # サービスステータスを確認（クライアント接続前）
                status_before = service._get_service_status()
                print(f"[Test] Status before connection: client_connecting={status_before.get('client_connecting', False)}", flush=True)
                
                # WriteRequestを作成してキューに追加
                from ble_orchestrator.orchestrator.types import WriteRequest
                
                write_data = WRITE_DATA_ON if i % 2 == 0 else WRITE_DATA_OFF
                request = WriteRequest(
                    mac_address=TARGET_MAC,
                    characteristic_uuid=CHARACTERISTIC_UUID,
                    data=write_data,
                    response_required=False
                )
                
                print(f"[Test] Sending write request: {write_data.hex()}", flush=True)
                
                # リクエストをキューに追加
                request_id = await service._enqueue_request(request)
                print(f"[Test] Request queued with ID: {request_id}", flush=True)
                
                # リクエスト完了を待機
                timeout = 30.0  # 30秒タイムアウト
                start_wait = time.time()
                
                while not request.is_done() and (time.time() - start_wait) < timeout:
                    await asyncio.sleep(0.1)
                
                if request.is_done():
                    if request.status.name == "COMPLETED":
                        print(f"[Test] ✅ Write succeeded", flush=True)
                        success_count += 1
                    else:
                        print(f"[Test] ❌ Write failed: {request.status.name}", flush=True)
                        if request.error_message:
                            print(f"[Test] Error: {request.error_message}", flush=True)
                        fail_count += 1
                else:
                    print(f"[Test] ❌ Write timeout", flush=True)
                    fail_count += 1
                
                # サービスステータスを確認（クライアント接続後）
                status_after = service._get_service_status()
                print(f"[Test] Status after connection: client_connecting={status_after.get('client_connecting', False)}", flush=True)
                
                # 間隔待機
                if i < REPEAT_COUNT - 1:
                    print(f"[Test] Waiting {SLEEP_BETWEEN_ATTEMPTS} seconds...", flush=True)
                    await asyncio.sleep(SLEEP_BETWEEN_ATTEMPTS)
                
            except Exception as e:
                print(f"[Test] ❌ Exception in round {i+1}: {e}", flush=True)
                fail_count += 1
        
        print(f"\n[Test] ✅ Test completed!", flush=True)
        print(f"[Test] Final Results - Success: {success_count}, Failed: {fail_count}", flush=True)
        
        # 最終的なサービスステータスを表示
        final_status = service._get_service_status()
        print(f"[Test] Final service status: {final_status}", flush=True)
        
    except Exception as e:
        print(f"[Test] ❌ Error during test: {e}", flush=True)
    finally:
        # サービスを停止
        try:
            await service.stop()
            print("[Test] ✅ BLE Orchestrator service stopped", flush=True)
        except Exception as e:
            print(f"[Test] ❌ Error stopping service: {e}", flush=True)

async def main():
    """メイン関数"""
    global test_start_time
    
    # シグナルハンドラーを設定
    signal.signal(signal.SIGINT, signal_handler)
    
    # テスト開始時刻を記録
    test_start_time = time.time()
    
    try:
        await test_exclusive_control()
    except asyncio.CancelledError:
        print("[Main] Tasks cancelled", flush=True)
    except Exception as e:
        print(f"[Main] Exception: {e}", flush=True)
    finally:
        if test_start_time:
            total_time = time.time() - test_start_time
            minutes = int(total_time // 60)
            seconds = int(total_time % 60)
            print(f"[Main] Test completed in {minutes}m {seconds}s", flush=True)

if __name__ == "__main__":
    asyncio.run(main()) 
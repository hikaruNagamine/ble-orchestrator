#!/usr/bin/env python3
"""
BleakClient失敗時のwatchdog機能テスト
存在しないデバイスに接続を試行してBleakClient失敗をシミュレートし、
watchdogのアダプタリセット機能が動作することを確認
"""

import asyncio
import logging
import time
from bleak import BleakClient, BleakError

# テスト設定
NON_EXISTENT_MAC = "00:00:00:00:00:00"  # 存在しないMACアドレス
TEST_CHARACTERISTIC_UUID = "cba20002-224d-11e6-9fb8-0002a5d5c51b"
TEST_DATA = bytearray.fromhex("570101")
CONNECT_TIMEOUT = 5.0  # 短いタイムアウトで素早く失敗させる
RETRY_COUNT = 3

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

async def test_bleakclient_failure():
    """
    BleakClient失敗をシミュレートしてwatchdog機能をテスト
    """
    logger.info("=== BleakClient Failure Watchdog Test ===")
    logger.info(f"Testing with non-existent device: {NON_EXISTENT_MAC}")
    logger.info(f"Connect timeout: {CONNECT_TIMEOUT}s")
    logger.info(f"Retry count: {RETRY_COUNT}")
    
    failure_count = 0
    
    for attempt in range(RETRY_COUNT):
        try:
            logger.info(f"Attempt {attempt + 1}/{RETRY_COUNT}: Connecting to {NON_EXISTENT_MAC}")
            
            async with BleakClient(NON_EXISTENT_MAC, timeout=CONNECT_TIMEOUT) as client:
                logger.info("Connected (unexpected!)")
                
                # 書き込みテスト
                await client.write_gatt_char(TEST_CHARACTERISTIC_UUID, TEST_DATA)
                logger.info("Write succeeded (unexpected!)")
                
        except (BleakError, asyncio.TimeoutError) as e:
            failure_count += 1
            logger.warning(f"BleakClient failed (expected): {e}")
            
            if attempt < RETRY_COUNT - 1:
                logger.info(f"Waiting before retry...")
                await asyncio.sleep(1.0)
            else:
                logger.error(f"BleakClient failed after {RETRY_COUNT} attempts - this should trigger watchdog")
                
        except Exception as e:
            failure_count += 1
            logger.error(f"Unexpected error: {e}")
            
            if attempt < RETRY_COUNT - 1:
                logger.info(f"Waiting before retry...")
                await asyncio.sleep(1.0)
            else:
                logger.error(f"Unexpected error after {RETRY_COUNT} attempts - this should trigger watchdog")
    
    logger.info(f"Test completed. Total failures: {failure_count}/{RETRY_COUNT}")
    
    if failure_count == RETRY_COUNT:
        logger.info("✅ All attempts failed as expected - watchdog should be triggered")
        logger.info("Check the ble-orchestrator logs for watchdog activity")
    else:
        logger.warning("⚠️ Some attempts succeeded unexpectedly")

async def test_with_real_device():
    """
    実在するデバイスでのテスト（オプション）
    """
    # 実際のBLEデバイスがある場合はここでテスト
    pass

async def main():
    """
    メイン関数
    """
    logger.info("Starting BleakClient failure watchdog test")
    
    try:
        # BleakClient失敗テスト
        await test_bleakclient_failure()
        
        # 少し待機してwatchdogの動作を確認
        logger.info("Waiting 10 seconds to observe watchdog activity...")
        await asyncio.sleep(10.0)
        
        logger.info("Test completed")
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 
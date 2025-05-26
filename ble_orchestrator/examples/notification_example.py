#!/usr/bin/env python3
import asyncio
import logging
import sys
import signal
from ble_orchestrator.client.client import BLEOrchestratorClient

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 終了フラグ
shutdown_event = asyncio.Event()

async def notification_callback(notification_data):
    """
    通知データを受信したときに呼び出されるコールバック関数
    """
    logger.info(f"通知受信: {notification_data}")
    
    # 通知データを解析して表示
    if "value" in notification_data:
        value = notification_data["value"]
        if isinstance(value, str):
            try:
                # 16進数文字列の場合はバイトに変換
                value_bytes = bytes.fromhex(value)
                logger.info(f"通知データ (16進数): {value}")
                logger.info(f"通知データ (バイト): {value_bytes}")
            except ValueError:
                logger.info(f"通知データ (文字列): {value}")
        elif isinstance(value, bytes):
            logger.info(f"通知データ (バイト): {value}")
            logger.info(f"通知データ (16進数): {value.hex()}")
        else:
            logger.info(f"通知データ: {value}")
    
    # デバイス情報も表示
    if "mac_address" in notification_data:
        logger.info(f"送信元デバイス: {notification_data['mac_address']}")
    if "characteristic_uuid" in notification_data:
        logger.info(f"特性UUID: {notification_data['characteristic_uuid']}")
    if "timestamp" in notification_data:
        logger.info(f"タイムスタンプ: {notification_data['timestamp']}")

async def notification_example(mac_address, service_uuid, characteristic_uuid, duration=60):
    """
    BLEデバイスの通知を購読するサンプル
    """
    client = BLEOrchestratorClient()
    callback_id = None
    
    try:
        # BLE Orchestratorに接続
        logger.info("BLE Orchestratorに接続中...")
        await client.connect()
        logger.info("接続完了")
        
        # 通知を購読
        logger.info(f"デバイス {mac_address} の通知を購読中...")
        callback_id = await client.subscribe_notifications(
            mac_address, 
            service_uuid, 
            characteristic_uuid, 
            notification_callback
        )
        logger.info(f"通知購読開始。callback_id: {callback_id}")
        
        # 終了するか、指定時間が経過するまで待機
        try:
            # 終了イベントか指定時間のどちらか早い方を待機
            wait_task = asyncio.create_task(shutdown_event.wait())
            timeout_task = asyncio.create_task(asyncio.sleep(duration))
            
            done, pending = await asyncio.wait(
                [wait_task, timeout_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 残りのタスクをキャンセル
            for task in pending:
                task.cancel()
                
            if wait_task in done:
                logger.info("終了イベントを受信しました")
            else:
                logger.info(f"{duration}秒経過しました")
                
        except asyncio.CancelledError:
            logger.info("タスクがキャンセルされました")
            
    except Exception as e:
        logger.error(f"エラー: {e}")
    finally:
        # 通知の購読解除
        if callback_id:
            logger.info(f"通知購読を解除中...")
            try:
                success = await client.unsubscribe_notifications(callback_id)
                logger.info(f"通知購読解除: {'成功' if success else '失敗'}")
            except Exception as e:
                logger.error(f"通知購読解除中にエラー: {e}")
        
        # 切断処理
        logger.info("BLE Orchestratorから切断中...")
        await client.disconnect()
        logger.info("切断完了")

def signal_handler():
    """
    Ctrl+Cなどのシグナルを受信したときのハンドラ
    """
    logger.info("終了シグナルを受信しました")
    shutdown_event.set()

def main():
    # コマンドライン引数の処理
    if len(sys.argv) < 4:
        print(f"使用方法: {sys.argv[0]} <MACアドレス> <サービスUUID> <特性UUID> [<待機時間(秒)>]")
        print(f"例: {sys.argv[0]} F1:2E:40:2A:67:6B 0000fd3d-0000-1000-8000-00805f9b34fb cba20d00-224d-11e6-9fb8-0002a5d5c51b")
        print(f"例: {sys.argv[0]} F1:2E:40:2A:67:6B 0000fd3d-0000-1000-8000-00805f9b34fb cba20d00-224d-11e6-9fb8-0002a5d5c51b 120")
        return 1
    
    mac_address = sys.argv[1]
    service_uuid = sys.argv[2]
    characteristic_uuid = sys.argv[3]
    duration = int(sys.argv[4]) if len(sys.argv) > 4 else 60
    
    # イベントループを取得
    loop = asyncio.get_event_loop()
    
    # シグナルハンドラを設定
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # サンプル実行
        loop.run_until_complete(
            notification_example(mac_address, service_uuid, characteristic_uuid, duration)
        )
    except KeyboardInterrupt:
        logger.info("キーボード割り込みによって終了します")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 
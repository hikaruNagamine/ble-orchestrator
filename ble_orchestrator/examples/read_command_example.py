#!/usr/bin/env python3
import asyncio
import logging
import sys
from ble_orchestrator.client.client import BLEOrchestratorClient

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def read_command_example(mac_address, service_uuid, characteristic_uuid):
    client = BLEOrchestratorClient()
    
    try:
        # BLE Orchestratorに接続
        logger.info("BLE Orchestratorに接続中...")
        await client.connect()
        logger.info("接続完了")
        
        # デバイスからの特性値の読み取り
        logger.info(f"デバイス {mac_address} から特性値を読み取り中...")
        
        # read_commandメソッドからFutureを取得
        future = await client.read_command(mac_address, service_uuid, characteristic_uuid)
        
        # リクエストIDをログに出力
        logger.info(f"リクエスト送信完了。応答待機中...")
        
        # Futureが完了するのを待機（タイムアウト付き）
        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            logger.info(f"応答受信: {response}")
            
            # 読み取りデータの表示
            if response.get("status") == "success":
                if "response_data" in response:
                    response_data = response.get("response_data")
                    if isinstance(response_data, bytes):
                        logger.info(f"読み取りデータ: {response_data.hex()}")
                    else:
                        logger.info(f"読み取りデータ: {response_data}")
                logger.info(f"読み取り成功: {response.get('message', 'OK')}")
            else:
                logger.error(f"エラー: {response.get('error', '不明なエラー')}")
                
        except asyncio.TimeoutError:
            logger.error("応答待機がタイムアウトしました")
        
    except Exception as e:
        logger.error(f"エラー: {e}")
    finally:
        # 切断処理
        logger.info("BLE Orchestratorから切断中...")
        await client.disconnect()
        logger.info("切断完了")

def main():
    # コマンドライン引数の処理
    if len(sys.argv) < 4:
        print(f"使用方法: {sys.argv[0]} <MACアドレス> <サービスUUID> <特性UUID>")
        print(f"例: {sys.argv[0]} E3:AB:70:A4:21:51 0000fd3d-0000-1000-8000-00805f9b34fb cba20d00-224d-11e6-9fb8-0002a5d5c51b")
        return 1
    
    mac_address = sys.argv[1]
    service_uuid = sys.argv[2]
    characteristic_uuid = sys.argv[3]
    
    # イベントループを取得して実行
    loop = asyncio.get_event_loop()
    loop.run_until_complete(read_command_example(mac_address, service_uuid, characteristic_uuid))

if __name__ == "__main__":
    sys.exit(main()) 
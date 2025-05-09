#!/usr/bin/env python3
import asyncio
import logging
import sys
from ble_orchestrator.client.client import BLEOrchestratorClient

# ロギング設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def send_command_example(mac_address, service_uuid, characteristic_uuid, data_hex, response_required=False):
    client = BLEOrchestratorClient()
    
    try:
        # BLE Orchestratorに接続
        logger.info("BLE Orchestratorに接続中...")
        await client.connect()
        logger.info("接続完了")
        
        # コマンド送信
        logger.info(f"デバイス {mac_address} にコマンド送信中...")
        
        # 16進数文字列をバイトデータに変換
        data = bytes.fromhex(data_hex) if isinstance(data_hex, str) else data_hex
        logger.info(f"送信データ: {data.hex()}")
        
        # send_commandメソッドからFutureを取得
        future = await client.send_command(
            mac_address, 
            service_uuid, 
            characteristic_uuid, 
            data,
            response_required=response_required,
            timeout=60.0,
        )
        
        # リクエストIDをログに出力
        logger.info(f"リクエスト送信完了。応答待機中...")
        
        # Futureが完了するのを待機（タイムアウト付き）
        try:
            response = await asyncio.wait_for(future, timeout=60.0)
            logger.info(f"応答受信: {response}")
            
            # レスポンスの表示
            if response.get("status") == "success":
                if response_required and "response_data" in response:
                    response_data = response.get("response_data")
                    if isinstance(response_data, bytes):
                        logger.info(f"レスポンスデータ: {response_data.hex()}")
                    else:
                        logger.info(f"レスポンスデータ: {response_data}")
                logger.info(f"コマンド送信成功: {response.get('message', 'OK')}")
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
    if len(sys.argv) < 5:
        print(f"使用方法: {sys.argv[0]} <MACアドレス> <サービスUUID> <特性UUID> <データ(16進数)> [<レスポンス要求:0/1>]")
        print(f"例: {sys.argv[0]} E3:AB:70:A4:21:51 0000fd3d-0000-1000-8000-00805f9b34fb cba20d00-224d-11e6-9fb8-0002a5d5c51b 01020304")
        print(f"例: {sys.argv[0]} E3:AB:70:A4:21:51 cba20d00-224d-11e6-9fb8-0002a5d5c51b cba20d00-224d-11e6-9fb8-0002a5d5c51b 01020304 1")
        return 1
    
    mac_address = sys.argv[1]
    service_uuid = sys.argv[2]
    characteristic_uuid = sys.argv[3]
    data_hex = sys.argv[4]
    response_required = bool(int(sys.argv[5])) if len(sys.argv) > 5 else False
    
    # イベントループを取得して実行
    loop = asyncio.get_event_loop()
    loop.run_until_complete(send_command_example(mac_address, service_uuid, characteristic_uuid, data_hex, response_required))

if __name__ == "__main__":
    sys.exit(main()) 
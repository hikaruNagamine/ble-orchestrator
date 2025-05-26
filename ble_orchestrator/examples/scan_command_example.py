#!/usr/bin/env python3
import asyncio
import logging
import sys
from ble_orchestrator.client.client import BLEOrchestratorClient

# ロギング設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def scan_data_example(mac_address, service_uuid=None, characteristic_uuid=None):
    client = BLEOrchestratorClient()
    
    try:
        # BLE Orchestratorに接続
        logger.info("BLE Orchestratorに接続中...")
        await client.connect()
        logger.info("接続完了")
        
        # スキャン済みデータを取得（デバイスに接続せずに）
        logger.info(f"デバイス {mac_address} のスキャン済みデータを取得中...")
        
        # scan_commandメソッドからFutureを取得
        future = await client.scan_command(mac_address, service_uuid, characteristic_uuid)
        
        # リクエストIDをログに出力
        logger.info(f"リクエスト送信完了。応答待機中...")
        
        # Futureが完了するのを待機（タイムアウト付き）
        try:
            response = await asyncio.wait_for(future, timeout=10.0)
            logger.info(f"応答受信: {response}")
            
            # データの表示
            if response.get("status") == "success":
                scan_data = response.get("data", {})
                logger.info("スキャンデータ詳細:")
                
                # 基本情報
                logger.info(f"デバイス名: {scan_data.get('name', '不明')}")
                logger.info(f"RSSI: {scan_data.get('rssi', '不明')}")
                
                # アドバタイズデータ
                adv_data = scan_data.get("advertisement_data", {})
                if adv_data:
                    logger.info("アドバタイズデータ:")
                    for key, value in adv_data.items():
                        if isinstance(value, bytes):
                            value = value.hex()
                        logger.info(f"  {key}: {value}")
                
                # Manufacturer Data (新規追加)
                manufacturer_data = scan_data.get("manufacturer_data", {})
                if manufacturer_data:
                    logger.info("メーカーデータ:")
                    for company_id, data in manufacturer_data.items():
                        logger.info(f"  会社ID: {company_id}, データ: {data}")
                
                # サービスデータ
                services = scan_data.get("services", [])
                if services:
                    logger.info("サービス一覧:")
                    for svc in services:
                        logger.info(f"  {svc}")
                
                # 特定のサービスやキャラクタリスティックのデータ
                if service_uuid and "service_data" in scan_data:
                    service_data = scan_data.get("service_data", {}).get(service_uuid)
                    if service_data:
                        logger.info(f"サービス {service_uuid} のデータ: {service_data}")
            else:
                logger.error(f"エラー: {response.get('error', '不明なエラー')}")
                
        except asyncio.TimeoutError:
            logger.error("応答待機がタイムアウトしました")
        
    except Exception as e:
        logger.error(f"エラー発生: {e}")
    finally:
        # 切断
        await client.disconnect()
        logger.info("切断完了")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用法: scan_command_example.py <MAC_ADDRESS> [SERVICE_UUID] [CHARACTERISTIC_UUID]")
        sys.exit(1)
        
    mac_address = sys.argv[1]
    service_uuid = sys.argv[2] if len(sys.argv) > 2 else None
    characteristic_uuid = sys.argv[3] if len(sys.argv) > 3 else None
    
    asyncio.run(scan_data_example(mac_address, service_uuid, characteristic_uuid)) 
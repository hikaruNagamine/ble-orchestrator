#!/usr/bin/env python3
import asyncio
import logging
from ble_orchestrator.client.client import BLEOrchestratorClient

# ロギング設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_basic_connection():
    client = BLEOrchestratorClient()
    
    try:
        # BLE Orchestratorに接続
        logger.info("BLE Orchestratorに接続中...")
        await client.connect()
        logger.info("接続完了")
        
        # 基本的なステータス取得をテスト
        logger.info("基本的なステータス取得をテスト中...")
        status_future = await client.send_request({
            "command": "get_status"
        })
        
        try:
            status_result = await asyncio.wait_for(status_future, timeout=10.0)
            logger.info(f"ステータス取得成功: {status_result}")
        except asyncio.TimeoutError:
            logger.error("ステータス取得がタイムアウトしました")
            return
        
        # キューの設定取得をテスト
        logger.info("キューの設定取得をテスト中...")
        config_future = await client.send_request({
            "command": "get_queue_config"
        })
        
        try:
            config_result = await asyncio.wait_for(config_future, timeout=10.0)
            logger.info(f"キュー設定取得結果: {config_result}")
        except asyncio.TimeoutError:
            logger.error("キュー設定取得がタイムアウトしました")
            return
        
    except Exception as e:
        logger.error(f"エラー: {e}")
    finally:
        # 切断処理
        logger.info("BLE Orchestratorから切断中...")
        await client.disconnect()
        logger.info("切断完了")

if __name__ == "__main__":
    asyncio.run(test_basic_connection()) 
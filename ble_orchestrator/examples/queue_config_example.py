#!/usr/bin/env python3
"""
キューの設定変更テストスクリプト
古いリクエストのスキップ機能の設定を変更する例
"""

import asyncio
import json
import logging
import sys
from ble_orchestrator.client.client import BLEOrchestratorClient

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_queue_config():
    """キューの設定変更をテスト"""
    client = BLEOrchestratorClient()
    
    try:
        # BLE Orchestratorに接続
        logger.info("BLE Orchestratorに接続中...")
        await client.connect()
        logger.info("接続完了")
        
        # 現在の設定を取得
        logger.info("現在のキュー設定を取得中...")
        current_config_future = await client.send_request({
            "command": "get_queue_config"
        })
        
        try:
            current_config = await asyncio.wait_for(current_config_future, timeout=30.0)
            
            if current_config.get("status") == "success":
                config = current_config.get("data", {})
                logger.info(f"現在の設定: {config}")
            else:
                logger.error(f"設定取得失敗: {current_config}")
                return
                
        except asyncio.TimeoutError:
            logger.error("設定取得がタイムアウトしました")
            return
        
        # 設定を変更（スキップ機能を無効化）
        logger.info("スキップ機能を無効化中...")
        update_future = await client.send_request({
            "command": "update_queue_config",
            "skip_old_requests": False
        })
        
        try:
            update_result = await asyncio.wait_for(update_future, timeout=30.0)
            
            if update_result.get("status") == "success":
                logger.info(f"設定更新成功: {update_result.get('data')}")
            else:
                logger.error(f"設定更新失敗: {update_result}")
                return
                
        except asyncio.TimeoutError:
            logger.error("設定更新がタイムアウトしました")
            return
        
        # 設定を変更（スキップ機能を有効化、待機時間を60秒に設定）
        logger.info("スキップ機能を有効化し、待機時間を60秒に設定中...")
        update_future = await client.send_request({
            "command": "update_queue_config",
            "skip_old_requests": True,
            "max_age_sec": 60.0
        })
        
        try:
            update_result = await asyncio.wait_for(update_future, timeout=30.0)
            
            if update_result.get("status") == "success":
                logger.info(f"設定更新成功: {update_result.get('data')}")
            else:
                logger.error(f"設定更新失敗: {update_result}")
                return
                
        except asyncio.TimeoutError:
            logger.error("設定更新がタイムアウトしました")
            return
        
        # 最終的な設定を確認
        logger.info("最終的な設定を確認中...")
        final_config_future = await client.send_request({
            "command": "get_queue_config"
        })
        
        try:
            final_config = await asyncio.wait_for(final_config_future, timeout=30.0)
            
            if final_config.get("status") == "success":
                config = final_config.get("data", {})
                logger.info(f"最終設定: {config}")
            else:
                logger.error(f"設定取得失敗: {final_config}")
                
        except asyncio.TimeoutError:
            logger.error("最終設定取得がタイムアウトしました")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
    finally:
        # 切断
        await client.disconnect()
        logger.info("切断完了")


async def main():
    """メイン関数"""
    try:
        await test_queue_config()
    except KeyboardInterrupt:
        logger.info("ユーザーによって中断されました")
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 
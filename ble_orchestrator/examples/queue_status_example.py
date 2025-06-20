#!/usr/bin/env python3
"""
キューの状態確認テストスクリプト
キューの詳細な状態と統計情報を確認する例
"""

import asyncio
import json
import logging
import sys
import time
from ble_orchestrator.client.client import BLEOrchestratorClient

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_queue_status():
    """キューの状態確認をテスト"""
    client = BLEOrchestratorClient()
    
    try:
        # BLE Orchestratorに接続
        logger.info("BLE Orchestratorに接続中...")
        await client.connect()
        logger.info("接続完了")
        
        # キューの詳細な状態を取得
        logger.info("キューの詳細な状態を取得中...")
        status_future = await client.send_request({
            "command": "get_queue_status"
        })
        
        try:
            status_result = await asyncio.wait_for(status_future, timeout=30.0)
            
            if status_result.get("status") == "success":
                status = status_result.get("data", {})
                logger.info("=== キューの詳細な状態 ===")
                logger.info(f"キューサイズ: {status.get('queue_size', 0)}")
                logger.info(f"アクティブなリクエスト数: {status.get('active_requests_count', 0)}")
                
                # アクティブなリクエストの詳細
                active_requests = status.get("active_requests", [])
                if active_requests:
                    logger.info("アクティブなリクエスト:")
                    for req in active_requests:
                        request_type = req.get('request_type', 'unknown')
                        logger.info(f"  - ID: {req['request_id']}")
                        logger.info(f"    MAC: {req['mac_address']}")
                        logger.info(f"    タイプ: {request_type}")
                        logger.info(f"    優先度: {req['priority']}")
                        logger.info(f"    ステータス: {req['status']}")
                        logger.info(f"    経過時間: {req['age_seconds']}秒")
                        logger.info(f"    タイムアウト: {req['timeout_sec']}秒")
                        logger.info("")
                else:
                    logger.info("アクティブなリクエストはありません")
                
                # 統計情報
                stats = status.get("stats", {})
                logger.info("=== 統計情報 ===")
                logger.info(f"総リクエスト数: {stats.get('total_requests', 0)}")
                logger.info(f"完了リクエスト数: {stats.get('completed_requests', 0)}")
                logger.info(f"失敗リクエスト数: {stats.get('failed_requests', 0)}")
                logger.info(f"タイムアウトリクエスト数: {stats.get('timeout_requests', 0)}")
                logger.info(f"スキップリクエスト数: {stats.get('skipped_requests', 0)}")
                logger.info(f"処理中リクエスト数: {stats.get('processing_requests', 0)}")
                
                # 設定情報
                config = status.get("config", {})
                logger.info("=== 設定情報 ===")
                logger.info(f"スキップ機能: {'有効' if config.get('skip_old_requests') else '無効'}")
                logger.info(f"最大待機時間: {config.get('max_age_sec', 0)}秒")
                
            else:
                logger.error(f"状態取得失敗: {status_result}")
                return
                
        except asyncio.TimeoutError:
            logger.error("キューの状態取得がタイムアウトしました")
            return
        
        # キューの統計情報のみを取得
        logger.info("\nキューの統計情報のみを取得中...")
        stats_future = await client.send_request({
            "command": "get_queue_stats"
        })
        
        try:
            stats_result = await asyncio.wait_for(stats_future, timeout=30.0)
            
            if stats_result.get("status") == "success":
                stats = stats_result.get("data", {})
                logger.info("=== 統計情報（簡易版） ===")
                for key, value in stats.items():
                    logger.info(f"{key}: {value}")
            else:
                logger.error(f"統計情報取得失敗: {stats_result}")
                
        except asyncio.TimeoutError:
            logger.error("統計情報取得がタイムアウトしました")
        
        # 複数回の状態確認（変化を観察）
        logger.info("\n=== 複数回の状態確認 ===")
        for i in range(3):
            logger.info(f"\n--- {i+1}回目の確認 ---")
            status_future = await client.send_request({
                "command": "get_queue_status"
            })
            
            try:
                status_result = await asyncio.wait_for(status_future, timeout=30.0)
                
                if status_result.get("status") == "success":
                    status = status_result.get("data", {})
                    logger.info(f"キューサイズ: {status.get('queue_size', 0)}")
                    logger.info(f"アクティブなリクエスト数: {status.get('active_requests_count', 0)}")
                    
                    stats = status.get("stats", {})
                    logger.info(f"完了リクエスト数: {stats.get('completed_requests', 0)}")
                    logger.info(f"スキップリクエスト数: {stats.get('skipped_requests', 0)}")
                else:
                    logger.error(f"状態取得失敗: {status_result}")
                    
            except asyncio.TimeoutError:
                logger.error(f"{i+1}回目の状態取得がタイムアウトしました")
            
            if i < 2:  # 最後の1回は待機しない
                await asyncio.sleep(2)
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
    finally:
        # 切断
        await client.disconnect()
        logger.info("切断完了")


async def main():
    """メイン関数"""
    try:
        await test_queue_status()
    except KeyboardInterrupt:
        logger.info("ユーザーによって中断されました")
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 
#!/usr/bin/env python3
"""
キューの状態をリアルタイムで監視するスクリプト
定期的にキューの状態を確認して表示する
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from ble_orchestrator.client.client import BLEOrchestratorClient

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def monitor_queue_status(interval_sec: float = 5.0, max_iterations: int = None):
    """キューの状態をリアルタイムで監視"""
    client = BLEOrchestratorClient()
    
    try:
        # BLE Orchestratorに接続
        logger.info("BLE Orchestratorに接続中...")
        await client.connect()
        logger.info("接続完了")
        logger.info(f"キューの監視を開始します（間隔: {interval_sec}秒）")
        logger.info("Ctrl+Cで停止")
        
        iteration = 0
        while True:
            if max_iterations and iteration >= max_iterations:
                break
                
            iteration += 1
            current_time = datetime.now().strftime("%H:%M:%S")
            
            try:
                # キューの状態を取得
                status_future = await client.send_request({
                    "command": "get_queue_status"
                })
                
                try:
                    status_result = await asyncio.wait_for(status_future, timeout=10.0)
                    
                    if status_result.get("status") == "success":
                        status = status_result.get("data", {})
                        
                        # 簡潔な表示
                        print(f"\n[{current_time}] キュー監視 #{iteration}")
                        print(f"キューサイズ: {status.get('queue_size', 0)}")
                        print(f"アクティブなリクエスト: {status.get('active_requests_count', 0)}")
                        
                        stats = status.get("stats", {})
                        print(f"統計 - 完了: {stats.get('completed_requests', 0)}, "
                              f"失敗: {stats.get('failed_requests', 0)}, "
                              f"タイムアウト: {stats.get('timeout_requests', 0)}, "
                              f"スキップ: {stats.get('skipped_requests', 0)}, "
                              f"処理中: {stats.get('processing_requests', 0)}")
                        
                        # アクティブなリクエストがある場合は詳細表示
                        active_requests = status.get("active_requests", [])
                        if active_requests:
                            print("アクティブなリクエスト:")
                            for req in active_requests:
                                request_type = req.get('request_type', 'unknown')
                                print(f"  {req['request_id'][:8]}... "
                                      f"{req['mac_address']} "
                                      f"[{request_type}] "
                                      f"({req['priority']}) "
                                      f"[{req['status']}] "
                                      f"{req['age_seconds']}秒経過 "
                                      f"[{req['request_id']}]")
                        
                        config = status.get("config", {})
                        print(f"設定 - スキップ: {'ON' if config.get('skip_old_requests') else 'OFF'}, "
                              f"最大待機時間: {config.get('max_age_sec', 0)}秒")
                        
                    else:
                        print(f"[{current_time}] エラー: {status_result.get('error', 'Unknown error')}")
                        
                except asyncio.TimeoutError:
                    print(f"[{current_time}] キュー状態取得がタイムアウトしました")
                    
            except Exception as e:
                print(f"[{current_time}] 監視エラー: {e}")
            
            # 指定された間隔で待機
            if max_iterations is None or iteration < max_iterations:
                try:
                    await asyncio.sleep(interval_sec)
                except asyncio.CancelledError:
                    logger.info("監視が中断されました")
                    break
                
    except KeyboardInterrupt:
        logger.info("監視を停止します")
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
    finally:
        # 切断
        try:
            await client.disconnect()
            logger.info("切断完了")
        except Exception as e:
            logger.error(f"切断中にエラーが発生しました: {e}")


async def main():
    """メイン関数"""
    # コマンドライン引数の処理
    interval_sec = 5.0
    max_iterations = None
    
    if len(sys.argv) > 1:
        try:
            interval_sec = float(sys.argv[1])
        except ValueError:
            logger.error("間隔は数値で指定してください")
            return
    
    if len(sys.argv) > 2:
        try:
            max_iterations = int(sys.argv[2])
        except ValueError:
            logger.error("最大繰り返し回数は整数で指定してください")
            return
    
    try:
        await monitor_queue_status(interval_sec, max_iterations)
    except KeyboardInterrupt:
        logger.info("ユーザーによって中断されました")
    except asyncio.CancelledError:
        logger.info("タスクがキャンセルされました")
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("プログラムが中断されました")
    except Exception as e:
        logger.error(f"プログラム実行中にエラーが発生しました: {e}") 
"""
優先度付きリクエストキューの管理
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Generic, cast

from .types import BLERequest, RequestPriority, RequestStatus

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BLERequest)


class RequestQueueManager(Generic[T]):
    """
    優先度付きリクエストキューマネージャー
    優先度付きキューで逐次処理とタイムアウト監視を行う
    """

    def __init__(self, worker_func: Callable[[T], Any]):
        """
        初期化
        worker_func: リクエスト処理を行う関数
        """
        self._queue = asyncio.PriorityQueue()  # (優先度, リクエストID, リクエスト)のタプルを格納
        self._active_requests: Dict[str, T] = {}
        self._worker_func = worker_func
        self._stop_event = asyncio.Event()
        self._worker_task = None

    async def start(self) -> None:
        """
        ワーカーを開始
        """
        if self._worker_task is not None:
            logger.warning("Queue worker is already running")
            return

        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Queue worker started")

    async def stop(self) -> None:
        """
        ワーカーを停止
        """
        if self._worker_task is None:
            return

        logger.info("Stopping queue worker...")
        self._stop_event.set()
        
        try:
            await asyncio.wait_for(self._worker_task, timeout=5.0)
        except asyncio.TimeoutError:
            self._worker_task.cancel()
            logger.warning("Queue worker task forcibly cancelled")
        except Exception as e:
            logger.error(f"Error while stopping queue worker: {e}")
            
        self._worker_task = None
        logger.info("Queue worker stopped")

    async def enqueue_request(self, request: T) -> str:
        """
        リクエストをキューに追加
        request: リクエストオブジェクト

        返り値: リクエストID
        """
        if not request.request_id:
            request.request_id = str(uuid.uuid4())
            
        priority_value = request.priority.value
        
        # キューに追加
        await self._queue.put((priority_value, request.request_id, request))
        self._active_requests[request.request_id] = request
        
        logger.info(
            f"Enqueued request {request.request_id} for {request.mac_address} "
            f"with priority {request.priority.name}"
        )
        
        return request.request_id

    async def get_request_status(self, request_id: str) -> Optional[T]:
        """
        リクエストのステータスを取得
        """
        return self._active_requests.get(request_id)

    def get_queue_size(self) -> int:
        """
        キューサイズを取得
        """
        return self._queue.qsize()

    async def _worker_loop(self) -> None:
        """
        キューからリクエストを取り出して処理するワーカーループ
        """
        try:
            while not self._stop_event.is_set():
                try:
                    # タイムアウト付きでキューからリクエストを取得
                    # キューが空の場合は0.1秒待機してループ
                    try:
                        priority, request_id, request = await asyncio.wait_for(
                            self._queue.get(), timeout=0.1
                        )
                    except asyncio.TimeoutError:
                        continue
                    
                    logger.info(
                        f"Processing request {request_id} for {request.mac_address} "
                        f"with priority {request.priority.name}"
                    )
                    
                    # リクエスト処理中に状態を更新
                    request.status = RequestStatus.PROCESSING
                    
                    try:
                        # タイムアウト付きでリクエスト処理
                        await asyncio.wait_for(
                            self._worker_func(request),
                            timeout=request.timeout_sec
                        )
                        request.status = RequestStatus.COMPLETED
                        logger.info(f"Request {request_id} completed successfully")
                    except asyncio.TimeoutError:
                        request.status = RequestStatus.TIMEOUT
                        request.error_message = "Request timed out"
                        logger.error(f"Request {request_id} timed out after {request.timeout_sec} seconds")
                    except Exception as e:
                        request.status = RequestStatus.FAILED
                        request.error_message = str(e)
                        logger.error(f"Request {request_id} failed with error: {e}")
                    finally:
                        # タスクの完了を通知
                        self._queue.task_done()
                        
                        # 一定時間経過したリクエストはactive_requestsから削除
                        # ここでは簡単のため、処理完了したものはすぐに削除
                        if request.status in [RequestStatus.COMPLETED, RequestStatus.FAILED, RequestStatus.TIMEOUT]:
                            self._active_requests.pop(request_id, None)
                
                except asyncio.CancelledError:
                    logger.info("Worker loop cancelled")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in worker loop: {e}")
                    await asyncio.sleep(1.0)  # エラー時は少し待機
        finally:
            logger.info("Worker loop terminated") 
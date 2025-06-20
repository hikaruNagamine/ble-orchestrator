"""
優先度付きリクエストキューの管理
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Generic, cast

from .config import REQUEST_MAX_AGE_SEC, SKIP_OLD_REQUESTS
from .types import BLERequest, RequestPriority, RequestStatus, WriteRequest, ReadRequest, ScanRequest, NotificationRequest

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
        
        # 古いリクエストスキップ設定
        self._skip_old_requests = SKIP_OLD_REQUESTS
        self._request_max_age_sec = REQUEST_MAX_AGE_SEC
        
        # 統計情報
        self._stats = {
            "total_requests": 0,
            "completed_requests": 0,
            "failed_requests": 0,
            "timeout_requests": 0,
            "skipped_requests": 0,
            "processing_requests": 0
        }

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
        
        # 統計情報を更新
        self._stats["total_requests"] += 1
        
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

    def get_queue_status(self) -> Dict[str, Any]:
        """
        キューの詳細な状態を取得
        """
        # アクティブなリクエストの詳細情報
        active_requests_info = []
        for request_id, request in self._active_requests.items():
            request_age = time.time() - request.created_at
            
            # リクエストタイプを判定
            if isinstance(request, WriteRequest):
                request_type = "send_command"
            elif isinstance(request, ReadRequest):
                request_type = "read_command"
            elif isinstance(request, ScanRequest):
                request_type = "scan_command"
            elif isinstance(request, NotificationRequest):
                request_type = "notification"
            else:
                request_type = "unknown"
            
            active_requests_info.append({
                "request_id": request_id,
                "mac_address": request.mac_address,
                "request_type": request_type,  # リクエストタイプを追加
                "priority": request.priority.name,
                "status": request.status.name,
                "age_seconds": round(request_age, 1),
                "timeout_sec": request.timeout_sec,
                "created_at": request.created_at
            })
        
        # 統計情報
        stats = self._stats.copy()
        stats["active_requests_count"] = len(self._active_requests)
        stats["queue_size"] = self._queue.qsize()
        
        return {
            "queue_size": self._queue.qsize(),
            "active_requests_count": len(self._active_requests),
            "active_requests": active_requests_info,
            "stats": stats,
            "config": self.get_skip_old_requests_config()
        }

    def get_queue_stats(self) -> Dict[str, Any]:
        """
        キューの統計情報を取得
        """
        return self._stats.copy()

    def update_skip_old_requests_config(self, skip_old_requests: bool, max_age_sec: Optional[float] = None) -> None:
        """
        古いリクエストスキップ設定を更新
        skip_old_requests: スキップ機能の有効/無効
        max_age_sec: 最大待機時間（秒）、Noneの場合は現在の値を維持
        """
        self._skip_old_requests = skip_old_requests
        if max_age_sec is not None:
            self._request_max_age_sec = max_age_sec
        
        logger.info(
            f"Updated skip old requests config: enabled={self._skip_old_requests}, "
            f"max_age={self._request_max_age_sec}s"
        )

    def get_skip_old_requests_config(self) -> Dict[str, Any]:
        """
        現在の古いリクエストスキップ設定を取得
        """
        return {
            "skip_old_requests": self._skip_old_requests,
            "max_age_sec": self._request_max_age_sec
        }

    def _is_request_too_old(self, request: T) -> bool:
        """
        リクエストが古すぎるかチェック
        """
        if not self._skip_old_requests:
            return False
            
        current_time = time.time()
        request_age = current_time - request.created_at
        
        if request_age > self._request_max_age_sec:
            logger.warning(
                f"Request {request.request_id} is too old ({request_age:.1f}s > {self._request_max_age_sec}s), "
                f"skipping execution"
            )
            return True
            
        return False

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
                    
                    # 古いリクエストのチェック
                    if self._is_request_too_old(request):
                        request.status = RequestStatus.FAILED
                        request.error_message = f"Request skipped due to age (>{self._request_max_age_sec}s)"
                        logger.warning(f"Request {request_id} skipped due to age")
                        self._queue.task_done()
                        self._active_requests.pop(request_id, None)
                        # 統計情報を更新
                        self._stats["skipped_requests"] += 1
                        continue
                    
                    # リクエスト処理中に状態を更新
                    request.status = RequestStatus.PROCESSING
                    self._stats["processing_requests"] += 1
                    
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
                        # 統計情報を更新
                        if request.status == RequestStatus.COMPLETED:
                            self._stats["completed_requests"] += 1
                        elif request.status == RequestStatus.FAILED:
                            self._stats["failed_requests"] += 1
                        elif request.status == RequestStatus.TIMEOUT:
                            self._stats["timeout_requests"] += 1
                        
                        # 処理中カウンタを減らす
                        self._stats["processing_requests"] = max(0, self._stats["processing_requests"] - 1)
                        
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
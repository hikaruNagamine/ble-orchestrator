"""
優先度付きリクエストキューの管理
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Generic, cast

from .config import REQUEST_MAX_AGE_SEC, SKIP_OLD_REQUESTS, SCAN_COMMAND_PARALLEL_WORKERS, SCAN_COMMAND_TIMEOUT_SEC
from .types import BLERequest, RequestPriority, RequestStatus, WriteRequest, ReadRequest, ScanRequest, NotificationRequest

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BLERequest)


class RequestQueueManager(Generic[T]):
    """
    優先度付きリクエストキューマネージャー
    優先度付きキューで逐次処理とタイムアウト監視を行う
    scan_commandは並行処理で高速化
    """

    def __init__(self, worker_func: Callable[[T], Any]):
        """
        初期化
        worker_func: リクエスト処理を行う関数
        """
        self._queue = asyncio.PriorityQueue()  # (優先度, リクエストID, リクエスト)のタプルを格納
        self._scan_queue = asyncio.Queue()  # scan_command専用キュー
        self._active_requests: Dict[str, T] = {}
        self._worker_func = worker_func
        self._stop_event = asyncio.Event()
        self._worker_task = None
        self._scan_worker_tasks = []  # scan_command専用ワーカータスク
        
        # 古いリクエストスキップ設定
        self._skip_old_requests = SKIP_OLD_REQUESTS
        self._request_max_age_sec = REQUEST_MAX_AGE_SEC
        
        # クリーンアップ設定
        self._cleanup_interval = 60  # 60秒ごとにクリーンアップ
        self._last_cleanup = time.time()
        
        # 統計情報
        self._stats = {
            "total_requests": 0,
            "completed_requests": 0,
            "failed_requests": 0,
            "timeout_requests": 0,
            "skipped_requests": 0,
            "processing_requests": 0,
            "scan_requests": 0,
            "scan_completed": 0,
            "scan_failed": 0
        }

    async def start(self) -> None:
        """
        ワーカーを開始
        """
        if self._worker_task is not None:
            logger.warning("Queue worker is already running")
            return

        self._stop_event.clear()
        
        # メインワーカー（send_command, read_command用）
        self._worker_task = asyncio.create_task(self._worker_loop())
        
        # scan_command専用ワーカー（並行処理）
        for i in range(SCAN_COMMAND_PARALLEL_WORKERS):
            scan_worker_task = asyncio.create_task(self._scan_worker_loop(f"scan_worker_{i}"))
            self._scan_worker_tasks.append(scan_worker_task)
        
        logger.info(f"Queue worker started with {SCAN_COMMAND_PARALLEL_WORKERS} scan workers")

    async def stop(self) -> None:
        """
        ワーカーを停止
        """
        if self._worker_task is None:
            return

        logger.info("Stopping queue worker...")
        self._stop_event.set()
        
        # scan_command専用ワーカーを停止
        if self._scan_worker_tasks:
            logger.info(f"Stopping {len(self._scan_worker_tasks)} scan workers...")
            for task in self._scan_worker_tasks:
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except asyncio.TimeoutError:
                    task.cancel()
                    logger.warning("Scan worker task forcibly cancelled")
                except Exception as e:
                    logger.error(f"Error stopping scan worker: {e}")
            self._scan_worker_tasks.clear()
        
        # メインワーカーを停止
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
            
        # scan_commandは専用キューに振り分け
        if isinstance(request, ScanRequest):
            await self._scan_queue.put(request)
            self._active_requests[request.request_id] = request
            self._stats["total_requests"] += 1
            self._stats["scan_requests"] += 1
            
            logger.info(
                f"Enqueued scan request {request.request_id} for {request.mac_address} "
                f"to scan queue (parallel processing)"
            )
            return request.request_id
        
        # その他のリクエストは通常の優先度キューに追加
        priority_value = request.priority.value
        
        # キューに追加
        await self._queue.put((priority_value, request.request_id, request))
        self._active_requests[request.request_id] = request
        
        # 統計情報を更新
        self._stats["total_requests"] += 1
        
        logger.info(
            f"Enqueued request {request.request_id} for {request.mac_address} "
            f"with priority {RequestPriority(priority_value).name}"
        )
        
        return request.request_id

    async def get_request_status(self, request_id: str) -> Optional[T]:
        """
        リクエストのステータスを取得
        """
        return self._active_requests.get(request_id)

    def get_queue_size(self) -> int:
        """
        キューサイズを取得（メインキュー + scanキュー）
        """
        return self._queue.qsize() + self._scan_queue.qsize()

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
        stats["scan_queue_size"] = self._scan_queue.qsize()
        stats["scan_workers"] = len(self._scan_worker_tasks)
        
        return {
            "queue_size": self._queue.qsize(),
            "scan_queue_size": self._scan_queue.qsize(),
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
                    # 定期的なクリーンアップを実行
                    await self._cleanup_old_requests()
                    
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
                        f"with priority {RequestPriority(priority).name}"
                    )
                    
                    # 古いリクエストのチェック（処理前に実行）
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

    async def _cleanup_old_requests(self) -> None:
        """
        古いリクエストを定期的にクリーンアップ
        """
        current_time = time.time()
        
        # クリーンアップ間隔をチェック
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
            
        self._last_cleanup = current_time
        
        # 古いリクエストを特定して削除
        old_requests = []
        for request_id, request in list(self._active_requests.items()):
            request_age = current_time - request.created_at
            
            # 完了済みまたは古すぎるリクエストを削除
            if (request.status in [RequestStatus.COMPLETED, RequestStatus.FAILED, RequestStatus.TIMEOUT] or
                request_age > self._request_max_age_sec * 1.5):  # 最大年齢の1.5倍に短縮
                old_requests.append(request_id)
        
        # 古いリクエストを削除
        for request_id in old_requests:
            request = self._active_requests.pop(request_id, None)
            if request:
                logger.debug(f"Cleaned up old request {request_id} (age: {current_time - request.created_at:.1f}s, status: {request.status.name})")
        
        if old_requests:
            logger.info(f"Cleaned up {len(old_requests)} old requests")
            
        # キューサイズが大きすぎる場合の警告
        queue_size = self._queue.qsize()
        scan_queue_size = self._scan_queue.qsize()
        total_queue_size = queue_size + scan_queue_size
        
        if total_queue_size > 20:
            logger.warning(f"Total queue size is large: {total_queue_size} requests pending (main: {queue_size}, scan: {scan_queue_size})")
        elif total_queue_size > 50:
            logger.error(f"Total queue size is very large: {total_queue_size} requests pending - consider restarting service")

    async def _scan_worker_loop(self, worker_name: str) -> None:
        """
        scan_command専用の並行ワーカーループ
        """
        logger.info(f"Scan worker {worker_name} started")
        
        try:
            while not self._stop_event.is_set():
                try:
                    # タイムアウト付きでscan_commandを取得
                    try:
                        request = await asyncio.wait_for(
                            self._scan_queue.get(), timeout=0.1
                        )
                    except asyncio.TimeoutError:
                        continue
                    
                    logger.debug(
                        f"Scan worker {worker_name} processing request {request.request_id} "
                        f"for {request.mac_address}"
                    )
                    
                    # 古いリクエストのチェック
                    if self._is_request_too_old(request):
                        request.status = RequestStatus.FAILED
                        request.error_message = f"Request skipped due to age (>{self._request_max_age_sec}s)"
                        logger.warning(f"Scan request {request.request_id} skipped due to age")
                        self._scan_queue.task_done()
                        self._active_requests.pop(request.request_id, None)
                        self._stats["skipped_requests"] += 1
                        self._stats["scan_failed"] += 1
                        continue
                    
                    # リクエスト処理中に状態を更新
                    request.status = RequestStatus.PROCESSING
                    self._stats["processing_requests"] += 1
                    
                    try:
                        # scan_command専用の短いタイムアウトで処理
                        await asyncio.wait_for(
                            self._worker_func(request),
                            timeout=SCAN_COMMAND_TIMEOUT_SEC
                        )
                        request.status = RequestStatus.COMPLETED
                        self._stats["scan_completed"] += 1
                        logger.debug(f"Scan request {request.request_id} completed by {worker_name}")
                    except asyncio.TimeoutError:
                        request.status = RequestStatus.TIMEOUT
                        request.error_message = "Scan request timed out"
                        logger.error(f"Scan request {request.request_id} timed out after {SCAN_COMMAND_TIMEOUT_SEC} seconds")
                        self._stats["scan_failed"] += 1
                    except Exception as e:
                        request.status = RequestStatus.FAILED
                        request.error_message = str(e)
                        logger.error(f"Scan request {request.request_id} failed with error: {e}")
                        self._stats["scan_failed"] += 1
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
                        self._scan_queue.task_done()
                        
                        # 処理完了したリクエストはactive_requestsから削除
                        if request.status in [RequestStatus.COMPLETED, RequestStatus.FAILED, RequestStatus.TIMEOUT]:
                            self._active_requests.pop(request.request_id, None)
                
                except asyncio.CancelledError:
                    logger.info(f"Scan worker {worker_name} cancelled")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in scan worker {worker_name}: {e}")
                    await asyncio.sleep(1.0)
        finally:
            logger.info(f"Scan worker {worker_name} terminated") 
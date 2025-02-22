import asyncio
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from ..types.request_task import RequestTask, CommandType, TaskResult
from ..exceptions import QueueFullError, TaskExecutionError

logger = logging.getLogger(__name__)

class QueueMetrics:
    """キューのメトリクス管理"""
    def __init__(self):
        self.total_processed: int = 0
        self.failed_tasks: int = 0
        self._processing_times: List[float] = []

    @property
    def average_processing_time(self) -> float:
        if not self._processing_times:
            return 0.0
        return sum(self._processing_times) / len(self._processing_times)

    def add_processing_time(self, time: float) -> None:
        self._processing_times.append(time)
        if len(self._processing_times) > 1000:  # 直近1000件のみ保持
            self._processing_times.pop(0)

class RequestQueue:
    """非同期リクエストキューマネージャー

    Attributes:
        _queue: タスクキュー
        _max_size: キューの最大サイズ
        _metrics: キューのメトリクス
    """
    def __init__(self, max_size: int = 1000, session_factory=None):
        self._queue: List[RequestTask] = []
        self._is_processing: bool = False
        self._process_task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_factory = session_factory or aiohttp.ClientSession
        self._max_size = max_size
        self._metrics = QueueMetrics()

    async def start(self):
        """キュー処理の開始"""
        logger.info("Starting request queue")
        self._session = self._session_factory()
        self._process_task = asyncio.create_task(self._process_queue())

    async def stop(self):
        """キュー処理の停止"""
        logger.info("Stopping request queue")
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()

    def enqueue(self, task: RequestTask) -> None:
        """タスクをキューに追加"""
        if len(self._queue) >= self._max_size:
            raise QueueFullError(f"Queue is full (max size: {self._max_size})")

        logger.debug(f"Enqueueing task {task.id}")
        self._queue.append(task)
        self._sort_queue()
        
        if not self._is_processing:
            asyncio.create_task(self._process_queue())

    def _sort_queue(self) -> None:
        """優先順位とタイムスタンプでソート"""
        self._queue.sort(key=lambda x: (-1 * (x.priority or 0), x.timestamp))

    async def _process_queue(self) -> None:
        """キューの処理"""
        while True:
            if not self._queue:
                self._is_processing = False
                await asyncio.sleep(0.1)
                continue

            self._is_processing = True
            task = self._queue.pop(0)
            start_time = datetime.now().timestamp()

            try:
                await self._execute_task(task)
                self._metrics.total_processed += 1
            except Exception as e:
                self._metrics.failed_tasks += 1
                logger.error(f"Error processing task {task.id}: {e}", exc_info=True)
            finally:
                processing_time = datetime.now().timestamp() - start_time
                self._metrics.add_processing_time(processing_time)
                await asyncio.sleep(0.1)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def _execute_task(self, task: RequestTask) -> TaskResult:
        """タスクの実行"""
        if not self._session:
            raise TaskExecutionError("Session not initialized")

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {"Content-Type": "application/json"}
            data = None
            if task.type == CommandType.SEND and task.payload:
                data = json.dumps(task.payload)

            async with self._session.request(
                method=task.type.value,
                url=task.url,
                headers=headers,
                data=data,
                timeout=timeout
            ) as response:
                if response.status >= 400:
                    raise TaskExecutionError(f"Request failed with status {response.status}")
                
                result = await response.json()
                logger.info(f"Task {task.id} completed successfully")
                return {"status": "success", "data": result, "error": None}

        except Exception as e:
            logger.error(f"Task execution error: {e}", exc_info=True)
            raise TaskExecutionError(f"Task execution failed: {str(e)}")

    @property
    def metrics(self) -> QueueMetrics:
        """キューのメトリクスを取得"""
        return self._metrics 
import pytest
from unittest.mock import AsyncMock, Mock
from datetime import datetime

from ble_controller.services.request_queue import RequestQueue
from ble_controller.types.request_task import RequestTask, CommandType
from ble_controller.exceptions import QueueFullError

@pytest.fixture
async def queue():
    """テスト用のRequestQueueインスタンスを作成"""
    mock_session = AsyncMock()
    queue = RequestQueue(max_size=2, session_factory=lambda: mock_session)
    await queue.start()
    yield queue
    await queue.stop()

@pytest.mark.asyncio
async def test_enqueue_max_size(queue):
    """キューの最大サイズテスト"""
    # 2つのタスクを追加（最大サイズ）
    task1 = RequestTask(id="1", type=CommandType.GET, url="/test")
    task2 = RequestTask(id="2", type=CommandType.GET, url="/test")
    queue.enqueue(task1)
    queue.enqueue(task2)

    # 3つ目のタスクを追加すると例外が発生
    task3 = RequestTask(id="3", type=CommandType.GET, url="/test")
    with pytest.raises(QueueFullError):
        queue.enqueue(task3)

@pytest.mark.asyncio
async def test_priority_ordering(queue):
    """優先順位のテスト"""
    task1 = RequestTask(id="1", type=CommandType.GET, url="/test", priority=1)
    task2 = RequestTask(id="2", type=CommandType.GET, url="/test", priority=2)
    
    queue.enqueue(task1)
    queue.enqueue(task2)

    assert queue._queue[0].id == "2"  # 優先順位の高いタスクが先頭に 
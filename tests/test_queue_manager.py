"""
queue_manager.pyのユニットテスト
"""

import asyncio
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch, call

from ble_orchestrator.orchestrator.types import BLERequest, RequestPriority, RequestStatus
from ble_orchestrator.orchestrator.queue_manager import RequestQueueManager


@pytest.fixture
def sample_request():
    """サンプルのBLERequestを作成"""
    return BLERequest(
        request_id=str(uuid.uuid4()),
        mac_address="AA:BB:CC:DD:EE:FF",
        priority=RequestPriority.NORMAL,
        timeout_sec=1.0
    )


@pytest.fixture
def high_priority_request():
    """高優先度のBLERequestを作成"""
    return BLERequest(
        request_id=str(uuid.uuid4()),
        mac_address="AA:BB:CC:DD:EE:FF",
        priority=RequestPriority.HIGH,
        timeout_sec=1.0
    )


@pytest.fixture
def low_priority_request():
    """低優先度のBLERequestを作成"""
    return BLERequest(
        request_id=str(uuid.uuid4()),
        mac_address="AA:BB:CC:DD:EE:FF",
        priority=RequestPriority.LOW,
        timeout_sec=1.0
    )


class TestRequestQueueManager:
    """RequestQueueManagerクラスのテスト"""

    @pytest.mark.asyncio
    async def test_enqueue_request(self, sample_request):
        """リクエストをキューに追加できることを確認"""
        # ワーカー関数のモック
        worker_func = AsyncMock()
        
        # キューマネージャーの作成
        queue_manager = RequestQueueManager(worker_func)
        
        # リクエストをキューに追加
        request_id = await queue_manager.enqueue_request(sample_request)
        
        # 返却されたIDが正しいことを確認
        assert request_id == sample_request.request_id
        
        # キューサイズが1増えることを確認
        assert queue_manager.get_queue_size() == 1
        
        # アクティブリクエストに追加されることを確認
        assert request_id in queue_manager._active_requests
        assert queue_manager._active_requests[request_id] == sample_request

    @pytest.mark.asyncio
    async def test_get_request_status(self, sample_request):
        """リクエストステータスが取得できることを確認"""
        worker_func = AsyncMock()
        queue_manager = RequestQueueManager(worker_func)
        
        # リクエストをキューに追加
        request_id = await queue_manager.enqueue_request(sample_request)
        
        # ステータスを取得
        status = await queue_manager.get_request_status(request_id)
        
        # 正しいリクエストが返されることを確認
        assert status == sample_request
        
        # 存在しないIDの場合はNoneが返ることを確認
        status = await queue_manager.get_request_status("nonexistent-id")
        assert status is None

    @pytest.mark.asyncio
    async def test_get_queue_size(self, sample_request, high_priority_request):
        """キューサイズが正しく取得できることを確認"""
        worker_func = AsyncMock()
        queue_manager = RequestQueueManager(worker_func)
        
        # キューが空の状態
        assert queue_manager.get_queue_size() == 0
        
        # リクエストを追加
        await queue_manager.enqueue_request(sample_request)
        assert queue_manager.get_queue_size() == 1
        
        # さらにリクエストを追加
        await queue_manager.enqueue_request(high_priority_request)
        assert queue_manager.get_queue_size() == 2

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """キューマネージャーの起動と停止が正しく行われることを確認"""
        worker_func = AsyncMock()
        queue_manager = RequestQueueManager(worker_func)
        
        # 開始前はワーカータスクがNone
        assert queue_manager._worker_task is None
        
        # 開始
        await queue_manager.start()
        
        # ワーカータスクが作成されることを確認
        assert queue_manager._worker_task is not None
        assert not queue_manager._stop_event.is_set()
        
        # 停止
        await queue_manager.stop()
        
        # ワーカータスクがNoneに戻ることを確認
        assert queue_manager._worker_task is None
        assert queue_manager._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_priority_ordering(self, sample_request, high_priority_request, low_priority_request):
        """優先度順に処理されることを確認"""
        # ワーカー関数は非同期の関数をモックしているが実際には処理を行わない
        worker_func = AsyncMock()
        
        queue_manager = RequestQueueManager(worker_func)
        
        # リクエストを逆順に追加（優先度: 低 > 普通 > 高）
        await queue_manager.enqueue_request(low_priority_request)
        await queue_manager.enqueue_request(sample_request)
        await queue_manager.enqueue_request(high_priority_request)
        
        # priorityの値を取得
        low_pri = low_priority_request.priority.value
        normal_pri = sample_request.priority.value
        high_pri = high_priority_request.priority.value
        
        # キュー内の順序を確認（実装依存部分なので慎重に）
        items = []
        while not queue_manager._queue.empty():
            item = await queue_manager._queue.get()
            items.append(item)
            queue_manager._queue.task_done()
        
        # 優先度順（値が小さいほど優先度が高い）になっていることを確認
        assert items[0][0] == high_pri  # 優先度: 高
        assert items[1][0] == normal_pri  # 優先度: 普通
        assert items[2][0] == low_pri  # 優先度: 低

    @pytest.mark.asyncio
    async def test_worker_loop_processing(self, sample_request):
        """ワーカーループがリクエストを処理することを確認"""
        # ワーカー関数のモック
        worker_func = AsyncMock()
        
        # キューマネージャーの作成と開始
        queue_manager = RequestQueueManager(worker_func)
        await queue_manager.start()
        
        # リクエストを追加
        await queue_manager.enqueue_request(sample_request)
        
        # リクエストが処理されるまで少し待つ
        await asyncio.sleep(0.2)
        
        # ワーカー関数が呼ばれたことを確認
        worker_func.assert_called_once_with(sample_request)
        
        # アクティブリクエストから削除されることを確認（処理完了後）
        assert sample_request.request_id not in queue_manager._active_requests
        
        # 停止
        await queue_manager.stop()

    @pytest.mark.asyncio
    async def test_worker_timeout(self, sample_request):
        """ワーカー処理のタイムアウトが正しく処理されることを確認"""
        # タイムアウトするワーカー関数のモック
        async def timeout_worker(request):
            await asyncio.sleep(10.0)  # 長時間待機
        
        # キューマネージャーの作成と開始
        queue_manager = RequestQueueManager(timeout_worker)
        await queue_manager.start()
        
        # 短いタイムアウトを設定したリクエストを追加
        sample_request.timeout_sec = 0.1  # 100ms
        await queue_manager.enqueue_request(sample_request)
        
        # タイムアウトするまで少し待つ
        await asyncio.sleep(0.2)
        
        # リクエストがタイムアウトステータスになることを確認
        assert sample_request.status == RequestStatus.TIMEOUT
        assert "timed out" in sample_request.error_message.lower()
        
        # アクティブリクエストから削除されることを確認
        assert sample_request.request_id not in queue_manager._active_requests
        
        # 停止
        await queue_manager.stop()

    @pytest.mark.asyncio
    async def test_worker_error(self, sample_request):
        """ワーカー処理のエラーが正しく処理されることを確認"""
        # エラーを発生させるワーカー関数のモック
        async def error_worker(request):
            raise ValueError("Test error")
        
        # キューマネージャーの作成と開始
        queue_manager = RequestQueueManager(error_worker)
        await queue_manager.start()
        
        # リクエストを追加
        await queue_manager.enqueue_request(sample_request)
        
        # エラーが発生するまで少し待つ
        await asyncio.sleep(0.2)
        
        # リクエストがエラーステータスになることを確認
        assert sample_request.status == RequestStatus.FAILED
        assert "test error" in sample_request.error_message.lower()
        
        # アクティブリクエストから削除されることを確認
        assert sample_request.request_id not in queue_manager._active_requests
        
        # 停止
        await queue_manager.stop() 
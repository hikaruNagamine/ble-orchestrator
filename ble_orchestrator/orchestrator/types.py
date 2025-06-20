"""
BLE Orchestratorで使用する型定義
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional, List, Callable, Awaitable, Union
from dataclasses_json import dataclass_json
import asyncio
import time


class RequestPriority(Enum):
    """リクエストの優先度"""
    HIGH = 0
    NORMAL = 1
    LOW = 2


class RequestStatus(Enum):
    """リクエスト処理状態"""
    PENDING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    FAILED = auto()
    TIMEOUT = auto()


@dataclass_json
@dataclass
class ScanResult:
    """スキャン結果"""
    address: str
    name: Optional[str] = None
    rssi: Optional[int] = None
    advertisement_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass_json
@dataclass
class BLERequest:
    """BLEリクエスト基本クラス"""
    request_id: str
    mac_address: str
    priority: RequestPriority = RequestPriority.NORMAL
    timeout_sec: float = 10.0
    status: RequestStatus = RequestStatus.PENDING
    error_message: Optional[str] = None
    response_data: Any = None
    created_at: float = field(default_factory=time.time)  # リクエスト作成時刻
    _done_event: asyncio.Event = field(default_factory=asyncio.Event, compare=False)

    async def wait_until_done(self, timeout: Optional[float] = None) -> None:
        """
        リクエストが完了するまで待機
        timeout: 待機タイムアウト（秒）
        """
        await asyncio.wait_for(self._done_event.wait(), timeout=timeout)

    def mark_as_done(self) -> None:
        """
        リクエストを完了としてマーク
        """
        self._done_event.set()


@dataclass_json
@dataclass
class ScanRequest(BLERequest):
    """
    スキャン要求
    デバイスに接続せずにスキャンキャッシュからデータを取得
    service_uuidとcharacteristic_uuidを指定すると、そのサービス/特性の情報のみを返す
    """
    service_uuid: Optional[str] = None
    characteristic_uuid: Optional[str] = None
    
    def __str__(self) -> str:
        return (
            f"ScanRequest(id={self.request_id}, "
            f"mac={self.mac_address}, "
            f"service={self.service_uuid}, "
            f"char={self.characteristic_uuid})"
        )


@dataclass_json
@dataclass
class ReadRequest(BLERequest):
    """センサー読み取り要求"""
    service_uuid: str = ""
    characteristic_uuid: str = ""
    response_data: Optional[bytearray] = None


@dataclass_json
@dataclass
class WriteRequest(BLERequest):
    """コマンド送信要求"""
    service_uuid: str = ""
    characteristic_uuid: str = ""
    data: bytes = field(default_factory=bytes)
    response_required: bool = False
    response_data: Optional[bytearray] = None


@dataclass_json
@dataclass
class NotificationRequest(BLERequest):
    """通知サブスクリプション要求"""
    service_uuid: str = ""
    characteristic_uuid: str = ""
    callback_id: str = ""  # 通知時のコールバック識別子
    # 0の場合は明示的に停止するまで継続（無限）
    notification_timeout_sec: float = 0.0
    # サブスクリプション解除用
    unsubscribe: bool = False


@dataclass_json
@dataclass
class NotificationData:
    """通知データ"""
    callback_id: str
    mac_address: str
    characteristic_uuid: str
    value: bytes
    timestamp: float


@dataclass
class ServiceStatus:
    """サービスステータス"""
    is_running: bool = True
    adapter_status: str = "ok"
    queue_size: int = 0
    last_error: Optional[str] = None
    uptime_sec: float = 0.0
    active_subscriptions: int = 0  # 通知サブスクリプション数 
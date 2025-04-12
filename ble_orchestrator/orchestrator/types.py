"""
BLE Orchestratorで使用する型定義
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional, List, Callable, Awaitable, Union
from dataclasses_json import dataclass_json


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


@dataclass_json
@dataclass
class ScanRequest(BLERequest):
    """スキャン要求"""
    pass


@dataclass_json
@dataclass
class ReadRequest(BLERequest):
    """センサー読み取り要求"""
    service_uuid: str
    characteristic_uuid: str
    response_data: Optional[bytearray] = None


@dataclass_json
@dataclass
class WriteRequest(BLERequest):
    """コマンド送信要求"""
    service_uuid: str
    characteristic_uuid: str
    data: bytes = field(default_factory=bytes)
    response_required: bool = False
    response_data: Optional[bytearray] = None


@dataclass
class ServiceStatus:
    """サービスステータス"""
    is_running: bool = True
    adapter_status: str = "ok"
    queue_size: int = 0
    last_error: Optional[str] = None
    uptime_sec: float = 0.0 
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Dict, TypedDict
from datetime import datetime

class CommandType(Enum):
    GET = "GET"
    SEND = "SEND"

class BLEDeviceData(TypedDict):
    address: str
    name: str
    rssi: int
    timestamp: str
    manufacturer_data: Dict[int, bytes]

class TaskResult(TypedDict):
    status: str
    data: Optional[Dict[str, Any]]
    error: Optional[str]

@dataclass(order=True)
class RequestTask:
    """リクエストタスクの定義

    Attributes:
        id: タスクの一意識別子
        type: GETまたはSENDのリクエストタイプ
        url: リクエスト先のエンドポイント
        priority: 優先順位（高いほど優先）
        payload: リクエストのデータ
        timestamp: タスク作成時刻
    """
    id: str
    type: CommandType
    url: str
    priority: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    def __post_init__(self):
        if self.priority is None:
            self.priority = 0 
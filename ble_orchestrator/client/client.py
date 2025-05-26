"""
BLE Orchestratorのクライアントライブラリ
UNIXソケットまたはTCPソケットを使ってIPC通信を行う
"""

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any, Dict, List, Optional, Union, Callable, Awaitable
from .request_client import BLERequestClient
from .notification_client import BLENotificationClient

logger = logging.getLogger(__name__)

class BLEOrchestratorClient:
    """
    BLE Orchestratorのクライアント
    シンプルなインターフェースでBLE操作を要求
    リクエスト用とノーティフィケーション用に別々のソケット接続を使用
    """
    def __init__(self, socket_path: Optional[str] = None, host: Optional[str] = None, port: Optional[int] = None, timeout: float = 10.0):
        """
        初期化
        socket_path: UNIXソケットパス（Linuxのみ）
        host, port: TCPソケットパラメータ
        timeout: 通信タイムアウト
        """
        self.req = BLERequestClient(socket_path, host, port, timeout)
        self.notif = BLENotificationClient(socket_path, host, port, timeout)

    async def connect(self) -> None:
        """
        サーバーに接続（リクエスト用とノーティフィケーション用の両方）
        """
        await self.req.connect()
        await self.notif.connect()
        logger.debug("Connected to BLE Orchestrator (both request and notification)")

    async def disconnect(self) -> None:
        """
        接続を閉じる（リクエスト用とノーティフィケーション用の両方）
        """
        await self.req.disconnect()
        await self.notif.disconnect()
        logger.debug("Disconnected from BLE Orchestrator (both request and notification)")

    # ---------------- リクエスト関連のProxy関数 ----------------

    async def read_command(
        self, 
        mac_address: str, 
        service_uuid: str, 
        characteristic_uuid: str,
        priority: str = "NORMAL",
        timeout: float = 10.0
    ) -> asyncio.Future:
        """
        デバイスの特性値を読み取るコマンドをリクエスト
        Futureを返すので、await result_future で結果を取得できる
        """
        return await self.req.read_command(
            mac_address, service_uuid, characteristic_uuid, priority, timeout
        )
        
    async def scan_command(
        self,
        mac_address: str,
        service_uuid: Optional[str] = None,
        characteristic_uuid: Optional[str] = None
    ) -> asyncio.Future:
        """
        スキャン済みデータからデバイスの情報を取得
        デバイスに接続せずに、最後のスキャン結果からデータを返す
        Futureを返すので、await result_future で結果を取得できる
        """
        return await self.req.scan_command(
            mac_address, service_uuid, characteristic_uuid
        )

    async def send_command(
        self, 
        mac_address: str, 
        service_uuid: str, 
        characteristic_uuid: str,
        data: Union[str, bytes, List[int]],
        response_required: bool = False,
        priority: str = "NORMAL",
        timeout: float = 10.0
    ) -> asyncio.Future:
        """
        コマンド送信をリクエスト
        Futureを返すので、await result_future で結果を取得できる
        """
        return await self.req.send_command(
            mac_address, service_uuid, characteristic_uuid, 
            data, response_required, priority, timeout
        )

    # ---------------- 通知関連のProxy関数 ----------------

    async def subscribe_notifications(
        self,
        mac_address: str,
        service_uuid: str,
        characteristic_uuid: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
        callback_id: Optional[str] = None,
    ) -> str:
        """
        BLE通知を購読
        callback: 通知を受信したときに呼び出される非同期コールバック関数
        callback_id: コールバックの識別子（省略時は自動生成）
        """
        return await self.notif.subscribe_notifications(
            mac_address, service_uuid, characteristic_uuid, callback, callback_id
        )

    async def unsubscribe_notifications(
        self,
        callback_id: str
    ) -> bool:
        """
        通知購読を解除
        """
        return await self.notif.unsubscribe_notifications(callback_id) 
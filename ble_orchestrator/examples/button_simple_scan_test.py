import asyncio
import time
import logging
from typing import Dict, Optional
from bleak import BleakScanner
from bleak.backends.device import BLEDevice

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ターゲットデバイスのMACアドレス
TARGET_DEVICE_MAC = "F1:2E:40:2A:67:6B"  # SwitchBotボタンのMACアドレス

# スキャン間隔 (秒)
SCAN_INTERVAL = 0.5

# 保存する履歴数
HISTORY_SIZE = 5

# スキャン実行時間 (秒)
SCAN_DURATION = 180

class SwitchbotButtonScanner:
    def __init__(self, target_mac: str):
        self.target_mac = target_mac.lower()
        self.last_data: Dict[str, bytes] = {}
        self.data_history: Dict[str, list] = {}
        self.last_seen = 0
        self.detection_count = 0
        self.is_running = True
        
    def _initialize_data_fields(self):
        """データフィールドを初期化"""
        self.data_history = {
            "service_data": [],
            "manufacturer_data": [],
            "rssi": []
        }
    
    def _record_data(self, device: BLEDevice):
        """デバイスデータを記録"""
        if not hasattr(device, "details"):
            return
            
        # RSSI記録
        if hasattr(device, "rssi"):
            self._add_to_history("rssi", device.rssi)
            
        # アドバタイズデータの取得
        adv_data = {}
        if hasattr(device, "metadata"):
            adv_data = device.metadata.get("advertisement_data", {})
        
        # サービスデータの記録
        service_data = adv_data.get("service_data", {})
        if service_data:
            self._add_to_history("service_data", service_data)
            
        # メーカーデータの記録
        manufacturer_data = adv_data.get("manufacturer_data", {})
        if manufacturer_data:
            self._add_to_history("manufacturer_data", manufacturer_data)
            
        # 現在の時刻を記録
        self.last_seen = time.time()
    
    def _add_to_history(self, field: str, value):
        """履歴に追加"""
        if field not in self.data_history:
            self.data_history[field] = []
            
        self.data_history[field].append(value)
        
        # 履歴サイズを制限
        if len(self.data_history[field]) > HISTORY_SIZE:
            self.data_history[field].pop(0)
    
    def _detect_changes(self) -> Optional[str]:
        """データ変更を検出"""
        # 履歴が少なすぎる場合は判定しない
        for field, values in self.data_history.items():
            if len(values) < 2:
                continue
                
            if field == "service_data":
                # サービスデータの変化を検出
                last = values[-1]
                prev = values[-2]
                
                # 特定のサービスUUIDのデータ変化を確認
                for uuid, data in last.items():
                    if uuid in prev and prev[uuid] != data:
                        self.detection_count += 1
                        return f"サービスデータ変化: {uuid}, 前: {prev[uuid].hex()}, 後: {data.hex()}"
                        
            elif field == "manufacturer_data":
                # メーカーデータの変化を検出
                last = values[-1]
                prev = values[-2]
                
                for company_id, data in last.items():
                    if company_id in prev and prev[company_id] != data:
                        self.detection_count += 1
                        return f"メーカーデータ変化: {company_id}, 前: {prev[company_id]}, 後: {data}"
                        
            elif field == "rssi":
                # RSSIの大きな変化を検出 (ボタン押下でRSSIが変わることがある)
                last = values[-1]
                prev = values[-2]
                
                if abs(last - prev) > 10:  # 10dBm以上の変化を検出
                    self.detection_count += 1
                    return f"RSSI変化: {prev} -> {last}"
                    
        return None
                
    async def scan_and_detect(self):
        """スキャンして変化を検出"""
        self._initialize_data_fields()
        
        print(f"🔍 {self.target_mac} のスキャンを開始します")
        print(f"📱 ボタンを押してください（{SCAN_DURATION}秒間監視します）")
        
        start_time = time.time()
        
        while self.is_running and (time.time() - start_time) < SCAN_DURATION:
            try:
                # スキャンを実行
                devices = await BleakScanner.discover(timeout=SCAN_INTERVAL)
                
                # ターゲットデバイスを探す
                for device in devices:
                    if device.address.lower() == self.target_mac:
                        # デバイス情報表示
                        if time.time() - self.last_seen > 1.0:  # 前回表示から1秒以上経過
                            print(f"📡 デバイス検出: {device.address}, RSSI: {device.rssi}dBm")
                        
                        # データを記録
                        self._record_data(device)
                        
                        # 変化を検出
                        change = self._detect_changes()
                        if change:
                            print("\n" + "="*50)
                            print(f"⚡ 変化検出！ [{time.strftime('%H:%M:%S')}]")
                            print(f"📊 {change}")
                            print("="*50 + "\n")
                
                # 数秒ごとに進行状況を表示
                elapsed = time.time() - start_time
                if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                    remaining = SCAN_DURATION - elapsed
                    print(f"⏳ 残り約{int(remaining)}秒...")
                
                # 短時間待機
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"スキャン中にエラー: {e}")
                await asyncio.sleep(1)
        
        # 結果を表示
        print("\n📊 スキャン結果サマリー:")
        print(f"⏱️ スキャン時間: {time.time() - start_time:.1f}秒")
        print(f"🔍 検出した変化: {self.detection_count}件")
        
        if self.detection_count > 0:
            print("✅ ボタンの押下イベントを検出できました！")
        else:
            print("❌ ボタンの押下イベントを検出できませんでした")
            
        print("\n💡 ヒント: スキャンの検出感度を上げるには、ボタンをデバイスに近づけてください")

async def main():
    # SwitchBotボタンスキャナーを作成
    scanner = SwitchbotButtonScanner(TARGET_DEVICE_MAC)
    
    # スキャン実行
    await scanner.scan_and_detect()

if __name__ == "__main__":
    # メインループ実行
    asyncio.run(main())
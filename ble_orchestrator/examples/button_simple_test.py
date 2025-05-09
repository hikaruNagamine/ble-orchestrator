from bleak import BleakClient
import asyncio
import logging
import time

# ロギング設定を修正 - bleakのログレベルを上げて、メインアプリは詳細に
logging.basicConfig(level=logging.INFO)  # メインは INFO レベル
logger = logging.getLogger(__name__)
# Bleakの詳細なログを抑制
logging.getLogger("bleak").setLevel(logging.WARNING)

async def dump_services(mac):
    print(f"デバイス {mac} のサービス情報を取得中...")
    async with BleakClient(mac) as client:
        svcs = await client.get_services()
        for svc in svcs:
            print(f"[Service] {svc.uuid}")
            for char in svc.characteristics:
                print(f"  [Char] {char.uuid} - {char.properties}")
    print("サービス情報取得完了\n")

async def main():
    # デバイスアドレス
    # device_address = "F1:2E:40:2A:67:6B"
    device_address = "34:85:18:18:57:C2"

    # 通知の記録用リスト
    notifications = []
    
    # 通知ハンドラー
    def notification_handler(sender, data):
        timestamp = time.time()
        hex_data = data.hex()
        notifications.append((timestamp, hex_data))
        
        # 見やすい区切り線を追加
        print("\n" + "="*50)
        print(f"⏰ 時間: {time.strftime('%H:%M:%S', time.localtime(timestamp))}")
        print(f"📱 通知データ: {hex_data}")
        print("="*50 + "\n")
    
    try:
        # サービス情報の表示
        await dump_services(device_address)
        
        # 接続
        print(f"デバイス {device_address} に接続中...")
        async with BleakClient(device_address) as client:
            print("✅ 接続成功")
            
            # 特性を監視するためのセットアップコマンド送信
            write_char = "cba20002-224d-11e6-9fb8-0002a5d5c51b"
            
            # モニタリングコマンドを送信 
            monitor_cmd = bytes([0x57, 0x01, 0x01]) 
            await client.write_gatt_char(write_char, monitor_cmd)
            print(f"✅ モニタリングコマンド送信完了: {monitor_cmd.hex()}")
            
            # 通知を有効化
            notify_char = "cba20003-224d-11e6-9fb8-0002a5d5c51b"
            await client.start_notify(notify_char, notification_handler)
            print("✅ 通知の有効化が完了しました")
            
            # 一定時間待機してボタンを押す時間を確保
            print("\n🔴 ボタンを押してみてください (60秒間待機します)...")
            print("   通知を受信したら、ここに表示されます\n")
            
            # 10秒ごとにカウントダウンを表示
            for i in range(6):
                await asyncio.sleep(10)
                remaining = 60 - (i+1)*10
                if remaining > 0:
                    print(f"⏳ 残り {remaining} 秒...")
            
            # 通知を無効化
            if client.is_connected:
                await client.stop_notify(notify_char)
                print("\n✅ 通知の無効化が完了しました")
            else:
                print("\n⚠️ クライアントは既に切断されています")

            print("\n✅ 通知の無効化が完了しました")
            
            # 結果のサマリーを表示
            print("\n📊 テスト結果サマリー:")
            if len(notifications) == 0:
                print("  通知は受信されませんでした")
            else:
                print(f"  受信した通知の数: {len(notifications)}")
                print("  通知データ一覧:")
                for i, (ts, data) in enumerate(notifications):
                    time_str = time.strftime('%H:%M:%S', time.localtime(ts))
                    print(f"  {i+1}. [{time_str}] {data}")
            
    except Exception as e:
        print(f"❌ エラー発生: {e}")

# スクリプト実行
if __name__ == "__main__":
    asyncio.run(main())
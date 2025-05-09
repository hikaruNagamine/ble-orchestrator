from bleak import BleakClient

async def dump_services(mac):
    async with BleakClient(mac) as client:
        svcs = await client.get_services()
        for svc in svcs:
            print(f"[Service] {svc.uuid}")
            for char in svc.characteristics:
                print(f"  [Char] {char.uuid} - {char.properties}")

import asyncio

# switchbot outdoor_meter
# asyncio.run(dump_services("E3:AB:70:A4:21:51"))

# switchbot plug-mini
# asyncio.run(dump_services("34:85:18:18:57:C2"))

# switchbot switchbot-remote (button)
asyncio.run(dump_services("F1:2E:40:2A:67:6B"))
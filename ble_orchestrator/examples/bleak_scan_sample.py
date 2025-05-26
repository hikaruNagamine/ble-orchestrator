import asyncio
from bleak import BleakScanner
import sys
import time

def format_manufacturer_data(manufacturer_data):
    if not manufacturer_data:
        return "None"
    
    result = []
    for company_id, data in manufacturer_data.items():
        company_id_hex = f"0x{company_id:04x}"
        # 16進数で表示
        result.append(f"Company ID {company_id_hex}: {data.hex()}")
        # 10進数で表示
        result.append(f"Company ID {company_id_hex} (decimal): {[b for b in data]}")
    
    return "\n    ".join(result)

async def scan_ble_devices(target_address=None, scan_time=5):
    print(f"Starting BLE scan on hci1 adapter...")
    
    # Create scanner instance with hci1 adapter
    scanner = BleakScanner(detection_callback=None, adapter="hci1")
    
    # Start scanning
    await scanner.start()
    print(f"Scanning for {scan_time} seconds...")
    
    # Wait for specified scan time
    await asyncio.sleep(scan_time)
    
    # Stop scanning
    await scanner.stop()
    print("Scan stopped.")
    
    # Get discovered devices with advertisement data
    devices_and_data = scanner.discovered_devices_and_advertisement_data
    
    print("\nDiscovered devices:")
    for device, advertisement_data in devices_and_data.values():
        print(f"Address: {device.address}")
        print(f"Name: {device.name}")
        print(f"RSSI: {advertisement_data.rssi}")
        print("-" * 50)
    
    # If target address is specified, find and display its details
    if target_address:
        target_info = next(
            (info for addr, info in devices_and_data.items() 
             if addr.lower() == target_address.lower()),
            None
        )
        
        if target_info:
            device, advertisement_data = target_info
            print(f"\nDetailed information for device {target_address}:")
            print(f"Address: {device.address}")
            print(f"Name: {device.name}")
            print(f"RSSI: {advertisement_data.rssi}")
            print("\nAdvertisement Data:")
            print(f"  - Service UUIDs: {advertisement_data.service_uuids}")
            print(f"  - Manufacturer Data:")
            print(f"    {format_manufacturer_data(advertisement_data.manufacturer_data)}")
            print(f"  - Service Data: {advertisement_data.service_data}")
            print(f"  - Local Name: {advertisement_data.local_name}")
            print(f"  - TX Power: {advertisement_data.tx_power}")
        else:
            print(f"\nDevice with address {target_address} not found")

async def main():
    # Check if target address is provided as command line argument
    target_address = sys.argv[1] if len(sys.argv) > 1 else None
    
    try:
        await scan_ble_devices(target_address, scan_time=5)
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())

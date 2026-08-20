"""
EG2A17 - Live BLE logger WITH real-time fall detection + alerts (V3)
====================================================================
This is the main program to run during a demo. It:
  1. Connects to the Nesso over BLE
  2. Stores each raw sample          (collection)
  3. Computes + stores magnitude     (processing)
  4. Runs the fall detector live     (detection)
  5. Raises an on-screen ALERT and logs an event when a fall/trip/near-miss
     is detected                     (alerting)

Backend (SQLite or MariaDB) is chosen in config.py.

Requires:  pip install bleak
           pip install mariadb        (only if DB_BACKEND = "mariadb")
"""

import asyncio
from datetime import datetime

from bleak import BleakScanner, BleakClient

import config
from storage import DataStore, parse_packet
from detector import FallDetector, magnitude


def alert(event):
    """Very visible console alert. On a real system this could send an
    SMS / push notification to a supervisor. Here we flash the terminal."""
    ts = datetime.now().strftime("%H:%M:%S")
    bar = "!" * 60
    print(f"\n\033[91m{bar}")
    print(f"  ALERT  [{ts}]  {event['type']}  "
          f"(severity {event['severity']}, peak {event['peak']} {event['unit']})")
    print(f"{bar}\033[0m\n")


async def main():
    device_name = input(f"Bluetooth device name [{config.DEFAULT_DEVICE}]: ").strip()
    if not device_name:
        device_name = config.DEFAULT_DEVICE

    print(f"Storage backend: {config.DB_BACKEND}")
    print(f"Scanning for '{device_name}' ...")
    device = await BleakScanner.find_device_by_name(device_name, timeout=10.0)
    if device is None:
        print(f"Device '{device_name}' not found. Is it advertising?")
        return
    print(f"Found {device.name} [{device.address}]")

    store = DataStore(device_name)
    detector = FallDetector(config.SAMPLE_RATE_HZ)
    count = 0
    event_count = 0

    def handler(characteristic, data):
        nonlocal count, event_count
        values = parse_packet(data)
        if values is None:
            store.bad_packets += 1
            return
        store.add_reading(values)

        ax, ay, az, gx, gy, gz = values
        event = detector.update(ax, ay, az, gx, gy, gz)
        if event:
            event_count += 1
            store.add_event(event["type"], event["severity"], event["peak"])
            alert(event)

        count += 1
        if count % 100 == 0:
            print(f"[{count:>7}] |a|={magnitude(ax,ay,az):.2f}g  "
                  f"events so far: {event_count}")

    try:
        async with BleakClient(device) as client:
            print(f"Connected to {device.name}. Recording — Ctrl+C to stop.\n")
            await client.start_notify(config.ACCELNGYRO_UUID, handler)
            while client.is_connected:
                await asyncio.sleep(1.0)
                store.flush()
            print("Device disconnected.")
    except asyncio.CancelledError:
        pass
    finally:
        store.close()
        print(f"Detected {event_count} safety events this session.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
    print("Program Stopped")

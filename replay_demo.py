"""
EG2A17 - Demo replay: feed a scripted 9.5 s IMU trace through the REAL
pipeline (parse_packet -> DataStore -> FallDetector) without needing the
Nesso hardware. Produces one NEAR_MISS, one STF and one FALL so the
dashboard has something to show.

Run:  python replay_demo.py     then:  streamlit run dashboard.py
"""

import math
import random
from datetime import datetime, timedelta

import config
from detector import FallDetector
from storage import DataStore, parse_packet

random.seed(4)  # group 4 :)

RATE = config.SAMPLE_RATE_HZ
DT = 1.0 / RATE


def walking(t):
    """~1 g with a 2 Hz step bounce + noise, moderate rotation."""
    az = 0.96 + 0.14 * math.sin(2 * math.pi * 2.0 * t) + random.gauss(0, 0.02)
    ax = 0.12 * math.sin(2 * math.pi * 2.0 * t + 1.3) + random.gauss(0, 0.02)
    ay = random.gauss(0, 0.04)
    g = [random.gauss(0, 25) + 60 * math.sin(2 * math.pi * 2.0 * t + i) for i in range(3)]
    return [ax, ay, az, *g]


def still(_t):
    """Lying on the ground: ~1 g, almost no rotation."""
    return [random.gauss(0, 0.02), random.gauss(0, 0.02), 1.0 + random.gauss(0, 0.03),
            random.gauss(0, 5), random.gauss(0, 5), random.gauss(0, 5)]


def freefall(_t):
    return [random.gauss(0, 0.05), random.gauss(0, 0.05), 0.33 + random.gauss(0, 0.03),
            random.gauss(0, 150), random.gauss(0, 150), random.gauss(0, 150)]


def impact(peak):
    def f(_t):
        return [peak * 0.55, peak * 0.35, peak * 0.75, 300, 250, 200]  # |a| ≈ peak
    return f


def near_miss_spike(_t):
    return [0.05, 0.08, 1.02, 390, 160, 80]   # big lurch, body still upright


# (duration_s, sample_fn) — a scripted incident timeline
SCRIPT = [
    (2.5, walking),
    (0.15, near_miss_spike),          # -> NEAR_MISS
    (1.8, walking),
    (0.45, freefall), (0.04, impact(3.2)), (1.15, still),   # -> STF (MED)
    (1.0, walking),
    (0.45, freefall), (0.04, impact(4.6)), (1.30, still),   # -> FALL (HIGH)
    (0.8, still),
]

store = DataStore(device_name=config.DEFAULT_DEVICE)
det = FallDetector()

base = datetime.now() - timedelta(seconds=sum(d for d, _ in SCRIPT))
i = 0
events = 0
for dur, fn in SCRIPT:
    for _ in range(int(dur * RATE)):
        t = i * DT
        vals = fn(t)
        # go through the real BLE packet path, validation included
        packet = (",".join(f"{v:.4f}" for v in vals)).encode()
        parsed = parse_packet(packet)
        if parsed is None:
            store.bad_packets += 1
            continue
        store.add_reading(parsed)
        ev = det.update(*parsed)
        if ev:
            ts = (base + timedelta(seconds=t)).isoformat(timespec="milliseconds")
            store.add_event(ev["type"], ev["severity"], ev["peak"], ts=ts)
            print(f"{ts}  {ev['type']:<9} severity={ev['severity']} "
                  f"peak={ev['peak']}{ev['unit']}")
            events += 1
        i += 1

# a few corrupted packets, to exercise the validation counter
for bad in (b"garbage", b"1,2,3", b"99,0,0,0,0,0"):
    if parse_packet(bad) is None:
        store.bad_packets += 1

store.close()

# spread the reading timestamps to true 10 ms spacing (add_reading stamps
# wall-clock time, but this replay inserts much faster than real time)
if config.DB_BACKEND == "sqlite":
    import sqlite3
    conn = sqlite3.connect(config.SQLITE_PATH)
    rows = conn.execute("SELECT id FROM imu_readings ORDER BY id").fetchall()
    conn.executemany(
        "UPDATE imu_readings SET timestamp=? WHERE id=?",
        [((base + timedelta(seconds=k * DT)).isoformat(timespec="milliseconds"), r[0])
         for k, r in enumerate(rows)],
    )
    conn.commit()
    conn.close()
print(f"\nReplay done: {i} samples, {events} events.")

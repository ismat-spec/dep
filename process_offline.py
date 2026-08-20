"""
EG2A17 - Offline processing + detection over stored data
=========================================================
Use this to (re)process data you already recorded, without the device:
  - Reads raw rows from imu_readings
  - Computes magnitude + a moving-average smoothed magnitude (processing)
  - Fills the imu_features table
  - Replays the SAME detector over the data and logs events

Great for tuning thresholds: change values in config.py, rerun this,
see how many events you get -- then keep the numbers that best match
your ground-truth notes ("I dropped it at 17:12:05", etc.).

Run:  python process_offline.py
"""

from collections import deque

import config
from detector import FallDetector, magnitude

WINDOW = 5   # moving-average window (samples) for smoothing


def connect():
    if config.DB_BACKEND == "mariadb":
        import mariadb
        return mariadb.connect(**config.MARIADB), "%s"
    import sqlite3
    return sqlite3.connect(config.SQLITE_PATH), "?"


def main():
    conn, ph = connect()
    cur = conn.cursor()

    # pull raw data in time order
    cur.execute("""SELECT device_name, timestamp,
                          acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z
                   FROM imu_readings ORDER BY id ASC""")
    rows = cur.fetchall()
    if not rows:
        print("No raw data found. Record some with nesso_live.py first.")
        return
    print(f"Processing {len(rows)} rows...")

    # clear old processed data so reruns are clean
    cur.execute("DELETE FROM imu_features")
    cur.execute("DELETE FROM events")
    conn.commit()

    detector = FallDetector(config.SAMPLE_RATE_HZ)
    smoothing = deque(maxlen=WINDOW)
    feature_rows = []
    events = []

    for r in rows:
        name, ts, ax, ay, az, gx, gy, gz = r
        amag = magnitude(ax, ay, az)
        gmag = magnitude(gx, gy, gz)
        smoothing.append(amag)
        asmooth = sum(smoothing) / len(smoothing)
        feature_rows.append((name, ts, amag, gmag, asmooth))

        ev = detector.update(ax, ay, az, gx, gy, gz)
        if ev:
            events.append((name, ts, ev["type"], ev["severity"], ev["peak"]))

    # bulk insert features
    cur.executemany(
        f"INSERT INTO imu_features "
        f"(device_name,timestamp,acc_mag,gyr_mag,acc_mag_smooth) "
        f"VALUES ({ph},{ph},{ph},{ph},{ph})", feature_rows)

    # insert detected events
    for e in events:
        cur.execute(
            f"INSERT INTO events "
            f"(device_name,timestamp,event_type,severity,peak_g) "
            f"VALUES ({ph},{ph},{ph},{ph},{ph})", e)
    conn.commit()

    print(f"Wrote {len(feature_rows)} feature rows.")
    print(f"Detected {len(events)} events:")
    for name, ts, etype, sev, peak in events:
        # peak is in g for FALL/STF, deg/s for rotational NEAR_MISS
        print(f"  {ts}  {etype:10s} {sev:4s}  peak {peak}")

    conn.close()


if __name__ == "__main__":
    main()

"""
EG2A17 - Query and verify stored data (RETRIEVAL stage)
========================================================
Reads from whatever database is configured in config.py (MariaDB or
SQLite), so it always matches what nesso_live.py wrote. Demonstrates the
retrieval stage of the pipeline:
  - Row counts and recording time span per device
  - The most recent samples
  - All detected safety events
  - Simple analysis: the 10 biggest acceleration spikes (fall candidates)

Run:  python query_data.py
"""

import config


def connect():
    """Open the same database the rest of the pipeline uses."""
    if config.DB_BACKEND == "mariadb":
        import mariadb
        return mariadb.connect(**config.MARIADB)
    import sqlite3
    return sqlite3.connect(config.SQLITE_PATH)


def main():
    conn = connect()
    cur = conn.cursor()

    # --- 1. Summary: rows and time span per device ---
    print("=== Recording summary ===")
    cur.execute("""SELECT device_name, COUNT(*), MIN(timestamp), MAX(timestamp)
                   FROM imu_readings GROUP BY device_name""")
    rows = cur.fetchall()
    if not rows:
        print("No data found. Record some with nesso_live.py first.")
        conn.close()
        return
    for name, n, start, end in rows:
        print(f"{name}: {n} rows, from {start} to {end}")

    # --- 2. Latest samples ---
    print("\n=== 5 most recent samples ===")
    cur.execute("""SELECT timestamp, acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z
                   FROM imu_readings ORDER BY id DESC LIMIT 5""")
    for ts, ax, ay, az, gx, gy, gz in cur.fetchall():
        print(f"{ts}  acc({ax:+.2f},{ay:+.2f},{az:+.2f})g  "
              f"gyr({gx:+.1f},{gy:+.1f},{gz:+.1f})dps")

    # --- 3. All detected events ---
    print("\n=== Detected safety events ===")
    cur.execute("""SELECT timestamp, event_type, severity, peak_g
                   FROM events ORDER BY id ASC""")
    evs = cur.fetchall()
    if not evs:
        print("No events detected.")
    else:
        for ts, etype, sev, peak in evs:
            print(f"  {ts}  {etype:10s} {sev:4s}  peak {peak}")

    # --- 4. Simple anomaly scan: biggest acceleration spikes ---
    # Total acceleration magnitude = sqrt(ax^2 + ay^2 + az^2). At rest this
    # is ~1 g; a fall shows free-fall (<0.7 g) then an impact spike (>1.8 g).
    print("\n=== Top 10 impact candidates (highest |acceleration|) ===")
    cur.execute("""SELECT timestamp,
                          (acc_x*acc_x + acc_y*acc_y + acc_z*acc_z) AS mag_sq
                   FROM imu_readings ORDER BY mag_sq DESC LIMIT 10""")
    for ts, mag_sq in cur.fetchall():
        print(f"{ts}  |a| = {mag_sq ** 0.5:.2f} g")

    conn.close()


if __name__ == "__main__":
    main()

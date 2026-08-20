"""
EG2A17 - Storage layer (works with BOTH SQLite and MariaDB)
============================================================
One class, DataStore, hides the database differences so the rest of the
project doesn't care which backend is used. Switch backends by editing
DB_BACKEND in config.py.

Three tables model the whole pipeline:
  imu_readings   -> raw samples (data collection)
  imu_features   -> processed values e.g. magnitude (data processing)
  events         -> detected falls / trips / near misses (insights)

MariaDB needs:  pip install mariadb   (and the MariaDB server installed)
SQLite needs:   nothing (built into Python)
"""

from datetime import datetime
import config


# ---- SQL is 99% the same; only the placeholder char differs ----
#   SQLite uses "?"   MariaDB uses "%s"
def _ph(backend):
    return "%s" if backend == "mariadb" else "?"


SCHEMA = {
    "imu_readings": """
        CREATE TABLE IF NOT EXISTS imu_readings (
            id          {pk},
            device_name VARCHAR(32) NOT NULL,
            timestamp   VARCHAR(32) NOT NULL,
            acc_x DOUBLE, acc_y DOUBLE, acc_z DOUBLE,
            gyr_x DOUBLE, gyr_y DOUBLE, gyr_z DOUBLE
        )
    """,
    "imu_features": """
        CREATE TABLE IF NOT EXISTS imu_features (
            id          {pk},
            device_name VARCHAR(32) NOT NULL,
            timestamp   VARCHAR(32) NOT NULL,
            acc_mag  DOUBLE,          -- sqrt(ax^2+ay^2+az^2)
            gyr_mag  DOUBLE,          -- sqrt(gx^2+gy^2+gz^2)
            acc_mag_smooth DOUBLE     -- moving-average smoothed magnitude
        )
    """,
    "events": """
        CREATE TABLE IF NOT EXISTS events (
            id          {pk},
            device_name VARCHAR(32) NOT NULL,
            timestamp   VARCHAR(32) NOT NULL,
            event_type  VARCHAR(16) NOT NULL,   -- FALL / STF / NEAR_MISS
            severity    VARCHAR(8),             -- LOW / MED / HIGH
            peak_g      DOUBLE,
            acknowledged INT DEFAULT 0
        )
    """,
}


class DataStore:
    def __init__(self, device_name="unknown"):
        self.device_name = device_name
        self.backend = config.DB_BACKEND
        self.ph = _ph(self.backend)
        self.buffer = []
        self.total_rows = 0
        self.bad_packets = 0

        if self.backend == "mariadb":
            import mariadb
            self.conn = mariadb.connect(**config.MARIADB)
            pk = "INT PRIMARY KEY AUTO_INCREMENT"
        else:
            import sqlite3
            self.conn = sqlite3.connect(config.SQLITE_PATH)
            pk = "INTEGER PRIMARY KEY AUTOINCREMENT"

        cur = self.conn.cursor()
        for ddl in SCHEMA.values():
            cur.execute(ddl.format(pk=pk))
        self.conn.commit()

    # ---------- raw readings ----------
    def add_reading(self, values):
        """values = [ax, ay, az, gx, gy, gz]"""
        ts = datetime.now().isoformat(timespec="milliseconds")
        self.buffer.append((self.device_name, ts, *values))
        if len(self.buffer) >= config.FLUSH_EVERY:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        p = self.ph
        sql = (f"INSERT INTO imu_readings "
               f"(device_name,timestamp,acc_x,acc_y,acc_z,gyr_x,gyr_y,gyr_z) "
               f"VALUES ({p},{p},{p},{p},{p},{p},{p},{p})")
        cur = self.conn.cursor()
        cur.executemany(sql, self.buffer)
        self.conn.commit()
        self.total_rows += len(self.buffer)
        self.buffer.clear()

    # ---------- events ----------
    def add_event(self, event_type, severity, peak_g, ts=None):
        ts = ts or datetime.now().isoformat(timespec="milliseconds")
        p = self.ph
        sql = (f"INSERT INTO events "
               f"(device_name,timestamp,event_type,severity,peak_g) "
               f"VALUES ({p},{p},{p},{p},{p})")
        cur = self.conn.cursor()
        cur.execute(sql, (self.device_name, ts, event_type, severity, peak_g))
        self.conn.commit()

    def close(self):
        self.flush()
        self.conn.close()
        print(f"\nStored {self.total_rows} rows "
              f"({self.bad_packets} corrupted packets skipped).")


def parse_packet(data):
    """Decode + validate one BLE packet. Returns 6 floats or None."""
    try:
        values = [float(v) for v in data.decode("utf-8").split(",")]
    except (UnicodeDecodeError, ValueError):
        return None
    if len(values) != 6:
        return None
    ax, ay, az, gx, gy, gz = values
    if any(abs(a) > config.MAX_ACC_G for a in (ax, ay, az)):
        return None
    if any(abs(g) > config.MAX_GYR_DPS for g in (gx, gy, gz)):
        return None
    return values

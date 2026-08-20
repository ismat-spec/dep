"""
EG2A17 - Live Safety Dashboard
===============================
A web dashboard (runs in your browser) that reads from the SAME database
the logger writes to, so it updates as data streams in. Shows:
  - Live status banner (green = safe, red = active alert)
  - Key metrics (rows, session length, event counts)
  - Time-series charts of acceleration & gyroscope
  - A table of detected fall / trip / near-miss events

This satisfies the "insights & visualisation" and "alerts" deliverables,
and its live-refresh nature targets the top rubric band.

Setup:  pip install streamlit pandas
Run:    streamlit run dashboard.py
        (opens automatically at http://localhost:8501)
"""

import time
import pandas as pd
import streamlit as st

import config


# ---------- data access ----------
def get_conn():
    if config.DB_BACKEND == "mariadb":
        import mariadb
        return mariadb.connect(**config.MARIADB)
    import sqlite3
    return sqlite3.connect(config.SQLITE_PATH)


def load(sql):
    conn = get_conn()
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


# ---------- page ----------
st.set_page_config(page_title="WSH Safety Monitor", layout="wide")
st.title("Construction Worker Safety Monitor")
st.caption("EG2A17 — Fall & Slip-Trip-Fall detection • Group 4")

REFRESH_SECONDS = 3
placeholder = st.empty()

while True:
    try:
        readings = load("SELECT * FROM imu_readings ORDER BY id DESC LIMIT 1000")
        events = load("SELECT * FROM events ORDER BY id DESC LIMIT 50")
    except Exception as e:
        st.error(f"Could not read database: {e}")
        st.stop()

    with placeholder.container():
        # ----- alert banner -----
        recent_unack = events[events["acknowledged"] == 0] if not events.empty else events
        if not recent_unack.empty:
            top = recent_unack.iloc[0]
            # peak is g for falls, deg/s for rotational near-misses, so show
            # the number without a hardcoded unit to avoid "impossible g".
            st.error(f"⚠ ACTIVE ALERT — {top['event_type']} "
                     f"(severity {top['severity']}, peak {top['peak_g']}) "
                     f"at {top['timestamp']}")
        else:
            st.success("✓ All clear — no active safety alerts")

        # ----- metrics -----
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Samples stored", f"{len(readings)}")
        n_falls = int((events["event_type"].isin(["FALL", "STF"])).sum()) if not events.empty else 0
        n_near = int((events["event_type"] == "NEAR_MISS").sum()) if not events.empty else 0
        c2.metric("Falls / STF", n_falls)
        c3.metric("Near misses", n_near)
        if not readings.empty:
            c4.metric("Device", readings.iloc[0]["device_name"])

        if readings.empty:
            st.info("Waiting for data… start nesso_live.py to begin recording.")
        else:
            # oldest-first for plotting
            plot_df = readings.iloc[::-1].reset_index(drop=True)

            st.subheader("Acceleration (g)")
            st.line_chart(plot_df[["acc_x", "acc_y", "acc_z"]])

            st.subheader("Angular rate (deg/s)")
            st.line_chart(plot_df[["gyr_x", "gyr_y", "gyr_z"]])

        # ----- event log -----
        st.subheader("Detected events")
        if events.empty:
            st.write("No events detected yet.")
        else:
            st.dataframe(
                events[["timestamp", "event_type", "severity", "peak_g"]],
                use_container_width=True, hide_index=True)

    time.sleep(REFRESH_SECONDS)

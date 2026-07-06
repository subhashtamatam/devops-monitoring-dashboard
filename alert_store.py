"""
alert_store.py — persistent alert history using SQLite.

"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts.db")
MAX_ALERT_HISTORY = 50


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the alerts table if it doesn't already exist. Safe to call
    every time the app starts — CREATE TABLE IF NOT EXISTS is a no-op if
    the table is already there, so existing history is never wiped."""
    conn = _get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            source TEXT NOT NULL,
            name TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def add_alert(source, name, severity, description):
    """Insert a new alert and trim history back down to MAX_ALERT_HISTORY,
    same cap behavior as the original in-memory list had."""
    conn = _get_connection()
    conn.execute(
        "INSERT INTO alerts (time, source, name, severity, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            datetime.now().strftime("%d %b %Y, %H:%M:%S"),
            source,
            name,
            severity,
            description,
        ),
    )
    conn.execute(
        """
        DELETE FROM alerts WHERE id NOT IN (
            SELECT id FROM alerts ORDER BY id DESC LIMIT ?
        )
        """,
        (MAX_ALERT_HISTORY,),
    )
    conn.commit()
    conn.close()


def get_alerts(limit=MAX_ALERT_HISTORY):
    """Return the most recent alerts, newest first — same shape as the
    original in-memory list of dicts (time, source, name, severity,
    description), so the /alerts template needs zero changes."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT time, source, name, severity, description "
        "FROM alerts ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def recent_alertmanager_alert_exists(name, lookback=5):
    """Used by the Alertmanager poller to avoid inserting duplicate
    entries for an alert that's already near the top of recent history —
    replaces the old `alert_history[:5]` in-memory check."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT name, source FROM alerts ORDER BY id DESC LIMIT ?",
        (lookback,),
    ).fetchall()
    conn.close()
    return any(r["name"] == name and r["source"] == "Alertmanager" for r in rows)

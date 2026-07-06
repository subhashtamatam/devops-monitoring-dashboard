"""
login_security.py — brute-force login protection.

"""
import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "login_security.db")

MAX_ATTEMPTS     = 5
LOCKOUT_SECONDS  = 300  # 5 minutes


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS failed_logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            attempted_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def record_failed_attempt(username):
    conn = _get_connection()
    conn.execute(
        "INSERT INTO failed_logins (username, attempted_at) VALUES (?, ?)",
        (username, time.time()),
    )
    conn.commit()
    conn.close()


def clear_failed_attempts(username):
    """Called after a successful login — resets the counter for that user."""
    conn = _get_connection()
    conn.execute("DELETE FROM failed_logins WHERE username = ?", (username,))
    conn.commit()
    conn.close()


def get_lockout_status(username):
    """Returns (is_locked, seconds_remaining, attempts_in_window).

    Only counts failures within the trailing LOCKOUT_SECONDS window. Once
    attempts_in_window reaches MAX_ATTEMPTS, the account is locked until
    LOCKOUT_SECONDS have passed since the most recent failure in that
    window (a rolling lockout, not a one-time timer)."""
    conn = _get_connection()
    cutoff = time.time() - LOCKOUT_SECONDS
    rows = conn.execute(
        "SELECT attempted_at FROM failed_logins "
        "WHERE username = ? AND attempted_at > ? ORDER BY attempted_at ASC",
        (username, cutoff),
    ).fetchall()
    conn.close()

    attempts = len(rows)
    if attempts < MAX_ATTEMPTS:
        return False, 0, attempts

    most_recent = rows[-1]["attempted_at"]
    unlock_time = most_recent + LOCKOUT_SECONDS
    remaining = max(0, int(unlock_time - time.time()))
    is_locked = remaining > 0
    return is_locked, remaining, attempts

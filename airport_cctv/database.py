# database.py
import os
import sqlite3
import threading
from typing import Any, Dict, List

import config

DB_PATH = os.path.join(config.LOG_DIR, "events.db")
_lock = threading.Lock()


def init_db() -> None:
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id            INTEGER PRIMARY KEY,
                type          TEXT    NOT NULL,
                track_id      INTEGER,
                time          TEXT,
                timestamp     REAL,
                clip_filename TEXT,
                clip_url      TEXT,
                clip_ready    INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()


def save_event(event: Dict[str, Any]) -> None:
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT OR REPLACE INTO events
               (id, type, track_id, time, timestamp, clip_filename, clip_url, clip_ready)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["id"],
                event["type"],
                event.get("track_id"),
                event.get("time"),
                event.get("timestamp"),
                event.get("clip_filename"),
                event.get("clip_url"),
                1 if event.get("clip_ready") else 0,
            ),
        )
        conn.commit()
        conn.close()


def update_event_clip(event_id: int, clip_filename: str, clip_url: str) -> None:
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE events SET clip_filename=?, clip_url=?, clip_ready=1 WHERE id=?",
            (clip_filename, clip_url, event_id),
        )
        conn.commit()
        conn.close()


def load_recent_events(limit: int = None) -> List[Dict[str, Any]]:
    if limit is None:
        limit = config.MAX_EVENTS
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    return [
        {
            "id": row["id"],
            "type": row["type"],
            "track_id": row["track_id"],
            "time": row["time"],
            "timestamp": row["timestamp"],
            "clip_filename": row["clip_filename"],
            "clip_url": row["clip_url"],
            "clip_ready": bool(row["clip_ready"]),
        }
        for row in rows
    ]


def get_db_stats() -> Dict[str, Any]:
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        rows = conn.execute(
            "SELECT type, COUNT(*) FROM events GROUP BY type"
        ).fetchall()
        conn.close()
    by_type = {r[0]: r[1] for r in rows}
    return {
        "total": total,
        "by_type": by_type,
        "enter_count": by_type.get("Enter", 0),
        "exit_count": by_type.get("Exit", 0),
    }

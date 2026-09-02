"""SQLite history of fault triggers and outcomes. No extra DB server."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.common.state import default_state_path


def default_db_path() -> Path:
    override = os.environ.get("DEMO_DB_PATH")
    if override:
        path = Path(override)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return default_state_path().with_name("events.db")


class EventStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def record(
        self,
        *,
        fault_id: str,
        action: str,
        result: str,
        detail: str = "",
        source: str = "controller",
    ) -> dict[str, Any]:
        created_at = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (created_at, fault_id, action, result, detail, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (created_at, fault_id, action, result, detail, source),
            )
            event_id = cursor.lastrowid
            conn.commit()
        return {
            "id": event_id,
            "created_at": created_at,
            "fault_id": fault_id,
            "action": action,
            "result": result,
            "detail": detail,
            "source": source,
        }

    def list(self, limit: int = 40, fault_id: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        sql = (
            "SELECT id, created_at, fault_id, action, result, detail, source "
            "FROM events"
        )
        params: list[Any] = []
        if fault_id:
            sql += " WHERE fault_id = ?"
            params.append(fault_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def last_by_fault(self) -> dict[str, dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.created_at, e.fault_id, e.action, e.result, e.detail, e.source
                FROM events e
                JOIN (
                    SELECT fault_id, MAX(id) AS max_id
                    FROM events
                    GROUP BY fault_id
                ) latest ON latest.max_id = e.id
                """
            ).fetchall()
        return {row["fault_id"]: dict(row) for row in rows}

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    fault_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'controller'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_fault_id ON events(fault_id, id DESC)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        return conn

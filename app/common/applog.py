"""Realistic application logs. Separate from SQLite operator history."""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from app.common.catalog import pick_log_line

Sink = Callable[[dict[str, Any]], None]


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def app_logs_enabled() -> bool:
    return env_flag("DEMO_APP_LOGS")


class LogRing:
    def __init__(self, maxlen: int = 200) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(entry)

    def tail(self, limit: int = 80) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._lock:
            items = list(self._items)
        return items[-limit:]


class AppLog:
    def __init__(
        self,
        sinks: list[Sink] | None = None,
        heartbeat_sec: float | None = None,
        ring: LogRing | None = None,
    ) -> None:
        self.ring = ring or LogRing()
        self.sinks = list(sinks or [])
        self.heartbeat_sec = (
            float(os.environ.get("DEMO_APP_LOG_HEARTBEAT_SEC", "15"))
            if heartbeat_sec is None
            else float(heartbeat_sec)
        )
        self._last_tick: dict[str, float] = {}
        self._seq = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> AppLog:
        sinks: list[Sink] = []
        if env_flag("DEMO_CLOUDWATCH_LOGS"):
            from app.common.cwlogs import CloudWatchSink, credentials_available

            if credentials_available():
                sinks.append(CloudWatchSink())
        return cls(sinks=sinks)

    def emit(self, fault_id: str, phase: str, *, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        with self._lock:
            self._seq += 1
            index = self._seq
            if phase == "stop":
                self._last_tick.pop(fault_id, None)
            else:
                self._last_tick[fault_id] = now
        entry = format_entry(fault_id, phase, index=index, now=now)
        self.ring.append(entry)
        for sink in self.sinks:
            try:
                sink(entry)
            except Exception:
                continue
        return entry

    def heartbeat(self, active_ids: list[str], *, now: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        emitted: list[dict[str, Any]] = []
        for fault_id in active_ids:
            last = self._last_tick.get(fault_id, 0.0)
            if now - last < self.heartbeat_sec:
                continue
            emitted.append(self.emit(fault_id, "tick", now=now))
        return emitted

    def list(self, limit: int = 80) -> list[dict[str, Any]]:
        return self.ring.tail(limit)


def format_entry(
    fault_id: str,
    phase: str,
    *,
    index: int = 0,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    msg = pick_log_line(fault_id, phase, index)
    level = "warn" if phase in {"start", "tick"} and _looks_bad(msg) else "info"
    req = secrets.token_hex(3)
    ts = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f'ts={ts} level={level} msg="{msg}" req={req}'
    return {
        "ts": now,
        "level": level,
        "msg": msg,
        "req": req,
        "line": line,
    }


def _looks_bad(msg: str) -> bool:
    lowered = msg.lower()
    return any(token in lowered for token in (" 50", " 502", " 503", "refused", "failed", "111"))


_default: AppLog | None = None


def get_applog() -> AppLog:
    global _default
    if _default is None:
        _default = AppLog.from_env()
    return _default


def reset_applog_for_tests() -> None:
    global _default
    _default = None

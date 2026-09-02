"""Realistic application logs. Separate from SQLite operator history."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.common.catalog import pick_log_line
from app.common.state import default_state_path

Sink = Callable[[dict[str, Any]], None]


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def app_logs_enabled() -> bool:
    return env_flag("DEMO_APP_LOGS")


def logging_active(store: Any = None) -> bool:
    """Access + fault lines always go to the local file for the CW agent."""
    return True


def default_app_log_path() -> Path:
    override = os.environ.get("DEMO_APP_LOG_PATH")
    if override:
        path = Path(override)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return default_state_path().with_name("app.log")


class FileLogStore:
    """JSONL next to state.json so controller and target share lines."""

    def __init__(self, path: Path | str | None = None, keep: int = 400) -> None:
        self.path = Path(path) if path else default_app_log_path()
        self.keep = keep
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, separators=(",", ":"))
        with self.path.open("a+", encoding="utf-8") as handle:
            _flock_exclusive(handle)
            try:
                handle.write(line + "\n")
                handle.flush()
                if handle.tell() > 256 * 1024:
                    handle.seek(0)
                    rows = handle.readlines()[-self.keep :]
                    handle.seek(0)
                    handle.truncate()
                    handle.writelines(rows)
                    handle.flush()
            finally:
                _flock_unlock(handle)

    def tail(self, limit: int = 80) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            _flock_exclusive(handle)
            try:
                rows = handle.readlines()[-limit:]
            finally:
                _flock_unlock(handle)
        out: list[dict[str, Any]] = []
        for raw in rows:
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return out


def _flock_exclusive(handle) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except ImportError:
        pass


def _flock_unlock(handle) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except ImportError:
        pass


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
        store: FileLogStore | None = None,
    ) -> None:
        self.ring = ring or LogRing()
        self.store = store
        self.sinks = list(sinks or [])
        self.heartbeat_sec = (
            float(os.environ.get("DEMO_APP_LOG_HEARTBEAT_SEC", "15"))
            if heartbeat_sec is None
            else float(heartbeat_sec)
        )
        self.settings_store = None
        self._last_tick: dict[str, float] = {}
        self._seq = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> AppLog:
        return cls(store=FileLogStore())

    def bind_store(self, store: Any) -> None:
        self.settings_store = store

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
        return self._publish(entry)

    def emit_access(
        self,
        method: str,
        path: str,
        status: int,
        elapsed_ms: int,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        now = time.time() if now is None else now
        msg = access_message(method, path, status, elapsed_ms)
        level = "warn" if status >= 400 else "info"
        return self._publish(make_entry(msg, level=level, now=now))

    def _publish(self, entry: dict[str, Any]) -> dict[str, Any]:
        self.ring.append(entry)
        if self.store is not None:
            try:
                self.store.append(entry)
            except Exception:
                pass
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
        if self.store is not None:
            rows = self.store.tail(limit)
            if rows:
                return rows
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
    return make_entry(msg, level=level, now=now)


def access_message(method: str, path: str, status: int, elapsed_ms: int) -> str:
    ms = max(0, int(elapsed_ms))
    if path.rstrip("/") == "/health" and status == 503:
        return "GET /health 503 ready=false"
    msg = f"{method} {path} {status} in {ms}ms"
    if status >= 500:
        msg += " error=internal"
    return msg


def make_entry(msg: str, *, level: str = "info", now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
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

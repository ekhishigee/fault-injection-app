"""File-locked JSON state shared by controller, target, and watchdog."""

from __future__ import annotations

import json
import os
import time
from enum import StrEnum
from pathlib import Path
from typing import Any

FAULT_IDS = (
    "cpu",
    "memory",
    "disk",
    "app_down",
    "nginx_down",
    "http_500",
    "slow_api",
    "health_fail",
)

FLAG_FAULTS = ("http_500", "slow_api", "health_fail")

DEFAULT_STATE_CANDIDATES = (
    "/var/lib/demo-faults/state.json",
    "/tmp/demo-faults/state.json",
)


class FaultStatus(StrEnum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"


def default_state_path() -> Path:
    override = os.environ.get("DEMO_STATE_PATH")
    if override:
        return Path(override)
    preferred = Path(DEFAULT_STATE_CANDIDATES[0])
    try:
        preferred.parent.mkdir(parents=True, exist_ok=True)
        if os.access(preferred.parent, os.W_OK):
            return preferred
    except OSError:
        pass
    fallback = Path(DEFAULT_STATE_CANDIDATES[1])
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def empty_fault() -> dict[str, Any]:
    return {
        "status": FaultStatus.IDLE.value,
        "started_at": None,
        "expires_at": None,
        "error": None,
    }


def empty_state() -> dict[str, Any]:
    return {
        "faults": {fault_id: empty_fault() for fault_id in FAULT_IDS},
        "flags": {fault_id: False for fault_id in FLAG_FAULTS},
    }


class StateStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_state_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict[str, Any]:
        with self._lock_file() as handle:
            return self._load(handle)

    def update(self, mutator) -> dict[str, Any]:
        with self._lock_file() as handle:
            data = self._load(handle)
            mutator(data)
            handle.seek(0)
            handle.truncate()
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
            return data

    def get_fault(self, fault_id: str) -> dict[str, Any]:
        return self.read()["faults"].get(fault_id, empty_fault())

    def set_fault(
        self,
        fault_id: str,
        *,
        status: FaultStatus,
        started_at: float | None = None,
        expires_at: float | None = None,
        error: str | None = None,
        keep_times: bool = False,
    ) -> dict[str, Any]:
        def mutate(data: dict[str, Any]) -> None:
            current = data["faults"].setdefault(fault_id, empty_fault())
            current["status"] = status.value
            current["error"] = error
            if keep_times:
                return
            current["started_at"] = started_at
            current["expires_at"] = expires_at

        return self.update(mutate)

    def set_flag(self, name: str, value: bool) -> dict[str, Any]:
        if name not in FLAG_FAULTS:
            raise KeyError(name)

        def mutate(data: dict[str, Any]) -> None:
            data["flags"][name] = bool(value)

        return self.update(mutate)

    def flags(self) -> dict[str, bool]:
        data = self.read()
        return {name: bool(data.get("flags", {}).get(name)) for name in FLAG_FAULTS}

    def expired_faults(self, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        expired: list[str] = []
        for fault_id, fault in self.read()["faults"].items():
            expires_at = fault.get("expires_at")
            if (
                fault.get("status") == FaultStatus.ACTIVE.value
                and expires_at is not None
                and now >= float(expires_at)
            ):
                expired.append(fault_id)
        return expired

    def _lock_file(self):
        return _locked_file(self.path)

    def _load(self, handle) -> dict[str, Any]:
        handle.seek(0)
        raw = handle.read().strip()
        if not raw:
            data = empty_state()
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = empty_state()
        return _normalize(data)


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    base = empty_state()
    faults = data.get("faults") if isinstance(data.get("faults"), dict) else {}
    flags = data.get("flags") if isinstance(data.get("flags"), dict) else {}
    for fault_id in FAULT_IDS:
        incoming = faults.get(fault_id) if isinstance(faults.get(fault_id), dict) else {}
        merged = empty_fault()
        merged.update({k: incoming[k] for k in merged if k in incoming})
        if merged["status"] not in {item.value for item in FaultStatus}:
            merged["status"] = FaultStatus.IDLE.value
        base["faults"][fault_id] = merged
    for name in FLAG_FAULTS:
        base["flags"][name] = bool(flags.get(name, False))
    return base


class _locked_file:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+", encoding="utf-8")
        _flock_exclusive(self.handle)
        return self.handle

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            _flock_unlock(self.handle)
            self.handle.close()
            self.handle = None


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

"""Cheap host gauges for the dashboard. Linux first, macOS fallbacks for local runs."""

from __future__ import annotations

import os
import shutil
import time
from typing import Any

_cpu_sample: tuple[float, float, float] | None = None


def system_gauges(disk_path: str) -> dict[str, Any]:
    return {
        "cpu_percent": cpu_percent(),
        "memory_percent": memory_percent(),
        "disk_percent": disk_percent(disk_path),
        "disk_path": disk_path if os.path.isdir(disk_path) else "/",
    }


def cpu_percent() -> float | None:
    global _cpu_sample
    current = _read_cpu_times()
    if current is None:
        return _loadavg_guess()
    if _cpu_sample is None:
        _cpu_sample = current
        time.sleep(0.08)
        current = _read_cpu_times()
        if current is None:
            return _loadavg_guess()
    previous = _cpu_sample
    _cpu_sample = current
    now, idle, total = current
    prev_now, prev_idle, prev_total = previous
    dt_idle = idle - prev_idle
    dt_total = total - prev_total
    if dt_total <= 0:
        return 0.0
    if now - prev_now > 30:
        return None
    busy = max(0.0, 1.0 - (dt_idle / dt_total))
    return round(busy * 100.0, 1)


def memory_percent() -> float | None:
    info = _meminfo()
    if not info:
        return None
    total = info.get("MemTotal")
    available = info.get("MemAvailable")
    if not total:
        return None
    if available is None:
        free = info.get("MemFree", 0)
        buffers = info.get("Buffers", 0)
        cached = info.get("Cached", 0)
        available = free + buffers + cached
    used = max(0, total - available)
    return round((used / total) * 100.0, 1)


def disk_percent(path: str) -> float | None:
    target = path if os.path.isdir(path) else "/"
    try:
        usage = shutil.disk_usage(target)
    except OSError:
        return None
    if usage.total <= 0:
        return None
    return round((usage.used / usage.total) * 100.0, 1)


def _read_cpu_times() -> tuple[float, float, float] | None:
    try:
        with open("/proc/stat", encoding="utf-8") as handle:
            line = handle.readline()
    except OSError:
        return None
    if not line.startswith("cpu "):
        return None
    parts = [float(item) for item in line.split()[1:]]
    if len(parts) < 4:
        return None
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    total = sum(parts)
    return time.time(), idle, total


def _meminfo() -> dict[str, int]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            rows = handle.readlines()
    except OSError:
        return {}
    parsed: dict[str, int] = {}
    for row in rows:
        if ":" not in row:
            continue
        key, raw = row.split(":", 1)
        number = raw.strip().split()[0]
        try:
            parsed[key] = int(number) * 1024
        except ValueError:
            continue
    return parsed


def _loadavg_guess() -> float | None:
    try:
        load1, _, _ = os.getloadavg()
    except OSError:
        return None
    cpus = os.cpu_count() or 1
    return round(min(100.0, (load1 / cpus) * 100.0), 1)

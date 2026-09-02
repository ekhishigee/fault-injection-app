"""Resource caps. Defaults are sized so CPU/memory faults are visible on a 2 vCPU box."""

from __future__ import annotations

import os
from dataclasses import dataclass

# systemd CPUQuota is percent of *one* CPU. 180% ≈ 90% of a 2 vCPU instance.
_CPU_QUOTA_PER_WORKER = 90


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def cpu_quota_for_workers(workers: int) -> str:
    return f"{_CPU_QUOTA_PER_WORKER * max(1, workers)}%"


@dataclass(frozen=True)
class Limits:
    cpu_workers_default: int = 2
    cpu_workers_max: int = 4
    cpu_timeout_sec: int = 90
    cpu_quota: str = "180%"

    mem_bytes_default: int = 128 * 1024 * 1024
    mem_bytes_max: int = 192 * 1024 * 1024
    mem_timeout_sec: int = 60
    mem_systemd_max: str = "256M"

    disk_fill_ratio: float = 0.85
    disk_timeout_sec: int = 180
    disk_mount: str = "/mnt/demo-disk"
    disk_fill_name: str = "fill.bin"

    app_fault_timeout_sec: int = 180
    slow_sleep_sec: float = 3.0
    slow_sleep_max: float = 5.0

    @classmethod
    def from_env(cls) -> Limits:
        base = cls()
        ncpu = os.cpu_count() or 2
        workers = _env_int("DEMO_CPU_WORKERS", ncpu)
        quota = os.environ.get("DEMO_CPU_QUOTA") or cpu_quota_for_workers(workers)
        return cls(
            cpu_workers_default=workers,
            cpu_workers_max=_env_int("DEMO_CPU_WORKERS_MAX", max(ncpu, 4)),
            cpu_timeout_sec=_env_int("DEMO_CPU_TIMEOUT_SEC", base.cpu_timeout_sec),
            cpu_quota=quota,
            mem_bytes_default=_env_int("DEMO_MEM_BYTES", base.mem_bytes_default),
            mem_bytes_max=_env_int("DEMO_MEM_BYTES_MAX", base.mem_bytes_max),
            mem_timeout_sec=_env_int("DEMO_MEM_TIMEOUT_SEC", base.mem_timeout_sec),
            mem_systemd_max=os.environ.get("DEMO_MEM_SYSTEMD_MAX", base.mem_systemd_max),
            disk_fill_ratio=float(os.environ.get("DEMO_DISK_FILL_RATIO", base.disk_fill_ratio)),
            disk_timeout_sec=_env_int("DEMO_DISK_TIMEOUT_SEC", base.disk_timeout_sec),
            disk_mount=os.environ.get("DEMO_DISK_MOUNT", base.disk_mount),
            disk_fill_name=os.environ.get("DEMO_DISK_FILL_NAME", base.disk_fill_name),
            app_fault_timeout_sec=_env_int(
                "DEMO_APP_FAULT_TIMEOUT_SEC", base.app_fault_timeout_sec
            ),
            slow_sleep_sec=float(os.environ.get("DEMO_SLOW_SLEEP_SEC", base.slow_sleep_sec)),
            slow_sleep_max=float(os.environ.get("DEMO_SLOW_SLEEP_MAX", base.slow_sleep_max)),
        )

    def clamp_cpu_workers(self, requested: int | None = None) -> int:
        workers = self.cpu_workers_default if requested is None else int(requested)
        if workers < 1:
            workers = 1
        return min(workers, self.cpu_workers_max)

    def clamp_mem_bytes(self, requested: int | None = None) -> int:
        size = self.mem_bytes_default if requested is None else int(requested)
        if size < 1:
            size = 1
        return min(size, self.mem_bytes_max)

    def clamp_slow_sleep(self, requested: float | None = None) -> float:
        delay = self.slow_sleep_sec if requested is None else float(requested)
        if delay < 0:
            delay = 0
        return min(delay, self.slow_sleep_max)

    @property
    def disk_fill_path(self) -> str:
        return os.path.join(self.disk_mount, self.disk_fill_name)

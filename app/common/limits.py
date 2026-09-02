"""Conservative resource caps for t4g.nano (2 vCPU, 0.5 GiB)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Limits:
    cpu_workers_default: int = 1
    cpu_workers_max: int = 2
    cpu_timeout_sec: int = 90
    cpu_quota: str = "70%"

    mem_bytes_default: int = 16 * 1024 * 1024
    mem_bytes_max: int = 32 * 1024 * 1024
    mem_timeout_sec: int = 60
    mem_systemd_max: str = "48M"

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
        return cls(
            cpu_workers_default=_env_int("DEMO_CPU_WORKERS", base.cpu_workers_default),
            cpu_workers_max=_env_int("DEMO_CPU_WORKERS_MAX", base.cpu_workers_max),
            cpu_timeout_sec=_env_int("DEMO_CPU_TIMEOUT_SEC", base.cpu_timeout_sec),
            cpu_quota=os.environ.get("DEMO_CPU_QUOTA", base.cpu_quota),
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

"""Abstract fault engine. Dashboard talks to this, not to stress-ng or systemctl."""

from __future__ import annotations

import os
import time
from typing import Any

from app.common.applog import AppLog, get_applog
from app.common.catalog import FAULT_LABELS
from app.common.events import EventStore
from app.common.limits import Limits
from app.common.state import FLAG_FAULTS, FAULT_IDS, FaultStatus, StateStore
from app.faults.runner import CommandRunner, CommandResult, FaultCtlRunner

RESOURCE_FAULTS = ("cpu", "memory", "disk")
SERVICE_FAULTS = {
    "app_down": "target",
    "nginx_down": "nginx",
}
SERVICE_NAMES = ("target", "nginx")


class FaultEngine:
    def __init__(
        self,
        store: StateStore | None = None,
        limits: Limits | None = None,
        runner: CommandRunner | None = None,
        events: EventStore | None = None,
        applog: AppLog | None = None,
    ) -> None:
        self.store = store or StateStore()
        self.limits = limits or Limits.from_env()
        self.runner = runner or FaultCtlRunner()
        self.events = events or EventStore()
        self.applog = applog or get_applog()
        self._expiring = False

    def status(self) -> dict[str, Any]:
        self.refresh()
        data = self.store.read()
        now = time.time()
        faults = {}
        active_ids: list[str] = []
        for fault_id in FAULT_IDS:
            item = data["faults"][fault_id]
            expires_at = item.get("expires_at")
            started_at = item.get("started_at")
            running_for = None
            expires_in = None
            if item["status"] == FaultStatus.ACTIVE.value and started_at is not None:
                running_for = max(0, int(now - float(started_at)))
                active_ids.append(fault_id)
            if item["status"] == FaultStatus.ACTIVE.value and expires_at is not None:
                expires_in = max(0, int(float(expires_at) - now))
            faults[fault_id] = {
                "id": fault_id,
                "label": FAULT_LABELS[fault_id],
                "status": item["status"],
                "started_at": started_at,
                "expires_at": expires_at,
                "expires_in": expires_in,
                "running_for": running_for,
                "error": item.get("error"),
            }
        self.applog.heartbeat(active_ids, now=now)
        return {
            "faults": faults,
            "flags": data["flags"],
            "services": {
                name: {"name": name, "status": self._service_status(name)}
                for name in SERVICE_NAMES
            },
        }

    def start(self, fault_id: str, duration_seconds: int | None = None) -> dict[str, Any]:
        self._require_fault(fault_id)
        self.refresh()
        current = self.store.get_fault(fault_id)
        if current["status"] == FaultStatus.ACTIVE.value:
            return self.status()
        expires_at = (
            time.time() + int(duration_seconds) if duration_seconds else None
        )
        try:
            if fault_id in RESOURCE_FAULTS:
                self._start_resource(fault_id, expires_at=expires_at)
            elif fault_id in SERVICE_FAULTS:
                self._start_service_fault(fault_id, expires_at=expires_at)
            else:
                self._start_flag(fault_id, expires_at=expires_at)
            self._record(fault_id, "trigger", "started")
            self.applog.emit(fault_id, "start")
        except FaultError as exc:
            self.store.set_fault(fault_id, status=FaultStatus.FAILED, error=str(exc))
            self._record(fault_id, "trigger", "failed", str(exc))
        return self.status()

    def stop(self, fault_id: str, *, action: str = "stop", source: str = "controller") -> dict[str, Any]:
        self._require_fault(fault_id)
        try:
            if fault_id in RESOURCE_FAULTS:
                self._stop_resource(fault_id)
            elif fault_id in SERVICE_FAULTS:
                self._stop_service_fault(fault_id)
            else:
                self._stop_flag(fault_id)
            self._record(fault_id, action, "stopped", source=source)
            self.applog.emit(fault_id, "stop")
        except FaultError as exc:
            self.store.set_fault(
                fault_id,
                status=FaultStatus.FAILED,
                error=str(exc),
                keep_times=True,
            )
            self._record(fault_id, action, "failed", str(exc), source=source)
        if self._expiring:
            return {}
        return self.status()

    def reset_all(self) -> dict[str, Any]:
        errors: list[str] = []
        was_active = [
            fault_id
            for fault_id in FAULT_IDS
            if self.store.get_fault(fault_id)["status"] == FaultStatus.ACTIVE.value
        ]
        for fault_id in FAULT_IDS:
            try:
                if fault_id in RESOURCE_FAULTS:
                    self._stop_resource(fault_id, from_reset=True)
                elif fault_id in SERVICE_FAULTS:
                    self._stop_service_fault(fault_id)
                else:
                    self._stop_flag(fault_id)
            except FaultError as exc:
                errors.append(f"{fault_id}: {exc}")
                self.store.set_fault(
                    fault_id,
                    status=FaultStatus.FAILED,
                    error=str(exc),
                    keep_times=True,
                )
                self._record(fault_id, "reset", "failed", str(exc))
        self._record("*", "reset", "stopped" if not errors else "failed", "; ".join(errors))
        for fault_id in was_active:
            self.applog.emit(fault_id, "stop")
        if was_active:
            self.applog.emit("*", "stop")
        return self.status()

    def expire_due(self) -> list[str]:
        due = self.store.expired_faults()
        self._expiring = True
        try:
            for fault_id in due:
                self.stop(fault_id, action="expire", source="timer")
        finally:
            self._expiring = False
        return due

    def refresh(self) -> None:
        if not self._expiring:
            self.expire_due()
        data = self.store.read()
        observe_units = os.environ.get("DEMO_OBSERVE_RESOURCE_UNITS", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        for fault_id in RESOURCE_FAULTS:
            fault = data["faults"][fault_id]
            if not observe_units or fault["status"] != FaultStatus.ACTIVE.value:
                continue
            if self._unit_active(fault_id):
                continue
            try:
                self._start_resource(fault_id, keep_times=True)
                self._record(
                    fault_id,
                    "rearm",
                    "started",
                    "worker exited; fault kept active until Stop",
                    source="refresh",
                )
            except FaultError as exc:
                self.store.set_fault(
                    fault_id,
                    status=FaultStatus.FAILED,
                    error=str(exc),
                    keep_times=True,
                )
                self._record(fault_id, "rearm", "failed", str(exc), source="refresh")
        for fault_id, service in SERVICE_FAULTS.items():
            fault = data["faults"][fault_id]
            if fault["status"] != FaultStatus.RECOVERING.value:
                continue
            if self._service_status(service) == "running":
                self.store.set_fault(fault_id, status=FaultStatus.IDLE)

    def control_service(self, name: str, action: str) -> dict[str, Any]:
        if name not in SERVICE_NAMES:
            raise FaultError(f"unknown service: {name}")
        if action not in {"start", "stop", "restart"}:
            raise FaultError(f"unknown action: {action}")
        result = self.runner.run([f"{name}-{action}"])
        self._raise_if_failed(result, f"{name} {action}")
        fault_id = "app_down" if name == "target" else "nginx_down"
        if action == "stop":
            self.store.set_fault(
                fault_id,
                status=FaultStatus.ACTIVE,
                started_at=time.time(),
                expires_at=None,
            )
            self._record(fault_id, "service_stop", "started")
            self.applog.emit(fault_id, "start")
        else:
            self.store.set_fault(fault_id, status=FaultStatus.IDLE)
            self._record(
                fault_id,
                "service_restart" if action == "restart" else "service_start",
                "stopped",
            )
            self.applog.emit(fault_id, "stop")
        return self.status()

    def _start_resource(
        self,
        fault_id: str,
        expires_at: float | None = None,
        keep_times: bool = False,
    ) -> None:
        args = self._resource_start_args(fault_id)
        result = self.runner.run(args)
        if not result.ok:
            raise FaultError(result.stderr or f"failed to start {fault_id}")
        self.store.set_fault(
            fault_id,
            status=FaultStatus.ACTIVE,
            started_at=time.time(),
            expires_at=expires_at,
            keep_times=keep_times,
        )

    def _stop_resource(self, fault_id: str, from_reset: bool = False) -> None:
        current = self.store.get_fault(fault_id)
        if current["status"] not in {
            FaultStatus.ACTIVE.value,
            FaultStatus.RECOVERING.value,
            FaultStatus.FAILED.value,
        } and not from_reset:
            return
        self.store.set_fault(
            fault_id,
            status=FaultStatus.RECOVERING,
            keep_times=True,
        )
        result = self.runner.run([f"{fault_id}-stop"])
        if not result.ok:
            raise FaultError(result.stderr or f"failed to stop {fault_id}")
        self.store.set_fault(fault_id, status=FaultStatus.IDLE)

    def _start_service_fault(self, fault_id: str, expires_at: float | None = None) -> None:
        service = SERVICE_FAULTS[fault_id]
        result = self.runner.run([f"{service}-stop"])
        self._raise_if_failed(result, f"stop {service}")
        self.store.set_fault(
            fault_id,
            status=FaultStatus.ACTIVE,
            started_at=time.time(),
            expires_at=expires_at,
        )

    def _stop_service_fault(self, fault_id: str) -> None:
        service = SERVICE_FAULTS[fault_id]
        self.store.set_fault(fault_id, status=FaultStatus.RECOVERING, keep_times=True)
        result = self.runner.run([f"{service}-start"])
        self._raise_if_failed(result, f"start {service}")
        self.store.set_fault(fault_id, status=FaultStatus.IDLE)

    def _start_flag(self, fault_id: str, expires_at: float | None = None) -> None:
        now = time.time()
        self.store.set_flag(fault_id, True)
        self.store.set_fault(
            fault_id,
            status=FaultStatus.ACTIVE,
            started_at=now,
            expires_at=expires_at,
        )

    def _stop_flag(self, fault_id: str) -> None:
        self.store.set_flag(fault_id, False)
        self.store.set_fault(fault_id, status=FaultStatus.IDLE)

    def _resource_start_args(self, fault_id: str) -> list[str]:
        if fault_id == "cpu":
            return ["cpu-start", str(self.limits.clamp_cpu_workers())]
        if fault_id == "memory":
            return ["memory-start", str(self.limits.clamp_mem_bytes())]
        if fault_id == "disk":
            return ["disk-start"]
        raise FaultError(f"not a resource fault: {fault_id}")

    def _unit_active(self, fault_id: str) -> bool:
        result = self.runner.run([f"{fault_id}-status"])
        return result.ok and result.stdout.strip() == "active"

    def _service_status(self, name: str) -> str:
        result = self.runner.run([f"{name}-status"])
        if result.ok and result.stdout.strip() == "active":
            return "running"
        return "stopped"

    def _require_fault(self, fault_id: str) -> None:
        if fault_id not in FAULT_IDS:
            raise FaultError(f"unknown fault: {fault_id}")

    def _raise_if_failed(self, result: CommandResult, action: str) -> None:
        if not result.ok:
            raise FaultError(result.stderr or f"failed to {action}")

    def _record(
        self,
        fault_id: str,
        action: str,
        result: str,
        detail: str = "",
        source: str = "controller",
    ) -> None:
        self.events.record(
            fault_id=fault_id,
            action=action,
            result=result,
            detail=detail,
            source=source,
        )


class FaultError(Exception):
    pass

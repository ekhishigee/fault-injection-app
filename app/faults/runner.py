"""Run privileged fault-ctl commands. Dry-run is used for local tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class CommandRunner:
    def run(self, args: list[str]) -> CommandResult:
        raise NotImplementedError


class FaultCtlRunner(CommandRunner):
    def __init__(self, ctl_path: str | None = None, use_sudo: bool = True) -> None:
        self.ctl_path = ctl_path or os.environ.get(
            "DEMO_FAULT_CTL", "/opt/demo-target/deploy/bin/demo-fault-ctl"
        )
        runtime = os.environ.get("DEMO_RUNTIME", "").lower()
        self.use_sudo = False if runtime == "compose" else use_sudo
        self.dry_run = os.environ.get("DEMO_DRY_RUN", "").lower() in {"1", "true", "yes"}

    def run(self, args: list[str]) -> CommandResult:
        if self.dry_run:
            return CommandResult(ok=True, stdout="dry-run")
        command = [self.ctl_path, *args]
        if self.use_sudo and os.geteuid() != 0:
            sudo = shutil.which("sudo") or "/usr/bin/sudo"
            command = [sudo, "-n", *command]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CommandResult(ok=False, stderr=str(exc), returncode=1)
        return CommandResult(
            ok=completed.returncode == 0,
            stdout=(completed.stdout or "").strip(),
            stderr=(completed.stderr or "").strip(),
            returncode=completed.returncode,
        )


class FakeRunner(CommandRunner):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.active: set[str] = set()
        self.fail_commands: set[str] = set()

    def run(self, args: list[str]) -> CommandResult:
        self.calls.append(list(args))
        action = args[0] if args else ""
        if action in self.fail_commands:
            return CommandResult(ok=False, stderr=f"forced fail: {action}", returncode=1)
        if action.endswith("-start") or action.endswith("-stop") or action.endswith(
            "-restart"
        ):
            kind = action.rsplit("-", 1)[0]
            if action.endswith("-stop"):
                self.active.discard(kind)
            else:
                self.active.add(kind)
            return CommandResult(ok=True, stdout="ok")
        if action.endswith("-status"):
            kind = action[: -len("-status")]
            running = kind in self.active
            return CommandResult(ok=True, stdout="active" if running else "inactive")
        return CommandResult(ok=True, stdout="ok")

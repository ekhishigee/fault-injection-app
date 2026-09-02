# Architecture

Two processes plus nginx. The dashboard is **not** behind nginx, so stopping nginx or the target does not take down the control panel.

| Unit / container | Bind | Role |
| --- | --- | --- |
| `demo-controller` | `0.0.0.0:8080` | Dashboard and fault API |
| `demo-target` | systemd: `127.0.0.1:8081`; Compose: `0.0.0.0:8081` | Health + sample API |
| nginx | `:80` | Reverse proxy to the target only |

Python + Flask + Waitress (1 process, 2 threads each). History is SQLite (`events.db` next to the state file). There is no extra database container.

## Run modes

**Laptop:** `docker compose up --build`. Resource faults use `stress-ng` inside the controller container. Target/nginx stop uses the Docker Engine API on the mounted socket.

**EC2 / Amazon Linux 2023:** `sudo ./deploy/install.sh`. Full steps: [ec2.md](ec2.md). Resource faults use `systemd-run` + `stress-ng` (`CPUQuota`, `MemoryMax`). Prefer this on small instances (0.5 GiB). Do not run Compose and the systemd install on the same host.

`demo-fault-ctl` picks the backend from `DEMO_RUNTIME` (`systemd` or `compose`). It does **not** treat a host `/var/run/docker.sock` as Compose — that would break an EC2 box that also has Docker installed.

## Data flow

```text
Operator :8080
  → demo-controller
      → /var/lib/demo-faults/state.json   (HTTP / slow / health flags)
      → demo-fault-ctl                    (systemd-run, or Docker API when DEMO_RUNTIME=compose)
  demo-target reads the state file
  nginx :80 → demo-target :8081
```

The dashboard never talks to `stress-ng` directly: `POST /faults/cpu/start` goes through `FaultEngine` → `demo-fault-ctl`.

## Why not a chaos daemon

A separate chaos agent (chaosd, Chaos Mesh, Toxiproxy) needs more RAM and, on ARM64, extra packaging. `stress-ng` plus a small helper covers the eight built-in faults.

## Trade-offs

- Two small Python processes cost more RSS than a single binary, but stay readable.
- Memory faults are a fixed +128 MiB (cap 192 MiB), not “drive the host to 80%”. On 0.5 GiB that is a visible spike; prefer 1 GiB if you need SSH to stay up.
- There is no auto-timeout. A fault stays until Stop or Reset All. Resource workers are still capped (`CPUQuota`, `MemoryMax`, isolated disk).

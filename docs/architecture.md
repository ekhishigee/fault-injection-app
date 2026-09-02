# Architecture

## Decision

Two systemd services on one `t4g.nano` (Amazon Linux 2023, ARM64):

| Unit | Bind | Role |
| --- | --- | --- |
| `demo-controller.service` | `0.0.0.0:8080` | Dashboard and fault API |
| `demo-target.service` | `127.0.0.1:8081` | Health + sample API |
| `nginx.service` | `:80` | Reverse proxy to the target only |
| `amazon-cloudwatch-agent.service` | — | Host metrics |
| `demo-probe.timer` | — | `DemoApp` custom metrics |

The dashboard is **not** behind nginx. Stopping nginx or the target must not take down the control panel.

Python + Flask + Waitress (1 process, 2 threads each) keeps RSS low. There is no React, Node, Redis, or database.

**Docker Compose is an optional run mode** for a laptop or an instance (`docker compose up --build`). Same processes and dashboard API. Resource faults use `stress-ng` inside the controller container; target/nginx stop uses the Docker Engine API over a mounted socket. For CloudWatch process alarms that match host unit names, prefer the systemd install on `t4g.nano`.

History is **SQLite** (`events.db` on the shared state volume), not Postgres. A DB container does not fit `t4g.nano`.

## Why not chaosd

- No official Linux ARM64 binary.
- Chaos Mesh ARM packaging for chaosd is still incomplete.
- A Go chaos daemon plus helpers is too large for 512 MiB RAM.

`stress-ng` is in the AL2023 aarch64 repos and is isolated with `systemd-run` (`CPUQuota`, `MemoryMax`). There is no auto-timeout: the fault stays until Stop so the monitoring system can see the alarm. The dashboard never talks to `stress-ng` directly: `POST /faults/cpu/start` goes through `FaultEngine` → `demo-fault-ctl`.

Toxiproxy and AWS FIS were skipped for the same reason: extra moving parts that do not help the first eight faults.

## Data flow

```text
Tester :8080
  → demo-controller
      → /var/lib/demo-faults/state.json   (HTTP / slow / health flags)
      → demo-fault-ctl                    (systemd-run, or Docker API when DEMO_RUNTIME=compose)
  demo-target reads the state file
  nginx :80 → demo-target :8081
  demo-probe.timer curls :80 and PutMetricData DemoApp
  CloudWatch Agent publishes mem / loop-disk / procstat
```

## Trade-offs

- Two small Python processes cost more RSS than a single Go binary, but stay readable and match the preferred stack.
- Memory faults are a fixed +16 MiB, not “drive the host to 80%”. That is the only safe option on nano.
- T4g Unlimited mode lets CPU stay high; stress still auto-stops at 90s so surplus-credit cost stays tiny.
- SentinelNexus mail routing and the cross-account `MonitoringRole` are out of this repo.

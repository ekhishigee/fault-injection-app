# Monitoring Demo Target

Lightweight fault-injection app used as a **monitoring target** for the AI Monitoring System.

A tester opens one dashboard, triggers a fault, watches the CloudWatch alarm, recovers, and returns the instance to healthy.

```text
Demo Dashboard (:8080)
  → Trigger Fault
  → EC2 / application becomes unhealthy
  → CloudWatch Alarm
  → AI Monitoring System
  → Recovery / runbook
  → Recover from the same dashboard
```

Designed for **Amazon Linux 2023 on t4g.nano** (ARM64, 0.5 GiB). No React, Node, Redis, or Postgres.

You can run it three ways: **Docker Compose** (laptop or instance), **systemd** on AL2023, or a bare Python dry-run.

## Can this instance run Docker?

**Yes on architecture. Tight on memory.** `t4g.nano` is Graviton ARM64, so Docker Engine and these images run. The limit is **0.5 GiB RAM**.

| Instance | RAM | Docker Compose | SQLite history | Postgres/MySQL container |
| --- | --- | --- | --- | --- |
| **t4g.nano (current)** | 0.5 GiB | Possible, but AL2023 + Docker + two apps + nginx + CloudWatch Agent will be cramped. Prefer systemd on nano. | Yes | **No** — will OOM |
| t4g.micro | 1 GiB | Reasonable for Compose | Yes | Risky |
| t4g.small | 2 GiB | Comfortable | Yes | Only if you really need it |

History uses **SQLite inside the existing volume** (`data/state/events.db` / `/var/lib/demo-faults/events.db`). That is the database in Docker: no extra container, and the dashboard can show which fault ran and how it ended.

## Architecture (short)

Two processes plus nginx:

- `demo-controller` on **:8080** — dashboard and `POST /faults/...` (never behind nginx)
- `demo-target` on **127.0.0.1:8081** — `GET /health`, `GET /api/demo`
- nginx on **:80** — proxies only the target

Faults go through an engine (`stress-ng` + systemd/Compose + a state file). A fault **stays ACTIVE until Stop** so a CloudWatch alarm can fire and the monitoring system can recover it. Trigger/stop is written to SQLite. **chaosd was rejected**: no official ARM64 binary and too heavy for 512 MiB. See [docs/architecture.md](docs/architecture.md).

## Faults

| Dashboard | Status | Trigger / Stop |
| --- | --- | --- |
| CPU High, Memory High, Disk High | IDLE / ACTIVE / RECOVERING / FAILED | yes |
| HTTP 500, Slow API, Health Failure | same | yes |
| Demo Target, Nginx | Running / Stopped | Stop / Restart |
| Reset All Faults | — | yes |

Mapping of each fault to metric, alarm, and recovery: [docs/fault-alarm-mapping.md](docs/fault-alarm-mapping.md).  
Safety limits: [docs/safety.md](docs/safety.md).

## Run with Docker Compose (local or instance)

Same dashboard and fault API. Good for a laptop and for a quick instance demo.

```bash
cp .env.example .env          # optional; default token is local-demo
docker compose up --build
```

| URL | What |
| --- | --- |
| http://localhost:8080/?token=local-demo | Dashboard (stays up if nginx/target are stopped) |
| http://localhost/health | Target via nginx |

If port 80 is taken: `DEMO_HTTP_PORT=8088 docker compose up --build`.

Compose services: `demo-controller`, `demo-target`, `demo-nginx`.

| Fault | What Compose does |
| --- | --- |
| CPU / Memory | `stress-ng` inside the controller container (still raises host CPU/RAM) |
| Disk | Writes up to 32 MiB under `./data/demo-disk` (see `.env.example` to use `/mnt/demo-disk` on EC2) |
| App / Nginx down | Docker Engine API `stop`/`start` on those containers via the mounted socket |
| HTTP 500 / Slow / Health | Shared state volume, same as systemd |

```bash
docker compose down
```

On **t4g.nano**, prefer the systemd install below if you need CloudWatch `procstat` on host unit names. Compose is the easier path for local UI and app-level faults.

### Compose on an EC2 instance

Install Docker Engine + Compose plugin, clone this repo, then `docker compose up --build -d`. Open security group ports **80** and **8080**. For the isolated disk loop created by `install.sh`:

```bash
DEMO_DISK_HOST_PATH=/mnt/demo-disk DEMO_DISK_FILL_CAP_BYTES=0 docker compose up --build -d
```

Host CloudWatch Agent / alarms are unchanged; run them on the instance as in the systemd section.

## Install with systemd (Amazon Linux 2023)

Instance role needs `CloudWatchAgentServerPolicy`, `cloudwatch:PutMetricData`, and SSM managed-instance. Tag the instance `App=demo-target`. Security group: 22 or SSM, **80**, **8080** from your admin network only.

```bash
sudo ./deploy/install.sh
sudo ./deploy/cloudwatch/install-agent.sh
```

The installer:

- installs Python 3, nginx, `stress-ng`
- creates user `demo`, venv, sudoers allowlist
- adds a 512 MiB disk swap file
- creates a 256 MiB loop filesystem at `/mnt/demo-disk` (disk faults never fill `/`)
- enables `demo-controller`, `demo-target`, nginx, probe

Dashboard URL (token is printed by the installer):

```text
http://<host>:8080/?token=<token>
```

Target health:

```text
http://<host>/health
```

Create alarms after you measure idle memory (do not keep the 80% guess):

```bash
grep -E 'MemTotal|MemAvailable' /proc/meminfo
aws cloudformation deploy \
  --template-file deploy/cloudwatch/alarms.cfn.yaml \
  --stack-name demo-app-alarms \
  --parameter-overrides InstanceId=i-xxxxxxxx MemoryUsedPercentThreshold=70 SnsTopicArn=arn:aws:sns:...
```

Optional SSM documents: `deploy/ssm/*.yaml` (see the mapping doc).

## Local run without Docker (dry-run)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export DEMO_DRY_RUN=1
export DEMO_STATE_PATH=/tmp/demo-faults/state.json
python -m app.target &          # :8081
python -m app.controller        # :8080
```

`DEMO_DRY_RUN=1` skips `sudo` / `stress-ng`. HTTP / health / slow flags still work.

```bash
pytest
```

## Manual verification

Default token is `local-demo` for Compose, or the file `/etc/demo-target/token` after `install.sh`.

```bash
export TOKEN="${TOKEN:-local-demo}"
curl -s http://127.0.0.1:8081/health          # 200 (systemd target, or skip on Compose)
curl -s http://127.0.0.1/health               # 200 via nginx
curl -s -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/api/status

# CPU
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/cpu/start
systemctl is-active demo-fault-cpu            # systemd
# or: docker exec demo-controller ls /tmp/demo-fault-pids
# Memory
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/memory/start
grep MemAvailable /proc/meminfo
# Disk
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/disk/start
df -h /mnt/demo-disk                          # systemd loop
ls -l data/demo-disk                          # Compose bind mount
# App down
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/app_down/start
systemctl is-active demo-target               # systemd: inactive
docker inspect -f '{{.State.Running}}' demo-target   # Compose: false
# Nginx down (dashboard on :8080 still works)
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/nginx_down/start
systemctl is-active nginx                     # systemd: inactive
docker inspect -f '{{.State.Running}}' demo-nginx    # Compose: false
# HTTP 500 — /health stays 200
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/http_500/start
curl -sI http://127.0.0.1/api/demo            # 500
# Slow API
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/slow_api/start
curl -s -o /dev/null -w '%{time_total}\n' http://127.0.0.1/api/demo
# Health fail
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/health_fail/start
curl -sI http://127.0.0.1/health              # 503

curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/reset
systemctl is-active demo-target nginx         # systemd: active
docker inspect -f '{{.State.Running}}' demo-target demo-nginx
df -h /mnt/demo-disk                          # fill file gone
ls data/demo-disk                             # Compose: fill.bin gone
```

Watch the matching alarm in CloudWatch, then Stop or Reset All and confirm it returns to OK.

## CloudWatch Agent

Minimal config: `deploy/cloudwatch/amazon-cloudwatch-agent.json`

- `mem_used_percent`
- `disk_used_percent` on `/mnt/demo-disk` only
- `procstat` for `demo-target` and nginx
- nginx access log, 3-day retention

`AWS/EC2` `CPUUtilization` does not need the agent. Application metrics (`HealthCheck`, `Http5xx`, `LatencyMs`) come from `demo-probe.timer` via AWS CLI so Flask does not import boto3.

## Project layout

```text
app/controller/         dashboard + REST
app/target/             health + /api/demo
app/common/             state file, limits, gauges
app/faults/             engine (swap-out the backend here)
docker-compose.yml      local / instance Compose
deploy/docker/          Dockerfile + nginx for Compose
deploy/                 systemd, nginx, sudoers, install, CloudWatch, SSM
docs/                   architecture, mapping, safety
```

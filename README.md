# Fault Injection Demo

A small dashboard for injecting CPU, memory, disk, process, and HTTP faults on a Linux host. Faults stay **ACTIVE until Stop** or **Reset All**.

Two supported run modes:

| Where | How |
| --- | --- |
| **Laptop** | Docker Compose |
| **EC2** (Amazon Linux 2023) | `deploy/install.sh` (systemd) |

No React, Node, Redis, or extra database. History is SQLite next to the state file.

## Run locally (Docker Compose)

```bash
cp .env.example .env          # optional; default token is local-demo
docker compose up --build
```

| URL | What |
| --- | --- |
| http://localhost:8080/?token=local-demo | Dashboard (stays up if nginx/target are stopped) |
| http://localhost/health | Target via nginx |

If port 80 is taken: `DEMO_HTTP_PORT=8088 docker compose up --build`.

| Fault | What Compose does |
| --- | --- |
| CPU / Memory | `stress-ng` inside the controller container (uses host CPU/RAM) |
| Disk | Writes up to 32 MiB under `./data/demo-disk` |
| App / Nginx down | Docker Engine API `stop`/`start` via the mounted socket |
| HTTP 500 / Slow / Health | Shared state volume |

```bash
docker compose down
```

On a laptop, Stop CPU when you are done — it keeps burning host/VM CPU until then.

## Run on EC2 (Amazon Linux 2023)

Step-by-step (security group, env, local log file): **[docs/ec2.md](docs/ec2.md)**.

```bash
sudo ./deploy/install.sh
sudo nano /etc/demo-target/env          # see deploy/env.example
sudo systemctl restart demo-controller demo-target
```

Dashboard: `http://<host>:8080/?token=$(sudo cat /etc/demo-target/token)`  
Target: `http://<host>/health`

Do not use Compose on t4g.nano. Optional host metrics: [docs/aws.md](docs/aws.md).

## Application logs

Operator history (`started` / `stopped`) stays on the dashboard. A second channel writes **application-looking** lines so a reader can infer the fault without being told.

Lines are written only when:

- the target is accessed (`GET /health`, `GET /api/demo`)
- a fault is triggered
- a fault is ACTIVE (about every 15s)
- a fault is stopped

`DEMO_APP_LOGS=1` shows the Application logs panel. The same lines are always written to **`/var/lib/demo-faults/app.log`** (or `DEMO_APP_LOG_PATH`). Point the CloudWatch Agent at that file yourself — the app does not call CloudWatch. See [docs/aws.md](docs/aws.md).

## Architecture (short)

- `demo-controller` on **:8080** — dashboard and `POST /faults/...` (never behind nginx)
- `demo-target` on **127.0.0.1:8081** — `GET /health`, `GET /api/demo`
- nginx on **:80** — proxies only the target

Faults go through `FaultEngine` → `demo-fault-ctl` (`stress-ng` + systemd or the Docker API + a state file). See [docs/architecture.md](docs/architecture.md).

## Faults

| Dashboard | Trigger / Stop |
| --- | --- |
| CPU High, Memory High, Disk High | yes |
| HTTP 500, Slow API, Health Failure | yes |
| Demo Target, Nginx | Stop / Start / Restart |
| Reset All Faults | yes |

What each fault does: [docs/faults.md](docs/faults.md).  
Safety limits: [docs/safety.md](docs/safety.md).

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

Default token is `local-demo` for Compose, or `/etc/demo-target/token` after `install.sh`.

```bash
export TOKEN="${TOKEN:-local-demo}"
curl -s http://127.0.0.1/health
curl -s -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/api/status

curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/cpu/start
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/cpu/stop
curl -s -X POST -H "X-Demo-Token: $TOKEN" http://127.0.0.1:8080/faults/reset
```

## Project layout

```text
app/controller/         dashboard + REST
app/target/             health + /api/demo
app/common/             state file, limits, gauges
app/faults/             engine
docker-compose.yml      local Compose
deploy/docker/          Dockerfile + nginx for Compose
deploy/                 systemd, nginx, sudoers, install
docs/                   architecture, faults, safety
```

## License

MIT. See [LICENSE](LICENSE).

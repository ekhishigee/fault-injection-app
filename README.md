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

Use the systemd installer, not Compose, on small instances (t4g.nano / 0.5 GiB). Compose plus Docker Engine plus two apps plus nginx does not fit that RAM comfortably.

Security group: **22** (or SSM), **80**, and **8080** from your admin network only.

```bash
sudo ./deploy/install.sh
```

The installer:

- installs Python 3, nginx, `stress-ng`
- creates user `demo`, a venv, and a sudoers allowlist
- adds a 512 MiB swap file
- creates a 256 MiB loop filesystem at `/mnt/demo-disk` (disk faults never fill `/`)
- enables `demo-controller`, `demo-target`, nginx, and an optional metric probe

Dashboard (token is printed by the installer):

```text
http://<host>:8080/?token=<token>
```

Target health:

```text
http://<host>/health
```

Optional host metrics, example alarms, and application logs: [docs/aws.md](docs/aws.md).

## Application logs

Operator history (`started` / `stopped`) stays on the dashboard. A second channel writes **application-looking** lines (runqueue, heap, 5xx, latency) so a reader can infer the fault without being told.

| Flag | Default | What it does |
| --- | --- | --- |
| `DEMO_APP_LOGS=1` | off | `GET /api/logs` and an Application logs panel |
| `DEMO_CLOUDWATCH_LOGS=1` | off | Same lines to CloudWatch Logs **if** AWS credentials exist (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`, `AWS_PROFILE`, or an instance role) |

Log group defaults to `/fault-inject/app`. See [`.env.example`](.env.example). Do not commit keys.

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

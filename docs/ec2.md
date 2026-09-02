# Run on EC2 (Amazon Linux 2023)

Use **systemd** (`deploy/install.sh`). Do not run Docker Compose on a nano (0.5 GiB).

## 1. Instance

| Item | Value |
| --- | --- |
| AMI | Amazon Linux 2023 (ARM64 on t4g, x86_64 on t3) |
| Size | t4g.nano works; t4g.micro (1 GiB) is more comfortable |
| Disk | 8 GiB is enough |
| SSH / SSM | SSM Session Manager, or port 22 from your IP |

**Security group** (admin network only):

- **22** — SSH (skip if you use SSM only)
- **80** — target via nginx (`/health`, `/api/demo`)
- **8080** — dashboard (not behind nginx)

**IAM instance role** (preferred over access keys):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["cloudwatch:PutMetricData"],
      "Resource": "*"
    }
  ]
}
```

Optional: attach `CloudWatchAgentServerPolicy` if you also install the CloudWatch Agent.

Tag the instance `App=demo-target` only if you use the example SSM documents.

## 2. Install

On the instance:

```bash
sudo dnf install -y git
git clone https://github.com/ekhishigee/fault-injection-app.git
cd fault-injection-app
sudo ./deploy/install.sh
```

Amazon Linux 2023 has no `python3-venv` package. The installer uses `python3 -m venv` from the main Python package.

The installer prints the dashboard URL and token.

```text
http://<public-ip>:8080/?token=<token>
http://<public-ip>/health
```

Token file: `/etc/demo-target/token`

```bash
sudo cat /etc/demo-target/token
```

Check services:

```bash
systemctl is-active demo-controller demo-target nginx
curl -sS http://127.0.0.1/health
curl -sS -H "X-Demo-Token: $(sudo cat /etc/demo-target/token)" http://127.0.0.1:8080/api/status
```

## 3. Env file

All runtime overrides go in **`/etc/demo-target/env`**. Both `demo-controller` and `demo-target` load it.

First install writes a starter file. Edit it, then restart:

```bash
sudo cp /opt/demo-target/deploy/env.example /etc/demo-target/env   # only if you want a fresh template
sudo chmod 644 /etc/demo-target/env
sudo nano /etc/demo-target/env
sudo systemctl restart demo-controller demo-target
```

### What to set

| Variable | Required | Meaning |
| --- | --- | --- |
| `DEMO_RUNTIME=systemd` | yes (installer sets it) | Fault backend is systemd, not Compose |
| `DEMO_DISK_MOUNT=/mnt/demo-disk` | yes | Isolated disk for Disk High |
| `DEMO_APP_LOGS=1` | recommended | Application logs panel on the dashboard |
| `AWS_REGION` | for CloudWatch | e.g. `ap-northeast-1` |
| `DEMO_CW_LOG_GROUP` | optional | default `/fault-inject/app` |
| `DEMO_CW_LOG_STREAM` | optional | default is the hostname |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | only without an instance role | Do not commit. Prefer the IAM role |
| `AWS_SESSION_TOKEN` | only for temporary keys | |
| `AWS_PROFILE` | rare | named profile on the box |

CloudWatch **on/off is not an env flag**. After env + restart, open the dashboard and use the **CloudWatch logs** switch. If keys/role or `logs:PutLogEvents` are missing, the switch stays off and the error is shown next to it.

Leave `DEMO_CLOUDWATCH_LOGS` unset. It is unused.

## 4. CloudWatch logs (after env)

1. Set `AWS_REGION` (and keys only if there is no role).
2. `sudo systemctl restart demo-controller demo-target`
3. Open `http://<ip>:8080/?token=...`
4. Turn **CloudWatch logs** on.
5. Trigger a fault or hit `http://<ip>/health` — lines go to `/fault-inject/app`.

## 5. Optional extras

Host metrics / example alarms: [aws.md](aws.md)

```bash
sudo ./deploy/cloudwatch/install-agent.sh
```

## 6. Update

```bash
cd /path/to/fault-injection-app
git pull
sudo ./deploy/install.sh
sudo systemctl restart demo-controller demo-target nginx
```

`install.sh` does **not** overwrite an existing `/etc/demo-target/env` or token.

## 7. Stop / uninstall (services only)

```bash
sudo systemctl disable --now demo-controller demo-target demo-probe.timer nginx
```

That does not delete `/opt/demo-target`, `/var/lib/demo-faults`, or `/mnt/demo-disk`.

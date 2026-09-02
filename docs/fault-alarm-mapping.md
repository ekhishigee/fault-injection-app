# Fault / alarm mapping

Every scenario: **Fault → symptom → CloudWatch metric → alarm → recovery**.

Treat missing data as `notBreaching`. Period 60s, two datapoints, so a tester can see ALARM in about two minutes.

| Fault | Symptom | Metric | Alarm | Recovery |
| --- | --- | --- | --- | --- |
| CPU High | CPU rises toward ~50% of 2 vCPU | `AWS/EC2` `CPUUtilization` | `DemoApp-CPU-High` (>40%) | Stop `demo-fault-cpu` (`POST /faults/cpu/stop` or `DemoApp-StopResourceFaults`) |
| Memory High | +16 MiB RSS | `CWAgent` `mem_used_percent` | `DemoApp-Memory-High` (idle + ~8 points, **not** 80–90%) | Stop `demo-fault-mem` |
| Disk High | `/mnt/demo-disk` fills to ~85% | `CWAgent` `disk_used_percent` path=`/mnt/demo-disk` | `DemoApp-Disk-High` (>70%) | Remove fill file / `POST /faults/disk/stop` |
| App Down | No target PID; `:80/health` is 502 | `CWAgent` `procstat_lookup_pid_count` pattern `python -m app.target` | `DemoApp-Target-Down` (<1) | `systemctl start demo-target` / `DemoApp-RestartTarget` |
| Nginx Down | `:80` down; `:8080` still works | `procstat_lookup_pid_count` pattern `nginx: master process` | `DemoApp-Nginx-Down` (<1) | `systemctl start nginx` / `DemoApp-RestartNginx` |
| HTTP 500 | `/api/demo` returns 500; `/health` stays 200 | `DemoApp` `Http5xx` | `DemoApp-HTTP-500` (≥1) | Clear flag (`POST /faults/http_500/stop`) |
| Slow API | `/api/demo` sleeps 3s | `DemoApp` `LatencyMs` | `DemoApp-Slow-API` (>2000) | Clear flag |
| Health fail | `/health` returns 503 | `DemoApp` `HealthCheck` | `DemoApp-Health-Fail` (<1) | Clear flag |

## Suggested Monitoring System catalog roles

Use a small set for Phase 1 E2E, not all eight at once:

| Role | Alarm | Why |
| --- | --- | --- |
| Resource + live metric condition | `DemoApp-CPU-High` | Decision can re-read `CPUUtilization` |
| Service restart runbook | `DemoApp-Nginx-Down` | `DemoApp-RestartNginx` (defaults, no parameters) |
| Deliberately unlinked / no-match | `DemoApp-HTTP-500` or `DemoApp-Disk-High` | Ingest + phone `no_match` |
| Optional app family | `DemoApp-Health-Fail` | Distinct from host CPU |

Tag the instance `App=demo-target` so the shipped SSM documents can target it with empty parameters.

Create documents (Owner=Self, type Automation):

```bash
aws ssm create-document --name DemoApp-RestartNginx \
  --document-type Automation --document-format YAML \
  --content file://deploy/ssm/DemoApp-RestartNginx.yaml
aws ssm create-document --name DemoApp-RestartTarget \
  --document-type Automation --document-format YAML \
  --content file://deploy/ssm/DemoApp-RestartTarget.yaml
aws ssm create-document --name DemoApp-StopResourceFaults \
  --document-type Automation --document-format YAML \
  --content file://deploy/ssm/DemoApp-StopResourceFaults.yaml
```

Alarms: `deploy/cloudwatch/alarms.cfn.yaml`. After the first `mem_used_percent` datapoints, set `MemoryUsedPercentThreshold` to idle + 8. SNS / SentinelNexus wiring is an SS/SN task.

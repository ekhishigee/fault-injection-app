# Safety

This program is meant to create faults. The limits exist so a `t4g.nano` stays reachable.

## Hard rules

- Never consume all memory. Default allocation is **16 MiB**, hard cap **32 MiB**, systemd `MemoryMax=48M`.
- Never fill `/`. Disk faults write only inside a **256 MiB loop** mounted at `/mnt/demo-disk` (systemd). Compose caps the fill file at **32 MiB** unless `DEMO_DISK_FILL_CAP_BYTES=0`.
- Never fork-bomb. CPU workers are 1 (max 2) with `CPUQuota=70%`.
- Never stop `demo-controller`, `sshd`, `amazon-ssm-agent`, or `amazon-cloudwatch-agent`.
- Never reboot the instance from the dashboard.
- Every resource fault has a cap and a manual Stop. There is **no auto-recover** — the fault stays until Stop or Reset All so a CloudWatch alarm can fire and the monitoring system can recover it.

## Why 80–90% memory is unsafe

Amazon Linux 2023 already treats 512 MiB as the minimum. zram is on by default on nano. After SSM Agent, CloudWatch Agent, nginx, and two Flask processes, idle `mem_used_percent` is often already high. Driving the box to 80–90% can OOM-kill sshd or the controller.

Install creates a **512 MiB disk-backed swap file** so zram is not the only overflow path. That does not make a large memory fault safe.

## How to set the memory alarm

After a quiet boot, with no faults active:

```bash
grep -E 'MemTotal|MemAvailable' /proc/meminfo
# or wait for CWAgent mem_used_percent and read the last datapoint
```

Set `DemoApp-Memory-High` to **that idle percent + about 8**. Example: idle 62% → threshold 70. Then +16 MiB (~3% of 512 MiB, plus reclaim noise) is enough to cross it.

If idle is already above ~75%, do **not** raise the fault size. Either accept a higher false-idle risk, or move the demo to `t4g.micro` (1 GiB).

## How long a fault stays

Until **Stop** or **Reset All**. The demo does not clear the fault by itself.

| Fault | Stays until | Still capped |
| --- | --- | --- |
| CPU | Stop | 1 worker (max 2), systemd `CPUQuota=70%` |
| Memory | Stop | 16 MiB (max 32), `MemoryMax=48M` |
| Disk | Stop | loop mount / 32 MiB Compose cap |
| HTTP 500 / Slow / Health | Stop | sleep cap 5s |
| App / Nginx down | Stop or a runbook starts the service | cannot stop controller/sshd |

The dashboard stays on :8080 if nginx is down. On a laptop, Stop CPU when you are done — it will keep burning host/VM CPU until then.

## Privilege

User `demo` may only run `/opt/demo-target/deploy/bin/demo-fault-ctl` via sudoers. That helper can start/stop nginx, demo-target, and the three `demo-fault-*` units. It cannot touch the controller or SSH.

## T4g CPU credits

t4g instances default to Unlimited mode, so `CPUUtilization` can stay high after credits are gone (surplus ~$0.04/vCPU-hour). Stress still stops at 90s. Keep the CPU alarm at **40% / 2×60s**, not 80% / 5 minutes.

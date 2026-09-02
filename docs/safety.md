# Safety

This program is meant to create faults. The limits exist so a small host stays reachable.

## Hard rules

- Never consume all memory. Default allocation is **128 MiB**, hard cap **192 MiB**, systemd `MemoryMax=256M`.
- Never fill `/`. Disk faults write only inside a **256 MiB loop** mounted at `/mnt/demo-disk` (systemd). Compose caps the fill file at **32 MiB** unless `DEMO_DISK_FILL_CAP_BYTES=0`.
- Never fork-bomb. CPU workers default to the host core count (max 4) with `CPUQuota` ≈ 90% × workers.
- Never stop `demo-controller` or `sshd` from the dashboard.
- Never reboot the instance from the dashboard.
- There is **no auto-recover**. The fault stays until Stop or Reset All.

## Why a 0.5 GiB box is tight

On a 512 MiB instance, idle memory is already high after the OS, nginx, and two Flask processes. A 128 MiB memory fault will show on the gauge and can still OOM-kill sshd or the controller if idle used is already above ~70%.

The installer creates a **512 MiB disk-backed swap file**. That does not make a large memory fault safe.

Prefer **t4g.micro (1 GiB)** or larger if you want a clear memory spike without risking SSH.

## How long a fault stays

Until **Stop** or **Reset All**. The app does not clear the fault by itself.

| Fault | Stays until | Still capped |
| --- | --- | --- |
| CPU | Stop | all cores (max 4), systemd `CPUQuota` ≈ 90% × workers |
| Memory | Stop | 128 MiB (max 192), `MemoryMax=256M` |
| Disk | Stop | loop mount / 32 MiB Compose cap |
| HTTP 500 / Slow / Health | Stop | sleep cap 5s |
| App / Nginx down | Stop or someone starts the service | cannot stop controller/sshd |

The dashboard stays on :8080 if nginx is down. On a laptop, Stop CPU when you are done — it will keep burning host/VM CPU until then.

## Privilege

User `demo` may only run `/opt/demo-target/deploy/bin/demo-fault-ctl` via sudoers. That helper can start/stop nginx, demo-target, and the three `demo-fault-*` units. It cannot touch the controller or SSH.

## CPU credits (burstable EC2)

Burstable instances in Unlimited mode can stay at high CPU after credits are gone (surplus charge). Stop the CPU fault when you are finished.

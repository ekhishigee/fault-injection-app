# Faults

Every fault stays **ACTIVE until Stop** or **Reset All**, unless Trigger included a duration.

| Fault | What you see | How it is implemented | How it stops |
| --- | --- | --- | --- |
| CPU High | Host CPU rises toward ~90% | `stress-ng --cpu` (all cores, `CPUQuota` ≈ 90% × cores) | `POST /faults/cpu/stop` |
| Memory High | RSS grows by 128 MiB | `stress-ng --vm` (cap 192 MiB, `MemoryMax=256M`) | `POST /faults/memory/stop` |
| Disk High | Isolated volume fills toward ~85% | `fallocate` on `/mnt/demo-disk` or `./data/demo-disk` | `POST /faults/disk/stop` (removes `fill.bin`) |
| App Down | `:80/health` is 502 | `systemctl stop demo-target` or Docker `stop` | Start the target from the dashboard |
| Nginx Down | `:80` down; `:8080` still works | `systemctl stop nginx` or Docker `stop` | Start nginx from the dashboard |
| HTTP 500 | `/api/demo` returns 500; `/health` stays 200 | State-file flag | `POST /faults/http_500/stop` |
| Slow API | `/api/demo` sleeps ~3s | State-file flag | `POST /faults/slow_api/stop` |
| Health fail | `/health` returns 503 | State-file flag | `POST /faults/health_fail/stop` |

API:

```text
POST /faults/<id>/start          optional JSON { "duration_seconds": 60 }
POST /faults/<id>/stop
POST /faults/reset
POST /services/{target,nginx}/{start,stop,restart}
GET  /api/status
GET  /api/events
```

`duration_seconds` must be an integer from 5 to 3600. Omit it to keep today's until-Stop behavior. When the time elapses, the next `/api/status` (dashboard poll) auto-stops the fault. A JSON body is honored even if `Content-Type` is missing or wrong; unknown keys and invalid values return 400. Starting an already-ACTIVE fault with a duration returns 400 — stop it first.

Optional AWS metrics and example alarms: [aws.md](aws.md).

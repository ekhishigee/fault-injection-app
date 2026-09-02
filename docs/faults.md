# Faults

Every fault stays **ACTIVE until Stop** or **Reset All**.

| Fault | What you see | How it is implemented | How it stops |
| --- | --- | --- | --- |
| CPU High | Host CPU rises toward ~50% | `stress-ng --cpu` | `POST /faults/cpu/stop` |
| Memory High | RSS grows by 16 MiB | `stress-ng --vm` | `POST /faults/memory/stop` |
| Disk High | Isolated volume fills toward ~85% | `fallocate` on `/mnt/demo-disk` or `./data/demo-disk` | `POST /faults/disk/stop` (removes `fill.bin`) |
| App Down | `:80/health` is 502 | `systemctl stop demo-target` or Docker `stop` | Start the target from the dashboard |
| Nginx Down | `:80` down; `:8080` still works | `systemctl stop nginx` or Docker `stop` | Start nginx from the dashboard |
| HTTP 500 | `/api/demo` returns 500; `/health` stays 200 | State-file flag | `POST /faults/http_500/stop` |
| Slow API | `/api/demo` sleeps ~3s | State-file flag | `POST /faults/slow_api/stop` |
| Health fail | `/health` returns 503 | State-file flag | `POST /faults/health_fail/stop` |

API:

```text
POST /faults/<id>/start
POST /faults/<id>/stop
POST /faults/reset
POST /services/{target,nginx}/{start,stop,restart}
GET  /api/status
GET  /api/events
```

Optional AWS metrics and example alarms: [aws.md](aws.md).

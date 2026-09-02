"""What each fault should produce. Shown on the dashboard next to history."""

from __future__ import annotations

from app.common.state import FAULT_IDS

FAULT_LABELS = {
    "cpu": "CPU High",
    "memory": "Memory High",
    "disk": "Disk High",
    "app_down": "Demo Target",
    "nginx_down": "Nginx",
    "http_500": "HTTP 500",
    "slow_api": "Slow API",
    "health_fail": "Health Failure",
}

CATALOG: dict[str, dict[str, str]] = {
    "cpu": {
        "label": FAULT_LABELS["cpu"],
        "group": "resource",
        "symptom": "Host CPU rises toward ~50%",
        "metric": "AWS/EC2 CPUUtilization",
        "alarm": "DemoApp-CPU-High",
        "expect_alarm": "ALARM in ~2 min if CPU > 40%",
        "recovered_when": "CPU stress stopped and utilization falls",
    },
    "memory": {
        "label": FAULT_LABELS["memory"],
        "group": "resource",
        "symptom": "RSS grows by a fixed 16 MiB",
        "metric": "CWAgent mem_used_percent",
        "alarm": "DemoApp-Memory-High",
        "expect_alarm": "ALARM if used% exceeds idle + ~8 points",
        "recovered_when": "Memory worker stopped",
    },
    "disk": {
        "label": FAULT_LABELS["disk"],
        "group": "resource",
        "symptom": "Loop/volume fill file appears",
        "metric": "CWAgent disk_used_percent /mnt/demo-disk",
        "alarm": "DemoApp-Disk-High",
        "expect_alarm": "ALARM if the isolated disk is > 70%",
        "recovered_when": "fill.bin removed",
    },
    "app_down": {
        "label": FAULT_LABELS["app_down"],
        "group": "service",
        "symptom": "demo-target process/container is down; /health via :80 is 502",
        "metric": "procstat pid_count demo-target",
        "alarm": "DemoApp-Target-Down",
        "expect_alarm": "ALARM when pid_count < 1",
        "recovered_when": "demo-target is running and /health is 200",
    },
    "nginx_down": {
        "label": FAULT_LABELS["nginx_down"],
        "group": "service",
        "symptom": "Port 80 is down; dashboard on :8080 still works",
        "metric": "procstat pid_count nginx",
        "alarm": "DemoApp-Nginx-Down",
        "expect_alarm": "ALARM when nginx pid_count < 1",
        "recovered_when": "nginx is running and :80/health is 200",
    },
    "http_500": {
        "label": FAULT_LABELS["http_500"],
        "group": "application",
        "symptom": "GET /api/demo returns 500; /health stays 200",
        "metric": "DemoApp Http5xx",
        "alarm": "DemoApp-HTTP-500",
        "expect_alarm": "ALARM when Http5xx ≥ 1",
        "recovered_when": "/api/demo returns 200",
    },
    "slow_api": {
        "label": FAULT_LABELS["slow_api"],
        "group": "application",
        "symptom": "GET /api/demo takes ~3 seconds",
        "metric": "DemoApp LatencyMs",
        "alarm": "DemoApp-Slow-API",
        "expect_alarm": "ALARM when LatencyMs > 2000",
        "recovered_when": "/api/demo is fast again",
    },
    "health_fail": {
        "label": FAULT_LABELS["health_fail"],
        "group": "application",
        "symptom": "GET /health returns 503",
        "metric": "DemoApp HealthCheck",
        "alarm": "DemoApp-Health-Fail",
        "expect_alarm": "ALARM when HealthCheck < 1",
        "recovered_when": "/health returns 200",
    },
}


def catalog_payload() -> dict[str, dict[str, str]]:
    return {fault_id: dict(CATALOG[fault_id]) for fault_id in FAULT_IDS}

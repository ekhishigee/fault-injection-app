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
        "effect": "Host CPU rises toward ~50% of available cores",
        "expect": "stress-ng stays running until Stop",
    },
    "memory": {
        "label": FAULT_LABELS["memory"],
        "group": "resource",
        "effect": "RSS grows by a fixed 16 MiB",
        "expect": "worker stays up until Stop (capped at 32 MiB)",
    },
    "disk": {
        "label": FAULT_LABELS["disk"],
        "group": "resource",
        "effect": "Fill file appears on the isolated disk mount",
        "expect": "usage rises until Stop; / is never filled",
    },
    "app_down": {
        "label": FAULT_LABELS["app_down"],
        "group": "service",
        "effect": "Target process/container is down; :80/health is 502",
        "expect": "dashboard on :8080 stays up",
    },
    "nginx_down": {
        "label": FAULT_LABELS["nginx_down"],
        "group": "service",
        "effect": "Port 80 is down",
        "expect": "dashboard on :8080 stays up",
    },
    "http_500": {
        "label": FAULT_LABELS["http_500"],
        "group": "application",
        "effect": "GET /api/demo returns 500",
        "expect": "/health stays 200",
    },
    "slow_api": {
        "label": FAULT_LABELS["slow_api"],
        "group": "application",
        "effect": "GET /api/demo takes ~3 seconds",
        "expect": "/health stays fast",
    },
    "health_fail": {
        "label": FAULT_LABELS["health_fail"],
        "group": "application",
        "effect": "GET /health returns 503",
        "expect": "stays 503 until Stop",
    },
}


def catalog_payload() -> dict[str, dict[str, str]]:
    return {fault_id: dict(CATALOG[fault_id]) for fault_id in FAULT_IDS}

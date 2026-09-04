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
        "effect": "Host CPU rises toward ~90% of available cores",
        "expect": "stress-ng stays running until Stop",
    },
    "memory": {
        "label": FAULT_LABELS["memory"],
        "group": "resource",
        "effect": "RSS grows by a fixed 128 MiB",
        "expect": "worker stays up until Stop (capped at 192 MiB)",
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


# One fictional incident story per fault. AI should read these as the cause.
# Do not name the fault or say started/stopped.
LOG_LINES: dict[str, dict[str, tuple[str, ...]]] = {
    "cpu": {
        "start": (
            "checkout queue 184 deep; p95 410ms after login wave",
            "search rps 920; worker pool saturated",
        ),
        "tick": (
            "checkout still queued 210; p95 388ms",
            "concurrent sessions 1400; worker busy 0.94",
        ),
        "stop": (
            "checkout queue drained; workers idle",
            "search rps 40; p95 11ms",
        ),
    },
    "memory": {
        "start": (
            "session cache +14MiB after login wave; rss 91MiB",
            "report batch pinned 18MiB; allocator slow path",
        ),
        "tick": (
            "rss 96MiB; session cache 2.1MiB/s; sessions 1400",
            "gc pause 47ms; live set 22MiB; report still pinned",
        ),
        "stop": (
            "session cache evicted; rss 77MiB",
            "report batch released; allocator back to bump path",
        ),
    },
    "disk": {
        "start": (
            "export wrote /var/lib/app/tmp 18MiB; fsync 210ms",
            "upload tmp volume 81% used; append 12MiB",
        ),
        "tick": (
            "export still appending 6MiB; fsync 180ms",
            "tmp volume 84% used; write queue 9",
        ),
        "stop": (
            "exports deleted; tmp volume 12% used; fsync 4ms",
            "upload /var/lib/app/tmp complete; space reclaimed",
        ),
    },
    "app_down": {
        "start": (
            "dial 127.0.0.1:8081: connection refused",
            "upstream app closed connection; checkout queued 12",
        ),
        "tick": (
            "retry dial 127.0.0.1:8081: connection refused",
            "no backends in pool; reqs queued 3",
        ),
        "stop": (
            "dial 127.0.0.1:8081 ok 3ms",
            "upstream app accepting connections",
        ),
    },
    "nginx_down": {
        "start": (
            "upstream connect failed (111)",
            "GET / via :80 502; clients retrying",
        ),
        "tick": (
            "proxy listen gone; connect (111)",
            "GET / via :80 502 still",
        ),
        "stop": (
            "upstream connect ok; GET / 200",
            "proxy listen :80 ready",
        ),
    },
    "http_500": {
        "start": (
            "POST /api/demo 500 in 12ms error=internal",
            "checkout handler panic recovered; status=500",
        ),
        "tick": (
            "POST /api/demo 500 in 11ms error=internal",
            "checkout still returning 500; request_id logged",
        ),
        "stop": (
            "POST /api/demo 200 in 9ms",
            "checkout handler ok; status=200",
        ),
    },
    "slow_api": {
        "start": (
            "GET /api/demo 200 in 3120ms",
            "inventory lookup 2980ms before write",
        ),
        "tick": (
            "GET /api/demo 200 in 3050ms",
            "inventory still 2.9s; still 200",
        ),
        "stop": (
            "GET /api/demo 200 in 18ms",
            "inventory lookup 6ms before write",
        ),
    },
    "health_fail": {
        "start": (
            "GET /health 503 ready=false",
            "readiness probe failed; deps=cache",
        ),
        "tick": (
            "GET /health 503 ready=false",
            "readiness still false; cache unreachable",
        ),
        "stop": (
            "GET /health 200 ready=true",
            "readiness probe ok; cache reachable",
        ),
    },
    "*": {
        "stop": (
            "pending jobs flushed; listeners quiet",
        ),
    },
}


def catalog_payload() -> dict[str, dict[str, str]]:
    return {fault_id: dict(CATALOG[fault_id]) for fault_id in FAULT_IDS}


def phase_log_lines(fault_id: str, phase: str) -> tuple[str, ...]:
    phases = LOG_LINES.get(fault_id) or LOG_LINES["*"]
    return phases.get(phase) or phases.get("tick") or ("job cycle complete",)


def pick_log_line(fault_id: str, phase: str, index: int = 0) -> str:
    lines = phase_log_lines(fault_id, phase)
    return lines[index % len(lines)]


def access_story(path: str, status: int, elapsed_ms: int) -> str | None:
    """Keep HTTP access lines in the same fictional story as the fault catalog."""
    normalized = path.rstrip("/") or "/"
    if normalized == "/health" and status == 503:
        return "cache unreachable"
    if normalized == "/api/demo" and status >= 500:
        return "checkout handler panic"
    if normalized == "/api/demo" and elapsed_ms >= 1000:
        return "inventory lookup slow"
    return None

from __future__ import annotations

import os
import time

from flask import Flask, g, jsonify, request

from app.common.applog import AppLog, get_applog, logging_active
from app.common.limits import Limits
from app.common.state import StateStore


def create_app(
    store: StateStore | None = None,
    limits: Limits | None = None,
    applog: AppLog | None = None,
) -> Flask:
    store = store or StateStore()
    limits = limits or Limits.from_env()
    injected_log = applog is not None
    applog = applog or get_applog()
    applog.bind_store(store)
    app = Flask(__name__)
    app.config["STORE"] = store
    app.config["LIMITS"] = limits
    app.config["APPLOG"] = applog

    @app.before_request
    def _mark_start():
        g.log_started = time.perf_counter()

    @app.after_request
    def _log_access(response):
        if request.path not in {"/health", "/api/demo"}:
            return response
        if not injected_log and not logging_active(store):
            return response
        started = getattr(g, "log_started", None)
        elapsed_ms = int((time.perf_counter() - started) * 1000) if started else 0
        try:
            applog.emit_access(request.method, request.path, response.status_code, elapsed_ms)
        except Exception:
            pass
        return response

    @app.get("/health")
    def health():
        flags = store.flags()
        if flags.get("health_fail"):
            return jsonify({"status": "unavailable", "reason": "injected health failure"}), 503
        return jsonify({"status": "ok"}), 200

    @app.get("/api/demo")
    def api_demo():
        flags = store.flags()
        if flags.get("slow_api"):
            time.sleep(limits.clamp_slow_sleep())
        if flags.get("http_500"):
            return jsonify({"error": "injected 500"}), 500
        return jsonify({"ok": True, "service": "demo-target"}), 200

    return app


def main() -> None:
    host = os.environ.get("DEMO_TARGET_HOST", "127.0.0.1")
    port = int(os.environ.get("DEMO_TARGET_PORT", "8081"))
    app = create_app()
    from waitress import serve

    serve(app, host=host, port=port, threads=2, ident="demo-target")


if __name__ == "__main__":
    main()

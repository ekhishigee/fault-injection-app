from __future__ import annotations

import os
import time

from flask import Flask, jsonify

from app.common.limits import Limits
from app.common.state import StateStore


def create_app(store: StateStore | None = None, limits: Limits | None = None) -> Flask:
    store = store or StateStore()
    limits = limits or Limits.from_env()
    app = Flask(__name__)
    app.config["STORE"] = store
    app.config["LIMITS"] = limits

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

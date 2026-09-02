from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, make_response, render_template, request

from app.common.catalog import catalog_payload
from app.common.events import EventStore
from app.common.limits import Limits
from app.common.metrics import system_gauges
from app.common.state import FAULT_IDS, StateStore
from app.controller.auth import load_token, request_token, require_token
from app.faults.engine import FaultEngine, FaultError

ROOT = Path(__file__).resolve().parents[1]


def create_app(
    engine: FaultEngine | None = None,
    limits: Limits | None = None,
    events: EventStore | None = None,
) -> Flask:
    limits = limits or Limits.from_env()
    events = events or (engine.events if engine else EventStore())
    engine = engine or FaultEngine(store=StateStore(), limits=limits, events=events)
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config["ENGINE"] = engine
    app.config["LIMITS"] = limits
    app.config["EVENTS"] = events

    @app.get("/")
    def dashboard():
        token = load_token()
        provided = request_token()
        authorized = token is None or provided == token
        response = make_response(
            render_template(
                "dashboard.html",
                token_required=token is not None,
                authorized=authorized,
            )
        )
        if authorized and provided:
            response.set_cookie("demo_token", provided, httponly=False, samesite="Lax")
        return response

    @app.get("/api/status")
    @require_token
    def api_status():
        return jsonify(_status_payload(engine, events, limits))

    @app.get("/api/events")
    @require_token
    def api_events():
        fault_id = request.args.get("fault_id")
        limit = int(request.args.get("limit", "40"))
        return jsonify({"events": events.list(limit=limit, fault_id=fault_id)})

    @app.post("/faults/<fault_id>/start")
    @require_token
    def start_fault(fault_id: str):
        return _fault_action(engine, fault_id, "start")

    @app.post("/faults/<fault_id>/stop")
    @require_token
    def stop_fault(fault_id: str):
        return _fault_action(engine, fault_id, "stop")

    @app.post("/faults/reset")
    @require_token
    def reset_faults():
        engine.reset_all()
        return jsonify(_status_payload(engine, events, limits))

    @app.post("/services/<name>/<action>")
    @require_token
    def service_action(name: str, action: str):
        try:
            engine.control_service(name, action)
        except FaultError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(_status_payload(engine, events, limits))

    return app


def _fault_action(engine: FaultEngine, fault_id: str, action: str):
    if fault_id not in FAULT_IDS:
        return jsonify({"error": f"unknown fault: {fault_id}"}), 404
    try:
        engine.start(fault_id) if action == "start" else engine.stop(fault_id)
    except FaultError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_status_payload(engine, engine.events, engine.limits))


def _status_payload(engine: FaultEngine, events: EventStore, limits: Limits) -> dict:
    payload = engine.status()
    last = events.last_by_fault()
    for fault_id, fault in payload["faults"].items():
        fault["last_event"] = last.get(fault_id)
    payload["system"] = system_gauges(limits.disk_mount)
    payload["catalog"] = catalog_payload()
    payload["events"] = events.list(limit=40)
    payload["runtime"] = os.environ.get("DEMO_RUNTIME", "systemd")
    return payload


def main() -> None:
    host = os.environ.get("DEMO_CONTROLLER_HOST", "0.0.0.0")
    port = int(os.environ.get("DEMO_CONTROLLER_PORT", "8080"))
    app = create_app()
    from waitress import serve

    serve(app, host=host, port=port, threads=2, ident="demo-controller")


if __name__ == "__main__":
    main()

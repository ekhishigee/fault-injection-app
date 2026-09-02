"""Optional shared-token gate for the fault dashboard."""

from __future__ import annotations

import os
from functools import wraps
from pathlib import Path

from flask import jsonify, request

DEFAULT_TOKEN_PATH = "/etc/demo-target/token"


def load_token() -> str | None:
    env_token = os.environ.get("DEMO_CONTROLLER_TOKEN")
    if env_token:
        return env_token.strip() or None
    path = Path(os.environ.get("DEMO_TOKEN_PATH", DEFAULT_TOKEN_PATH))
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def request_token() -> str | None:
    header = request.headers.get("X-Demo-Token")
    if header:
        return header.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    query = request.args.get("token")
    if query:
        return query.strip()
    cookie = request.cookies.get("demo_token")
    if cookie:
        return cookie.strip()
    return None


def require_token(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = load_token()
        if not expected:
            return view(*args, **kwargs)
        provided = request_token()
        if provided != expected:
            return jsonify({"error": "unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapped

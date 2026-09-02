from app.common.applog import AppLog, FileLogStore, access_message, format_entry
from app.common.catalog import LOG_LINES
from app.common.events import EventStore
from app.common.limits import Limits
from app.common.state import StateStore
from app.controller.app import create_app as create_controller
from app.faults.engine import FaultEngine
from app.faults.runner import FakeRunner
from app.target.app import create_app as create_target

BANNED = ("cpu", "started", "fault", "trigger", "leak", "inject")


def make_engine(tmp_path, applog=None):
    log = applog or AppLog()
    return FaultEngine(
        store=StateStore(tmp_path / "state.json"),
        limits=Limits(),
        runner=FakeRunner(),
        events=EventStore(tmp_path / "events.db"),
        applog=log,
    )


def test_log_catalog_has_no_giveaway_words():
    blob = " ".join(
        line
        for phases in LOG_LINES.values()
        for lines in phases.values()
        for line in lines
    ).lower()
    for word in BANNED:
        assert word not in blob, word


def test_cpu_start_and_stop_are_realistic(tmp_path):
    applog = AppLog()
    engine = make_engine(tmp_path, applog)
    engine.start("cpu")
    start_line = applog.list()[-1]["line"].lower()
    assert "cpu" not in start_line
    assert "started" not in start_line
    assert "runqueue" in start_line or "scheduler" in start_line or "hash job" in start_line
    engine.stop("cpu")
    stop_line = applog.list()[-1]["line"].lower()
    assert "cpu" not in stop_line
    assert "started" not in stop_line
    assert applog.list()[-1]["msg"] != applog.list()[0]["msg"] or "idle" in stop_line or "lag 2ms" in stop_line


def test_heartbeat_waits_interval(tmp_path):
    applog = AppLog(heartbeat_sec=30)
    engine = make_engine(tmp_path, applog)
    engine.start("memory")
    assert len(applog.list()) == 1
    engine.status()
    assert len(applog.list()) == 1
    applog.heartbeat(["memory"], now=applog.list()[0]["ts"] + 31)
    assert len(applog.list()) == 2
    assert "rss" in applog.list()[-1]["msg"].lower() or "gc" in applog.list()[-1]["msg"].lower()


def test_from_env_writes_local_file_only(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_APP_LOG_PATH", str(tmp_path / "app.log"))
    log = AppLog.from_env()
    assert log.sinks == []
    assert log.store is not None
    log.emit_access("GET", "/health", 200, 4)
    assert (tmp_path / "app.log").exists()


def test_status_has_no_cloudwatch_switch(tmp_path):
    engine = make_engine(tmp_path)
    client = create_controller(engine=engine, applog=engine.applog).test_client()
    body = client.get("/api/status").get_json()
    assert "cloudwatch_logs" not in body
    assert client.post("/api/settings/cloudwatch-logs", json={"enabled": True}).status_code == 404


def test_api_logs_hidden_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_APP_LOGS", raising=False)
    engine = make_engine(tmp_path)
    client = create_controller(engine=engine, applog=engine.applog).test_client()
    assert client.get("/api/logs").status_code == 404
    body = client.get("/api/status").get_json()
    assert body["app_logs_enabled"] is False
    assert "app_logs" not in body


def test_api_logs_shown_when_flag_on(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_APP_LOGS", "1")
    engine = make_engine(tmp_path)
    client = create_controller(engine=engine, applog=engine.applog).test_client()
    client.post("/faults/cpu/start")
    response = client.get("/api/logs")
    assert response.status_code == 200
    lines = " ".join(item["line"] for item in response.get_json()["logs"]).lower()
    assert "cpu" not in lines
    assert "started" not in lines
    status = client.get("/api/status").get_json()
    assert status["app_logs_enabled"] is True
    assert status["app_logs"]


def test_format_entry_has_ts_and_req():
    entry = format_entry("slow_api", "start")
    assert "3120ms" in entry["msg"] or "2980ms" in entry["msg"]
    assert "req=" in entry["line"]
    assert entry["line"].startswith("ts=")


def test_target_access_is_logged(tmp_path):
    applog = AppLog()
    store = StateStore(tmp_path / "state.json")
    client = create_target(store=store, limits=Limits(), applog=applog).test_client()
    assert client.get("/health").status_code == 200
    assert client.get("/api/demo").status_code == 200
    lines = [item["msg"] for item in applog.list()]
    assert any(msg.startswith("GET /health 200") for msg in lines)
    assert any(msg.startswith("GET /api/demo 200") for msg in lines)
    blob = " ".join(lines).lower()
    for word in BANNED:
        assert word not in blob

    store.set_flag("http_500", True)
    assert client.get("/api/demo").status_code == 500
    assert "GET /api/demo 500" in applog.list()[-1]["msg"]
    assert "started" not in applog.list()[-1]["line"]


def test_access_message_health_fail():
    assert access_message("GET", "/health", 503, 8) == "GET /health 503 ready=false"
    assert "cpu" not in access_message("GET", "/api/demo", 200, 12)


def test_shared_file_store(tmp_path):
    store = FileLogStore(tmp_path / "app.log")
    writer = AppLog(store=store)
    reader = AppLog(store=store)
    writer.emit_access("GET", "/health", 200, 4)
    rows = reader.list()
    assert rows[-1]["msg"].startswith("GET /health 200")

from app.common.applog import AppLog, format_entry
from app.common.catalog import LOG_LINES
from app.common.cwlogs import CloudWatchSink, credentials_available
from app.common.events import EventStore
from app.common.limits import Limits
from app.common.state import StateStore
from app.controller.app import create_app as create_controller
from app.faults.engine import FaultEngine
from app.faults.runner import FakeRunner

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


def test_from_env_skips_cloudwatch_without_flag_or_creds(monkeypatch):
    monkeypatch.delenv("DEMO_CLOUDWATCH_LOGS", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    assert AppLog.from_env().sinks == []

    monkeypatch.setenv("DEMO_CLOUDWATCH_LOGS", "1")
    monkeypatch.setattr("app.common.cwlogs.credentials_available", lambda: False)
    assert AppLog.from_env().sinks == []


def test_from_env_attaches_cloudwatch_when_ready(monkeypatch):
    sink = object()
    monkeypatch.setenv("DEMO_CLOUDWATCH_LOGS", "1")
    monkeypatch.setattr("app.common.cwlogs.credentials_available", lambda: True)
    monkeypatch.setattr("app.common.cwlogs.CloudWatchSink", lambda: sink)
    assert AppLog.from_env().sinks == [sink]


def test_credentials_keys_or_profile(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    assert credentials_available() is True
    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    monkeypatch.setenv("AWS_PROFILE", "demo")
    assert credentials_available() is True


def test_cloudwatch_sink_puts_line():
    captured = []

    class FakeClient:
        def create_log_group(self, **kwargs):
            return None

        def create_log_stream(self, **kwargs):
            return None

        def put_log_events(self, **kwargs):
            captured.append(kwargs)
            return {"nextSequenceToken": "2"}

    sink = CloudWatchSink(group="/fault-inject/app", stream="box", client=FakeClient())
    sink({"ts": 1000.0, "line": 'ts=... msg="heap +14MiB after batch; rss 91MiB"', "msg": "x"})
    assert captured[0]["logGroupName"] == "/fault-inject/app"
    assert "heap" in captured[0]["logEvents"][0]["message"]


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

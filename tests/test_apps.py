from app.common.events import EventStore
from app.common.limits import Limits
from app.common.state import StateStore
from app.controller.app import create_app as create_controller
from app.faults.engine import FaultEngine
from app.faults.runner import FakeRunner
from app.target.app import create_app as create_target


def make_controller(tmp_path):
    events = EventStore(tmp_path / "events.db")
    engine = FaultEngine(
        store=StateStore(tmp_path / "state.json"),
        limits=Limits(),
        runner=FakeRunner(),
        events=events,
    )
    return create_controller(engine=engine, limits=Limits(), events=events).test_client()


def test_target_health_and_injected_faults(tmp_path):
    store = StateStore(tmp_path / "state.json")
    client = create_target(store=store, limits=Limits()).test_client()
    assert client.get("/health").status_code == 200
    assert client.get("/api/demo").status_code == 200

    store.set_flag("health_fail", True)
    assert client.get("/health").status_code == 503

    store.set_flag("health_fail", False)
    store.set_flag("http_500", True)
    assert client.get("/api/demo").status_code == 500
    assert client.get("/health").status_code == 200


def test_controller_status_and_fault_api(tmp_path):
    client = make_controller(tmp_path)
    status = client.get("/api/status")
    assert status.status_code == 200
    body = status.get_json()
    assert body["faults"]["cpu"]["status"] == "IDLE"
    assert "system" in body
    assert "CPU" in body["catalog"]["cpu"]["effect"]

    started = client.post("/faults/cpu/start")
    assert started.status_code == 200
    started_body = started.get_json()
    assert started_body["faults"]["cpu"]["status"] == "ACTIVE"
    assert started_body["faults"]["cpu"]["expires_at"] is None
    assert started_body["faults"]["cpu"]["expires_in"] is None
    assert started_body["events"][0]["result"] == "started"

    stopped = client.post("/faults/cpu/stop")
    assert stopped.status_code == 200
    assert stopped.get_json()["events"][0]["result"] == "stopped"

    reset = client.post("/faults/reset")
    assert reset.status_code == 200
    assert reset.get_json()["faults"]["cpu"]["status"] == "IDLE"


def test_controller_start_with_duration(tmp_path):
    client = make_controller(tmp_path)
    started = client.post("/faults/cpu/start", json={"duration_seconds": 30})
    assert started.status_code == 200
    fault = started.get_json()["faults"]["cpu"]
    assert fault["status"] == "ACTIVE"
    assert fault["expires_at"] is not None
    assert 25 <= fault["expires_in"] <= 30


def test_controller_status_expires_due_fault(tmp_path, monkeypatch):
    now = {"t": 1_000_000.0}

    def fake_time():
        return now["t"]

    monkeypatch.setattr("app.faults.engine.time.time", fake_time)
    monkeypatch.setattr("app.common.state.time.time", fake_time)
    client = make_controller(tmp_path)
    started = client.post("/faults/cpu/start", json={"duration_seconds": 30})
    assert started.status_code == 200
    now["t"] = 1_000_031.0
    status = client.get("/api/status")
    assert status.status_code == 200
    body = status.get_json()
    assert body["faults"]["cpu"]["status"] == "IDLE"
    assert any(
        event["action"] == "expire" and event["source"] == "timer"
        for event in body["events"]
    )


def test_controller_honors_json_without_json_content_type(tmp_path):
    client = make_controller(tmp_path)
    response = client.post(
        "/faults/cpu/start",
        data=b'{"duration_seconds": 30}',
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == 200
    fault = response.get_json()["faults"]["cpu"]
    assert fault["status"] == "ACTIVE"
    assert fault["expires_at"] is not None


def test_controller_rejects_unknown_duration_key(tmp_path):
    client = make_controller(tmp_path)
    response = client.post("/faults/cpu/start", json={"duration": 30})
    assert response.status_code == 400


def test_controller_rejects_duration_on_active_fault(tmp_path):
    client = make_controller(tmp_path)
    assert client.post("/faults/cpu/start").status_code == 200
    response = client.post("/faults/cpu/start", json={"duration_seconds": 30})
    assert response.status_code == 400
    assert "already active" in response.get_json()["error"]


def test_controller_rejects_invalid_duration(tmp_path):
    client = make_controller(tmp_path)
    bodies = (
        {"duration_seconds": 3},
        {"duration_seconds": -1},
        {"duration_seconds": 99999},
        {"duration_seconds": "abc"},
        {"duration_seconds": True},
        {"duration_seconds": 30.5},
    )
    for body in bodies:
        response = client.post("/faults/cpu/start", json=body)
        assert response.status_code == 400, body
        assert "duration_seconds" in response.get_json()["error"]


def test_controller_rejects_unknown_fault(tmp_path):
    client = make_controller(tmp_path)
    response = client.post("/faults/reboot/start")
    assert response.status_code == 404

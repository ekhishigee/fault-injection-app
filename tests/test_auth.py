from app.common.limits import Limits
from app.common.state import StateStore
from app.controller.app import create_app
from app.faults.engine import FaultEngine
from app.faults.runner import FakeRunner


def test_api_requires_token_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_CONTROLLER_TOKEN", "secret")
    engine = FaultEngine(
        store=StateStore(tmp_path / "state.json"),
        limits=Limits(),
        runner=FakeRunner(),
    )
    client = create_app(engine=engine).test_client()
    assert client.get("/api/status").status_code == 401
    ok = client.get("/api/status", headers={"X-Demo-Token": "secret"})
    assert ok.status_code == 200

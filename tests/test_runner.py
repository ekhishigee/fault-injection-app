from app.faults.runner import FaultCtlRunner


def test_compose_runtime_does_not_use_sudo(monkeypatch):
    monkeypatch.setenv("DEMO_RUNTIME", "compose")
    runner = FaultCtlRunner()
    assert runner.use_sudo is False
    assert runner.dry_run is False

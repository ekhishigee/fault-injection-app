from app.common.state import FaultStatus, StateStore, empty_state


def test_read_returns_normalized_empty_state(tmp_path):
    store = StateStore(tmp_path / "state.json")
    data = store.read()
    assert set(data["faults"]) == set(empty_state()["faults"])
    assert data["faults"]["cpu"]["status"] == FaultStatus.IDLE.value


def test_set_fault_and_flag_round_trip(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.set_flag("http_500", True)
    store.set_fault("http_500", status=FaultStatus.ACTIVE, started_at=1, expires_at=2)
    data = store.read()
    assert data["flags"]["http_500"] is True
    assert data["faults"]["http_500"]["status"] == "ACTIVE"
    assert data["faults"]["http_500"]["expires_at"] == 2
    store.set_setting("cloudwatch_logs", True)
    assert store.settings()["cloudwatch_logs"] is True


def test_expired_faults(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.set_fault("cpu", status=FaultStatus.ACTIVE, started_at=1, expires_at=10)
    store.set_fault("disk", status=FaultStatus.ACTIVE, started_at=1, expires_at=50)
    assert store.expired_faults(now=20) == ["cpu"]

from app.common.events import EventStore


def test_event_round_trip(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.record(fault_id="cpu", action="trigger", result="started", detail="ok")
    store.record(fault_id="cpu", action="stop", result="stopped")
    rows = store.list()
    assert len(rows) == 2
    assert rows[0]["result"] == "stopped"
    last = store.last_by_fault()
    assert last["cpu"]["action"] == "stop"

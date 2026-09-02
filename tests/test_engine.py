from app.common.events import EventStore
from app.common.limits import Limits
from app.common.state import FaultStatus, StateStore
from app.faults.engine import FaultEngine
from app.faults.runner import FakeRunner


def make_engine(tmp_path):
    return FaultEngine(
        store=StateStore(tmp_path / "state.json"),
        limits=Limits(),
        runner=FakeRunner(),
        events=EventStore(tmp_path / "events.db"),
    )


def test_start_and_stop_cpu(tmp_path):
    engine = make_engine(tmp_path)
    status = engine.start("cpu")
    assert status["faults"]["cpu"]["status"] == FaultStatus.ACTIVE.value
    assert ["cpu-start", "2"] in engine.runner.calls
    status = engine.stop("cpu")
    assert status["faults"]["cpu"]["status"] == FaultStatus.IDLE.value
    assert ["cpu-stop"] in engine.runner.calls
    assert engine.events.list()[0]["result"] == "stopped"


def test_memory_start_uses_clamped_bytes(tmp_path):
    engine = make_engine(tmp_path)
    engine.start("memory")
    assert ["memory-start", str(128 * 1024 * 1024)] in engine.runner.calls


def test_failed_start_marks_failed(tmp_path):
    engine = make_engine(tmp_path)
    engine.runner.fail_commands.add("cpu-start")
    status = engine.start("cpu")
    assert status["faults"]["cpu"]["status"] == FaultStatus.FAILED.value


def test_http_flag_round_trip(tmp_path):
    engine = make_engine(tmp_path)
    engine.start("http_500")
    assert engine.store.flags()["http_500"] is True
    engine.stop("http_500")
    assert engine.store.flags()["http_500"] is False
    assert engine.store.get_fault("http_500")["status"] == FaultStatus.IDLE.value


def test_reset_all_stops_resource_and_starts_services(tmp_path):
    engine = make_engine(tmp_path)
    engine.start("cpu")
    engine.start("app_down")
    engine.reset_all()
    assert engine.store.get_fault("cpu")["status"] == FaultStatus.IDLE.value
    assert engine.store.get_fault("app_down")["status"] == FaultStatus.IDLE.value
    assert ["target-start"] in engine.runner.calls


def test_trigger_is_recorded_in_sqlite(tmp_path):
    engine = make_engine(tmp_path)
    engine.start("cpu")
    rows = engine.events.list()
    assert rows[0]["fault_id"] == "cpu"
    assert rows[0]["action"] == "trigger"
    assert rows[0]["result"] == "started"


def test_faults_do_not_auto_expire(tmp_path):
    engine = make_engine(tmp_path)
    engine.start("slow_api")
    engine.start("cpu")
    assert engine.store.get_fault("slow_api")["expires_at"] is None
    assert engine.store.get_fault("cpu")["expires_at"] is None
    assert engine.expire_due() == []
    engine.refresh()
    assert engine.store.get_fault("slow_api")["status"] == FaultStatus.ACTIVE.value
    assert engine.store.flags()["slow_api"] is True
    assert engine.status()["faults"]["cpu"]["running_for"] is not None
    assert engine.status()["faults"]["cpu"]["expires_in"] is None

from app.common.limits import Limits


def test_cpu_workers_are_clamped():
    limits = Limits()
    assert limits.clamp_cpu_workers(0) == 1
    assert limits.clamp_cpu_workers(1) == 1
    assert limits.clamp_cpu_workers(8) == 2


def test_memory_bytes_never_exceed_hard_cap():
    limits = Limits()
    assert limits.clamp_mem_bytes(16 * 1024 * 1024) == 16 * 1024 * 1024
    assert limits.clamp_mem_bytes(512 * 1024 * 1024) == 32 * 1024 * 1024


def test_slow_sleep_is_capped():
    limits = Limits()
    assert limits.clamp_slow_sleep(30) == 5.0
    assert limits.clamp_slow_sleep(-1) == 0

from app.common.limits import Limits, cpu_quota_for_workers


def test_cpu_workers_are_clamped():
    limits = Limits()
    assert limits.clamp_cpu_workers(0) == 1
    assert limits.clamp_cpu_workers(1) == 1
    assert limits.clamp_cpu_workers(2) == 2
    assert limits.clamp_cpu_workers(8) == 4


def test_cpu_quota_scales_with_workers():
    assert cpu_quota_for_workers(2) == "180%"
    assert cpu_quota_for_workers(1) == "90%"


def test_memory_bytes_never_exceed_hard_cap():
    limits = Limits()
    assert limits.clamp_mem_bytes(128 * 1024 * 1024) == 128 * 1024 * 1024
    assert limits.clamp_mem_bytes(512 * 1024 * 1024) == 192 * 1024 * 1024


def test_slow_sleep_is_capped():
    limits = Limits()
    assert limits.clamp_slow_sleep(30) == 5.0
    assert limits.clamp_slow_sleep(-1) == 0

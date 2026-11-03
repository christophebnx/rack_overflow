import pytest

from rack_overflow.domain.supervision import RestartPolicy, next_delay

POLICY = RestartPolicy()


def test_default_policy() -> None:
    assert (POLICY.initial_s, POLICY.factor, POLICY.max_s, POLICY.stable_after_s) == (1, 2, 300, 60)


def test_first_crash_waits_the_initial_delay() -> None:
    assert next_delay(POLICY, None, 0.5) == 1


def test_delays_double_up_to_the_cap() -> None:
    delays: list[float] = []
    delay = None
    for _ in range(12):
        delay = next_delay(POLICY, delay, 1)
        delays.append(delay)
    assert delays == [1, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300, 300]


@pytest.mark.parametrize(("uptime", "delay"), [(59.9, 16), (60, 1), (3600, 1)])
def test_a_long_run_resets_the_delay(uptime: float, delay: float) -> None:
    assert next_delay(POLICY, 8, uptime) == delay

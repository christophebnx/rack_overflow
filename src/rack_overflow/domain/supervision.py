"""Restart delay policy of `rack supervise` (D-038, D-051). Pure: uptimes are passed in."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RestartPolicy:
    """Delay before restarting a crashed server: `initial_s`, times `factor`, at most `max_s`;
    back to `initial_s` after a run of at least `stable_after_s`."""

    initial_s: float = 1
    factor: float = 2
    max_s: float = 300
    stable_after_s: float = 60


def next_delay(policy: RestartPolicy, previous_delay_s: float | None, uptime_s: float) -> float:
    """Seconds to wait before the next start, after a run that lasted `uptime_s`."""
    if previous_delay_s is None or uptime_s >= policy.stable_after_s:
        return policy.initial_s
    return min(previous_delay_s * policy.factor, policy.max_s)

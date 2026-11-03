"""Edge cases of the device operations on a migrated temporary database (D-049)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings
from rack_overflow.domain import devices as rules
from rack_overflow.domain.devices import DeviceState, PairingOutcome
from rack_overflow.services import devices
from rack_overflow.storage import db, schema

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def _wrong(*codes: str) -> str:
    return next(code for code in (f"{n:08d}" for n in range(100)) if code not in codes)


def _attempts(engine: Engine) -> list[int]:
    with engine.connect() as connection:
        query = sa.select(schema.pairing_code.c.attempts).order_by(schema.pairing_code.c.id)
        return list(connection.execute(query).scalars())


def test_code_one_second_before_expiry_pairs(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    late = NOW + rules.CODE_TTL - timedelta(seconds=1)
    assert devices.pair(migrated_engine, new.code, late).outcome is PairingOutcome.PAIRED


def test_microseconds_of_now_do_not_extend_the_code(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW.replace(microsecond=999_999))
    assert new.expires_at == NOW + rules.CODE_TTL
    assert (
        devices.pair(migrated_engine, new.code, NOW + rules.CODE_TTL).outcome is PairingOutcome.CODE_EXPIRED
    )


def test_wrong_guess_is_not_charged_to_a_revoked_or_paired_device(migrated_engine: Engine) -> None:
    revoked = devices.add_device(migrated_engine, "Old", NOW)
    devices.revoke_device(migrated_engine, "Old", NOW)
    paired = devices.add_device(migrated_engine, "Mac", NOW)
    devices.pair(migrated_engine, paired.code, NOW)
    live = devices.add_device(migrated_engine, "iPhone", NOW)
    result = devices.pair(migrated_engine, _wrong(revoked.code, paired.code, live.code), NOW)
    assert result.remaining_attempts == rules.MAX_ATTEMPTS - 1
    assert _attempts(migrated_engine) == [0, 0, 1]


def test_one_exhausted_code_does_not_block_the_other_live_code(migrated_engine: Engine) -> None:
    first = devices.add_device(migrated_engine, "iPhone", NOW)
    for _ in range(rules.MAX_ATTEMPTS - 1):
        devices.pair(migrated_engine, _wrong(first.code), NOW)
    second = devices.add_device(migrated_engine, "Mac", NOW)
    result = devices.pair(migrated_engine, _wrong(first.code, second.code), NOW)
    assert result == devices.PairingResult(PairingOutcome.WRONG_CODE, remaining_attempts=4)
    assert devices.pair(migrated_engine, first.code, NOW).outcome is PairingOutcome.TOO_MANY_ATTEMPTS
    assert devices.pair(migrated_engine, second.code, NOW).outcome is PairingOutcome.PAIRED


def test_re_added_device_pairs_and_the_revoked_token_stays_refused(migrated_engine: Engine) -> None:
    first = devices.add_device(migrated_engine, "iPhone", NOW)
    old_token = devices.pair(migrated_engine, first.code, NOW).token
    assert old_token is not None
    devices.revoke_device(migrated_engine, " iPhone ", NOW)
    again = devices.add_device(migrated_engine, "iPhone", NOW)
    new_token = devices.pair(migrated_engine, again.code, NOW).token
    assert new_token is not None and new_token != old_token
    assert devices.authenticate(migrated_engine, old_token, NOW) is None
    device = devices.authenticate(migrated_engine, new_token, NOW)
    assert device is not None and device.name == "iPhone"
    states = [(info.name, info.state) for info in devices.list_devices(migrated_engine)]
    assert states == [("iPhone", DeviceState.REVOKED), ("iPhone", DeviceState.PAIRED)]


def test_revoking_twice_is_refused(migrated_engine: Engine) -> None:
    devices.add_device(migrated_engine, "iPhone", NOW)
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    with pytest.raises(rules.DeviceError, match="no active device"):
        devices.revoke_device(migrated_engine, "iPhone", NOW)


def test_same_code_drawn_twice_judges_the_newest(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(devices, "_new_code", lambda: "12345678")
    devices.add_device(migrated_engine, "iPhone", NOW)
    devices.add_device(migrated_engine, "Mac", NOW)
    result = devices.pair(migrated_engine, "12345678", NOW)
    assert (result.outcome, result.device_name) == (PairingOutcome.PAIRED, "Mac")


def test_code_is_eight_digits_with_leading_zeros(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(devices.secrets, "randbelow", lambda bound: 42)
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    assert new.code == "00000042"
    assert devices.pair(migrated_engine, "0000 0042", NOW).outcome is PairingOutcome.PAIRED


def test_concurrent_pairing_with_one_code_pairs_once(migrated_engine: Engine, settings: Settings) -> None:
    code = devices.add_device(migrated_engine, "iPhone", NOW).code
    engines = [db.create_engine(settings.database_path) for _ in range(4)]
    results: list[devices.PairingResult] = []
    barrier = threading.Barrier(len(engines))

    def attempt(engine: Engine) -> None:
        barrier.wait()
        results.append(devices.pair(engine, code, NOW))

    threads = [threading.Thread(target=attempt, args=(engine,)) for engine in engines]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    for engine in engines:
        engine.dispose()
    outcomes = sorted(result.outcome.value for result in results)
    assert outcomes == ["code_expired"] * 3 + ["paired"]


def test_authenticate_with_a_clock_behind_last_seen_neither_fails_nor_writes(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    token = devices.pair(migrated_engine, new.code, NOW).token
    assert token is not None
    device = devices.authenticate(migrated_engine, token, NOW - timedelta(hours=2))
    assert device is not None and not device.renewed

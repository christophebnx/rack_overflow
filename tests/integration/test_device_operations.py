"""Device operations on a migrated temporary database, with an injected `now`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.config import Settings
from rack_overflow.domain import devices as rules
from rack_overflow.domain.devices import DeviceError, DeviceState, PairingOutcome
from rack_overflow.services import devices
from rack_overflow.storage import devices as queries
from rack_overflow.storage import schema
from rack_overflow.storage.errors import DeviceNameTakenError

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10**8:08d}"


def _attempts(engine: Engine) -> list[int]:
    with engine.connect() as connection:
        return list(connection.execute(sa.select(schema.pairing_code.c.attempts)).scalars())


def test_add_returns_the_code_once_and_stores_only_its_hash(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "  iPhone ", NOW)
    assert new.name == "iPhone"
    assert rules.normalise_code(new.code) == new.code
    assert new.expires_at == NOW + rules.CODE_TTL
    with migrated_engine.connect() as connection:
        device = connection.execute(sa.select(schema.device)).one()
        code = connection.execute(sa.select(schema.pairing_code)).one()
    assert (device.user_id, device.token_hash, device.created_at) == (1, None, "2026-11-03T18:04:05Z")
    assert (code.code_hash, code.expires_at, code.attempts) == (
        rules.hash_secret(new.code),
        "2026-11-03T18:14:05Z",
        0,
    )


def test_code_pairs_once(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    result = devices.pair(migrated_engine, rules.format_code(new.code), NOW + timedelta(minutes=1))
    assert result.outcome is PairingOutcome.PAIRED
    assert result.device_name == "iPhone"
    assert result.token is not None and rules.looks_like_token(result.token)
    again = devices.pair(migrated_engine, new.code, NOW + timedelta(minutes=2))
    assert again == devices.PairingResult(PairingOutcome.CODE_EXPIRED)


def test_code_expires_after_ten_minutes(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    result = devices.pair(migrated_engine, new.code, NOW + rules.CODE_TTL)
    assert result == devices.PairingResult(PairingOutcome.CODE_EXPIRED)


def test_wrong_code_charges_the_live_code(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    result = devices.pair(migrated_engine, _wrong(new.code), NOW)
    assert result == devices.PairingResult(PairingOutcome.WRONG_CODE, remaining_attempts=4)
    assert _attempts(migrated_engine) == [1]


def test_fifth_wrong_attempt_blocks_the_code(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    outcomes = [devices.pair(migrated_engine, _wrong(new.code), NOW) for _ in range(rules.MAX_ATTEMPTS)]
    assert [result.remaining_attempts for result in outcomes[:-1]] == [4, 3, 2, 1]
    assert outcomes[-1] == devices.PairingResult(PairingOutcome.TOO_MANY_ATTEMPTS)
    assert devices.pair(migrated_engine, new.code, NOW).outcome is PairingOutcome.TOO_MANY_ATTEMPTS
    # a sixth wrong guess finds no live code: nothing charged
    assert devices.pair(migrated_engine, _wrong(new.code), NOW) == devices.PairingResult(
        PairingOutcome.WRONG_CODE
    )
    assert _attempts(migrated_engine) == [rules.MAX_ATTEMPTS]


def test_fourth_wrong_attempt_still_lets_the_right_code_pair(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    for _ in range(rules.MAX_ATTEMPTS - 1):
        devices.pair(migrated_engine, _wrong(new.code), NOW)
    assert devices.pair(migrated_engine, new.code, NOW).outcome is PairingOutcome.PAIRED


@pytest.mark.parametrize("raw", ["1234", "abcdefgh", "", "1234 56789"])
def test_malformed_input_charges_nothing(migrated_engine: Engine, raw: str) -> None:
    devices.add_device(migrated_engine, "iPhone", NOW)
    assert devices.pair(migrated_engine, raw, NOW) == devices.PairingResult(PairingOutcome.WRONG_CODE)
    assert _attempts(migrated_engine) == [0]


def test_wrong_guess_without_a_live_code_changes_nothing(migrated_engine: Engine) -> None:
    devices.add_device(migrated_engine, "iPhone", NOW)
    late = NOW + rules.CODE_TTL
    assert devices.pair(migrated_engine, "00000000", late) == devices.PairingResult(PairingOutcome.WRONG_CODE)
    assert _attempts(migrated_engine) == [0]


def test_wrong_guess_reports_the_smallest_remaining_count(migrated_engine: Engine) -> None:
    first = devices.add_device(migrated_engine, "iPhone", NOW)
    devices.pair(migrated_engine, _wrong(first.code), NOW)
    second = devices.add_device(migrated_engine, "Mac", NOW)
    wrong = next(code for code in (f"{n:08d}" for n in range(100)) if code not in {first.code, second.code})
    result = devices.pair(migrated_engine, wrong, NOW)
    assert result == devices.PairingResult(PairingOutcome.WRONG_CODE, remaining_attempts=3)
    assert sorted(_attempts(migrated_engine)) == [1, 2]


def test_revoked_device_code_is_refused(migrated_engine: Engine) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    assert devices.pair(migrated_engine, new.code, NOW).outcome is PairingOutcome.CODE_EXPIRED


def test_duplicate_active_name_is_refused_until_revoked(migrated_engine: Engine) -> None:
    devices.add_device(migrated_engine, "iPhone", NOW)
    with pytest.raises(DeviceError, match='device "iPhone" already exists; revoke it first'):
        devices.add_device(migrated_engine, " iPhone", NOW)
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    assert devices.add_device(migrated_engine, "iPhone", NOW).name == "iPhone"


def test_storage_refuses_a_duplicate_active_name(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        queries.insert_device(connection, 1, "iPhone", "2026-11-03T18:04:05Z")
        with pytest.raises(DeviceNameTakenError):
            queries.insert_device(connection, 1, "iPhone", "2026-11-03T18:04:05Z")
    assert [info.name for info in devices.list_devices(migrated_engine)] == ["iPhone"]


def test_revoking_an_unknown_name_is_refused(migrated_engine: Engine) -> None:
    with pytest.raises(DeviceError, match='no active device named "Nope"'):
        devices.revoke_device(migrated_engine, "Nope", NOW)


def test_list_shows_states_oldest_first(migrated_engine: Engine) -> None:
    assert devices.list_devices(migrated_engine) == []
    phone = devices.add_device(migrated_engine, "iPhone", NOW)
    devices.add_device(migrated_engine, "Mac", NOW + timedelta(seconds=1))
    devices.add_device(migrated_engine, "Old", NOW + timedelta(seconds=2))
    devices.pair(migrated_engine, phone.code, NOW + timedelta(minutes=1))
    devices.revoke_device(migrated_engine, "Old", NOW)
    listed = devices.list_devices(migrated_engine)
    assert [(info.name, info.state) for info in listed] == [
        ("iPhone", DeviceState.PAIRED),
        ("Mac", DeviceState.PENDING),
        ("Old", DeviceState.REVOKED),
    ]
    assert listed[0].last_seen_at == NOW + timedelta(minutes=1)
    assert listed[1].last_seen_at is None
    assert listed[0].created_at == NOW


def _paired(engine: Engine) -> str:
    new = devices.add_device(engine, "iPhone", NOW)
    token = devices.pair(engine, new.code, NOW).token
    assert token is not None
    return token


def _last_seen(engine: Engine) -> str:
    with engine.connect() as connection:
        return connection.execute(sa.select(schema.device.c.last_seen_at)).scalar_one()


def test_authenticate_a_valid_token(migrated_engine: Engine) -> None:
    token = _paired(migrated_engine)
    device = devices.authenticate(migrated_engine, token, NOW + timedelta(minutes=5))
    assert device is not None
    assert (device.user_id, device.name, device.renewed) == (1, "iPhone", False)
    assert _last_seen(migrated_engine) == "2026-11-03T18:04:05Z"


def test_authenticate_renews_after_an_hour(migrated_engine: Engine) -> None:
    token = _paired(migrated_engine)
    almost = devices.authenticate(migrated_engine, token, NOW + rules.RENEW_AFTER - timedelta(seconds=1))
    assert almost is not None and not almost.renewed
    renewed = devices.authenticate(migrated_engine, token, NOW + rules.RENEW_AFTER)
    assert renewed is not None and renewed.renewed
    assert _last_seen(migrated_engine) == "2026-11-03T19:04:05Z"


def test_authenticate_refuses_unknown_revoked_and_expired_tokens(migrated_engine: Engine) -> None:
    token = _paired(migrated_engine)
    assert devices.authenticate(migrated_engine, "A" * rules.TOKEN_LENGTH, NOW) is None
    assert devices.authenticate(migrated_engine, token, NOW + rules.TOKEN_LIFETIME) is None
    devices.revoke_device(migrated_engine, "iPhone", NOW)
    assert devices.authenticate(migrated_engine, token, NOW) is None


def test_malformed_token_skips_the_database(migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migrated_engine, "begin", lambda: pytest.fail("database touched"))
    assert devices.authenticate(migrated_engine, "short", NOW) is None
    assert devices.authenticate(migrated_engine, "é" * rules.TOKEN_LENGTH, NOW) is None


def test_code_and_token_are_never_stored_in_clear(migrated_engine: Engine, settings: Settings) -> None:
    new = devices.add_device(migrated_engine, "iPhone", NOW)
    devices.pair(migrated_engine, _wrong(new.code), NOW)
    token = devices.pair(migrated_engine, new.code, NOW).token
    assert token is not None
    migrated_engine.dispose()
    stored = b"".join(path.read_bytes() for path in settings.storage.data_dir.glob("rack.sqlite*"))
    assert new.code.encode() not in stored
    assert token.encode() not in stored
    assert rules.hash_secret(token).encode() in stored

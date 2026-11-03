"""Device operations (D-040, D-049): add, list, revoke, pair and authenticate, one transaction each.

The random pairing code and token are drawn here (`secrets`) and returned in clear once; only
their SHA-256 hashes are stored. `now` comes from the caller.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from rack_overflow.domain import devices as rules
from rack_overflow.domain.devices import DeviceError, DeviceState, PairingOutcome
from rack_overflow.domain.timestamps import from_text, to_text
from rack_overflow.domain.users import SINGLE_USER_ID
from rack_overflow.storage import devices as queries
from rack_overflow.storage.errors import DeviceNameTakenError


@dataclass(frozen=True)
class NewDevice:
    """A device just added, with its pairing code in clear (shown once)."""

    name: str
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class DeviceInfo:
    """One row of `rack device list`."""

    name: str
    state: DeviceState
    created_at: datetime
    last_seen_at: datetime | None


@dataclass(frozen=True)
class PairingResult:
    """Outcome of a pairing attempt; `token` in clear only when paired."""

    outcome: PairingOutcome
    token: str | None = None
    remaining_attempts: int | None = None
    device_name: str | None = None


@dataclass(frozen=True)
class Device:
    """An authenticated device; `renewed` when its last use was just refreshed."""

    id: int
    user_id: int
    name: str
    renewed: bool


def _new_code() -> str:
    return f"{secrets.randbelow(10**rules.CODE_DIGITS):0{rules.CODE_DIGITS}d}"


def add_device(engine: Engine, name: str, now: datetime) -> NewDevice:
    """Create an unpaired device and its pairing code; an active device with the same name is refused."""
    name = rules.validate_name(name)
    code = _new_code()
    expires_at = now + rules.CODE_TTL
    with engine.begin() as connection:
        try:
            device_id = queries.insert_device(connection, SINGLE_USER_ID, name, to_text(now))
        except DeviceNameTakenError as error:
            raise DeviceError(str(error)) from error
        queries.insert_pairing_code(connection, device_id, rules.hash_secret(code), to_text(expires_at))
    return NewDevice(name=name, code=code, expires_at=from_text(to_text(expires_at)))


def list_devices(engine: Engine) -> list[DeviceInfo]:
    """Every device, revoked ones included, oldest first."""
    with engine.begin() as connection:
        rows = queries.all_devices(connection)
    return [
        DeviceInfo(
            name=row.name,
            state=rules.state_of(paired=row.token_hash is not None, revoked=row.revoked_at is not None),
            created_at=from_text(row.created_at),
            last_seen_at=from_text(row.last_seen_at) if row.last_seen_at else None,
        )
        for row in rows
    ]


def revoke_device(engine: Engine, name: str, now: datetime) -> None:
    """Revoke the active device named `name`: its token and pending codes stop working at once."""
    with engine.begin() as connection:
        row = queries.active_device_by_name(connection, SINGLE_USER_ID, name.strip())
        if row is None:
            raise DeviceError(f'no active device named "{name.strip()}"')
        queries.revoke(connection, row.id, to_text(now))


def pair(engine: Engine, raw_code: str, now: datetime) -> PairingResult:
    """Pair a browser with the code typed in; a wrong guess is charged to every live code (D-049)."""
    code = rules.normalise_code(raw_code)
    if code is None:
        return PairingResult(PairingOutcome.WRONG_CODE)  # malformed: guesses nothing, charges nothing
    with engine.begin() as connection:
        matches = queries.codes_by_hash(connection, rules.hash_secret(code))
        if matches:
            return _pair_match(connection, matches[0], now)
        return _charge_miss(connection, now)


def _pair_match(connection: sa.Connection, row: sa.Row, now: datetime) -> PairingResult:
    outcome = rules.judge_match(
        from_text(row.expires_at),
        from_text(row.used_at) if row.used_at else None,
        row.attempts,
        device_revoked=row.device_revoked_at is not None,
        device_paired=row.device_token_hash is not None,
        now=now,
    )
    if outcome is not PairingOutcome.PAIRED:
        return PairingResult(outcome)
    token = secrets.token_urlsafe(rules.TOKEN_BYTES)
    savepoint = connection.begin_nested()
    claimed = queries.mark_used(connection, row.id, to_text(now)) and queries.set_token(
        connection, row.device_id, rules.hash_secret(token), to_text(now)
    )
    if not claimed:  # used or paired since it was read: nothing written, same refusal
        savepoint.rollback()
        return PairingResult(PairingOutcome.CODE_EXPIRED)
    savepoint.commit()
    return PairingResult(outcome, token=token, device_name=row.device_name)


def _charge_miss(connection: sa.Connection, now: datetime) -> PairingResult:
    live = [
        row
        for row in queries.unused_codes(connection)
        if rules.is_live(from_text(row.expires_at), None, row.attempts, now)
    ]
    queries.add_attempt(connection, [row.id for row in live])
    outcome, remaining = rules.judge_miss([row.attempts + 1 for row in live])
    return PairingResult(outcome, remaining_attempts=remaining)


def authenticate(engine: Engine, token: str, now: datetime) -> Device | None:
    """The active device holding `token`, or None; refreshes its last use at most once an hour."""
    if not rules.looks_like_token(token):
        return None
    with engine.begin() as connection:
        row = queries.device_by_token_hash(connection, rules.hash_secret(token))
        if row is None:
            return None
        last_seen = from_text(row.last_seen_at) if row.last_seen_at else None
        if not rules.token_valid(last_seen, now):
            return None
        renewed = rules.needs_renewal(last_seen, now)
        if renewed:
            queries.touch(connection, row.id, to_text(now))
    return Device(id=row.id, user_id=row.user_id, name=row.name, renewed=renewed)

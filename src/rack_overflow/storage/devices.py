"""Device and pairing-code queries (SQLAlchemy Core). Each takes a `Connection`: the caller owns the
transaction. Timestamps are database text (`domain.timestamps`); no rule is decided here."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from rack_overflow.storage.errors import DeviceNameTakenError
from rack_overflow.storage.schema import device, pairing_code

ACTIVE = device.c.revoked_at.is_(None)


def insert_device(connection: sa.Connection, user_id: int, name: str, created_at: str) -> int:
    """Insert an unpaired device and return its id; an active device with this name is refused."""
    savepoint = connection.begin_nested()
    try:
        result = connection.execute(
            sa.insert(device).values(user_id=user_id, name=name, created_at=created_at)
        )
    except sa.exc.IntegrityError:
        savepoint.rollback()
        raise DeviceNameTakenError(f'device "{name}" already exists; revoke it first') from None
    savepoint.commit()
    return int(result.inserted_primary_key[0])


def insert_pairing_code(connection: sa.Connection, device_id: int, code_hash: str, expires_at: str) -> int:
    """Insert a pairing code for `device_id` and return its id."""
    result = connection.execute(
        sa.insert(pairing_code).values(device_id=device_id, code_hash=code_hash, expires_at=expires_at)
    )
    return int(result.inserted_primary_key[0])


def active_device_by_name(connection: sa.Connection, user_id: int, name: str) -> sa.Row | None:
    """The active (not revoked) device of `user_id` named `name`, or None."""
    query = sa.select(device).where(device.c.user_id == user_id, device.c.name == name, ACTIVE)
    return connection.execute(query).first()


def all_devices(connection: sa.Connection) -> Sequence[sa.Row]:
    """Every device, revoked ones included, oldest first."""
    query = sa.select(device).order_by(device.c.created_at, device.c.id)
    return connection.execute(query).all()


def revoke(connection: sa.Connection, device_id: int, now: str) -> None:
    """Mark the device revoked: its token and codes stop working."""
    connection.execute(sa.update(device).where(device.c.id == device_id).values(revoked_at=now))


def codes_by_hash(connection: sa.Connection, code_hash: str) -> Sequence[sa.Row]:
    """Codes with this hash, newest first, with their device's `revoked_at`, `token_hash` and `name`."""
    query = (
        sa.select(
            pairing_code,
            device.c.revoked_at.label("device_revoked_at"),
            device.c.token_hash.label("device_token_hash"),
            device.c.name.label("device_name"),
        )
        .join(device, device.c.id == pairing_code.c.device_id)
        .where(pairing_code.c.code_hash == code_hash)
        .order_by(pairing_code.c.id.desc())
    )
    return connection.execute(query).all()


def unused_codes(connection: sa.Connection) -> Sequence[sa.Row]:
    """Unused codes of active, unpaired devices (the caller keeps the live ones)."""
    query = (
        sa.select(pairing_code)
        .join(device, device.c.id == pairing_code.c.device_id)
        .where(pairing_code.c.used_at.is_(None), ACTIVE, device.c.token_hash.is_(None))
        .order_by(pairing_code.c.id)
    )
    return connection.execute(query).all()


def add_attempt(connection: sa.Connection, code_ids: Sequence[int]) -> None:
    """Charge one attempt to each code of `code_ids`."""
    if code_ids:
        connection.execute(
            sa.update(pairing_code)
            .where(pairing_code.c.id.in_(code_ids))
            .values(attempts=pairing_code.c.attempts + 1)
        )


def mark_used(connection: sa.Connection, code_id: int, now: str) -> None:
    """Mark the code used: it never pairs again."""
    connection.execute(sa.update(pairing_code).where(pairing_code.c.id == code_id).values(used_at=now))


def set_token(connection: sa.Connection, device_id: int, token_hash: str, now: str) -> None:
    """Store the hash of the device's token and its first use."""
    connection.execute(
        sa.update(device).where(device.c.id == device_id).values(token_hash=token_hash, last_seen_at=now)
    )


def device_by_token_hash(connection: sa.Connection, token_hash: str) -> sa.Row | None:
    """The active device holding this token hash, or None."""
    return connection.execute(sa.select(device).where(device.c.token_hash == token_hash, ACTIVE)).first()


def touch(connection: sa.Connection, device_id: int, now: str) -> None:
    """Record the device's last use."""
    connection.execute(sa.update(device).where(device.c.id == device_id).values(last_seen_at=now))

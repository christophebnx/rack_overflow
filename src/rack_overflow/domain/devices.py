"""Device pairing and token rules (D-040, D-049). Pure: `now` is passed in, no randomness drawn here.

A device is created with a one-time pairing code; typing it in the browser issues a token, stored
as a hash and sent back as a cookie. Callers draw the random code and token (`secrets`).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from rack_overflow.domain.errors import DomainError

CODE_DIGITS = 8
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
TOKEN_BYTES = 32
TOKEN_LENGTH = 43  # `secrets.token_urlsafe(TOKEN_BYTES)`: 32 bytes in unpadded base64url
TOKEN_LIFETIME = timedelta(days=400)
RENEW_AFTER = timedelta(hours=1)
NAME_MAX = 40

_CODE = re.compile(rf"[0-9]{{{CODE_DIGITS}}}", re.ASCII)
_TOKEN = re.compile(rf"[A-Za-z0-9_-]{{{TOKEN_LENGTH}}}", re.ASCII)
_CODE_SEPARATORS = str.maketrans("", "", " -")


class DeviceError(DomainError):
    """A device operation was refused (invalid name, name taken, unknown device)."""


class PairingOutcome(StrEnum):
    """Result of a pairing attempt (stable English codes)."""

    PAIRED = "paired"
    WRONG_CODE = "wrong_code"
    CODE_EXPIRED = "code_expired"
    TOO_MANY_ATTEMPTS = "too_many_attempts"


class DeviceState(StrEnum):
    """What `rack device list` shows for a device."""

    PENDING = "pending"
    PAIRED = "paired"
    REVOKED = "revoked"


def validate_name(raw: str) -> str:
    """The device name stripped: 1 to `NAME_MAX` characters, no control character."""
    name = raw.strip()
    if not name:
        raise DeviceError("device name must not be empty")
    if len(name) > NAME_MAX:
        raise DeviceError(f"device name must be at most {NAME_MAX} characters")
    if any(unicodedata.category(char) == "Cc" for char in name):
        raise DeviceError("device name must not contain control characters")
    return name


def normalise_code(raw: str) -> str | None:
    """The code without spaces and hyphens, or None unless it is exactly `CODE_DIGITS` ASCII digits."""
    code = raw.translate(_CODE_SEPARATORS)
    return code if _CODE.fullmatch(code) else None


def format_code(code: str) -> str:
    """The code as displayed: two groups of four digits (`1234 5678`)."""
    half = len(code) // 2
    return f"{code[:half]} {code[half:]}"


def hash_secret(secret: str) -> str:
    """SHA-256 hex digest of a pairing code or a token (no salt, no slow hash: D-049)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def looks_like_token(token: str) -> bool:
    """True when `token` has the shape of an issued token (checked before any database access)."""
    return _TOKEN.fullmatch(token) is not None


def is_live(expires_at: datetime, used_at: datetime | None, attempts: int, now: datetime) -> bool:
    """An unused, unexpired code with attempts left: the codes a wrong guess is charged to."""
    return used_at is None and now < expires_at and attempts < MAX_ATTEMPTS


def judge_match(
    expires_at: datetime,
    used_at: datetime | None,
    attempts: int,
    *,
    device_revoked: bool,
    device_paired: bool,
    now: datetime,
) -> PairingOutcome:
    """Outcome of typing a code whose hash matched a stored code."""
    if used_at is not None or now >= expires_at or device_revoked or device_paired:
        return PairingOutcome.CODE_EXPIRED
    if attempts >= MAX_ATTEMPTS:
        return PairingOutcome.TOO_MANY_ATTEMPTS
    return PairingOutcome.PAIRED


def judge_miss(charged_attempts: Sequence[int]) -> tuple[PairingOutcome, int | None]:
    """Outcome of a wrong guess, from the attempt counts of the live codes after charging them.

    No live code: `wrong_code` with no count. Every charged code exhausted: `too_many_attempts`.
    Else `wrong_code` with the smallest number of attempts left.
    """
    if not charged_attempts:
        return PairingOutcome.WRONG_CODE, None
    left = [MAX_ATTEMPTS - attempts for attempts in charged_attempts if attempts < MAX_ATTEMPTS]
    if not left:
        return PairingOutcome.TOO_MANY_ATTEMPTS, None
    return PairingOutcome.WRONG_CODE, min(left)


def state_of(*, paired: bool, revoked: bool) -> DeviceState:
    """Revoked wins; else paired once a token was issued; else pending."""
    if revoked:
        return DeviceState.REVOKED
    return DeviceState.PAIRED if paired else DeviceState.PENDING


def token_valid(last_seen_at: datetime | None, now: datetime) -> bool:
    """A token stays valid while it was used within `TOKEN_LIFETIME`."""
    return last_seen_at is not None and now - last_seen_at < TOKEN_LIFETIME


def needs_renewal(last_seen_at: datetime | None, now: datetime) -> bool:
    """`last_seen_at` is refreshed (and the cookie re-sent) at most once per `RENEW_AFTER`."""
    return last_seen_at is None or now - last_seen_at >= RENEW_AFTER

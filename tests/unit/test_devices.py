from datetime import UTC, datetime, timedelta

import pytest

from rack_overflow.domain import devices
from rack_overflow.domain.devices import DeviceError, DeviceState, PairingOutcome
from rack_overflow.domain.errors import DomainError
from rack_overflow.domain.users import SINGLE_USER_ID

NOW = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)
LATER = NOW + devices.CODE_TTL


def test_single_user_id() -> None:
    assert SINGLE_USER_ID == 1


def test_device_error_is_a_domain_error() -> None:
    assert issubclass(DeviceError, DomainError)


@pytest.mark.parametrize(("raw", "name"), [("iPhone", "iPhone"), ("  Mac de bureau ", "Mac de bureau")])
def test_valid_names_are_stripped(raw: str, name: str) -> None:
    assert devices.validate_name(raw) == name


def test_name_at_the_limit_passes() -> None:
    assert devices.validate_name("x" * devices.NAME_MAX) == "x" * devices.NAME_MAX


@pytest.mark.parametrize("raw", ["", "   ", "x" * (devices.NAME_MAX + 1), "a\nb", "a\tb", "a\x7fb", "a\x85b"])
def test_invalid_names_are_refused(raw: str) -> None:
    with pytest.raises(DeviceError):
        devices.validate_name(raw)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("12345678", "12345678"),
        ("1234 5678", "12345678"),
        ("1234-5678", "12345678"),
        (" 12 34-56 78 ", "12345678"),
        ("1234567", None),
        ("123456789", None),
        ("1234567a", None),
        ("", None),
        ("١٢٣٤٥٦٧٨", None),  # non-ASCII digits
        ("1234\t5678", None),
    ],
)
def test_normalise_code(raw: str, code: str | None) -> None:
    assert devices.normalise_code(raw) == code


def test_format_code() -> None:
    assert devices.format_code("01234567") == "0123 4567"


def test_hash_secret_is_sha256_hex() -> None:
    assert devices.hash_secret("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.parametrize(
    ("token", "shaped"),
    [
        ("A" * 43, True),
        ("aZ09_-" * 7 + "x", True),
        ("A" * 42, False),
        ("A" * 44, False),
        ("A" * 42 + "=", False),
    ],
)
def test_looks_like_token(token: str, shaped: bool) -> None:
    assert devices.looks_like_token(token) is shaped


def test_is_live() -> None:
    assert devices.is_live(LATER, None, 0, NOW)
    assert devices.is_live(LATER, None, devices.MAX_ATTEMPTS - 1, NOW)
    assert not devices.is_live(LATER, None, devices.MAX_ATTEMPTS, NOW)
    assert not devices.is_live(LATER, NOW, 0, NOW)
    assert not devices.is_live(LATER, None, 0, LATER)  # expires_at == now is expired


def _judge(**overrides: object) -> PairingOutcome:
    values: dict[str, object] = {
        "expires_at": LATER,
        "used_at": None,
        "attempts": 0,
        "device_revoked": False,
        "device_paired": False,
        "now": NOW,
    }
    values.update(overrides)
    return devices.judge_match(
        values["expires_at"],  # type: ignore[arg-type]
        values["used_at"],  # type: ignore[arg-type]
        values["attempts"],  # type: ignore[arg-type]
        device_revoked=values["device_revoked"],  # type: ignore[arg-type]
        device_paired=values["device_paired"],  # type: ignore[arg-type]
        now=values["now"],  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("overrides", "outcome"),
    [
        ({}, PairingOutcome.PAIRED),
        ({"attempts": 4}, PairingOutcome.PAIRED),
        ({"attempts": 5}, PairingOutcome.TOO_MANY_ATTEMPTS),
        ({"now": LATER - timedelta(seconds=1)}, PairingOutcome.PAIRED),
        ({"now": LATER}, PairingOutcome.CODE_EXPIRED),
        ({"used_at": NOW}, PairingOutcome.CODE_EXPIRED),
        ({"device_revoked": True}, PairingOutcome.CODE_EXPIRED),
        ({"device_paired": True}, PairingOutcome.CODE_EXPIRED),
        ({"now": LATER, "attempts": 5}, PairingOutcome.CODE_EXPIRED),
    ],
)
def test_judge_match(overrides: dict[str, object], outcome: PairingOutcome) -> None:
    assert _judge(**overrides) is outcome


@pytest.mark.parametrize(
    ("charged", "result"),
    [
        ([], (PairingOutcome.WRONG_CODE, None)),
        ([1], (PairingOutcome.WRONG_CODE, 4)),
        ([4], (PairingOutcome.WRONG_CODE, 1)),
        ([5], (PairingOutcome.TOO_MANY_ATTEMPTS, None)),
        ([5, 2], (PairingOutcome.WRONG_CODE, 3)),
        ([3, 2], (PairingOutcome.WRONG_CODE, 2)),
        ([5, 5], (PairingOutcome.TOO_MANY_ATTEMPTS, None)),
    ],
)
def test_judge_miss(charged: list[int], result: tuple[PairingOutcome, int | None]) -> None:
    assert devices.judge_miss(charged) == result


@pytest.mark.parametrize(
    ("paired", "revoked", "state"),
    [
        (False, False, DeviceState.PENDING),
        (True, False, DeviceState.PAIRED),
        (True, True, DeviceState.REVOKED),
        (False, True, DeviceState.REVOKED),
    ],
)
def test_state_of(paired: bool, revoked: bool, state: DeviceState) -> None:
    assert devices.state_of(paired=paired, revoked=revoked) is state


def test_token_valid_boundaries() -> None:
    assert devices.token_valid(NOW, NOW)
    assert devices.token_valid(NOW, NOW + devices.TOKEN_LIFETIME - timedelta(seconds=1))
    assert not devices.token_valid(NOW, NOW + devices.TOKEN_LIFETIME)
    assert not devices.token_valid(None, NOW)


def test_needs_renewal_boundaries() -> None:
    assert not devices.needs_renewal(NOW, NOW)
    assert not devices.needs_renewal(NOW, NOW + devices.RENEW_AFTER - timedelta(seconds=1))
    assert devices.needs_renewal(NOW, NOW + devices.RENEW_AFTER)
    assert devices.needs_renewal(None, NOW)


def test_constants() -> None:
    assert (devices.CODE_DIGITS, devices.MAX_ATTEMPTS, devices.NAME_MAX) == (8, 5, 40)
    durations = (devices.CODE_TTL, devices.TOKEN_LIFETIME, devices.RENEW_AFTER)
    assert durations == (timedelta(minutes=10), timedelta(days=400), timedelta(hours=1))

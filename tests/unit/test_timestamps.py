from datetime import UTC, datetime, timedelta, timezone

import pytest

from rack_overflow.domain.errors import DomainError
from rack_overflow.domain.timestamps import TimestampError, from_text, to_text


def test_round_trip_in_utc() -> None:
    moment = datetime(2026, 11, 3, 18, 4, 5, tzinfo=UTC)
    assert to_text(moment) == "2026-11-03T18:04:05Z"
    assert from_text("2026-11-03T18:04:05Z") == moment


def test_other_zone_is_converted_and_microseconds_dropped() -> None:
    paris = timezone(timedelta(hours=1))
    assert to_text(datetime(2026, 11, 3, 19, 4, 5, 999999, tzinfo=paris)) == "2026-11-03T18:04:05Z"


def test_naive_datetime_is_refused() -> None:
    with pytest.raises(DomainError):
        to_text(datetime(2026, 11, 3, 18, 4, 5))


@pytest.mark.parametrize("text", ["2026-11-03 18:04:05", "2026-11-03T18:04:05+00:00", "", "x"])
def test_malformed_text_is_refused(text: str) -> None:
    with pytest.raises(TimestampError):
        from_text(text)


def test_parsed_value_is_aware_utc() -> None:
    assert from_text("2026-01-01T00:00:00Z").tzinfo is UTC

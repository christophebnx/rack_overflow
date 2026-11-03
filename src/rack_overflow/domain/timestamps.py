"""Database timestamp text: UTC `YYYY-MM-DDTHH:MM:SSZ`, the one format of every timestamp column.

Pure: callers pass aware datetimes in; seconds precision (microseconds are dropped).
"""

from __future__ import annotations

from datetime import UTC, datetime

from rack_overflow.domain.errors import DomainError

TEXT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class TimestampError(DomainError):
    """A datetime without a time zone, or a text that is not a database timestamp."""


def to_text(moment: datetime) -> str:
    """`moment` (aware) as UTC database text; a naive datetime is refused."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise TimestampError("timestamp must be timezone-aware")
    return moment.astimezone(UTC).strftime(TEXT_FORMAT)


def from_text(text: str) -> datetime:
    """The aware UTC datetime of a database timestamp text."""
    try:
        return datetime.strptime(text, TEXT_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        raise TimestampError(f"not a database timestamp: {text!r}") from None

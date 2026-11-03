"""The one log line format of the server and the supervisor: UTC timestamp, level, logger, message."""

from __future__ import annotations

import logging
import time

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_formatter() -> logging.Formatter:
    """A formatter writing `LOG_FORMAT` with UTC timestamps."""
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    formatter.converter = time.gmtime
    return formatter

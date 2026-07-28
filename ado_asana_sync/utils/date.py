"""
Date utilities.

This module contains utility functions for working with datetime objects.
"""

import logging
import os
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_LOGGER = logging.getLogger(__name__)


def iso8601_utc(timestamp: datetime) -> str:
    """
    Convert a given datetime object to a string representation in ISO 8601 format with UTC timezone.

    Args:
        timestamp (datetime): A datetime object representing a specific date and time.

    Returns:
        str: A string representing the given datetime object in ISO 8601 format with UTC timezone.

    Note:
        Naive datetime objects (without timezone information) are assumed to be in UTC.
    """
    if not timestamp.tzinfo:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat()


def get_ado_timezone() -> tzinfo:
    """
    Resolve the IANA timezone that ADO due-date instants should be interpreted in.

    Reads the `ADO_TIMEZONE` environment variable. Falls back to UTC when unset, blank, or
    an invalid IANA name is given (a warning is logged in the invalid case). This never
    consults the host machine's local timezone.

    Returns:
        tzinfo: `timezone.utc` by default, or the resolved `ZoneInfo` for a valid name.
    """
    name = os.environ.get("ADO_TIMEZONE", "").strip()
    if not name:
        return timezone.utc

    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        _LOGGER.warning("Invalid ADO_TIMEZONE '%s', falling back to UTC", name)
        return timezone.utc


def _to_local_date_string(value: datetime, tz: tzinfo) -> str:
    """
    Convert a datetime to a YYYY-MM-DD calendar date string in the given timezone.

    Naive datetimes are assumed to be UTC (never the host's local timezone) before conversion.

    Args:
        value: The datetime to convert.
        tz: The timezone to render the calendar date in.

    Returns:
        str: The calendar date in `tz`, formatted as YYYY-MM-DD.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz).strftime("%Y-%m-%d")

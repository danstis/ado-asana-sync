"""
Date utilities.

This module contains utility functions for working with datetime objects.
"""

from datetime import datetime, timezone


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

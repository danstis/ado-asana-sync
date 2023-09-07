from datetime import datetime, timezone

def iso8601_utc(dt: datetime) -> str:
    """
    Convert a given datetime object to a string representation in ISO 8601 format with UTC timezone.

    Args:
        dt (datetime): A datetime object representing a specific date and time.

    Returns:
        str: A string representing the given datetime object in ISO 8601 format with UTC timezone.
    """
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

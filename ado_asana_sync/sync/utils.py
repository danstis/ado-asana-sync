"""Utility functions shared across sync modules."""

import logging
from datetime import date, datetime, tzinfo
from urllib.parse import quote

from ado_asana_sync.utils.date import _to_local_date_string, get_ado_timezone

_LOGGER = logging.getLogger(__name__)


def extract_reviewer_vote(reviewer) -> str:
    """
    Extract the vote from an ADO reviewer object.

    ADO vote values include:
    - 'approved' (10) - Approve
    - 'approvedWithSuggestions' (5) - Approve with suggestions
    - 'noVote' (0) - No vote
    - 'waitingForAuthor' (-5) - Waiting for author
    - 'rejected' (-10) - Reject
    """
    try:
        # Try different possible attribute names for the vote
        vote = getattr(reviewer, "vote", None)

        # Vote might be an integer or string, normalize to string
        if vote is not None:
            # Handle integer vote values (ADO API sometimes returns integers)
            if isinstance(vote, int):
                vote_mapping = {
                    10: "approved",
                    5: "approvedWithSuggestions",
                    0: "noVote",
                    -5: "waitingForAuthor",
                    -10: "rejected",
                }
                vote = vote_mapping.get(vote, str(vote))

            _LOGGER.debug("Extracted reviewer vote: %s", vote)
            return str(vote)

        _LOGGER.debug("No vote found for reviewer")
        return "noVote"

    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.error("Failed to extract vote from reviewer: %s", e)
        return "noVote"


def convert_ado_date_to_asana_format(iso_datetime_string: str, tz: tzinfo | None = None) -> str:
    """
    Convert ADO ISO datetime string to Asana YYYY-MM-DD format.

    A date-only input (no time component) is returned unchanged: it is already a calendar date
    rather than an instant, so shifting it through `tz` would move it to the wrong day.

    Args:
        iso_datetime_string: ISO 8601 datetime string from ADO
        tz: Timezone to render the calendar date in. Defaults to `get_ado_timezone()`
            (the `ADO_TIMEZONE` env var, or UTC if unset).

    Returns:
        str: The calendar date in `tz`, formatted as YYYY-MM-DD

    Raises:
        ValueError: If the datetime string is invalid
        TypeError: If input is None or not a string
    """
    if not iso_datetime_string or not isinstance(iso_datetime_string, str):
        raise TypeError("Input must be a non-empty string")

    value = iso_datetime_string.strip()

    try:
        if "T" not in value and " " not in value:
            return date.fromisoformat(value).isoformat()

        # Handle Z timezone suffix by replacing with +00:00
        normalized_string = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized_string)
        return _to_local_date_string(dt, tz or get_ado_timezone())
    except ValueError as e:
        raise ValueError(f"Invalid datetime format: {iso_datetime_string}") from e


def validate_due_date(due_date: str | None) -> bool:
    """
    Validate that due_date is in correct YYYY-MM-DD format.

    Args:
        due_date: Due date string to validate, or None

    Returns:
        bool: True if valid or None, False if invalid format
    """
    if due_date is None:
        return True

    if not isinstance(due_date, str):
        return False

    try:
        # Check format is exactly YYYY-MM-DD (10 characters)
        if len(due_date) != 10:
            return False

        # Check separators are in right place
        if due_date[4] != "-" or due_date[7] != "-":
            return False

        # Parse as date to validate actual date values
        datetime.strptime(due_date, "%Y-%m-%d")
        return True

    except (ValueError, TypeError):
        return False


def encode_url_for_asana(url: str | None) -> str | None:
    """
    Encode a URL for use in Asana custom link fields.

    This function ensures URLs are properly percent-encoded while preserving
    the URL structure. This is necessary because Asana link fields require
    properly formatted URLs, and spaces or other special characters will
    make the link non-clickable.

    Important: This function assumes input URLs are NOT already percent-encoded.
    Azure DevOps APIs return unencoded URLs (e.g., spaces as literal spaces),
    so this simple encoding approach is appropriate. If the input is already
    encoded, it will be double-encoded (e.g., %20 becomes %2520).

    Args:
        url: The URL to encode, or None

    Returns:
        str | None: The URL-encoded string with spaces and special characters
                    properly encoded (e.g., spaces become %20), or None if input is None

    Example:
        >>> encode_url_for_asana("https://dev.azure.com/org/project with spaces")
        'https://dev.azure.com/org/project%20with%20spaces'
    """
    if not url:
        return url

    # Use quote with safe characters that are allowed in URLs per RFC 3986
    # This preserves the URL structure (scheme, slashes, etc.) while encoding
    # spaces and other special characters that break Asana links
    return quote(url, safe=":/?#[]@!$&'()*+,;=")

"""The util module contains utility functions that are used throughout the application."""

from typing import Any


def safe_get(obj: dict | object, *attrs_keys: str) -> Any:
    """
    Safely retrieves nested attributes from an object.

    Args:
        obj: The object to retrieve attributes from.
        *attrs_keys: Variable number of attribute keys.

    Returns:
        The value of the nested attribute if found, else None.
    """
    for attr_key in attrs_keys:
        if isinstance(obj, dict):
            obj = obj.get(attr_key)
        else:
            obj = getattr(obj, attr_key, None)
        if obj is None:
            return None
    return obj

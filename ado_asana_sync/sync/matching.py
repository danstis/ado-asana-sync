"""User and task matching logic between ADO and Asana."""

from __future__ import annotations

from .ado_parser import ADOAssignedUser


def matching_user(user_list: list[dict], ado_user: ADOAssignedUser | None) -> dict | None:
    """Check if a given email exists in a list of user dicts."""
    if ado_user is None:
        return None
    for user in user_list:
        if user["email"].lower() == ado_user.email.lower() or user["name"].lower() == ado_user.display_name.lower():
            return user
    return None

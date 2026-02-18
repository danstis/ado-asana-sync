"""Validate which Asana users are active vs deactivated in a workspace.

This script compares the ``/users`` endpoint against workspace memberships and
reports:

- Users returned by ``/users`` who have an active membership
- Users returned by ``/users`` who are marked inactive (``is_active: false``)
- Users returned by ``/users`` who have no workspace membership at all

It can also optionally probe Audit Log events for user-removal/deprovisioning
activity, which is useful when removed users are no longer returned by either
``/users`` or workspace memberships.

Usage::

    # Ensure ASANA_TOKEN and ASANA_WORKSPACE_NAME are set in your environment
    # (or in a .env file in the project root).
    uv run python scripts/validate_asana_users.py

    # Optional: inspect recent user-removal events (enterprise admin tokens)
    ASANA_VALIDATE_AUDIT_LOG=1 uv run python scripts/validate_asana_users.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv()
except ImportError:
    pass

import asana  # type: ignore
from asana.rest import ApiException  # type: ignore


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _fetch_recent_user_removal_events(
    client: asana.ApiClient,
    workspace_gid: str,
    days: int,
) -> list[dict[str, Any]] | None:
    """Fetch likely user-removal/deprovisioning events from audit logs.

    Returns ``None`` when the token/workspace cannot access audit log events.
    """
    audit_api = asana.AuditLogAPIApi(client)
    start_at = (datetime.now(UTC) - timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    opts = {
        "start_at": start_at,
        "limit": 100,
    }

    try:
        events = list(audit_api.get_audit_log_events(workspace_gid, opts, item_limit=1000))
    except ApiException as exc:
        print(f"\nAudit log probe skipped: unable to query audit log events ({exc}).")
        return None

    keywords = ("remove", "deprovision", "suspend", "disable")
    candidates: list[dict[str, Any]] = []

    for event in events:
        event_type = str(event.get("event_type", "")).lower()
        action = str(event.get("action", "")).lower()
        resource_type = str(event.get("resource_type", "")).lower()

        if "user" not in " ".join([event_type, resource_type]):
            continue

        haystack = " ".join([event_type, action])
        if any(word in haystack for word in keywords):
            candidates.append(event)

    return candidates


def _format_user(user_obj: dict[str, Any]) -> str:
    gid = user_obj.get('gid', 'N/A')
    name = user_obj.get('name', 'N/A')
    email = user_obj.get('email', 'N/A')
    return f"GID: {gid:15s}  Name: {name:30s}  Email: {email}"


def main() -> None:
    token = os.environ.get("ASANA_TOKEN", "")
    workspace_name = os.environ.get("ASANA_WORKSPACE_NAME", "")

    if not token:
        print("ERROR: ASANA_TOKEN environment variable is required.")
        sys.exit(1)
    if not workspace_name:
        print("ERROR: ASANA_WORKSPACE_NAME environment variable is required.")
        sys.exit(1)

    check_audit_log = _is_truthy(os.environ.get("ASANA_VALIDATE_AUDIT_LOG", "0"))
    audit_window_days = int(os.environ.get("ASANA_VALIDATE_AUDIT_LOG_DAYS", "90"))

    # Set up the Asana client
    config = asana.Configuration()
    config.access_token = token
    client = asana.ApiClient(config)

    # Resolve workspace GID
    workspaces_api = asana.WorkspacesApi(client)
    workspace_gid: str | None = None
    try:
        for ws in workspaces_api.get_workspaces(opts={}):
            if ws["name"] == workspace_name:
                workspace_gid = ws["gid"]
                break
    except ApiException as exc:
        print(f"ERROR: Failed to list workspaces: {exc}")
        sys.exit(1)

    if workspace_gid is None:
        print(f"ERROR: Workspace '{workspace_name}' not found.")
        sys.exit(1)

    print(f"Workspace: {workspace_name} (GID: {workspace_gid})")
    print("=" * 70)

    # ---- Fetch users from /users endpoint ----
    users_api = asana.UsersApi(client)
    try:
        all_users = list(users_api.get_users({"workspace": workspace_gid, "opt_fields": "email,name"}))
    except ApiException as exc:
        print(f"ERROR: Failed to fetch users: {exc}")
        sys.exit(1)

    user_map: dict[str, dict[str, Any]] = {u["gid"]: u for u in all_users}

    print(f"\nUsers returned by /users endpoint: {len(all_users)}")

    # ---- Fetch workspace memberships ----
    memberships_api = asana.WorkspaceMembershipsApi(client)
    try:
        memberships = list(
            memberships_api.get_workspace_memberships_for_workspace(
                workspace_gid,
                {"opt_fields": "is_active,is_guest,user,user.name"},
            )
        )
    except ApiException as exc:
        print(f"ERROR: Failed to fetch workspace memberships: {exc}")
        sys.exit(1)

    print(f"Workspace memberships returned: {len(memberships)}")

    # Build lookup of membership status by user GID
    membership_status: dict[str, bool] = {}
    membership_details: dict[str, dict[str, Any]] = {}
    for membership in memberships:
        user_obj = membership.get("user") or {}
        gid = user_obj.get("gid")
        if gid:
            membership_status[gid] = membership.get("is_active", True)
            membership_details[gid] = membership

    # ---- Classify users ----
    active_users: list[dict[str, Any]] = []
    inactive_users: list[dict[str, Any]] = []
    no_membership_users: list[dict[str, Any]] = []

    for user in all_users:
        gid = user["gid"]
        if gid not in membership_status:
            no_membership_users.append(user)
        elif membership_status[gid] is False:
            inactive_users.append(user)
        else:
            active_users.append(user)

    # ---- Report ----
    print(f"\n{'ACTIVE users':30s}: {len(active_users)}")
    print(f"{'INACTIVE users (is_active=false)':30s}: {len(inactive_users)}")
    print(f"{'Users with NO membership':30s}: {len(no_membership_users)}")

    if inactive_users:
        print("\n--- INACTIVE users (is_active: false) ---")
        for user in inactive_users:
            print(f"  {_format_user(user)}")

    if no_membership_users:
        print("\n--- Users with NO workspace membership ---")
        for user in no_membership_users:
            print(f"  {_format_user(user)}")

    # Show users in memberships but NOT in /users (deactivated and removed from user list)
    membership_only_gids = set(membership_status.keys()) - set(user_map.keys())
    membership_only_inactive = [gid for gid in membership_only_gids if membership_status.get(gid) is False]
    if membership_only_inactive:
        print(f"\n--- Memberships with is_active=false NOT in /users ({len(membership_only_inactive)}) ---")
        for gid in membership_only_inactive:
            membership = membership_details[gid]
            user_obj = membership.get("user") or {}
            print(f"  {_format_user({'gid': gid, 'name': user_obj.get('name'), 'email': user_obj.get('email')})}")

    # Optional: audit log probing for removed users that no longer appear in users/memberships.
    if check_audit_log:
        print("\n" + "-" * 70)
        print(f"Audit log probe enabled (last {audit_window_days} day(s)).")
        candidates = _fetch_recent_user_removal_events(client, workspace_gid, audit_window_days)

        if candidates is not None:
            print(f"Potential user removal/deprovision events found: {len(candidates)}")
            for event in candidates[:20]:
                created_at = event.get("created_at", "N/A")
                event_type = event.get("event_type", "N/A")
                resource_name = (event.get("resource") or {}).get("name", "N/A")
                resource_gid = (event.get("resource") or {}).get("gid", "N/A")
                print(
                    "  "
                    f"{created_at}  event_type={event_type}  "
                    f"resource={resource_name} ({resource_gid})"
                )
            if len(candidates) > 20:
                print(f"  ... and {len(candidates) - 20} more")

    # Summary
    would_be_filtered = len(inactive_users) + len(no_membership_users)
    print("\n" + "=" * 70)
    print(f"With the whitelist approach, {would_be_filtered} user(s) would be filtered out of sync.")
    if would_be_filtered == 0:
        print("All users returned by /users have active workspace memberships.")
        print(
            "If Admin Console still shows users as Removed, they are likely no longer "
            "returned by these endpoints. Enable ASANA_VALIDATE_AUDIT_LOG=1 for extra visibility."
        )
    else:
        print("These users will NOT be assigned tasks during sync.")


if __name__ == "__main__":
    main()

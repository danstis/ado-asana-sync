"""Validate which Asana users are active vs deactivated in a workspace.

This script connects to the Asana API and compares the results from the
``/users`` endpoint against workspace memberships. It reports:

- Users returned by ``/users`` who have an active membership
- Users returned by ``/users`` who are marked inactive (``is_active: false``)
- Users returned by ``/users`` who have no workspace membership at all

Usage::

    # Ensure ASANA_TOKEN and ASANA_WORKSPACE_NAME are set in your environment
    # (or in a .env file in the project root).
    uv run python scripts/validate_asana_users.py
"""

from __future__ import annotations

import os
import sys

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv()
except ImportError:
    pass

import asana  # type: ignore
from asana.rest import ApiException  # type: ignore


def main() -> None:
    token = os.environ.get("ASANA_TOKEN", "")
    workspace_name = os.environ.get("ASANA_WORKSPACE_NAME", "")

    if not token:
        print("ERROR: ASANA_TOKEN environment variable is required.")
        sys.exit(1)
    if not workspace_name:
        print("ERROR: ASANA_WORKSPACE_NAME environment variable is required.")
        sys.exit(1)

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

    user_map: dict[str, dict] = {}
    for u in all_users:
        user_map[u["gid"]] = u

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
    membership_details: dict[str, dict] = {}
    for m in memberships:
        user_obj = m.get("user") or {}
        gid = user_obj.get("gid")
        if gid:
            membership_status[gid] = m.get("is_active", True)
            membership_details[gid] = m

    # ---- Classify users ----
    active_users: list[dict] = []
    inactive_users: list[dict] = []
    no_membership_users: list[dict] = []

    for u in all_users:
        gid = u["gid"]
        if gid not in membership_status:
            no_membership_users.append(u)
        elif membership_status[gid] is False:
            inactive_users.append(u)
        else:
            active_users.append(u)

    # ---- Report ----
    print(f"\n{'ACTIVE users':30s}: {len(active_users)}")
    print(f"{'INACTIVE users (is_active=false)':30s}: {len(inactive_users)}")
    print(f"{'Users with NO membership':30s}: {len(no_membership_users)}")

    if inactive_users:
        print("\n--- INACTIVE users (is_active: false) ---")
        for u in inactive_users:
            print(f"  GID: {u['gid']:15s}  Name: {u.get('name', 'N/A'):30s}  Email: {u.get('email', 'N/A')}")

    if no_membership_users:
        print("\n--- Users with NO workspace membership ---")
        for u in no_membership_users:
            print(f"  GID: {u['gid']:15s}  Name: {u.get('name', 'N/A'):30s}  Email: {u.get('email', 'N/A')}")

    # Show users in memberships but NOT in /users (deactivated and removed from user list)
    membership_only_gids = set(membership_status.keys()) - set(user_map.keys())
    membership_only_inactive = [gid for gid in membership_only_gids if membership_status.get(gid) is False]
    if membership_only_inactive:
        print(f"\n--- Memberships with is_active=false NOT in /users ({len(membership_only_inactive)}) ---")
        for gid in membership_only_inactive:
            m = membership_details[gid]
            user_obj = m.get("user") or {}
            print(f"  GID: {gid:15s}  Name: {user_obj.get('name', 'N/A'):30s}  Email: {user_obj.get('email', 'N/A')}")

    # Summary
    would_be_filtered = len(inactive_users) + len(no_membership_users)
    print("\n" + "=" * 70)
    print(f"With the whitelist approach, {would_be_filtered} user(s) would be filtered out of sync.")
    if would_be_filtered == 0:
        print("All users returned by /users have active workspace memberships.")
    else:
        print("These users will NOT be assigned tasks during sync.")


if __name__ == "__main__":
    main()

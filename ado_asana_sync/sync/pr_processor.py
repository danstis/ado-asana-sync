"""Logic for processing individual pull requests and reviewers."""

from __future__ import annotations

import re
import types
from datetime import datetime, timezone
from typing import Any, List

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App
from .group_member_cache import GroupMemberCache
from .pr_asana_helpers import (
    _REVIEWER_APPROVED_STATES,
    _get_cached_asana_task,
    _record_pr_action,
    create_asana_pr_task,
    update_asana_pr_task,
)
from .pull_request_item import PullRequestItem
from .sync import (
    ADOAssignedUser,
    get_asana_task_by_name,
    matching_user,
)
from .utils import extract_reviewer_vote

_LOGGER, _TRACER = setup_logging_and_tracing(__name__)

_GROUP_REVIEWER_PATTERN = re.compile(r"^\[.+\]\\")

# Inverse of the vote_mapping in utils.extract_reviewer_vote — used to preserve
# an existing review_status when the group reviewer object is passed to helpers
# that derive vote from the reviewer object.
_REVIEW_STATUS_TO_VOTE: dict[str, int] = {
    "approved": 10,
    "approvedWithSuggestions": 5,
    "noVote": 0,
    "waitingForAuthor": -5,
    "rejected": -10,
}


def _get_reviewer_display_name(reviewer) -> str:
    """Extract display name from an ADO reviewer object."""
    return (
        getattr(reviewer, "display_name", None)
        or getattr(reviewer, "displayName", None)
        or getattr(reviewer, "name", None)
        or "Unknown Group"
    )


def is_group_reviewer(reviewer) -> bool:
    """Return True when the ADO reviewer is a group/container (not an individual)."""
    if getattr(reviewer, "is_container", False) is True:
        return True

    display_name = _get_reviewer_display_name(reviewer)

    if _GROUP_REVIEWER_PATTERN.match(display_name):
        return True

    unique_name = getattr(reviewer, "unique_name", None) or getattr(reviewer, "uniqueName", None) or ""
    if "\\" in display_name and (not unique_name or unique_name.startswith("vstfs:///")):
        return True

    return False


def _resolve_group_reviewer_default_user(asana_users: List[dict], user_ref: str) -> dict | None:
    """Resolve the configured default Asana user for group reviewers by email, GID, or display name."""
    if not user_ref:
        return None
    ref_lower = user_ref.lower()
    for user in asana_users:
        if user.get("email", "").lower() == ref_lower:
            return user
        if user.get("gid", "") == user_ref:
            return user
        if user.get("name", "").lower() == ref_lower:
            return user
    return None


def _resolve_single_member(graph_client, member_descriptor: str) -> ADOAssignedUser | None:
    """Resolve one graph descriptor to an ADOAssignedUser; returns None for nested groups."""
    try:
        user = graph_client.get_user(member_descriptor)
        email = user.mail_address or getattr(user, "principal_name", None)
        display_name = user.display_name
        if email and display_name:
            return ADOAssignedUser(display_name, email)
        return None
    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.debug("Skipping member descriptor '%s' (may be a nested group): %s", member_descriptor, e)
        return None


def _resolve_group_members_from_ado(
    app: App, reviewer, group_member_cache: GroupMemberCache | None = None
) -> List[ADOAssignedUser] | None:
    """Resolve a group reviewer to individual member users via the ADO Graph API.

    Checks *group_member_cache* before calling the ADO Graph API.  On a
    successful API call the result is written back to the cache.

    Returns:
        List[ADOAssignedUser]: successfully resolved members (may be empty).
        None: expansion could not be performed (unavailable client, missing id,
              or API error) — callers should use cached members to preserve tasks.
    """
    reviewer_id = getattr(reviewer, "id", None)

    # Return cached result when available (avoids repeat Graph API calls).
    if group_member_cache and reviewer_id:
        cached = group_member_cache.get(reviewer_id)
        if cached is not None:
            return cached

    graph_client = getattr(app, "ado_graph_client", None)
    if graph_client is None:
        _LOGGER.warning("ado_graph_client not initialised; cannot expand group '%s'", _get_reviewer_display_name(reviewer))
        return None
    if not reviewer_id:
        _LOGGER.warning("Group reviewer has no 'id' attribute; cannot resolve members")
        return None
    try:
        descriptor_result = graph_client.get_descriptor(reviewer_id)
        memberships = graph_client.list_memberships(descriptor_result.value, direction="Down")
        members = [
            user
            for membership in memberships
            for user in [_resolve_single_member(graph_client, membership.member_descriptor)]
            if user is not None
        ]
        if group_member_cache:
            group_member_cache.set(reviewer_id, members)
        return members
    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.warning("Failed to resolve members of group '%s': %s", _get_reviewer_display_name(reviewer), e)
        return None


def _collect_expanded_member_gids(
    app: App,
    reviewer,
    asana_users: List[dict],
    user_lookup_cache: dict | None,
    group_member_cache: GroupMemberCache | None = None,
) -> set[str] | None:
    """Resolve group reviewer members and return their Asana GIDs.

    Returns None when group member resolution failed and no cached fallback exists.
    Callers should treat None as "skip GID update" to avoid spurious task closures.
    """
    members = _resolve_group_members_from_ado(app, reviewer, group_member_cache)
    if members is None:
        return None
    gids: set[str] = set()
    for member in members:
        asana_user = _cache_reviewer_lookup(asana_users, member, user_lookup_cache)
        if asana_user:
            gids.add(asana_user["gid"])
    return gids


def _get_existing_pr_item_gids(app: App, pr) -> set[str]:
    """Return all reviewer GIDs currently stored in the DB for a PR."""
    if app.pr_matches is None:
        return set()

    def query_fn(record):
        return record.get("ado_pr_id") == pr.pull_request_id

    return {str(task["reviewer_gid"]) for task in app.pr_matches.search(query_fn) if task.get("reviewer_gid")}


def _get_db_group_gids(app: App, pr, reviewer_id: str) -> set[str]:
    """Query pr_matches for tasks previously created from a specific group reviewer expansion.

    Used as a cold-cache fallback: even if the GroupMemberCache entry has expired
    or been deleted, tasks tagged with source_group_reviewer_id can still be recovered
    from the database so they are not incorrectly closed during a transient API failure.
    """
    if app.pr_matches is None:
        return set()

    def query_fn(record):
        return record.get("ado_pr_id") == pr.pull_request_id and record.get("source_group_reviewer_id") == reviewer_id

    return {str(t["reviewer_gid"]) for t in app.pr_matches.search(query_fn) if t.get("reviewer_gid")}


def _get_group_preservation_gids(
    app: App,
    pr,
    reviewer,
    asana_users: List[dict],
    user_lookup_cache: dict | None,
    group_member_cache: GroupMemberCache | None,
) -> set[str]:
    """Return Asana GIDs to preserve when live group expansion fails.

    Priority:
    1. In-memory / persistent cache (fast, no DB query).
    2. DB records tagged with source_group_reviewer_id (covers cold/expired cache).
    3. Empty set when neither source has data (genuine first run — nothing to preserve).
    """
    reviewer_id = getattr(reviewer, "id", None)

    # 1. Try cache first.
    if group_member_cache and reviewer_id:
        cached_members = group_member_cache.get(reviewer_id)
        if cached_members:
            gids: set[str] = set()
            for member in cached_members:
                asana_user = _cache_reviewer_lookup(asana_users, member, user_lookup_cache)
                if asana_user:
                    gids.add(asana_user["gid"])
            return gids

    # 2. Fall back to DB records from prior successful expansions.
    if reviewer_id:
        return _get_db_group_gids(app, pr, reviewer_id)

    return set()


def _collect_gids_for_reviewer(
    app: App,
    reviewer,
    pr,
    asana_users: List[dict],
    user_lookup_cache: dict | None,
    group_member_cache: GroupMemberCache | None = None,
) -> set[str]:
    """Return the GIDs to add to current_reviewer_gids for a single reviewer.

    For expand_group_members strategy with a group reviewer, returns member GIDs.
    On expansion failure, falls back to cached or DB-stored member GIDs for this
    group only, so unrelated reviewer removals are still processed correctly.
    For all other cases, returns a singleton set or empty set.
    """
    if is_group_reviewer(reviewer) and getattr(app, "group_reviewer_strategy", "ignore") == "expand_group_members":
        expanded = _collect_expanded_member_gids(app, reviewer, asana_users, user_lookup_cache, group_member_cache)
        if expanded is None:
            return _get_group_preservation_gids(app, pr, reviewer, asana_users, user_lookup_cache, group_member_cache)
        return expanded
    gid = _collect_reviewer_gid(app, reviewer, asana_users, user_lookup_cache)
    return {gid} if gid else set()


def _collect_group_reviewer_gid(app: App, reviewer, asana_users: List[dict]) -> str | None:
    """Return the synthetic GID to track for a group reviewer, or None to skip."""
    strategy = getattr(app, "group_reviewer_strategy", "ignore")
    if strategy == "ignore":
        return None
    if strategy == "expand_group_members":
        return None  # individual GIDs collected via _collect_expanded_member_gids
    if strategy == "default_user":
        default_ref = getattr(app, "group_reviewer_default_user", "")
        if _resolve_group_reviewer_default_user(asana_users, default_ref) is None:
            return None
    return f"group:{_get_reviewer_display_name(reviewer)}"


def _collect_reviewer_gid(app: App, reviewer, asana_users: List[dict], user_lookup_cache: dict | None) -> str | None:
    """Determine the reviewer GID to add to current_reviewer_gids, or None if not applicable."""
    if is_group_reviewer(reviewer):
        return _collect_group_reviewer_gid(app, reviewer, asana_users)
    ado_reviewer = create_ado_user_from_reviewer(reviewer)
    if not ado_reviewer:
        return None
    asana_matched_user = _cache_reviewer_lookup(asana_users, ado_reviewer, user_lookup_cache)
    return asana_matched_user["gid"] if asana_matched_user else None


def _create_new_group_reviewer_task(
    app: App,
    pr_item: PullRequestItem,
    asana_project_tasks: List[dict],
    asana_project: str,
) -> None:
    """Create or link an Asana task for a new group reviewer mapping."""
    asana_task = get_asana_task_by_name(asana_project_tasks, pr_item.asana_title)
    if asana_task is None:
        if app.asana_tag_gid is not None:
            create_asana_pr_task(app, asana_project, pr_item, app.asana_tag_gid)
    else:
        pr_item.asana_gid = asana_task["gid"]
        pr_item.asana_updated = asana_task.get("modified_at")
        pr_item.updated_date = iso8601_utc(datetime.now())
        pr_item.save(app)
        if app.asana_tag_gid is not None:
            update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)


def _update_existing_group_reviewer_match(
    app: App,
    existing_match: PullRequestItem,
    pr,
    reviewer,
    assignee_gid: str | None,
    asana_project_tasks: List[dict],
    asana_project: str,
) -> None:
    """Sync an existing group reviewer DB record and its Asana task with current PR state."""
    new_vote = extract_reviewer_vote(reviewer)
    if (
        existing_match.title == pr.title
        and existing_match.status == pr.status
        and existing_match.review_status == new_vote
        and existing_match.assignee_gid == assignee_gid
        and existing_match.asana_gid
    ):
        _LOGGER.debug("Group reviewer task is already up to date: %s", existing_match.asana_title)
        return
    existing_match.title = pr.title
    existing_match.status = pr.status
    existing_match.updated_date = iso8601_utc(datetime.now())
    existing_match.review_status = new_vote
    existing_match.assignee_gid = assignee_gid
    if app.asana_tag_gid is None:
        existing_match.save(app)
        return
    if existing_match.asana_gid:
        update_asana_pr_task(app, existing_match, app.asana_tag_gid, asana_project)
        return
    asana_task = get_asana_task_by_name(asana_project_tasks, existing_match.asana_title)
    if asana_task is not None:
        existing_match.asana_gid = asana_task["gid"]
        existing_match.asana_updated = asana_task.get("modified_at")
        update_asana_pr_task(app, existing_match, app.asana_tag_gid, asana_project)
    else:
        create_asana_pr_task(app, asana_project, existing_match, app.asana_tag_gid)


def _resolve_group_reviewer_assignee(app: App, pr, asana_users: List[dict], display_name: str, strategy: str) -> str | None:
    """Resolve the Asana assignee GID for a group reviewer based on the configured strategy.

    Returns None for unassigned_task strategy or when the default user cannot be resolved.
    """
    if strategy != "default_user":
        return None
    default_user_ref = getattr(app, "group_reviewer_default_user", "")
    resolved = _resolve_group_reviewer_default_user(asana_users, default_user_ref)
    if resolved is None:
        _LOGGER.warning(
            "PR %s: cannot resolve GROUP_REVIEWER_DEFAULT_USER '%s' — skipping group reviewer '%s'",
            pr.pull_request_id,
            default_user_ref,
            display_name,
        )
        return None
    _LOGGER.info(
        "PR %s: group reviewer '%s' mapped to default user '%s'",
        pr.pull_request_id,
        display_name,
        resolved["name"],
    )
    return resolved["gid"]


def _make_vote_preserving_reviewer(reviewer, existing_match: PullRequestItem):
    """Return a reviewer proxy with the existing vote to prevent group vote overwrites."""
    preserved_vote = _REVIEW_STATUS_TO_VOTE.get(existing_match.review_status or "noVote", 0)
    return types.SimpleNamespace(vote=preserved_vote)


def _handle_expand_group_reviewer(
    app: App,
    pr,
    repository,
    reviewer,
    asana_users: List[dict],
    asana_project_tasks: List[dict],
    asana_project: str,
    group_member_cache: GroupMemberCache | None = None,
) -> None:
    """Handle expand_group_members strategy: create/update individual member tasks."""
    display_name = _get_reviewer_display_name(reviewer)
    reviewer_id = getattr(reviewer, "id", None)
    members = _resolve_group_members_from_ado(app, reviewer, group_member_cache)
    if members is None:
        _LOGGER.warning("PR %s: group '%s' expansion failed; existing tasks preserved", pr.pull_request_id, display_name)
        return
    if not members:
        _LOGGER.info("PR %s: group '%s' resolved to no members, skipping", pr.pull_request_id, display_name)
        return
    for member in members:
        asana_matched_user = matching_user(asana_users, member)
        if not asana_matched_user:
            _LOGGER.debug(
                "PR %s: group member %s <%s> not found in Asana",
                pr.pull_request_id,
                member.display_name,
                member.email,
            )
            continue
        existing_match = PullRequestItem.search(app, ado_pr_id=pr.pull_request_id, reviewer_gid=asana_matched_user["gid"])
        if existing_match is None:
            create_new_pr_reviewer_task(
                app,
                pr,
                repository,
                reviewer,
                asana_matched_user,
                asana_project_tasks,
                asana_project,
                source_group_reviewer_id=reviewer_id,
            )
        else:
            # Lazy backfill: tag tasks created before source_group_reviewer_id existed so
            # the DB fallback can protect them on future cold-cache expansion failures.
            if existing_match.source_group_reviewer_id is None and reviewer_id:
                existing_match.source_group_reviewer_id = reviewer_id
                if getattr(app, "dry_run", False) is not True:
                    existing_match.save(app)
            # Use a vote-preserving proxy so the group's aggregate vote cannot overwrite
            # an individual reviewer's vote (e.g. when a user is both a direct reviewer
            # and a member of the expanded group).
            vote_proxy = _make_vote_preserving_reviewer(reviewer, existing_match)
            update_existing_pr_reviewer_task(
                app, pr, repository, vote_proxy, existing_match, asana_matched_user, asana_project
            )


def _handle_group_reviewer(
    app: App,
    pr,
    repository,
    reviewer,
    asana_users: List[dict],
    asana_project_tasks: List[dict],
    asana_project: str,
    group_member_cache: GroupMemberCache | None = None,
) -> None:
    """Handle an ADO group/container reviewer according to the configured GROUP_REVIEWER_STRATEGY.

    Strategies:
    - ignore (default): log and skip, identical to previous behaviour.
    - expand_group_members: resolve members via ADO Graph API and create individual tasks.
    - default_user: create/update a task assigned to GROUP_REVIEWER_DEFAULT_USER.
    - unassigned_task: create/update an unassigned task with the group name in the title.
    """
    display_name = _get_reviewer_display_name(reviewer)
    strategy = getattr(app, "group_reviewer_strategy", "ignore")

    _LOGGER.info(
        "PR %s: group reviewer '%s' — applying strategy '%s'",
        pr.pull_request_id,
        display_name,
        strategy,
    )

    if strategy == "ignore":
        return

    if strategy == "expand_group_members":
        _handle_expand_group_reviewer(
            app, pr, repository, reviewer, asana_users, asana_project_tasks, asana_project, group_member_cache
        )
        return

    assignee_gid = _resolve_group_reviewer_assignee(app, pr, asana_users, display_name, strategy)
    if strategy == "default_user" and assignee_gid is None:
        return

    synthetic_gid = f"group:{display_name}"
    pr_url = (
        getattr(pr, "web_url", "")
        or f"{app.ado_url}/{repository.project.name}/_git/{repository.name}/pullrequest/{pr.pull_request_id}"
    )
    current_utc_time = iso8601_utc(datetime.now(timezone.utc))

    existing_match = PullRequestItem.search(app, ado_pr_id=pr.pull_request_id, reviewer_gid=synthetic_gid)

    if existing_match is None:
        pr_item = PullRequestItem(
            ado_pr_id=pr.pull_request_id,
            ado_repository_id=repository.id,
            title=pr.title,
            status=pr.status,
            url=pr_url,
            reviewer_gid=synthetic_gid,
            reviewer_name=f"Group: {display_name}",
            created_date=current_utc_time,
            updated_date=current_utc_time,
            review_status=extract_reviewer_vote(reviewer),
            assignee_gid=assignee_gid,
        )
        _create_new_group_reviewer_task(app, pr_item, asana_project_tasks, asana_project)
    else:
        _update_existing_group_reviewer_match(
            app, existing_match, pr, reviewer, assignee_gid, asana_project_tasks, asana_project
        )


def create_ado_user_from_reviewer(reviewer) -> Any:
    """Convert an ADO reviewer object to a user object similar to work item assigned users."""
    try:
        display_name = (
            getattr(reviewer, "display_name", None)
            or getattr(reviewer, "displayName", None)
            or getattr(reviewer, "name", None)
        )
        email = (
            getattr(reviewer, "unique_name", None) or getattr(reviewer, "uniqueName", None) or getattr(reviewer, "email", None)
        )

        if hasattr(reviewer, "user") and reviewer.user:
            user_obj = reviewer.user
            display_name = display_name or getattr(user_obj, "display_name", None) or getattr(user_obj, "displayName", None)
            email = email or getattr(user_obj, "unique_name", None) or getattr(user_obj, "uniqueName", None)

        _LOGGER.debug(
            "Extracted reviewer info: display_name='%s', email='%s'",
            display_name,
            email,
        )

        if not display_name or not email:
            _LOGGER.warning(
                "Incomplete reviewer info: display_name='%s', email='%s'",
                display_name,
                email,
            )
            return None

        return ADOAssignedUser(display_name, email)

    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.error("Failed to extract user info from reviewer: %s", e)
        return None


def _get_reviewer_id(reviewer) -> str | None:
    """Extract the unique identifier for a reviewer."""
    if hasattr(reviewer, "user") and reviewer.user:
        return getattr(reviewer.user, "unique_name", None) or getattr(reviewer.user, "uniqueName", None)
    return getattr(reviewer, "unique_name", None) or getattr(reviewer, "uniqueName", None)


def _cache_reviewer_lookup(asana_users: List[dict], ado_reviewer, user_lookup_cache: dict | None) -> dict | None:
    """Look up the Asana user for a reviewer, using and updating the cache when available."""
    reviewer_key = f"{ado_reviewer.display_name}:{ado_reviewer.email}"
    if user_lookup_cache is not None and reviewer_key in user_lookup_cache:
        return user_lookup_cache[reviewer_key]
    asana_matched_user = matching_user(asana_users, ado_reviewer)
    if user_lookup_cache is not None:
        user_lookup_cache[reviewer_key] = asana_matched_user
    return asana_matched_user


def process_pull_request(
    app: App,
    pr,
    repository,
    asana_users: List[dict],
    asana_project_tasks: List[dict],
    asana_project: str,
    user_lookup_cache: dict | None = None,
    group_member_cache: GroupMemberCache | None = None,
) -> None:
    """Process a single pull request, creating reviewer tasks."""
    _LOGGER.debug("Processing PR %s: %s", pr.pull_request_id, pr.title)

    if app.ado_git_client is None:
        raise ValueError("app.ado_git_client is None")
    try:
        reviewers = app.ado_git_client.get_pull_request_reviewers(repository.id, pr.pull_request_id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.error("Failed to get reviewers for PR %s: %s", pr.pull_request_id, e)
        return

    if not reviewers:
        _LOGGER.debug("No reviewers found for PR %s", pr.pull_request_id)
        handle_removed_reviewers(app, pr, set(), asana_project)
        return

    processed_reviewers: set[str] = set()
    current_reviewer_gids: set[str] = set()

    for reviewer in reviewers:
        reviewer_id = _get_reviewer_id(reviewer)

        if reviewer_id and reviewer_id in processed_reviewers:
            _LOGGER.debug(
                "Skipping duplicate reviewer %s for PR %s",
                reviewer_id,
                pr.pull_request_id,
            )
            continue

        if reviewer_id:
            processed_reviewers.add(reviewer_id)

        current_reviewer_gids.update(
            _collect_gids_for_reviewer(app, reviewer, pr, asana_users, user_lookup_cache, group_member_cache)
        )

        process_pr_reviewer(
            app,
            pr,
            repository,
            reviewer,
            asana_users,
            asana_project_tasks,
            asana_project,
            group_member_cache,
        )

    handle_removed_reviewers(app, pr, current_reviewer_gids, asana_project)


def _close_removed_reviewer_task(app: App, pr_item: PullRequestItem, asana_project: str) -> None:
    """Close the Asana task for a reviewer that was removed from a PR."""
    pr_item.status = "reviewer_removed"
    pr_item.review_status = "removed"
    pr_item.updated_date = iso8601_utc(datetime.now())

    if pr_item.asana_gid and app.asana_tag_gid is not None:
        try:
            update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)
            _LOGGER.info(
                "Closed Asana task for removed reviewer: %s",
                pr_item.asana_title,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            _LOGGER.error(
                "Failed to close Asana task for removed reviewer %s: %s",
                pr_item.asana_title,
                e,
            )
    else:
        pr_item.processing_state = "closed"
        if getattr(app, "dry_run", False) is True:
            _record_pr_action(app, "close", pr_item)
            return
        pr_item.save(app)


def handle_removed_reviewers(app: App, pr, current_reviewer_gids: set, asana_project: str) -> None:
    """Handle reviewers that have been removed from the PR by closing their Asana tasks."""
    if app.pr_matches is None:
        raise ValueError("app.pr_matches is None")

    existing_pr_tasks = app.pr_matches.search_by_json_fields({"ado_pr_id": pr.pull_request_id})

    if not existing_pr_tasks:
        return

    for task_data in existing_pr_tasks:
        clean_task_data = {k: v for k, v in task_data.items() if k != "doc_id"}
        pr_item = PullRequestItem(**clean_task_data)

        if pr_item.ado_pr_id != pr.pull_request_id:
            _LOGGER.warning(
                "Skipping corrupted PR item: expected PR ID %s but got %s with title '%s'",
                pr.pull_request_id,
                pr_item.ado_pr_id,
                pr_item.title,
            )
            continue

        if pr_item.reviewer_gid not in current_reviewer_gids:
            _LOGGER.info(
                "Reviewer %s removed from PR %s, closing task: %s",
                pr_item.reviewer_name or pr_item.reviewer_gid,
                pr.pull_request_id,
                pr_item.asana_title,
            )
            _close_removed_reviewer_task(app, pr_item, asana_project)


def process_pr_reviewer(
    app: App,
    pr,
    repository,
    reviewer,
    asana_users: List[dict],
    asana_project_tasks: List[dict],
    asana_project: str,
    group_member_cache: GroupMemberCache | None = None,
) -> None:
    """Process a single reviewer for a pull request."""
    if is_group_reviewer(reviewer):
        _handle_group_reviewer(
            app, pr, repository, reviewer, asana_users, asana_project_tasks, asana_project, group_member_cache
        )
        return

    ado_reviewer = create_ado_user_from_reviewer(reviewer)
    if not ado_reviewer:
        _LOGGER.debug("Could not extract user info from reviewer for PR %s", pr.pull_request_id)
        return

    asana_matched_user = matching_user(asana_users, ado_reviewer)
    if not asana_matched_user:
        _LOGGER.info(
            "PR %s: reviewer %s <%s> not found in Asana",
            pr.pull_request_id,
            ado_reviewer.display_name,
            ado_reviewer.email,
        )
        return

    _LOGGER.debug(
        "Processing PR %s reviewer %s (Asana GID: %s)",
        pr.pull_request_id,
        asana_matched_user["name"],
        asana_matched_user["gid"],
    )

    existing_match = PullRequestItem.search(app, ado_pr_id=pr.pull_request_id, reviewer_gid=asana_matched_user["gid"])

    if existing_match is None:
        create_new_pr_reviewer_task(
            app,
            pr,
            repository,
            reviewer,
            asana_matched_user,
            asana_project_tasks,
            asana_project,
        )
    else:
        update_existing_pr_reviewer_task(
            app,
            pr,
            repository,
            reviewer,
            existing_match,
            asana_matched_user,
            asana_project,
        )


def create_new_pr_reviewer_task(
    app: App,
    pr,
    repository,
    reviewer,
    asana_matched_user: dict,
    asana_project_tasks: List[dict],
    asana_project: str,
    source_group_reviewer_id: str | None = None,
) -> None:
    """Create a new Asana task for a PR reviewer."""
    _LOGGER.debug(
        "Creating new reviewer task for PR %s, reviewer %s",
        pr.pull_request_id,
        asana_matched_user["name"],
    )

    current_utc_time = iso8601_utc(datetime.now(timezone.utc))
    pr_url = (
        getattr(pr, "web_url", "")
        or f"{app.ado_url}/{repository.project.name}/_git/{repository.name}/pullrequest/{pr.pull_request_id}"
    )

    pr_item = PullRequestItem(
        ado_pr_id=pr.pull_request_id,
        ado_repository_id=repository.id,
        title=pr.title,
        status=pr.status,
        url=pr_url,
        reviewer_gid=asana_matched_user["gid"],
        reviewer_name=asana_matched_user["name"],
        created_date=current_utc_time,
        updated_date=current_utc_time,
        review_status=extract_reviewer_vote(reviewer),
        source_group_reviewer_id=source_group_reviewer_id,
    )

    asana_task = get_asana_task_by_name(asana_project_tasks, pr_item.asana_title)

    if asana_task is None:
        _LOGGER.debug("Creating new Asana task for PR %s reviewer", pr.pull_request_id)

        if pr_item.review_status in _REVIEWER_APPROVED_STATES:
            _LOGGER.info(
                "Reviewer %s already approved PR %s, task will be created as completed",
                pr_item.reviewer_name,
                pr.pull_request_id,
            )

        if app.asana_tag_gid is not None:
            create_asana_pr_task(app, asana_project, pr_item, app.asana_tag_gid)
    else:
        _LOGGER.debug("Linking existing Asana task for PR %s reviewer", pr.pull_request_id)
        pr_item.asana_gid = asana_task["gid"]
        pr_item.asana_updated = asana_task.get("modified_at")
        pr_item.updated_date = iso8601_utc(datetime.now())
        if getattr(app, "dry_run", False) is not True:
            pr_item.save(app)
        if app.asana_tag_gid is not None:
            update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)


def _check_title_change(pr, existing_match: PullRequestItem) -> bool:
    """Check for a PR title change and validate data integrity. Returns False if corruption detected."""
    if existing_match.title != pr.title:
        _LOGGER.info("PR title changed from '%s' to '%s'", existing_match.title, pr.title)
        if existing_match.ado_pr_id != pr.pull_request_id:
            _LOGGER.error(
                "Critical data corruption detected: PR item has ID %s but PR object has ID %s. "
                "This would create a title/ID mismatch. Skipping update to prevent corruption.",
                existing_match.ado_pr_id,
                pr.pull_request_id,
            )
            return False
    return True


def _log_review_status_change(pr, existing_match: PullRequestItem, reviewer) -> None:
    """Log changes to a reviewer's vote status."""
    new_status = extract_reviewer_vote(reviewer)
    if existing_match.review_status == new_status:
        return
    old_status = existing_match.review_status or "noVote"
    _LOGGER.info(
        "PR %s reviewer %s vote changed from '%s' to '%s'",
        pr.pull_request_id,
        existing_match.reviewer_name or existing_match.reviewer_gid,
        old_status,
        new_status,
    )
    if new_status in _REVIEWER_APPROVED_STATES:
        _LOGGER.info(
            "Reviewer %s approved PR %s, task will be closed",
            existing_match.reviewer_name or existing_match.reviewer_gid,
            pr.pull_request_id,
        )
    elif old_status in _REVIEWER_APPROVED_STATES and new_status not in _REVIEWER_APPROVED_STATES:
        _LOGGER.info(
            "Reviewer %s approval reset on PR %s, task will be reopened",
            existing_match.reviewer_name or existing_match.reviewer_gid,
            pr.pull_request_id,
        )


def update_existing_pr_reviewer_task(
    app: App,
    pr,
    _repository,
    reviewer,
    existing_match: PullRequestItem,
    asana_matched_user: dict,
    asana_project: str,
) -> None:
    """Update an existing Asana task for a PR reviewer."""
    reviewer_name_updated = False
    if not existing_match.reviewer_name:
        existing_match.reviewer_name = asana_matched_user["name"]
        if getattr(app, "dry_run", False) is not True:
            existing_match.save(app)
        reviewer_name_updated = True
        _LOGGER.info("Updated reviewer name for PR task: %s", existing_match.asana_title)

    if existing_match.is_current(app, pr, reviewer) and not reviewer_name_updated:
        _LOGGER.debug("PR reviewer task is already up to date: %s", existing_match.asana_title)
        return

    _LOGGER.debug("Updating PR reviewer task: %s", existing_match.asana_title)

    asana_task = _get_cached_asana_task(app, existing_match.asana_gid) if existing_match.asana_gid else None
    if asana_task is None:
        _LOGGER.error("No Asana task found with gid: %s", existing_match.asana_gid)
        return

    if not _check_title_change(pr, existing_match):
        return
    _log_review_status_change(pr, existing_match, reviewer)

    existing_match.title = pr.title
    existing_match.status = pr.status
    existing_match.updated_date = iso8601_utc(datetime.now())
    existing_match.review_status = extract_reviewer_vote(reviewer)
    existing_match.asana_updated = asana_task["modified_at"]

    if app.asana_tag_gid is not None:
        update_asana_pr_task(app, existing_match, app.asana_tag_gid, asana_project)

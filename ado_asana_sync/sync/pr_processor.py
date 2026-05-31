"""Logic for processing individual pull requests and reviewers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App
from .pr_asana_helpers import (
    _REVIEWER_APPROVED_STATES,
    _get_cached_asana_task,
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

        ado_reviewer = create_ado_user_from_reviewer(reviewer)
        if ado_reviewer:
            asana_matched_user = _cache_reviewer_lookup(asana_users, ado_reviewer, user_lookup_cache)
            if asana_matched_user:
                current_reviewer_gids.add(asana_matched_user["gid"])

        process_pr_reviewer(
            app,
            pr,
            repository,
            reviewer,
            asana_users,
            asana_project_tasks,
            asana_project,
            user_lookup_cache,
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
        pr_item.save(app)


def handle_removed_reviewers(app: App, pr, current_reviewer_gids: set, asana_project: str) -> None:
    """Handle reviewers that have been removed from the PR by closing their Asana tasks."""
    if app.pr_matches is None:
        raise ValueError("app.pr_matches is None")

    def query_func(record):
        return record.get("ado_pr_id") == pr.pull_request_id

    existing_pr_tasks = app.pr_matches.search(query_func)

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
    user_lookup_cache: dict | None = None,
) -> None:
    """Process a single reviewer for a pull request."""
    ado_reviewer = create_ado_user_from_reviewer(reviewer)
    if not ado_reviewer:
        _LOGGER.debug("Could not extract user info from reviewer for PR %s", pr.pull_request_id)
        return

    asana_matched_user = _cache_reviewer_lookup(asana_users, ado_reviewer, user_lookup_cache)
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

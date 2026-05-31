"""Asana API helpers specific to pull request sync."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import asana
from asana.rest import ApiException

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .asana import get_asana_task
from .dry_run import DryRunReport
from .pull_request_item import PullRequestItem
from .sync import find_custom_field_by_name
from .utils import encode_url_for_asana

if TYPE_CHECKING:
    from .app import App

_LOGGER, _TRACER = setup_logging_and_tracing(__name__)

_PR_CLOSED_STATES = {"completed", "abandoned", "draft"}
_REVIEWER_APPROVED_STATES = {"approved", "approvedWithSuggestions"}


def _is_dry_run(app: App) -> bool:
    return getattr(app, "dry_run", False) is True


def _get_dry_run_report(app: App) -> DryRunReport:
    report = getattr(app, "dry_run_report", None)
    if report is None:
        report = DryRunReport()
        app.dry_run_report = report
    return report


def _record_pr_action(app: App, action: str, pr_item: PullRequestItem) -> None:
    report = _get_dry_run_report(app)
    pr_id = int(pr_item.ado_pr_id)
    title = str(pr_item.title)
    if action == "create":
        report.record_pr_create(ado_pr_id=pr_id, title=title)
    elif action == "update":
        report.record_pr_update(ado_pr_id=pr_id, title=title)
    elif action == "close":
        report.record_pr_close(ado_pr_id=pr_id, title=title)


def _get_cached_custom_field(app: App, asana_project, field_name: str):
    """Get custom field with caching to avoid repeated API calls."""
    if hasattr(app, "_spec_class"):
        return find_custom_field_by_name(app, asana_project, field_name)

    project_str = asana_project if isinstance(asana_project, str) else str(asana_project.get("gid", asana_project))
    cache_key = f"{project_str}:{field_name}"
    if hasattr(app, "pr_sync_cache") and cache_key in app.pr_sync_cache["custom_fields"]:  # type: ignore[attr-defined]
        return app.pr_sync_cache["custom_fields"][cache_key]  # type: ignore[attr-defined]

    field = find_custom_field_by_name(app, asana_project, field_name)
    if hasattr(app, "pr_sync_cache"):
        app.pr_sync_cache["custom_fields"][cache_key] = field  # type: ignore[attr-defined]
    return field


def _get_cached_asana_task(app: App, asana_gid: str):
    """Get Asana task with caching to avoid repeated API calls."""
    if not asana_gid:
        return None

    if hasattr(app, "_spec_class"):
        return get_asana_task(app, asana_gid)

    if hasattr(app, "pr_sync_cache") and asana_gid in app.pr_sync_cache["asana_tasks"]:  # type: ignore[attr-defined]
        return app.pr_sync_cache["asana_tasks"][asana_gid]  # type: ignore[attr-defined]

    task = get_asana_task(app, asana_gid)
    if hasattr(app, "pr_sync_cache"):
        app.pr_sync_cache["asana_tasks"][asana_gid] = task  # type: ignore[attr-defined]
    return task


def create_asana_pr_task(app: App, asana_project: str, pr_item: PullRequestItem, tag: str) -> None:
    """Create an Asana task for a pull request reviewer."""
    is_completed = (
        pr_item.status in _PR_CLOSED_STATES
        or pr_item.review_status in _REVIEWER_APPROVED_STATES
        or pr_item.status == "reviewer_removed"
        or pr_item.review_status == "removed"
    )

    _LOGGER.debug(
        "Creating Asana task %s: completed=%s (review_status='%s', pr_status='%s')",
        pr_item.asana_title,
        is_completed,
        pr_item.review_status or "none",
        pr_item.status or "none",
    )

    if _is_dry_run(app):
        _record_pr_action(app, "create", pr_item)
        pr_item.asana_gid = pr_item.asana_gid or f"dry-run-pr-{pr_item.ado_pr_id}"
        pr_item.processing_state = "closed" if is_completed else "open"
        _LOGGER.info("Dry-run mode: would create PR task for PR %s", pr_item.ado_pr_id)
        return

    tasks_api_instance = asana.TasksApi(app.asana_client)

    link_custom_field = _get_cached_custom_field(app, asana_project, "Link")
    link_custom_field_id = link_custom_field.get("custom_field", {}).get("gid") if link_custom_field else None

    body = {
        "data": {
            "name": pr_item.asana_title,
            "html_notes": f"<body>{pr_item.asana_notes_link}</body>",
            "projects": [asana_project],
            "assignee": pr_item.reviewer_gid,
            "tags": [tag],
            "completed": is_completed,
        },
    }

    if link_custom_field_id:
        body["data"]["custom_fields"] = {link_custom_field_id: encode_url_for_asana(pr_item.url)}

    try:
        result = tasks_api_instance.create_task(body, opts={})
        pr_item.asana_gid = result["gid"]
        pr_item.asana_updated = result["modified_at"]
        pr_item.updated_date = iso8601_utc(datetime.now())

        if is_completed:
            pr_item.processing_state = "closed"
            _LOGGER.debug("Setting new PR %d processing_state to 'closed' (created as completed)", pr_item.ado_pr_id)
        else:
            pr_item.processing_state = "open"
            _LOGGER.debug("Setting new PR %d processing_state to 'open' (created as active)", pr_item.ado_pr_id)

        pr_item.save(app)
    except ApiException as exception:
        _LOGGER.error("Exception when calling TasksApi->create_task: %s\n", exception)


def update_asana_pr_task(app: App, pr_item: PullRequestItem, tag: str, asana_project_gid: str) -> None:
    """Update an Asana task for a pull request reviewer."""
    is_completed = (
        pr_item.status in _PR_CLOSED_STATES
        or pr_item.review_status in _REVIEWER_APPROVED_STATES
        or pr_item.status == "reviewer_removed"
        or pr_item.review_status == "removed"
    )

    _LOGGER.debug(
        "Updating Asana task %s: completed=%s (review_status='%s', pr_status='%s')",
        pr_item.asana_title,
        is_completed,
        pr_item.review_status or "none",
        pr_item.status or "none",
    )

    if _is_dry_run(app):
        action = "close" if is_completed else "update"
        _record_pr_action(app, action, pr_item)
        _LOGGER.info("Dry-run mode: would %s PR task for PR %s", action, pr_item.ado_pr_id)
        return

    tasks_api_instance = asana.TasksApi(app.asana_client)

    link_custom_field = _get_cached_custom_field(app, asana_project_gid, "Link")
    link_custom_field_id = link_custom_field.get("custom_field", {}).get("gid") if link_custom_field else None

    body = {
        "data": {
            "name": pr_item.asana_title,
            "html_notes": f"<body>{pr_item.asana_notes_link}</body>",
            "assignee": pr_item.reviewer_gid,
            "completed": is_completed,
        }
    }

    if link_custom_field_id:
        body["data"]["custom_fields"] = {link_custom_field_id: encode_url_for_asana(pr_item.url)}

    try:
        result = tasks_api_instance.update_task(body, pr_item.asana_gid, opts={})
        pr_item.asana_updated = result["modified_at"]
        pr_item.updated_date = iso8601_utc(datetime.now())

        if is_completed:
            pr_item.processing_state = "closed"
            _LOGGER.debug("Setting PR %d processing_state to 'closed' (task completed)", pr_item.ado_pr_id)
        else:
            pr_item.processing_state = "open"
            _LOGGER.debug("Setting PR %d processing_state to 'open' (task reopened)", pr_item.ado_pr_id)

        pr_item.save(app)

        add_tag_to_pr_task(app, pr_item, tag)

        if is_completed:
            add_closure_comment_to_pr_task(app, pr_item)
    except ApiException as exception:
        _LOGGER.error("Exception when calling TasksApi->update_task: %s\n", exception)


def add_tag_to_pr_task(app: App, pr_item: PullRequestItem, tag: str) -> None:
    """Adds a tag to a pull request task if it is not already assigned."""
    if _is_dry_run(app):
        _LOGGER.info("Dry-run mode: would tag PR task %s with %s", pr_item.asana_title, tag)
        return
    api_instance = asana.TagsApi(app.asana_client)
    try:
        api_response = api_instance.get_tags_for_task(pr_item.asana_gid, opts={})
        task_tags_gids = [t["gid"] for t in api_response]

        if tag not in task_tags_gids:
            _LOGGER.debug("adding tag to PR task '%s'", pr_item.asana_title)
            tasks_api_instance = asana.TasksApi(app.asana_client)
            body = {"data": {"tag": tag}}
            tasks_api_instance.add_tag_for_task(body, pr_item.asana_gid)
    except ApiException as exception:
        _LOGGER.error("Exception when adding tag to PR task: %s\n", exception)


def add_closure_comment_to_pr_task(app: App, pr_item: PullRequestItem) -> None:
    """Add a comment to a pull request task explaining why it was closed."""
    if _is_dry_run(app):
        _LOGGER.info("Dry-run mode: would add closure comment to PR task %s", pr_item.asana_title)
        return
    if not pr_item.asana_gid:
        return

    closure_reasons = {
        "completed": "Pull request has been completed and merged",
        "abandoned": "Pull request has been abandoned",
        "draft": "Pull request has been moved to draft status",
        "reviewer_removed": "You have been removed as a reviewer from this pull request",
    }

    closure_reason = closure_reasons.get(pr_item.status, f"Pull request status changed to {pr_item.status}")

    if (
        pr_item.status in _PR_CLOSED_STATES or pr_item.status == "reviewer_removed" or pr_item.review_status == "removed"
    ) and pr_item.review_status not in _REVIEWER_APPROVED_STATES:
        stories_api_instance = asana.StoriesApi(app.asana_client)
        try:
            body = {"data": {"text": f"Task closed automatically: {closure_reason}", "type": "comment"}}
            stories_api_instance.create_story_for_task(body, pr_item.asana_gid, opts={})
            _LOGGER.debug("Added closure comment to PR task %s: %s", pr_item.asana_title, closure_reason)
        except ApiException as exception:
            _LOGGER.error("Exception when adding closure comment to PR task: %s\n", exception)

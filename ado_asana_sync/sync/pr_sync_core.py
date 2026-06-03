"""PR sync orchestration - top-level functions for synchronizing pull requests."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List

try:
    from azure.devops.v7_0.git.models import GitPullRequestSearchCriteria
except ImportError:
    GitPullRequestSearchCriteria = None

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App
from .group_member_cache import GroupMemberCache
from .pr_asana_helpers import _PR_CLOSED_STATES, _get_cached_asana_task, _record_pr_action, update_asana_pr_task
from .pr_processor import create_ado_user_from_reviewer, process_pull_request
from .pull_request_item import PullRequestItem
from .sync import (
    get_asana_project_tasks,
    get_asana_users,
    matching_user,
)
from .utils import extract_reviewer_vote

_LOGGER, _TRACER = setup_logging_and_tracing(__name__)

_ADO_GIT_CLIENT_NONE_MSG = "app.ado_git_client is None"
_ADO_PR_MATCHES_NONE_MSG = "app.pr_matches is None"
_ADO_DOES_NOT_EXIST = "does not exist"


def _should_skip_closed_pr(pr_item: PullRequestItem) -> bool:
    """Check if a PR should be skipped because it's already closed and processed."""
    return pr_item.processing_state == "closed"


def _get_open_pr_tasks(app: App, repository) -> list:
    """Query database for open PR tasks, optionally filtered by repository."""
    if app.pr_matches is None:
        raise ValueError(_ADO_PR_MATCHES_NONE_MSG)
    if repository:
        repository_id = repository.id

        def repo_query_func(record):
            return record.get("ado_repository_id") == repository_id and record.get("processing_state", "open") != "closed"

        tasks = app.pr_matches.search(repo_query_func)
        _LOGGER.info(
            "Second pass: processing repository %s (ID: %s) open database PR tasks not handled in active PR sync",
            repository.name,
            repository.id,
        )
        if tasks:
            pr_task_info = [(task.get("ado_pr_id"), task.get("ado_repository_id")) for task in tasks]
            _LOGGER.debug("Second pass: Found PR tasks for repository %s: %s", repository.name, pr_task_info)
    else:

        def all_query_func(record):
            return record.get("processing_state", "open") != "closed"

        tasks = app.pr_matches.search(all_query_func)
        _LOGGER.info("Second pass: processing all open database PR tasks not handled in active PR sync")
        _LOGGER.debug("Second pass: found %d open PR tasks in database", len(tasks))
    return tasks


def _update_pr_reviewer_status(app: App, pr_item: PullRequestItem, asana_users: List[dict], repository) -> Any:
    """Fetch PR from ADO and update reviewer status. Returns the PR object."""
    if app.ado_git_client is None:
        raise ValueError(_ADO_GIT_CLIENT_NONE_MSG)
    pr = app.ado_git_client.get_pull_request_by_id(pr_item.ado_pr_id)
    _LOGGER.debug("Second pass: Successfully retrieved PR %d with status '%s'", pr_item.ado_pr_id, pr.status)

    try:
        reviewers = app.ado_git_client.get_pull_request_reviewers(repository.id, pr_item.ado_pr_id)
        for reviewer in reviewers:
            ado_reviewer = create_ado_user_from_reviewer(reviewer)
            if ado_reviewer:
                asana_matched = matching_user(asana_users, ado_reviewer)
                if asana_matched and asana_matched.get("gid") == pr_item.reviewer_gid:
                    old_review_status = pr_item.review_status
                    pr_item.review_status = extract_reviewer_vote(reviewer)
                    if old_review_status != pr_item.review_status:
                        _LOGGER.info(
                            "Second pass: Updated review status for PR %d reviewer %s from '%s' to '%s'",
                            pr_item.ado_pr_id,
                            pr_item.reviewer_name or pr_item.reviewer_gid,
                            old_review_status or "none",
                            pr_item.review_status,
                        )
                    break
    except Exception as reviewer_error:  # pylint: disable=broad-exception-caught
        _LOGGER.debug(
            "Second pass: Could not fetch reviewers for PR %d: %s (will proceed with existing review status)",
            pr_item.ado_pr_id,
            reviewer_error,
        )
    return pr


def _finalize_closed_pr_task(app: App, pr_item: PullRequestItem, pr: Any, asana_project: str) -> None:
    """Update Asana and DB for a PR confirmed as closed."""
    if not pr_item.asana_gid:
        return
    asana_task = _get_cached_asana_task(app, pr_item.asana_gid)
    pr_item.status = pr.status if pr else "completed"
    pr_item.updated_date = iso8601_utc(datetime.now())

    if asana_task and not asana_task.get("completed", False):
        if app.asana_tag_gid is not None:
            update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)
    else:
        if getattr(app, "dry_run", False) is True:
            _record_pr_action(app, "close", pr_item)
            return
        pr_item.save(app)
        _LOGGER.debug(
            "Second pass: PR %d task already completed, updated database record with final review_status='%s'",
            pr_item.ado_pr_id,
            pr_item.review_status or "none",
        )


def _handle_inaccessible_pr(app: App, pr_item: PullRequestItem, asana_project: str) -> None:
    """Close Asana task for a PR that cannot be retrieved from ADO."""
    if not pr_item.asana_gid:
        return
    asana_task = _get_cached_asana_task(app, pr_item.asana_gid)
    pr_item.status = "abandoned"
    pr_item.updated_date = iso8601_utc(datetime.now())

    if asana_task and not asana_task.get("completed", False) and app.asana_tag_gid is not None:
        update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)
    else:
        pr_item.processing_state = "closed"
        if getattr(app, "dry_run", False) is True:
            _record_pr_action(app, "close", pr_item)
            return
        pr_item.save(app)
    _LOGGER.info("Closed Asana task for inaccessible PR %d", pr_item.ado_pr_id)


def _process_pr_via_ado(
    app: App,
    pr_item: PullRequestItem,
    asana_users: List[dict],
    asana_project: str,
    repository,
    counters: dict,
) -> None:
    """Fetch and process a single PR task via ADO, updating Asana as needed."""
    try:
        if app.ado_git_client is None:
            raise ValueError(_ADO_GIT_CLIENT_NONE_MSG)
        if repository is None:
            _LOGGER.debug("Repository not provided; skipping ADO lookup for PR %s", pr_item.ado_pr_id)
            return

        pr = _update_pr_reviewer_status(app, pr_item, asana_users, repository)

        if pr and pr.status not in _PR_CLOSED_STATES:
            _LOGGER.debug("Skipping PR %d (status '%s' not in closed states)", pr_item.ado_pr_id, pr.status)
            return

        _LOGGER.info("Processing closed PR %s with status '%s'", pr_item.ado_pr_id, pr.status if pr else "not found")
        counters["processed"] += 1
        _finalize_closed_pr_task(app, pr_item, pr, asana_project)

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_msg = str(e)
        _LOGGER.debug("Exception getting PR %d from ADO: %s", pr_item.ado_pr_id, e)
        if _ADO_DOES_NOT_EXIST in error_msg or "permission" in error_msg or "invalid literal for int()" in error_msg:
            _LOGGER.warning(
                "PR %d cannot be retrieved from ADO (does not exist or no permission). "
                "Closing associated Asana task. Error: %s",
                pr_item.ado_pr_id,
                error_msg,
            )
            _handle_inaccessible_pr(app, pr_item, asana_project)
            counters["processed"] += 1
            return
        _LOGGER.warning("Failed to process closed PR %s: %s", pr_item.ado_pr_id, e)


def _process_single_pr_task(
    app: App,
    pr_task_data: dict,
    asana_users: List[dict],
    asana_project: str,
    processed_pr_ids: set,
    repository,
    counters: dict,
) -> None:
    """Process a single PR task record in the second pass."""
    clean_pr_task_data = {k: v for k, v in pr_task_data.items() if k != "doc_id"}
    pr_item = PullRequestItem(**clean_pr_task_data)
    _LOGGER.debug("Second pass examining PR %d", pr_item.ado_pr_id)

    if pr_item.ado_pr_id in processed_pr_ids:
        _LOGGER.debug("Second pass skipping PR %d (already processed as active)", pr_item.ado_pr_id)
        counters["skipped_active"] += 1
        return

    if not pr_item.validate_data_consistency():
        _LOGGER.warning(
            "Skipping PR item with inconsistent data: PR ID %s, URL %s, title '%s'",
            pr_item.ado_pr_id,
            pr_item.url,
            pr_item.title,
        )
        return

    if _should_skip_closed_pr(pr_item):
        _LOGGER.info(
            "Skipping PR %d (status='%s', Asana task already completed) - avoiding redundant API call",
            pr_item.ado_pr_id,
            pr_item.status,
        )
        counters["skipped_closed"] += 1
        return

    if repository:
        _LOGGER.debug(
            "Second pass: Attempting to retrieve PR %d from repository %s (current repo ID: %s, stored repo ID: %s)",
            pr_item.ado_pr_id,
            repository.name,
            repository.id,
            pr_item.ado_repository_id,
        )
    else:
        _LOGGER.debug(
            "Second pass: Attempting to retrieve PR %d (stored repo ID: %s)", pr_item.ado_pr_id, pr_item.ado_repository_id
        )

    _process_pr_via_ado(app, pr_item, asana_users, asana_project, repository, counters)


def _log_second_pass_summary(repository, processed_count: int, skipped_active_count: int, skipped_closed_count: int) -> None:
    """Log the summary of the second pass processing."""
    if repository:
        _LOGGER.info(
            "Second pass completed for repository %s: processed %d closed PRs, "
            "skipped %d active PRs, skipped %d already-closed PRs",
            repository.name,
            processed_count,
            skipped_active_count,
            skipped_closed_count,
        )
    else:
        _LOGGER.info(
            "Second pass completed: processed %d closed PRs, skipped %d active PRs, skipped %d already-closed PRs",
            processed_count,
            skipped_active_count,
            skipped_closed_count,
        )


def sync_pull_requests(app: App, ado_project, asana_workspace_id: str, asana_project: str) -> None:
    """Synchronizes pull requests from Azure DevOps to Asana."""
    with _TRACER.start_as_current_span("sync_pull_requests") as span:
        span.add_event("Start PR sync")

        _LOGGER.info("Starting pull request sync for project %s", ado_project.name)

        asana_users = get_asana_users(app, asana_workspace_id)
        asana_project_tasks = get_asana_project_tasks(app, asana_project)

        if not hasattr(app, "pr_sync_cache"):
            app.pr_sync_cache = {  # type: ignore[attr-defined]
                "custom_fields": {},
                "asana_tasks": {},
            }

        if app.ado_git_client is None:
            raise ValueError(_ADO_GIT_CLIENT_NONE_MSG)
        try:
            repositories = app.ado_git_client.get_repositories(ado_project.id)
        except Exception as e:  # pylint: disable=broad-exception-caught
            error_msg = str(e)
            if _ADO_DOES_NOT_EXIST in error_msg or "permission" in error_msg:
                _LOGGER.info(
                    "Skipping PR sync for project %s due to access restrictions",
                    ado_project.name,
                )
                return
            _LOGGER.error("Failed to get repositories for project %s: %s", ado_project.name, e)
            return

        for repo in repositories:
            _LOGGER.info("Processing repository %s", repo.name)
            try:
                repo_processed_prs = process_repository_pull_requests(
                    app, repo, asana_users, asana_project_tasks, asana_project
                )
                process_closed_pull_requests(app, asana_users, asana_project, repo_processed_prs, repo)
            except Exception as e:  # pylint: disable=broad-exception-caught
                error_msg = str(e)
                if _ADO_DOES_NOT_EXIST in error_msg or "permission" in error_msg:
                    _LOGGER.debug(
                        "Skipping repository %s due to access restrictions: %s",
                        repo.name,
                        e,
                    )
                else:
                    _LOGGER.error("Failed to process repository %s: %s", repo.name, e)

        _LOGGER.info("Completed pull request sync for project %s", ado_project.name)


def process_repository_pull_requests(
    app: App,
    repository,
    asana_users: List[dict],
    asana_project_tasks: List[dict],
    asana_project: str,
) -> set[int]:
    """Process pull requests for a specific repository."""
    processed_pr_ids: set[int] = set()
    user_lookup_cache: dict[str, dict | None] = {}
    # Re-use the app-level persistent cache when available; otherwise use a run-scoped one.
    group_member_cache: GroupMemberCache = getattr(app, "group_member_cache", None) or GroupMemberCache()

    if GitPullRequestSearchCriteria:
        search_criteria = GitPullRequestSearchCriteria(status="active")
    else:
        search_criteria = {"status": "active"}

    if app.ado_git_client is None:
        raise ValueError(_ADO_GIT_CLIENT_NONE_MSG)
    try:
        pull_requests = app.ado_git_client.get_pull_requests(repository.id, search_criteria)
    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.error("Failed to get pull requests for repository %s: %s", repository.name, e)
        return processed_pr_ids

    for pr in pull_requests:
        process_pull_request(
            app, pr, repository, asana_users, asana_project_tasks, asana_project, user_lookup_cache, group_member_cache
        )
        processed_pr_ids.add(pr.pull_request_id)

    return processed_pr_ids


def process_closed_pull_requests(
    app: App, _asana_users: List[dict], asana_project: str, processed_pr_ids: set[int] | None = None, repository=None
) -> None:
    """Process pull requests that are no longer active but still have tasks in the database."""
    if app.pr_matches is None:
        raise ValueError("app.pr_matches is None")

    if processed_pr_ids is None:
        processed_pr_ids = set()

    repo_pr_tasks = _get_open_pr_tasks(app, repository)
    counters = {"processed": 0, "skipped_active": 0, "skipped_closed": 0}

    for pr_task_data in repo_pr_tasks:
        _process_single_pr_task(app, pr_task_data, _asana_users, asana_project, processed_pr_ids, repository, counters)

    _log_second_pass_summary(repository, counters["processed"], counters["skipped_active"], counters["skipped_closed"])

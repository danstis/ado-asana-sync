"""PR sync orchestration - top-level functions for synchronizing pull requests."""

from __future__ import annotations

from datetime import datetime
from typing import List

try:
    from azure.devops.v7_0.git.models import GitPullRequestSearchCriteria
except ImportError:
    GitPullRequestSearchCriteria = None

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App
from .pr_asana_helpers import _PR_CLOSED_STATES, _get_cached_asana_task, update_asana_pr_task
from .pr_processor import create_ado_user_from_reviewer, process_pull_request
from .pull_request_item import PullRequestItem
from .sync import (
    get_asana_project_tasks,
    get_asana_users,
    matching_user,
)
from .utils import extract_reviewer_vote

_LOGGER, _TRACER = setup_logging_and_tracing(__name__)


def _should_skip_closed_pr(pr_item: PullRequestItem) -> bool:
    """Check if a PR should be skipped because it's already closed and processed."""
    return pr_item.processing_state == "closed"


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
            raise ValueError("app.ado_git_client is None")
        try:
            repositories = app.ado_git_client.get_repositories(ado_project.id)
        except Exception as e:  # pylint: disable=broad-exception-caught
            error_msg = str(e)
            if "does not exist" in error_msg or "permission" in error_msg:
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
                if "does not exist" in error_msg or "permission" in error_msg:
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

    if GitPullRequestSearchCriteria:
        search_criteria = GitPullRequestSearchCriteria(status="active")
    else:
        search_criteria = {"status": "active"}

    if app.ado_git_client is None:
        raise ValueError("app.ado_git_client is None")
    try:
        pull_requests = app.ado_git_client.get_pull_requests(repository.id, search_criteria)
    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.error("Failed to get pull requests for repository %s: %s", repository.name, e)
        return processed_pr_ids

    for pr in pull_requests:
        process_pull_request(app, pr, repository, asana_users, asana_project_tasks, asana_project, user_lookup_cache)
        processed_pr_ids.add(pr.pull_request_id)

    return processed_pr_ids


def process_closed_pull_requests(  # noqa: C901
    app: App, _asana_users: List[dict], asana_project: str, processed_pr_ids: set[int] | None = None, repository=None
) -> None:
    """
    Process pull requests that are no longer active but still have tasks in the database.

    Note: Complexity justified by necessary error handling and cleanup logic.
    """
    if app.pr_matches is None:
        raise ValueError("app.pr_matches is None")

    if processed_pr_ids is None:
        processed_pr_ids = set()

    if repository:
        repository_id = repository.id

        def repo_query_func(record):
            return record.get("ado_repository_id") == repository_id and record.get("processing_state", "open") != "closed"

        repo_pr_tasks = app.pr_matches.search(repo_query_func)
        _LOGGER.info(
            "Second pass: processing repository %s (ID: %s) open database PR tasks not handled in active PR sync",
            repository.name,
            repository.id,
        )

        if repo_pr_tasks:
            pr_task_info = [(task.get("ado_pr_id"), task.get("ado_repository_id")) for task in repo_pr_tasks]
            _LOGGER.debug("Second pass: Found PR tasks for repository %s: %s", repository.name, pr_task_info)
    else:

        def all_query_func(record):
            return record.get("processing_state", "open") != "closed"

        repo_pr_tasks = app.pr_matches.search(all_query_func)
        _LOGGER.info("Second pass: processing all open database PR tasks not handled in active PR sync")
        _LOGGER.debug("Second pass: found %d open PR tasks in database", len(repo_pr_tasks))
    skipped_active_count = 0
    skipped_closed_count = 0
    processed_count = 0

    for pr_task_data in repo_pr_tasks:
        clean_pr_task_data = {k: v for k, v in pr_task_data.items() if k != "doc_id"}
        pr_item = PullRequestItem(**clean_pr_task_data)

        _LOGGER.debug("Second pass examining PR %d", pr_item.ado_pr_id)

        if pr_item.ado_pr_id in processed_pr_ids:
            _LOGGER.debug("Second pass skipping PR %d (already processed as active)", pr_item.ado_pr_id)
            skipped_active_count += 1
            continue

        if not pr_item.validate_data_consistency():
            _LOGGER.warning(
                "Skipping PR item with inconsistent data: PR ID %s, URL %s, title '%s'",
                pr_item.ado_pr_id,
                pr_item.url,
                pr_item.title,
            )
            continue

        if _should_skip_closed_pr(pr_item):
            _LOGGER.info(
                "Skipping PR %d (status='%s', Asana task already completed) - avoiding redundant API call",
                pr_item.ado_pr_id,
                pr_item.status,
            )
            skipped_closed_count += 1
            continue

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

        try:
            if app.ado_git_client is None:
                raise ValueError("app.ado_git_client is None")
            if repository is None:
                _LOGGER.debug("Repository not provided; skipping ADO lookup for PR %s", pr_item.ado_pr_id)
                continue

            pr = app.ado_git_client.get_pull_request_by_id(pr_item.ado_pr_id)

            _LOGGER.debug("Second pass: Successfully retrieved PR %d with status '%s'", pr_item.ado_pr_id, pr.status)

            try:
                reviewers = app.ado_git_client.get_pull_request_reviewers(repository.id, pr_item.ado_pr_id)
                for reviewer in reviewers:
                    ado_reviewer = create_ado_user_from_reviewer(reviewer)
                    if ado_reviewer:
                        asana_matched = matching_user(_asana_users, ado_reviewer)
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

            if pr and pr.status not in _PR_CLOSED_STATES:
                _LOGGER.debug("Skipping PR %d (status '%s' not in closed states)", pr_item.ado_pr_id, pr.status)
                continue

            _LOGGER.info("Processing closed PR %s with status '%s'", pr_item.ado_pr_id, pr.status if pr else "not found")
            processed_count += 1

            if pr_item.asana_gid:
                asana_task = _get_cached_asana_task(app, pr_item.asana_gid)
                pr_item.status = pr.status if pr else "completed"
                pr_item.updated_date = iso8601_utc(datetime.now())

                if asana_task and not asana_task.get("completed", False):
                    if app.asana_tag_gid is not None:
                        update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)
                else:
                    pr_item.save(app)
                    _LOGGER.debug(
                        "Second pass: PR %d task already completed, updated database record with final review_status='%s'",
                        pr_item.ado_pr_id,
                        pr_item.review_status or "none",
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught
            error_msg = str(e)
            _LOGGER.debug("Exception getting PR %d from ADO: %s", pr_item.ado_pr_id, e)
            if "does not exist" in error_msg or "permission" in error_msg or "invalid literal for int()" in error_msg:
                _LOGGER.warning(
                    "PR %d cannot be retrieved from ADO (does not exist or no permission). "
                    "Closing associated Asana task. Error: %s",
                    pr_item.ado_pr_id,
                    error_msg,
                )
                if pr_item.asana_gid:
                    asana_task = _get_cached_asana_task(app, pr_item.asana_gid)
                    if asana_task and not asana_task.get("completed", False):
                        pr_item.status = "abandoned"
                        pr_item.updated_date = iso8601_utc(datetime.now())
                        if app.asana_tag_gid is not None:
                            update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)
                        processed_count += 1
                        _LOGGER.info("Closed Asana task for inaccessible PR %d", pr_item.ado_pr_id)
                continue
            _LOGGER.warning("Failed to process closed PR %s: %s", pr_item.ado_pr_id, e)
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

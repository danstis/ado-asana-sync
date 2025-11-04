"""This module contains functions for synchronizing pull requests between Azure DevOps and Asana."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

try:
    from azure.devops.v7_0.git.models import GitPullRequestSearchCriteria
except ImportError:
    # Fallback if git models are not available
    GitPullRequestSearchCriteria = None

import asana
from asana.rest import ApiException

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App
from .asana import get_asana_task
from .pull_request_item import PullRequestItem
from .sync import (
    ADOAssignedUser,
    find_custom_field_by_name,
    get_asana_project_tasks,
    get_asana_task_by_name,
    get_asana_users,
    matching_user,
)
from .utils import encode_url_for_asana, extract_reviewer_vote

# This module uses the logger and tracer instances _LOGGER and _TRACER for logging and tracing, respectively.
_LOGGER, _TRACER = setup_logging_and_tracing(__name__)

# PR status mapping - determines when to close Asana tasks
_PR_CLOSED_STATES = {"completed", "abandoned", "draft"}
# ADO reviewer vote values that should close the Asana task
_REVIEWER_APPROVED_STATES = {"approved", "approvedWithSuggestions"}


def _get_cached_custom_field(app: App, asana_project, field_name: str):
    """Get custom field with caching to avoid repeated API calls."""
    # Skip caching in test mode (when app has spec attribute indicating it's a Mock)
    if hasattr(app, "_spec_class"):
        return find_custom_field_by_name(app, asana_project, field_name)

    # Handle both string and dict project formats for backward compatibility
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
    if not asana_gid:  # Early return for invalid inputs
        return None

    # Skip caching in test mode (when app has spec attribute indicating it's a Mock)
    if hasattr(app, "_spec_class"):
        return get_asana_task(app, asana_gid)

    if hasattr(app, "pr_sync_cache") and asana_gid in app.pr_sync_cache["asana_tasks"]:  # type: ignore[attr-defined]
        return app.pr_sync_cache["asana_tasks"][asana_gid]  # type: ignore[attr-defined]

    task = get_asana_task(app, asana_gid)
    if hasattr(app, "pr_sync_cache"):
        app.pr_sync_cache["asana_tasks"][asana_gid] = task  # type: ignore[attr-defined]
    return task


def _should_skip_closed_pr(pr_item: PullRequestItem) -> bool:
    """
    Check if a PR should be skipped because it's already closed and processed.

    Uses the database processing_state field to avoid API calls.
    Skips PRs that have processing_state = "closed".
    """
    return pr_item.processing_state == "closed"


def sync_pull_requests(app: App, ado_project, asana_workspace_id: str, asana_project: str) -> None:
    """
    Synchronizes pull requests from Azure DevOps to Asana.

    Creates separate Asana tasks for each reviewer of each pull request.
    """
    with _TRACER.start_as_current_span("sync_pull_requests") as span:
        span.add_event("Start PR sync")

        _LOGGER.info("Starting pull request sync for project %s", ado_project.name)

        # Get all Asana users for user matching
        asana_users = get_asana_users(app, asana_workspace_id)

        # Get all Asana tasks in this project
        asana_project_tasks = get_asana_project_tasks(app, asana_project)

        # Cache for performance optimization
        if not hasattr(app, "pr_sync_cache"):
            app.pr_sync_cache = {  # type: ignore[attr-defined]
                "custom_fields": {},  # Cache custom field lookups
                "asana_tasks": {},  # Cache Asana task lookups
            }

        # Get all repositories in the ADO project
        if app.ado_git_client is None:
            raise ValueError("app.ado_git_client is None")
        try:
            repositories = app.ado_git_client.get_repositories(ado_project.id)
        except Exception as e:  # pylint: disable=broad-exception-caught  # pylint: disable=broad-exception-caught
            error_msg = str(e)
            if "does not exist" in error_msg or "permission" in error_msg:
                _LOGGER.info(
                    "Skipping PR sync for project %s due to access restrictions",
                    ado_project.name,
                )
                return
            _LOGGER.error("Failed to get repositories for project %s: %s", ado_project.name, e)
            return

        # Process pull requests for each repository using two-pass approach
        for repo in repositories:
            _LOGGER.info("Processing repository %s", repo.name)
            try:
                # First Pass: Process active PRs from ADO
                repo_processed_prs = process_repository_pull_requests(
                    app, repo, asana_users, asana_project_tasks, asana_project
                )

                # Second Pass: Process database PR tasks for this repository that weren't in first pass
                process_closed_pull_requests(app, asana_users, asana_project, repo_processed_prs, repo)
            except Exception as e:  # pylint: disable=broad-exception-caught  # pylint: disable=broad-exception-caught
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
    """
    Process pull requests for a specific repository.

    Returns:
        set[int]: Set of PR IDs that were processed in this repository.
    """
    processed_pr_ids: set[int] = set()

    # Cache user lookup for performance
    user_lookup_cache: dict[str, dict | None] = {}

    # Get active pull requests
    if GitPullRequestSearchCriteria:
        search_criteria = GitPullRequestSearchCriteria(
            status="active"  # Only get active PRs
        )
    else:
        # Fallback to simple parameters
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


def process_pull_request(  # noqa: C901
    app: App,
    pr,
    repository,
    asana_users: List[dict],
    asana_project_tasks: List[dict],
    asana_project: str,
    user_lookup_cache: dict | None = None,
) -> None:
    """
    Process a single pull request, creating reviewer tasks.

    Note: Complexity justified by necessary error handling and business logic.
    """
    _LOGGER.debug("Processing PR %s: %s", pr.pull_request_id, pr.title)

    if app.ado_git_client is None:
        raise ValueError("app.ado_git_client is None")
    try:
        # Get reviewers for this pull request
        reviewers = app.ado_git_client.get_pull_request_reviewers(repository.id, pr.pull_request_id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.error("Failed to get reviewers for PR %s: %s", pr.pull_request_id, e)
        return

    if not reviewers:
        _LOGGER.debug("No reviewers found for PR %s", pr.pull_request_id)
        # Handle case where all reviewers have been removed
        handle_removed_reviewers(app, pr, set(), asana_project)  # Empty set means no current reviewers
        return

    # Process each reviewer (deduplicate by email to avoid processing the same reviewer multiple times)
    processed_reviewers = set()
    current_reviewer_gids = set()

    for reviewer in reviewers:
        # Try to get a unique identifier for the reviewer
        reviewer_id = None
        if hasattr(reviewer, "user") and reviewer.user:
            reviewer_id = getattr(reviewer.user, "unique_name", None) or getattr(reviewer.user, "uniqueName", None)
        else:
            reviewer_id = getattr(reviewer, "unique_name", None) or getattr(reviewer, "uniqueName", None)

        if reviewer_id and reviewer_id in processed_reviewers:
            _LOGGER.debug(
                "Skipping duplicate reviewer %s for PR %s",
                reviewer_id,
                pr.pull_request_id,
            )
            continue

        if reviewer_id:
            processed_reviewers.add(reviewer_id)

        # Get the Asana user GID for this reviewer to track current reviewers
        ado_reviewer = create_ado_user_from_reviewer(reviewer)
        if ado_reviewer:
            # Use cache for user lookup to avoid repeated matching
            reviewer_key = f"{ado_reviewer.display_name}:{ado_reviewer.email}"
            if user_lookup_cache is not None and reviewer_key in user_lookup_cache:
                asana_matched_user = user_lookup_cache[reviewer_key]
            else:
                asana_matched_user = matching_user(asana_users, ado_reviewer)
                if user_lookup_cache is not None:
                    user_lookup_cache[reviewer_key] = asana_matched_user

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

    # Handle removed reviewers - close tasks for reviewers no longer on the PR
    handle_removed_reviewers(app, pr, current_reviewer_gids, asana_project)


def handle_removed_reviewers(  # noqa: C901
    app: App, pr, current_reviewer_gids: set, asana_project: str
) -> None:
    """
    Handle reviewers that have been removed from the PR by closing their Asana tasks.
    """
    # Find all existing PR tasks for this PR
    if app.pr_matches is None:
        raise ValueError("app.pr_matches is None")

    # Use more efficient database query
    def query_func(record):
        return record.get("ado_pr_id") == pr.pull_request_id

    existing_pr_tasks = app.pr_matches.search(query_func)

    # Early return if no tasks found
    if not existing_pr_tasks:
        return

    for task_data in existing_pr_tasks:
        # Remove doc_id before creating PullRequestItem
        clean_task_data = {k: v for k, v in task_data.items() if k != "doc_id"}
        pr_item = PullRequestItem(**clean_task_data)

        # Validate that this PR item is for the correct PR
        if pr_item.ado_pr_id != pr.pull_request_id:
            _LOGGER.warning(
                "Skipping corrupted PR item: expected PR ID %s but got %s with title '%s'",
                pr.pull_request_id,
                pr_item.ado_pr_id,
                pr_item.title,
            )
            continue

        # If this reviewer is no longer in the current reviewers list, close their task
        if pr_item.reviewer_gid not in current_reviewer_gids:
            _LOGGER.info(
                "Reviewer %s removed from PR %s, closing task: %s",
                pr_item.reviewer_name or pr_item.reviewer_gid,
                pr.pull_request_id,
                pr_item.asana_title,
            )

            # Update the PR item to mark it as removed/completed
            pr_item.status = "reviewer_removed"
            pr_item.review_status = "removed"
            pr_item.updated_date = iso8601_utc(datetime.now())

            # Close the Asana task
            if pr_item.asana_gid:
                try:
                    if app.asana_tag_gid is not None:
                        update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)
                    _LOGGER.info(
                        "Closed Asana task for removed reviewer: %s",
                        pr_item.asana_title,
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught  # pylint: disable=broad-exception-caught
                    _LOGGER.error(
                        "Failed to close Asana task for removed reviewer %s: %s",
                        pr_item.asana_title,
                        e,
                    )


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
    """
    Process a single reviewer for a pull request.
    """
    # Convert ADO reviewer to user format similar to work items
    ado_reviewer = create_ado_user_from_reviewer(reviewer)
    if not ado_reviewer:
        _LOGGER.debug("Could not extract user info from reviewer for PR %s", pr.pull_request_id)
        return

    # Find matching Asana user (with caching)
    reviewer_key = f"{ado_reviewer.display_name}:{ado_reviewer.email}"
    if user_lookup_cache is not None and reviewer_key in user_lookup_cache:
        asana_matched_user = user_lookup_cache[reviewer_key]
    else:
        asana_matched_user = matching_user(asana_users, ado_reviewer)
        if user_lookup_cache is not None:
            user_lookup_cache[reviewer_key] = asana_matched_user
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

    # Check if this PR-reviewer combination already exists
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
    """
    Create a new Asana task for a PR reviewer.
    """
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

    # Check if there's already an Asana task with matching title
    asana_task = get_asana_task_by_name(asana_project_tasks, pr_item.asana_title)

    if asana_task is None:
        # Create new Asana task
        _LOGGER.debug("Creating new Asana task for PR %s reviewer", pr.pull_request_id)

        # Log if the task will be created as completed due to approval
        if pr_item.review_status in _REVIEWER_APPROVED_STATES:
            _LOGGER.info(
                "Reviewer %s already approved PR %s, task will be created as completed",
                pr_item.reviewer_name,
                pr.pull_request_id,
            )

        if app.asana_tag_gid is not None:
            create_asana_pr_task(app, asana_project, pr_item, app.asana_tag_gid)
    else:
        # Link existing task
        _LOGGER.debug("Linking existing Asana task for PR %s reviewer", pr.pull_request_id)
        pr_item.asana_gid = asana_task["gid"]
        pr_item.asana_updated = asana_task.get("modified_at")
        pr_item.updated_date = iso8601_utc(datetime.now())
        pr_item.save(app)
        # Update the task to ensure it has the correct status and assignee
        if app.asana_tag_gid is not None:
            update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)


def update_existing_pr_reviewer_task(
    app: App,
    pr,
    _repository,
    reviewer,
    existing_match: PullRequestItem,
    asana_matched_user: dict,
    asana_project: str,
) -> None:
    """
    Update an existing Asana task for a PR reviewer.
    """
    # Ensure reviewer name is set first (for backwards compatibility with existing items)
    reviewer_name_updated = False
    if not existing_match.reviewer_name:
        existing_match.reviewer_name = asana_matched_user["name"]
        existing_match.save(app)  # Save the updated reviewer name
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

    # Update PR item with latest data
    title_changed = existing_match.title != pr.title
    review_status_changed = existing_match.review_status != extract_reviewer_vote(reviewer)

    if title_changed:
        _LOGGER.info("PR title changed from '%s' to '%s'", existing_match.title, pr.title)

        # Validate that the PR ID hasn't been mixed up before updating
        if existing_match.ado_pr_id != pr.pull_request_id:
            _LOGGER.error(
                "Critical data corruption detected: PR item has ID %s but PR object has ID %s. "
                "This would create a title/ID mismatch. Skipping update to prevent corruption.",
                existing_match.ado_pr_id,
                pr.pull_request_id,
            )
            return

    if review_status_changed:
        old_status = existing_match.review_status or "noVote"
        new_status = extract_reviewer_vote(reviewer)
        _LOGGER.info(
            "PR %s reviewer %s vote changed from '%s' to '%s'",
            pr.pull_request_id,
            existing_match.reviewer_name or existing_match.reviewer_gid,
            old_status,
            new_status,
        )

        # Check if this change means the task should be completed or reopened
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

    existing_match.title = pr.title
    existing_match.status = pr.status
    existing_match.updated_date = iso8601_utc(datetime.now())
    existing_match.review_status = extract_reviewer_vote(reviewer)
    existing_match.asana_updated = asana_task["modified_at"]

    if app.asana_tag_gid is not None:
        update_asana_pr_task(app, existing_match, app.asana_tag_gid, asana_project)


def create_asana_pr_task(app: App, asana_project: str, pr_item: PullRequestItem, tag: str) -> None:
    """
    Create an Asana task for a pull request reviewer.
    """

    # Determine if task should be completed based on review status
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

    tasks_api_instance = asana.TasksApi(app.asana_client)

    # Find the custom field ID for 'link'
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
        # Update PR item with created task info
        pr_item.asana_gid = result["gid"]
        pr_item.asana_updated = result["modified_at"]
        pr_item.updated_date = iso8601_utc(datetime.now())

        # Set processing state based on initial task completion
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
    """
    Update an Asana task for a pull request reviewer.
    """

    # Determine if task should be completed
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

    tasks_api_instance = asana.TasksApi(app.asana_client)

    # Find the custom field ID for 'link'
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
        # Update the asana task item.
        result = tasks_api_instance.update_task(body, pr_item.asana_gid, opts={})
        pr_item.asana_updated = result["modified_at"]
        pr_item.updated_date = iso8601_utc(datetime.now())

        # Update processing state based on task completion
        if is_completed:
            pr_item.processing_state = "closed"
            _LOGGER.debug("Setting PR %d processing_state to 'closed' (task completed)", pr_item.ado_pr_id)
        else:
            # Ensure it's marked as open if task was reopened
            pr_item.processing_state = "open"
            _LOGGER.debug("Setting PR %d processing_state to 'open' (task reopened)", pr_item.ado_pr_id)

        pr_item.save(app)

        # Add the tag to the updated item if it does not already have it assigned.
        add_tag_to_pr_task(app, pr_item, tag)

        # Add closure comment if task was closed due to PR state change
        if is_completed:
            add_closure_comment_to_pr_task(app, pr_item)
    except ApiException as exception:
        _LOGGER.error("Exception when calling TasksApi->update_task: %s\n", exception)


def add_tag_to_pr_task(app: App, pr_item: PullRequestItem, tag: str) -> None:
    """
    Adds a tag to a pull request task if it is not already assigned.
    """

    # Get current tags for the task
    api_instance = asana.TagsApi(app.asana_client)
    try:
        # Get a task's tags
        api_response = api_instance.get_tags_for_task(pr_item.asana_gid, opts={})
        task_tags_gids = [t["gid"] for t in api_response]

        if tag not in task_tags_gids:
            # Add the tag to the task.
            _LOGGER.debug("adding tag to PR task '%s'", pr_item.asana_title)
            tasks_api_instance = asana.TasksApi(app.asana_client)
            body = {"data": {"tag": tag}}
            tasks_api_instance.add_tag_for_task(body, pr_item.asana_gid)
    except ApiException as exception:
        _LOGGER.error("Exception when adding tag to PR task: %s\n", exception)


def add_closure_comment_to_pr_task(app: App, pr_item: PullRequestItem) -> None:
    """
    Add a comment to a pull request task explaining why it was closed due to PR state change.
    """

    if not pr_item.asana_gid:
        return

    # Determine closure reason based on PR status
    closure_reasons = {
        "completed": "Pull request has been completed and merged",
        "abandoned": "Pull request has been abandoned",
        "draft": "Pull request has been moved to draft status",
        "reviewer_removed": "You have been removed as a reviewer from this pull request",
    }

    closure_reason = closure_reasons.get(pr_item.status, f"Pull request status changed to {pr_item.status}")

    # Only add comment if task was closed due to PR state change (not reviewer approval)
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


def process_closed_pull_requests(  # noqa: C901
    app: App, _asana_users: List[dict], asana_project: str, processed_pr_ids: set[int] | None = None, repository=None
) -> None:
    """
    Process pull requests that are no longer active but still have tasks in the database.

    Args:
        app: The App instance
        _asana_users: List of Asana users (unused in current implementation)
        asana_project: Asana project identifier
        processed_pr_ids: Set of PR IDs that were already processed in first pass
        repository: Repository object to filter PR tasks and make API calls (if provided)

    Note: Complexity justified by necessary error handling and cleanup logic.
    """
    if app.pr_matches is None:
        raise ValueError("app.pr_matches is None")

    if processed_pr_ids is None:
        processed_pr_ids = set()

    # Filter PR tasks by repository if specified
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

        # Log which PR tasks were found for this repository
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
        # Remove doc_id before creating PullRequestItem
        clean_pr_task_data = {k: v for k, v in pr_task_data.items() if k != "doc_id"}
        pr_item = PullRequestItem(**clean_pr_task_data)

        _LOGGER.debug("Second pass examining PR %d", pr_item.ado_pr_id)

        # Skip PRs that were already processed in first pass (active PRs)
        if pr_item.ado_pr_id in processed_pr_ids:
            _LOGGER.debug("Second pass skipping PR %d (already processed as active)", pr_item.ado_pr_id)
            skipped_active_count += 1
            continue

        # Skip processing if data consistency validation fails
        if not pr_item.validate_data_consistency():
            _LOGGER.warning(
                "Skipping PR item with inconsistent data: PR ID %s, URL %s, title '%s'",
                pr_item.ado_pr_id,
                pr_item.url,
                pr_item.title,
            )
            continue

        # Skip PRs that are already closed and have completed Asana tasks to avoid redundant API calls
        if _should_skip_closed_pr(pr_item):
            _LOGGER.info(
                "Skipping PR %d (status='%s', Asana task already completed) - avoiding redundant API call",
                pr_item.ado_pr_id,
                pr_item.status,
            )
            skipped_closed_count += 1
            continue

        # Try to get the current PR from ADO to check its status
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

            # Azure DevOps Python client signature: get_pull_request_by_id(pull_request_id, project=None)
            # PR IDs are globally unique, so we can retrieve by ID alone
            pr = app.ado_git_client.get_pull_request_by_id(pr_item.ado_pr_id)

            _LOGGER.debug("Second pass: Successfully retrieved PR %d with status '%s'", pr_item.ado_pr_id, pr.status)

            # Fetch reviewers to get current vote status
            try:
                reviewers = app.ado_git_client.get_pull_request_reviewers(repository.id, pr_item.ado_pr_id)
                # Find the reviewer matching this pr_item's reviewer_gid
                for reviewer in reviewers:
                    # Match reviewer to the pr_item's assigned reviewer
                    ado_reviewer = create_ado_user_from_reviewer(reviewer)
                    if ado_reviewer:
                        # Use matching_user to check if this is the same person
                        asana_matched = matching_user(_asana_users, ado_reviewer)
                        if asana_matched and asana_matched.get("gid") == pr_item.reviewer_gid:
                            # Update review_status with current vote
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
                # PR is still active, skip
                _LOGGER.debug("Skipping PR %d (status '%s' not in closed states)", pr_item.ado_pr_id, pr.status)
                continue

            # PR is closed/completed, update the Asana task accordingly
            _LOGGER.info("Processing closed PR %s with status '%s'", pr_item.ado_pr_id, pr.status if pr else "not found")
            processed_count += 1

            if pr_item.asana_gid:
                asana_task = _get_cached_asana_task(app, pr_item.asana_gid)
                # Update PR item status for database record
                pr_item.status = pr.status if pr else "completed"
                pr_item.updated_date = iso8601_utc(datetime.now())

                if asana_task and not asana_task.get("completed", False):
                    # Task is not completed yet, update it in Asana
                    if app.asana_tag_gid is not None:
                        update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)
                else:
                    # Task already completed, just update database record
                    pr_item.save(app)
                    _LOGGER.debug(
                        "Second pass: PR %d task already completed, updated database record with final review_status='%s'",
                        pr_item.ado_pr_id,
                        pr_item.review_status or "none",
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught  # pylint: disable=broad-exception-caught
            # Check if it's a permission or not found error
            error_msg = str(e)
            _LOGGER.debug("Exception getting PR %d from ADO: %s", pr_item.ado_pr_id, e)
            if "does not exist" in error_msg or "permission" in error_msg or "invalid literal for int()" in error_msg:
                _LOGGER.warning(
                    "PR %d cannot be retrieved from ADO (does not exist or no permission). "
                    "Closing associated Asana task. Error: %s",
                    pr_item.ado_pr_id,
                    error_msg,
                )
                # If we can't retrieve the PR (deleted or no access), close the task
                if pr_item.asana_gid:
                    asana_task = _get_cached_asana_task(app, pr_item.asana_gid)
                    if asana_task and not asana_task.get("completed", False):
                        # Close the Asana task - PR no longer accessible
                        pr_item.status = "abandoned"  # Use abandoned status for closure
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


def create_ado_user_from_reviewer(reviewer) -> Any:
    """
    Convert an ADO reviewer object to a user object similar to work item assigned users.
    """
    try:
        # ADO reviewer structure may vary, extract display name and email
        # Try different possible attribute names
        display_name = (
            getattr(reviewer, "display_name", None)
            or getattr(reviewer, "displayName", None)
            or getattr(reviewer, "name", None)
        )
        email = (
            getattr(reviewer, "unique_name", None) or getattr(reviewer, "uniqueName", None) or getattr(reviewer, "email", None)
        )

        # Sometimes the reviewer might have a nested user object
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

        # Create a user object similar to ADOAssignedUser from sync.py
        return ADOAssignedUser(display_name, email)

    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.error("Failed to extract user info from reviewer: %s", e)
        return None

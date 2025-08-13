"""This module contains functions for synchronizing pull requests between Azure DevOps and Asana."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

try:
    from azure.devops.v7_0.git.models import GitPullRequestSearchCriteria
except ImportError:
    # Fallback if git models are not available
    GitPullRequestSearchCriteria = None

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App
from .asana import get_asana_task
from .pull_request_item import PullRequestItem
from .utils import extract_reviewer_vote

# This module uses the logger and tracer instances _LOGGER and _TRACER for logging and tracing, respectively.
_LOGGER, _TRACER = setup_logging_and_tracing(__name__)

# PR status mapping - determines when to close Asana tasks
_PR_CLOSED_STATES = {"completed", "abandoned"}
# ADO reviewer vote values that should close the Asana task
_REVIEWER_APPROVED_STATES = {"approved", "approvedWithSuggestions"}


def sync_pull_requests(
    app: App, ado_project, asana_workspace_id: str, asana_project: str
) -> None:
    """
    Synchronizes pull requests from Azure DevOps to Asana.

    Creates separate Asana tasks for each reviewer of each pull request.
    """
    with _TRACER.start_as_current_span("sync_pull_requests") as span:
        span.add_event("Start PR sync")

        _LOGGER.info("Starting pull request sync for project %s", ado_project.name)

        # Get all Asana users for user matching
        from .sync import get_asana_users

        asana_users = get_asana_users(app, asana_workspace_id)

        # Get all Asana tasks in this project
        from .sync import get_asana_project_tasks

        asana_project_tasks = get_asana_project_tasks(app, asana_project)

        # Get all repositories in the ADO project
        if app.ado_git_client is None:
            raise ValueError("app.ado_git_client is None")
        try:
            repositories = app.ado_git_client.get_repositories(ado_project.id)
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg or "permission" in error_msg:
                _LOGGER.info(
                    "Skipping PR sync for project %s due to access restrictions",
                    ado_project.name,
                )
                return
            _LOGGER.error(
                "Failed to get repositories for project %s: %s", ado_project.name, e
            )
            return

        # Process pull requests for each repository
        for repo in repositories:
            _LOGGER.info("Processing repository %s", repo.name)
            try:
                process_repository_pull_requests(
                    app, repo, asana_users, asana_project_tasks, asana_project
                )
            except Exception as e:
                error_msg = str(e)
                if "does not exist" in error_msg or "permission" in error_msg:
                    _LOGGER.debug(
                        "Skipping repository %s due to access restrictions: %s",
                        repo.name,
                        e,
                    )
                else:
                    _LOGGER.error("Failed to process repository %s: %s", repo.name, e)

        # Process existing PR matches that may no longer be active
        process_closed_pull_requests(app, asana_users, asana_project)

        _LOGGER.info("Completed pull request sync for project %s", ado_project.name)


def process_repository_pull_requests(
    app: App,
    repository,
    asana_users: List[dict],
    asana_project_tasks: List[dict],
    asana_project: str,
) -> None:
    """
    Process pull requests for a specific repository.
    """
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
        pull_requests = app.ado_git_client.get_pull_requests(
            repository.id, search_criteria
        )
    except Exception as e:
        _LOGGER.error(
            "Failed to get pull requests for repository %s: %s", repository.name, e
        )
        return

    for pr in pull_requests:
        process_pull_request(
            app, pr, repository, asana_users, asana_project_tasks, asana_project
        )


def process_pull_request(  # noqa: C901
    app: App,
    pr,
    repository,
    asana_users: List[dict],
    asana_project_tasks: List[dict],
    asana_project: str,
) -> None:
    """
    Process a single pull request, creating reviewer tasks.

    Note: Complexity justified by necessary error handling and business logic.
    """
    _LOGGER.info("Processing PR %s: %s", pr.pull_request_id, pr.title)

    if app.ado_git_client is None:
        raise ValueError("app.ado_git_client is None")
    try:
        # Get reviewers for this pull request
        reviewers = app.ado_git_client.get_pull_request_reviewers(
            repository.id, pr.pull_request_id
        )
    except Exception as e:
        _LOGGER.error("Failed to get reviewers for PR %s: %s", pr.pull_request_id, e)
        return

    if not reviewers:
        _LOGGER.debug("No reviewers found for PR %s", pr.pull_request_id)
        # Handle case where all reviewers have been removed
        handle_removed_reviewers(
            app, pr, set(), asana_project
        )  # Empty set means no current reviewers
        return

    # Process each reviewer (deduplicate by email to avoid processing the same reviewer multiple times)
    processed_reviewers = set()
    current_reviewer_gids = set()

    for reviewer in reviewers:
        # Try to get a unique identifier for the reviewer
        reviewer_id = None
        if hasattr(reviewer, "user") and reviewer.user:
            reviewer_id = getattr(reviewer.user, "unique_name", None) or getattr(
                reviewer.user, "uniqueName", None
            )
        else:
            reviewer_id = getattr(reviewer, "unique_name", None) or getattr(
                reviewer, "uniqueName", None
            )

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
            from .sync import matching_user

            asana_matched_user = matching_user(asana_users, ado_reviewer)
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
        )

    # Handle removed reviewers - close tasks for reviewers no longer on the PR
    handle_removed_reviewers(app, pr, current_reviewer_gids, asana_project)


def handle_removed_reviewers(
    app: App, pr, current_reviewer_gids: set, asana_project: str
) -> None:
    """
    Handle reviewers that have been removed from the PR by closing their Asana tasks.
    """
    # Find all existing PR tasks for this PR
    if app.pr_matches is None:
        raise ValueError("app.pr_matches is None")

    def query_func(record):
        return record.get("ado_pr_id") == pr.pull_request_id
    existing_pr_tasks = app.pr_matches.search(query_func)

    for task_data in existing_pr_tasks:
        # Remove doc_id before creating PullRequestItem
        clean_task_data = {k: v for k, v in task_data.items() if k != 'doc_id'}
        pr_item = PullRequestItem(**clean_task_data)

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
                except Exception as e:
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
) -> None:
    """
    Process a single reviewer for a pull request.
    """
    # Convert ADO reviewer to user format similar to work items
    ado_reviewer = create_ado_user_from_reviewer(reviewer)
    if not ado_reviewer:
        _LOGGER.debug(
            "Could not extract user info from reviewer for PR %s", pr.pull_request_id
        )
        return

    # Find matching Asana user
    from .sync import matching_user

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

    # Check if this PR-reviewer combination already exists
    existing_match = PullRequestItem.search(
        app, ado_pr_id=pr.pull_request_id, reviewer_gid=asana_matched_user["gid"]
    )

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
    _LOGGER.info(
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
    from .sync import get_asana_task_by_name

    asana_task = get_asana_task_by_name(asana_project_tasks, pr_item.asana_title)

    if asana_task is None:
        # Create new Asana task
        _LOGGER.info("Creating new Asana task for PR %s reviewer", pr.pull_request_id)

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
        _LOGGER.info(
            "Linking existing Asana task for PR %s reviewer", pr.pull_request_id
        )
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
        _LOGGER.info(
            "Updated reviewer name for PR task: %s", existing_match.asana_title
        )

    if existing_match.is_current(app, pr, reviewer) and not reviewer_name_updated:
        _LOGGER.info(
            "PR reviewer task is already up to date: %s", existing_match.asana_title
        )
        return

    _LOGGER.info("Updating PR reviewer task: %s", existing_match.asana_title)

    asana_task = get_asana_task(app, existing_match.asana_gid) if existing_match.asana_gid else None
    if asana_task is None:
        _LOGGER.error("No Asana task found with gid: %s", existing_match.asana_gid)
        return

    # Update PR item with latest data
    title_changed = existing_match.title != pr.title
    review_status_changed = existing_match.review_status != extract_reviewer_vote(
        reviewer
    )

    if title_changed:
        _LOGGER.info(
            "PR title changed from '%s' to '%s'", existing_match.title, pr.title
        )

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
        elif (
            old_status in _REVIEWER_APPROVED_STATES
            and new_status not in _REVIEWER_APPROVED_STATES
        ):
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


def create_asana_pr_task(
    app: App, asana_project: str, pr_item: PullRequestItem, tag: str
) -> None:
    """
    Create an Asana task for a pull request reviewer.
    """
    import asana
    from asana.rest import ApiException

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
    from .sync import find_custom_field_by_name

    link_custom_field = find_custom_field_by_name(app, asana_project, "Link")
    link_custom_field_id = (
        link_custom_field.get("custom_field", {}).get("gid")
        if link_custom_field
        else None
    )

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
        body["data"]["custom_fields"] = {link_custom_field_id: pr_item.url}

    try:
        result = tasks_api_instance.create_task(body, opts={})
        # Update PR item with created task info
        pr_item.asana_gid = result["gid"]
        pr_item.asana_updated = result["modified_at"]
        pr_item.updated_date = iso8601_utc(datetime.now())
        pr_item.save(app)
    except ApiException as exception:
        _LOGGER.error("Exception when calling TasksApi->create_task: %s\n", exception)


def update_asana_pr_task(
    app: App, pr_item: PullRequestItem, tag: str, asana_project_gid: str
) -> None:
    """
    Update an Asana task for a pull request reviewer.
    """
    import asana
    from asana.rest import ApiException

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
    from .sync import find_custom_field_by_name

    link_custom_field = find_custom_field_by_name(app, asana_project_gid, "Link")
    link_custom_field_id = (
        link_custom_field.get("custom_field", {}).get("gid")
        if link_custom_field
        else None
    )

    body = {
        "data": {
            "name": pr_item.asana_title,
            "html_notes": f"<body>{pr_item.asana_notes_link}</body>",
            "assignee": pr_item.reviewer_gid,
            "completed": is_completed,
        }
    }

    if link_custom_field_id:
        body["data"]["custom_fields"] = {link_custom_field_id: pr_item.url}

    try:
        # Update the asana task item.
        result = tasks_api_instance.update_task(body, pr_item.asana_gid, opts={})
        pr_item.asana_updated = result["modified_at"]
        pr_item.updated_date = iso8601_utc(datetime.now())
        pr_item.save(app)

        # Add the tag to the updated item if it does not already have it assigned.
        add_tag_to_pr_task(app, pr_item, tag)
    except ApiException as exception:
        _LOGGER.error("Exception when calling TasksApi->update_task: %s\n", exception)


def add_tag_to_pr_task(app: App, pr_item: PullRequestItem, tag: str) -> None:
    """
    Adds a tag to a pull request task if it is not already assigned.
    """
    import asana
    from asana.rest import ApiException

    # Get current tags for the task
    api_instance = asana.TagsApi(app.asana_client)
    try:
        # Get a task's tags
        api_response = api_instance.get_tags_for_task(pr_item.asana_gid, opts={})
        task_tags_gids = [t["gid"] for t in api_response]

        if tag not in task_tags_gids:
            # Add the tag to the task.
            _LOGGER.info("adding tag to PR task '%s'", pr_item.asana_title)
            tasks_api_instance = asana.TasksApi(app.asana_client)
            body = {"data": {"tag": tag}}
            tasks_api_instance.add_tag_for_task(body, pr_item.asana_gid)
    except ApiException as exception:
        _LOGGER.error("Exception when adding tag to PR task: %s\n", exception)


def process_closed_pull_requests(  # noqa: C901
    app: App, _asana_users: List[dict], asana_project: str
) -> None:
    """
    Process pull requests that are no longer active but still have tasks in the database.

    Note: Complexity justified by necessary error handling and cleanup logic.
    """
    if app.pr_matches is None:
        raise ValueError("app.pr_matches is None")
    all_pr_tasks = app.pr_matches.all()

    for pr_task_data in all_pr_tasks:
        # Remove doc_id before creating PullRequestItem
        clean_pr_task_data = {k: v for k, v in pr_task_data.items() if k != 'doc_id'}
        pr_item = PullRequestItem(**clean_pr_task_data)

        try:
            # Try to get the current PR from ADO
            if app.ado_git_client is None:
                raise ValueError("app.ado_git_client is None")
            repository_id = pr_item.ado_repository_id
            pr = app.ado_git_client.get_pull_request_by_id(
                pr_item.ado_pr_id, repository_id
            )

            if pr and pr.status not in _PR_CLOSED_STATES:
                # PR is still active, skip
                continue

            # PR is closed/completed, update the Asana task accordingly
            _LOGGER.info("Processing closed PR %s", pr_item.ado_pr_id)

            if pr_item.asana_gid:
                asana_task = get_asana_task(app, pr_item.asana_gid)
                if asana_task and not asana_task.get("completed", False):
                    # Close the Asana task
                    pr_item.status = pr.status if pr else "completed"
                    pr_item.updated_date = iso8601_utc(datetime.now())
                    if app.asana_tag_gid is not None:
                        update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)

        except Exception as e:
            # Check if it's a permission/project not found error
            error_msg = str(e)
            if "does not exist" in error_msg or "permission" in error_msg:
                _LOGGER.debug(
                    "Skipping closed PR %s due to project access: %s",
                    pr_item.ado_pr_id,
                    e,
                )
                # The project may have been deleted or access revoked, skip silently
                continue
            else:
                _LOGGER.warning(
                    "Failed to process closed PR %s: %s", pr_item.ado_pr_id, e
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
            getattr(reviewer, "unique_name", None)
            or getattr(reviewer, "uniqueName", None)
            or getattr(reviewer, "email", None)
        )

        # Sometimes the reviewer might have a nested user object
        if hasattr(reviewer, "user") and reviewer.user:
            user_obj = reviewer.user
            display_name = (
                display_name
                or getattr(user_obj, "display_name", None)
                or getattr(user_obj, "displayName", None)
            )
            email = (
                email
                or getattr(user_obj, "unique_name", None)
                or getattr(user_obj, "uniqueName", None)
            )

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
        from .sync import ADOAssignedUser

        return ADOAssignedUser(display_name, email)

    except Exception as e:
        _LOGGER.error("Failed to extract user info from reviewer: %s", e)
        return None

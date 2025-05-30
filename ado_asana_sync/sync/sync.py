from __future__ import annotations

import concurrent.futures
import json
import os
from dataclasses import dataclass
from typing import Tuple, Any
from datetime import datetime, timezone, timedelta
from time import sleep

import asana  # type: ignore
from asana.rest import ApiException  # type: ignore
from azure.devops.v7_0.work.models import TeamContext  # type: ignore
from azure.devops.v7_0.work_item_tracking.models import WorkItem  # type: ignore

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing
from ado_asana_sync.utils.utils import safe_get

from .app import App
from .asana import get_asana_task
from .task_item import TaskItem

# This module uses the logger and tracer instances _LOGGER and _TRACER for logging and tracing, respectively.
_LOGGER, _TRACER = setup_logging_and_tracing(__name__)
# _SYNC_THRESHOLD defines the number of days to continue syncing closed tasks, after this many days they will be removed from
# the sync DB.
_SYNC_THRESHOLD = os.environ.get("SYNC_THRESHOLD", 30)
# _CLOSED_STATES defines a list of states that will be considered as completed. If the ADO state matches one of these values
# it will cause the linked Asana task to be closed.
_CLOSED_STATES = set(
    state.strip()
    for state in os.environ.get("CLOSED_STATES", "Closed,Removed,Done").split(",")
)
# _THREAD_COUNT contains the max number of project threads to execute concurrently.
_THREAD_COUNT = max(1, int(os.environ.get("THREAD_COUNT", 8)))

# ADO field constants
ADO_STATE = "System.State"
ADO_TITLE = "System.Title"
ADO_WORK_ITEM_TYPE = "System.WorkItemType"

# Cache for custom fields
CUSTOM_FIELDS_CACHE = {}
CUSTOM_FIELDS_AVAILABLE = True
LAST_CACHE_REFRESH = datetime.now(timezone.utc)
CACHE_VALIDITY_DURATION = timedelta(hours=24)


def start_sync(app: App) -> None:
    _LOGGER.info("Defined closed states: %s", sorted(list(_CLOSED_STATES)))
    try:
        app.asana_tag_gid = create_tag_if_not_existing(
            app,
            get_asana_workspace(app, app.asana_workspace_name),
            app.asana_tag_name,
        )
    except Exception as exception:
        _LOGGER.error("Failed to create or get Asana tag: %s", exception)
        return
    while True:
        with _TRACER.start_as_current_span("start_sync") as span:
            span.add_event("Start sync run")
            # Check if the cache is valid
            global CUSTOM_FIELDS_CACHE, LAST_CACHE_REFRESH
            now = datetime.now(timezone.utc)
            if (
                CUSTOM_FIELDS_AVAILABLE
                and now - LAST_CACHE_REFRESH >= CACHE_VALIDITY_DURATION
            ):
                CUSTOM_FIELDS_CACHE.clear()
                LAST_CACHE_REFRESH = now
                _LOGGER.info("Custom field cache cleared")

            projects = read_projects()
            # Use the lower of the _THREAD_COUNT and the length of projects.
            optimal_thread_count = min(len(projects), _THREAD_COUNT)
            _LOGGER.info(
                "Syncing %s projects using %s threads",
                len(projects),
                optimal_thread_count,
            )
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=optimal_thread_count
            ) as executor:
                try:
                    executor.map(sync_project, [app] * len(projects), projects)
                except Exception as exception:
                    _LOGGER.error("Error in sync_project thread: %s", exception)

            _LOGGER.info(
                "Sync process complete, sleeping for %s seconds", app.sleep_time
            )

        sleep(app.sleep_time)


def read_projects() -> list:
    """
    Read projects from JSON file and return as a list.
    """
    with _TRACER.start_as_current_span("read_projects"):
        # Initialize an empty list to store the projects
        projects = []

        # Open the JSON file and load the data
        with open(
            os.path.join(os.path.dirname(__package__), "data", "projects.json"),
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        # Iterate over each project in the data and append it to the projects list
        for project in data:
            projects.append(
                {
                    "adoProjectName": project["adoProjectName"],
                    "adoTeamName": project["adoTeamName"],
                    "asanaProjectName": project["asanaProjectName"],
                }
            )

        # Return the list of projects
        return projects


def create_tag_if_not_existing(app: App, workspace: str, tag: str) -> str | None:
    """
    Create a tag for a given workspace if it does not already exist.
    """
    with _TRACER.start_as_current_span("create_tag_if_not_existing"):
        # Check if the tag_gid is stored in the config table
        tag_config = app.config.get(doc_id=1)
        tag_gid = tag_config.get("tag_gid") if tag_config else None

        if tag_gid:
            _LOGGER.info("tag_gid found in database for '%s'", tag)
            return tag_gid

        # If tag_gid does not exist in the config, proceed to get or create the tag
        existing_tag = get_tag_by_name(app, workspace, tag)
        if existing_tag is not None:
            # Store the tag_gid in the config table
            with app.db_lock:
                app.config.upsert({"tag_gid": existing_tag["gid"]}, {"doc_id": 1})
            return existing_tag["gid"]
        api_instance = asana.TagsApi(app.asana_client)
        body = {"data": {"name": tag}}
        try:
            # Create a tag
            _LOGGER.info("tag '%s' not found, creating it", tag)
            api_response = api_instance.create_tag_for_workspace(body, workspace, {})
            # Store the new tag_gid in the config table
            with app.db_lock:
                app.config.upsert({"tag_gid": api_response["gid"]}, {"doc_id": 1})
            return api_response["gid"]
        except ApiException as exception:
            _LOGGER.error(
                "Exception when calling TagsApi->create_tag_for_workspace: %s\n",
                exception,
            )
            return None


def get_tag_by_name(app: App, workspace: str, tag: str) -> dict | None:
    """
    Retrieves a tag by its name from a given workspace.
    """
    with _TRACER.start_as_current_span("get_tag_by_name"):
        api_instance = asana.TagsApi(app.asana_client)
        try:
            # Get all tags in the workspace.
            _LOGGER.info("get workspace tag '%s'", tag)
            opts = {"workspace": workspace}
            api_response = api_instance.get_tags(opts)

            # Iterate through the tags to find the desired tag.
            tags_by_name = {t["name"]: t for t in api_response}
            return tags_by_name.get(tag)
        except ApiException as exception:
            _LOGGER.error("Exception when calling TagsApi->get_tags: %s\n", exception)
            return None


def get_asana_task_tags(app: App, task: TaskItem) -> list[dict]:
    """
    Retrieves the tags assigned to a given Asana task.
    """
    with _TRACER.start_as_current_span("get_asana_task_tags"):
        api_instance = asana.TagsApi(app.asana_client)

        try:
            # Get a task's tags
            api_response = api_instance.get_tags_for_task(task.asana_gid, opts={})
            return list(api_response)
        except ApiException as exception:
            _LOGGER.error(
                "Exception when calling TagsApi->get_tags_for_task: %s\n", exception
            )
            return []


def tag_asana_item(app: App, task: TaskItem, tag: str) -> None:
    """
    Adds a tag to a given item if it is not already assigned.
    """
    api_instance = asana.TasksApi(app.asana_client)
    task_tags = get_asana_task_tags(app, task)
    task_tags_gids = [t["gid"] for t in task_tags]
    if tag not in task_tags_gids:
        # Add the tag to the task.
        try:
            _LOGGER.info(
                "adding tag '%s' to task '%s'", app.asana_tag_name, task.asana_title
            )
            body = {"data": {"tag": tag}}
            api_instance.add_tag_for_task(body, task.asana_gid)
            return None
        except ApiException as exception:
            _LOGGER.error(
                "Exception when calling TasksApi->add_tag_for_task: %s\n", exception
            )
    return None


def sync_project(app: App, project):
    """
    Synchronizes a project by mapping ADO work items to Asana tasks.
    """
    # Log the item being synced.
    _LOGGER.info(
        "syncing from %s/%s -> %s/%s",
        project["adoProjectName"],
        project["adoTeamName"],
        app.asana_workspace_name,
        project["asanaProjectName"],
    )

    # Get project IDs
    try:
        ado_project, ado_team, asana_workspace_id, asana_project = get_project_ids(
            app, project
        )
    except Exception as e:
        _LOGGER.error("Error getting project IDs: %s", e)
        return

    # Get all Asana users in the workspace, this will enable user matching.
    asana_users = get_asana_users(app, asana_workspace_id)

    # Get all Asana Tasks in this project.
    _LOGGER.info(
        "Getting all Asana tasks for project %s [%s]",
        project["adoProjectName"],
        asana_project,
    )
    asana_project_tasks = get_asana_project_tasks(app, asana_project)

    # Get the backlog items for the ADO project and team.
    ado_items = app.ado_work_client.get_backlog_level_work_items(
        TeamContext(team_id=ado_team.id, project_id=ado_project.id),
        "Microsoft.RequirementCategory",
    )

    # Process backlog items
    process_backlog_items(
        app, ado_items, asana_users, asana_project_tasks, asana_project
    )

    # Process any existing matched items that are no longer returned in the backlog (closed or removed).
    all_tasks = app.matches.all()
    processed_item_ids = set(item.target.id for item in ado_items.work_items)
    process_closed_items(app, all_tasks, processed_item_ids, asana_users, asana_project)


def get_project_ids(app: App, project) -> Tuple[Any, Any, str, str | None]:
    """
    Get the necessary project IDs for syncing.
    """
    try:
        # Get the ADO project by name.
        ado_project = app.ado_core_client.get_project(project["adoProjectName"])
    except NameError as exception:
        _LOGGER.error(
            "ADO project %s not found: %s", project["adoProjectName"], exception
        )
        raise exception

    try:
        # Get the ADO team by name within the ADO project.
        ado_team = app.ado_core_client.get_team(
            project["adoProjectName"], project["adoTeamName"]
        )
    except NameError as exception:
        _LOGGER.error(
            "ADO team %s not found in project %s: %s",
            project["adoTeamName"],
            project["adoProjectName"],
            exception,
        )
        raise exception

    try:
        # Get the Asana workspace ID by name.
        asana_workspace_id = get_asana_workspace(app, app.asana_workspace_name)
    except NameError as exception:
        _LOGGER.error(
            "Asana workspace %s not found: %s", app.asana_workspace_name, exception
        )
        raise exception

    # Get the Asana project by name within the Asana workspace.
    try:
        asana_project = get_asana_project(
            app, asana_workspace_id, project["asanaProjectName"]
        )
    except NameError as exception:
        _LOGGER.error(
            "Asana project %s not found in workspace %s: %s",
            project["asanaProjectName"],
            app.asana_workspace_name,
            exception,
        )
        raise exception

    return ado_project, ado_team, asana_workspace_id, asana_project


def process_backlog_items(
    app, ado_items, asana_users, asana_project_tasks, asana_project
):
    """
    Processes the backlog items from ADO.
    """
    for wi in ado_items.work_items:
        # Get the work item from the ID
        ado_task = app.ado_wit_client.get_work_item(wi.target.id)
        process_backlog_item(
            app, ado_task, asana_users, asana_project_tasks, asana_project
        )


def process_backlog_item(
    app, ado_task, asana_users, asana_project_tasks, asana_project
):
    """
    Processes a single backlog item.
    """
    existing_match = TaskItem.search(app, ado_id=ado_task.id)
    ado_assigned = get_task_user(ado_task)

    if ado_assigned is None and existing_match is None:
        _LOGGER.debug(
            "%s:skipping item as it is not assigned",
            ado_task.fields[ADO_TITLE],
        )
        return

    asana_matched_user = matching_user(asana_users, ado_assigned)
    if asana_matched_user is None and existing_match is None:
        return

    if existing_match is None:
        create_new_task_mapping(
            app, ado_task, asana_matched_user, asana_project_tasks, asana_project
        )
    else:
        update_existing_task(
            app, ado_task, existing_match, asana_matched_user, asana_project
        )


def create_new_task_mapping(
    app, ado_task, asana_matched_user, asana_project_tasks, asana_project
):
    """
    Creates a new task mapping between ADO and Asana.
    """
    _LOGGER.info("%s:unmapped task", ado_task.fields[ADO_TITLE])
    current_utc_time = iso8601_utc(datetime.now(timezone.utc))
    existing_match = TaskItem(
        ado_id=ado_task.id,
        ado_rev=ado_task.rev,
        title=ado_task.fields[ADO_TITLE],
        item_type=ado_task.fields[ADO_WORK_ITEM_TYPE],
        state=ado_task.fields[ADO_STATE],
        created_date=current_utc_time,
        updated_date=current_utc_time,
        url=safe_get(ado_task, "_links", "additional_properties", "html", "href"),
        assigned_to=(
            asana_matched_user.get("gid", None)
            if asana_matched_user is not None
            else None
        ),
    )
    # Check if there is a matching asana task with a matching title.
    asana_task = get_asana_task_by_name(asana_project_tasks, existing_match.asana_title)
    if asana_task is None:
        # The Asana task does not exist, create it and map the tasks.
        _LOGGER.info(
            "%s:no matching asana task exists, creating new task",
            ado_task.fields[ADO_TITLE],
        )
        create_asana_task(
            app,
            asana_project,
            existing_match,
            app.asana_tag_gid,
        )
    else:
        # The Asana task exists, map the tasks in the db.
        _LOGGER.info("%s:dating task", ado_task.fields[ADO_TITLE])
        existing_match.asana_gid = asana_task["gid"]
        update_asana_task(
            app,
            existing_match,
            app.asana_tag_gid,
            asana_project,
        )


def update_existing_task(
    app, ado_task, existing_match, asana_matched_user, asana_project
):
    """
    Updates an existing Asana task based on ADO changes.
    """
    if existing_match.is_current(app):
        _LOGGER.info("%s:task is already up to date", existing_match.asana_title)
        return

    _LOGGER.info("%s:task has been updated, updating task", existing_match.asana_title)
    asana_task = get_asana_task(app, existing_match.asana_gid)
    if asana_task is None:
        _LOGGER.error("No Asana task found with gid: %s", existing_match.asana_gid)
        return
    existing_match.ado_rev = ado_task.rev
    existing_match.title = ado_task.fields[ADO_TITLE]
    existing_match.item_type = ado_task.fields[ADO_WORK_ITEM_TYPE]
    existing_match.state = ado_task.fields[ADO_STATE]
    existing_match.updated_date = iso8601_utc(datetime.now())
    existing_match.url = safe_get(
        ado_task, "_links", "additional_properties", "html", "href"
    )
    existing_match.assigned_to = (
        asana_matched_user.get("gid", None) if asana_matched_user is not None else None
    )
    existing_match.asana_updated = asana_task["modified_at"]
    update_asana_task(
        app,
        existing_match,
        app.asana_tag_gid,
        asana_project,
    )


def process_closed_items(
    app, all_tasks, processed_item_ids, asana_users, asana_project
):
    """
    Processes items that are closed or removed from the backlog.
    """
    for wi in all_tasks:
        if wi["ado_id"] not in processed_item_ids:
            _LOGGER.info("Processing closed item %s", wi["ado_id"])
            if is_item_older_than_threshold(wi):
                _LOGGER.info("%s:Task is older than %s days, removing mapping", wi["ado_id"], _SYNC_THRESHOLD)
                remove_mapping(app, wi)
                continue

            existing_match = get_existing_match(app, wi)
            if existing_match is None:
                continue

            try:
                ado_task = app.ado_wit_client.get_work_item(existing_match.ado_id)
            except Exception as e:
                _LOGGER.warning("Failed to fetch work item %s: %s", existing_match.ado_id, e)
                continue
            if existing_match.is_current(app):
                _LOGGER.info(
                    "%s:Task is up to date",
                    existing_match.asana_title,
                )
                continue

            _LOGGER.info(
                "%s:Task has been updated, updating task",
                existing_match.asana_title,
            )
            update_task_if_needed(
                app, ado_task, existing_match, asana_users, asana_project
            )


def is_item_older_than_threshold(wi):
    """
    Determines if a work item is older than a specified threshold.
    """
    return (
        datetime.now(timezone.utc) - datetime.fromisoformat(wi["updated_date"])
    ).days > _SYNC_THRESHOLD


def remove_mapping(app, wi):
    """
    Removes the mapping of a work item (wi) from the application's database if it has not been updated within a specified
    threshold.
    """
    _LOGGER.info(
        "%s: %s:Task has not been updated in %s days, removing mapping",
        wi["item_type"],
        wi["title"],
        _SYNC_THRESHOLD,
    )
    with app.db_lock:
        app.matches.remove(doc_ids=[wi.doc_id])


def get_existing_match(app, wi):
    """
    Searches for an existing match of a work item in the database.
    """
    existing_match = TaskItem.search(app, ado_id=wi["ado_id"])
    if existing_match is None:
        _LOGGER.warning(
            "Task with ADO ID %s not found in database",
            wi["ado_id"],
        )
    return existing_match


def update_task_if_needed(app, ado_task, existing_match, asana_users, asana_project):
    """
    Updates an Asana task if needed based on the provided Azure DevOps (ADO) task.
    """
    asana_task = get_asana_task(app, existing_match.asana_gid)
    ado_assigned = get_task_user(ado_task)
    asana_matched_user = matching_user(asana_users, ado_assigned)
    if asana_task is None:
        _LOGGER.error("No Asana task found with gid: %s", existing_match.asana_gid)
        return
    existing_match.ado_rev = ado_task.rev
    existing_match.title = ado_task.fields[ADO_TITLE]
    existing_match.item_type = ado_task.fields[ADO_WORK_ITEM_TYPE]
    existing_match.state = ado_task.fields[ADO_STATE]
    existing_match.updated_date = iso8601_utc(datetime.now())
    existing_match.url = safe_get(
        ado_task, "_links", "additional_properties", "html", "href"
    )
    existing_match.assigned_to = (
        asana_matched_user.get("gid", None) if asana_matched_user is not None else None
    )
    existing_match.asana_updated = asana_task["modified_at"]
    update_asana_task(
        app,
        existing_match,
        app.asana_tag_gid,
        asana_project,
    )


@dataclass
class ADOAssignedUser:
    """
    Class to store the details of the assigned user in ADO.
    """

    display_name: str
    email: str


def get_task_user(task: WorkItem) -> ADOAssignedUser | None:
    """
    Return the email and display name of the user assigned to the Azure DevOps work item.
    If no user is assigned, then return None.
    """
    assigned_to = task.fields.get("System.AssignedTo", None)
    if assigned_to is not None:
        display_name = assigned_to.get("displayName", None)
        email = assigned_to.get("uniqueName", None)
        if display_name is None or email is None:
            return None
        return ADOAssignedUser(display_name, email)
    return None


def matching_user(user_list: list[dict], ado_user: ADOAssignedUser) -> dict | None:
    """
    Check if a given email exists in a list of user dicts.
    """
    if ado_user is None:
        return None
    for user in user_list:
        if (
            user["email"].lower() == ado_user.email.lower()
            or user["name"].lower() == ado_user.display_name.lower()
        ):
            return user
    return None


def get_asana_workspace(app: App, name: str) -> str:
    """
    Returns the workspace gid for the named Asana workspace.
    """
    api_instance = asana.WorkspacesApi(app.asana_client)
    try:
        # Get all workspaces
        api_response = api_instance.get_workspaces(opts={})
        for w in api_response:
            if w["name"] == name:
                return w["gid"]
        raise NameError(f"No workspace found with name '{name}'")
    except ApiException as exception:
        _LOGGER.error(
            "Exception when calling WorkspacesApi->get_workspaces: %s\n", exception
        )
        raise ValueError(f"Call to Asana API failed: {exception}") from exception


def get_asana_project(app: App, workspace_gid, name) -> str | None:
    """
    Returns the project gid for the named Asana project.
    """
    api_instance = asana.ProjectsApi(app.asana_client)
    try:
        # Get all projects
        opts = {"workspace": workspace_gid, "archived": False, "opt_fields": "name"}
        api_response = api_instance.get_projects(opts)
        for p in api_response:
            if p["name"] == name:
                return p["gid"]
        raise NameError(f"No project found with name '{name}'")
    except ApiException as exception:
        _LOGGER.error(
            "Exception when calling ProjectsApi->get_projects: %s\n", exception
        )
        return None


def get_asana_task_by_name(task_list: list[dict], task_name: str) -> dict | None:
    """
    Returns the entire task dict for the named Asana task from the given list of tasks.
    """

    for t in task_list:
        if t["name"] == task_name:
            return t
    return None


def get_asana_project_tasks(app: App, asana_project) -> list[dict]:
    """
    Returns a list of task dicts for the given Asana project.
    """
    api_instance = asana.TasksApi(app.asana_client)
    all_tasks = []
    offset = None
    try:
        # Get all tasks in the project.
        while True:
            api_params = {
                "project": asana_project,
                "limit": app.asana_page_size,
                "opt_fields": (
                    "assignee_section,due_at,name,completed_at,tags,dependents,"
                    "projects,completed,permalink_url,parent,assignee,"
                    "assignee_status,num_subtasks,modified_at,workspace,due_on"
                ),
            }
            if offset:
                api_params["offset"] = offset

            api_response = api_instance.get_tasks(api_params)

            # Append tasks to the all_tasks list.
            all_tasks.extend(api_response)

            # Check for continuation token in the response.
            offset = None
            for response in api_response:
                offset = getattr(response.get("next_page"), "offset", None)
            if not offset:
                break
        return all_tasks
    except ApiException as exception:
        _LOGGER.error(
            "Exception in get_asana_project_tasks when calling TasksApi->get_tasks: %s",
            exception,
        )
        return []


def create_asana_task(app: App, asana_project: str, task: TaskItem, tag: str) -> None:
    """
    Create an Asana task in the specified project.
    """
    tasks_api_instance = asana.TasksApi(app.asana_client)
    # Find the custom field ID for 'link'
    link_custom_field = find_custom_field_by_name(app, asana_project, "Link")
    link_custom_field_id = (
        link_custom_field.get("custom_field", {}).get("gid")
        if link_custom_field
        else None
    )

    body = {
        "data": {
            "name": task.asana_title,
            "html_notes": f"<body>{task.asana_notes_link}</body>",
            "projects": [asana_project],
            "assignee": task.assigned_to,
            "tags": [tag],
            "completed": task.state in _CLOSED_STATES,
        },
    }

    if link_custom_field_id:
        body["data"]["custom_fields"] = {link_custom_field_id: task.url}

    try:
        result = tasks_api_instance.create_task(body, opts={})
        # add the match to the db.
        task.asana_gid = result["gid"]
        task.asana_updated = result["modified_at"]
        task.updated_date = iso8601_utc(datetime.now())
        task.save(app)
    except ApiException as exception:
        _LOGGER.error("Exception when calling TasksApi->create_task: %s\n", exception)


def update_asana_task(
    app: App, task: TaskItem, tag: str, asana_project_gid: str
) -> None:
    """
    Update an Asana task with the provided task details.
    """
    tasks_api_instance = asana.TasksApi(app.asana_client)

    # Find the custom field ID for 'link'
    link_custom_field = find_custom_field_by_name(app, asana_project_gid, "Link")
    link_custom_field_id = (
        link_custom_field.get("custom_field", {}).get("gid")
        if link_custom_field
        else None
    )

    body = {
        "data": {
            "name": task.asana_title,
            "html_notes": f"<body>{task.asana_notes_link}</body>",
            "assignee": task.assigned_to,
            "completed": task.state in _CLOSED_STATES,
        }
    }

    if link_custom_field_id:
        body["data"]["custom_fields"] = {link_custom_field_id: task.url}

    try:
        # Update the asana task item.
        result = tasks_api_instance.update_task(body, task.asana_gid, opts={})
        task.asana_updated = result["modified_at"]
        task.updated_date = iso8601_utc(datetime.now())
        task.save(app)
        # Add the tag to the updated item if it does not already have it assigned.
        tag_asana_item(app, task, tag)
    except ApiException as exception:
        _LOGGER.error("Exception when calling TasksApi->update_task: %s\n", exception)


def get_asana_project_custom_fields(app: App, project_gid: str) -> list[dict]:
    """
    Retrieves all custom fields for a provided Asana project.
    """
    global CUSTOM_FIELDS_AVAILABLE
    if CUSTOM_FIELDS_AVAILABLE is False:
        return []

    if project_gid in CUSTOM_FIELDS_CACHE:
        return CUSTOM_FIELDS_CACHE[project_gid]

    api_instance = asana.CustomFieldSettingsApi(app.asana_client)
    try:
        _LOGGER.info("Fetching custom fields for project %s", project_gid)
        opts = {"limit": 100}
        custom_fields = []
        while True:
            api_response = api_instance.get_custom_field_settings_for_project(
                project_gid, opts
            )
            custom_fields.extend(api_response)
            if "offset" in api_response:
                opts["offset"] = api_response["offset"]
            else:
                break
        CUSTOM_FIELDS_CACHE[project_gid] = custom_fields
        return custom_fields
    except ApiException as exception:
        if exception.status == 402:
            _LOGGER.info(
                "Custom Field Settings are not available for free users, disabling custom fields."
            )
            CUSTOM_FIELDS_AVAILABLE = False
            return []
        else:
            _LOGGER.error(
                "Exception when calling CustomFieldSettingsApi->get_custom_field_settings_for_project: %s\n",
                exception,
            )
            return []
    except Exception as e:
        _LOGGER.error("An unexpected error occurred: %s", str(e))
        return []


def find_custom_field_by_name(
    app: App, project_gid: str, field_name: str
) -> dict | None:
    """
    Finds a custom field in the project by the custom field's name.
    """
    custom_fields = get_asana_project_custom_fields(app, project_gid)
    for field in custom_fields:
        if field.get("custom_field", {}).get("name") == field_name:
            return field
    return None


def get_asana_users(app: App, asana_workspace_gid: str) -> list[dict]:
    """
    Retrieves a list of Asana users in a specific workspace.
    """
    users_api_instance = asana.UsersApi(app.asana_client)
    opts = {
        "workspace": asana_workspace_gid,
        "opt_fields": "email,name",
    }

    try:
        api_response = users_api_instance.get_users(opts)
        return list(api_response)
    except ApiException as exception:
        _LOGGER.error("Exception when calling UsersApi->get_users: %s\n", exception)
        return []
    except Exception as e:
        _LOGGER.error("An unexpected error occurred: %s", str(e))
        return []

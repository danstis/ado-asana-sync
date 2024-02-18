from __future__ import annotations

import concurrent.futures
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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

    Returns:
        projects (list): List of projects with specific attributes.
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

    Args:
        app (App): The App object containing the Asana client.
        workspace (str): The ID of the workspace to create the tag in.
        tag (str): The name of the tag to create.

    Returns:
        str: The GUID of the tag.

    Raises:
        ApiException: If an error occurs while making the API call.
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
            app.config.upsert({"tag_gid": existing_tag["gid"]}, {"doc_id": 1})
            return existing_tag["gid"]
        api_instance = asana.TagsApi(app.asana_client)
        body = {"data": {"name": tag}}
        try:
            # Create a tag
            _LOGGER.info("tag '%s' not found, creating it", tag)
            api_response = api_instance.create_tag_for_workspace(body, workspace, {})
            # Store the new tag_gid in the config table
            app.config.upsert({"tag_gid": api_response["gid"]}, {"doc_id": 1})
            return api_response["gid"]
        except ApiException as exception:
            _LOGGER.error(
                "Exception when calling TagsApi->create_tag_for_workspace: %s\n",
                exception,
            )
            return None


def get_tag_by_name(app: App, workspace: str, tag: str) -> dict | None:
    """Retrieves a tag by its name from a given workspace.

    Args:
        app (App): The Asana client instance.
        workspace (str): The ID of the workspace.
        tag (str): The name of the tag to retrieve.

    Returns:
        dict | None: The tags GUID if found, or None if not found.
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

    Args:
        app (App): The Asana client instance.
        task (TaskItem): The Asana task to retrieve the tags for.

    Returns:
        list[dict]: A list of dictionaries representing the tags assigned to the task.
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

    Args:
        app (App): The Asana client instance.
        task (TaskItem): The Asana task to add the tag to.
        tag (str): The name of the tag to add.

    Returns:
        None
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

    Args:
        app (App): The main application object.
        project (dict): A dictionary containing information about the project to sync. It should have the following keys:
            - adoProjectName (str): The name of the ADO project.
            - adoTeamName (str): The name of the ADO team within the ADO project.
            - asanaProjectName (str): The name of the Asana project within the Asana workspace.

    Returns:
        None
    """
    # Log the item being synced.
    _LOGGER.info(
        "syncing from %s/%s -> %s/%s",
        project["adoProjectName"],
        project["adoTeamName"],
        app.asana_workspace_name,
        project["asanaProjectName"],
    )

    try:
        # Get the ADO project by name.
        ado_project = app.ado_core_client.get_project(project["adoProjectName"])
    except NameError as exception:
        _LOGGER.error(
            "ADO project %s not found: %s", project["adoProjectName"], exception
        )
        return

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
        return

    try:
        # Get the Asana workspace ID by name.
        asana_workspace_id = get_asana_workspace(app, app.asana_workspace_name)
    except NameError as exception:
        _LOGGER.error(
            "Asana workspace %s not found: %s", app.asana_workspace_name, exception
        )
        return

    # Get all Asana users in the workspace, this will enable user matching.
    asana_users = get_asana_users(app, asana_workspace_id)

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
        return

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

    # Loop through each backlog item
    for wi in ado_items.work_items:
        # Get the work item from the ID
        ado_task = app.ado_wit_client.get_work_item(wi.target.id)

        # Skip this item if is not assigned, or the assignee does not match an Asana user,
        # unless it has previously been matched.
        existing_match = TaskItem.search(app, ado_id=ado_task.id)
        ado_assigned = get_task_user(ado_task)
        if ado_assigned is None and existing_match is None:
            _LOGGER.debug(
                "%s:skipping item as it is not assigned",
                ado_task.fields[ADO_TITLE],
            )
            continue
        asana_matched_user = matching_user(asana_users, ado_assigned)
        if asana_matched_user is None and existing_match is None:
            continue

        if existing_match is None:
            _LOGGER.info("%s:unmapped task", ado_task.fields[ADO_TITLE])
            existing_match = TaskItem(
                ado_id=ado_task.id,
                ado_rev=ado_task.rev,
                title=ado_task.fields[ADO_TITLE],
                item_type=ado_task.fields[ADO_WORK_ITEM_TYPE],
                state=ado_task.fields[ADO_STATE],
                created_date=iso8601_utc(datetime.utcnow()),
                updated_date=iso8601_utc(datetime.utcnow()),
                url=safe_get(
                    ado_task, "_links", "additional_properties", "html", "href"
                ),
                assigned_to=(
                    asana_matched_user.get("gid", None)
                    if asana_matched_user is not None
                    else None
                ),
            )
            # Check if there is a matching asana task with a matching title.
            asana_task = get_asana_task_by_name(
                asana_project_tasks, existing_match.asana_title
            )
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
                )  # type: ignore[arg-type]
                continue
            else:
                # The Asana task exists, map the tasks in the db.
                _LOGGER.info("%s:dating task", ado_task.fields[ADO_TITLE])
                existing_match.asana_gid = asana_task["gid"]
                update_asana_task(
                    app,
                    existing_match,
                    app.asana_tag_gid,
                )  # type: ignore[arg-type]
                continue

        # If already mapped, check if the item needs an update (ado rev is higher, or asana item is newer).
        if existing_match.is_current(app):
            _LOGGER.info("%s:task is already up to date", existing_match.asana_title)
            continue

        # Update the asana task, as it is not current.
        _LOGGER.info(
            "%s:task has been updated, updating task", existing_match.asana_title
        )
        asana_task = get_asana_task(app, existing_match.asana_gid)
        if asana_task is None:
            _LOGGER.error("No Asana task found with gid: %s", existing_match.asana_gid)
            continue
        existing_match.ado_rev = ado_task.rev
        existing_match.title = ado_task.fields[ADO_TITLE]
        existing_match.item_type = ado_task.fields[ADO_WORK_ITEM_TYPE]
        existing_match.state = ado_task.fields[ADO_STATE]
        existing_match.updated_date = iso8601_utc(datetime.now())
        existing_match.url = safe_get(
            ado_task, "_links", "additional_properties", "html", "href"
        )
        existing_match.assigned_to = (
            asana_matched_user.get("gid", None)
            if asana_matched_user is not None
            else None
        )
        existing_match.asana_updated = asana_task["modified_at"]
        update_asana_task(
            app,
            existing_match,
            app.asana_tag_gid,
        )

    # Process any existing matched items that are no longer returned in the backlog (closed or removed).
    all_tasks = app.matches.all()
    processed_item_ids = set(item.target.id for item in ado_items.work_items)
    for wi in all_tasks:
        if wi["ado_id"] not in processed_item_ids:
            _LOGGER.debug("Processing closed item %s", wi["ado_id"])
            # Check if this work item is older than the threshold. If so delete the mapping.
            if (
                datetime.now(timezone.utc) - datetime.fromisoformat(wi["updated_date"])
            ).days > _SYNC_THRESHOLD:
                _LOGGER.info(
                    "%s: %s:Task has not been updated in %s days, removing mapping",
                    wi["item_type"],
                    wi["title"],
                    _SYNC_THRESHOLD,
                )
                app.matches.remove(doc_ids=[wi.doc_id])
                continue

            # Get the work item details from ADO.
            existing_match = TaskItem.search(app, ado_id=wi["ado_id"])
            if existing_match is None:
                _LOGGER.warning(
                    "Task with ADO ID %s not found in database",
                    wi["ado_id"],
                )
                continue
            ado_task = app.ado_wit_client.get_work_item(existing_match.ado_id)

            # Check if the item is already up to date.
            if existing_match.is_current(app):
                _LOGGER.debug(
                    "%s:Task is up to date",
                    existing_match.asana_title,
                )
                continue
            # Update the asana task, as it is not current.
            asana_task = get_asana_task(app, existing_match.asana_gid)
            ado_assigned = get_task_user(ado_task)
            asana_matched_user = matching_user(asana_users, ado_assigned)
            if asana_task is None:
                _LOGGER.error(
                    "No Asana task found with gid: %s", existing_match.asana_gid
                )
                continue
            existing_match.ado_rev = ado_task.rev
            existing_match.title = ado_task.fields[ADO_TITLE]
            existing_match.item_type = ado_task.fields[ADO_WORK_ITEM_TYPE]
            existing_match.state = ado_task.fields[ADO_STATE]
            existing_match.updated_date = iso8601_utc(datetime.now())
            existing_match.url = safe_get(
                ado_task, "_links", "additional_properties", "html", "href"
            )
            existing_match.assigned_to = (
                asana_matched_user.get("gid", None)
                if asana_matched_user is not None
                else None
            )
            existing_match.asana_updated = asana_task["modified_at"]
            update_asana_task(
                app,
                existing_match,
                app.asana_tag_gid,
            )  # type: ignore[arg-type]


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

    Args:
        task (WorkItem): The Azure DevOps work item object.

    Returns:
        ADOAssignedUser: The details of the assigned user in ADO.
        None: If the task is not assigned.
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

    Args:
        user_list (list[dict]): A list of user dicts representing users.
        user (ADOAssignedUser): An ADO User representation, containing display_name and email.

    Returns:
        dict: The matching asana user.
        None: If no matching user is found.
    """
    if ado_user is None:
        return None
    for user in user_list:
        if user["email"] == ado_user.email or user["name"] == ado_user.display_name:
            return user
    return None


def get_asana_workspace(app: App, name: str) -> str:
    """
    Returns the workspace gid for the named Asana workspace.

    :param app: The application object.
    :type app: App
    :param name: The name of the workspace.
    :type name: str
    :return: Workspace gid.
    :rtype: str
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

    :param app: The application object.
    :type app: App
    :param workspace_gid: The workspace GID.
    :type workspace_gid: str
    :param name: The name of the project.
    :type name: str
    :return: Project gid if found, None otherwise.
    :rtype: str | None
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

    :param task_list: List of Asana tasks to search in.
    :type task_list: list[dict]
    :param task_name: The name of the Asana task.
    :type task_name: str
    :return: Task dict or None if no task is found.
    :rtype: dict or None
    """

    for t in task_list:
        if t["name"] == task_name:
            return t
    return None


def get_asana_project_tasks(app: App, asana_project) -> list[dict]:
    """
    Returns a list of task dicts for the given Asana project.

    Args:
        app (App): The application object.
        asana_project (str): The gid of the Asana project.

    Returns:
        list[dict]: A list of task dicts for the given project.
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

    Args:
        app (App): An instance of the 'App' class that provides the connection to Asana.
        asana_project (str): The name of the Asana project to create the task in.
        task (TaskItem): An instance of the 'TaskItem' class that contains the details of the task to be created.
        tag (str): The Asana tag details to assign to the task.

    Returns:
        None
    """
    tasks_api_instance = asana.TasksApi(app.asana_client)
    body = {
        "data": {
            "name": task.asana_title,
            "html_notes": f"<body>{task.asana_notes_link}</body>",
            "projects": [asana_project],
            "assignee": task.assigned_to,
            "tags": [tag],
            "state": task.state in _CLOSED_STATES,
        }
    }
    try:
        result = tasks_api_instance.create_task(body, opts={})
        # add the match to the db.
        task.asana_gid = result["gid"]
        task.asana_updated = result["modified_at"]
        task.updated_date = iso8601_utc(datetime.now())
        task.save(app)
    except ApiException as exception:
        _LOGGER.error("Exception when calling TasksApi->create_task: %s\n", exception)


def update_asana_task(app: App, task: TaskItem, tag: str) -> None:
    """
    Update an Asana task with the provided task details.

    Args:
        a (app): An instance of the app class that provides the connection to ADO and Asana.
        asana_task_id (str): The ID of the Asana task to be updated.
        task (work_item): An instance of the work_item class that contains the details of the task to be updated.
        tag (TagResponse): The Asana tag details to assign to the task.

    Returns:
        None: The function does not return any value. The Asana task is updated with the provided details.
    """
    tasks_api_instance = asana.TasksApi(app.asana_client)
    body = {
        "data": {
            "name": task.asana_title,
            "html_notes": f"<body>{task.asana_notes_link}</body>",
            "assignee": task.assigned_to,
            "completed": task.state in _CLOSED_STATES,
        }
    }

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


def get_asana_users(app: App, asana_workspace_gid: str) -> list[dict]:
    """
    Retrieves a list of Asana users in a specific workspace.

    Args:
        a (app): An instance of the `app` class that provides the Asana API client.
        asana_workspace_gid (str): The ID of the Asana workspace to retrieve users from.

    Returns:
        list: A list of user dicts representing the Asana users in the specified
        workspace.
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

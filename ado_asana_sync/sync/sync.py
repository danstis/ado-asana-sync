from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
import asana
from asana import UserResponse, TagResponse
from asana.rest import ApiException
from ado_asana_sync.sync.app import App
from azure.devops.v7_0.work_item_tracking.models import WorkItem
from azure.devops.v7_0.work.models import TeamContext
from tinydb import Query


class TaskItem:
    """
    Represents a task item in the synchronization process between Azure DevOps (ADO) and Asana.

    Each TaskItem object corresponds to a work item in ADO and a task in Asana. It contains information about the task such as its ID, revision number, title, type, URL, and the IDs of the corresponding Asana task and user.

    Attributes:
        ado_id (int): The ID of the task in ADO.
        ado_rev (int): The revision number of the task in ADO.
        title (str): The title of the task.
        item_type (str): The type of the task.
        url (str): The URL of the task in ADO.
        asana_gid (str): The ID of the corresponding task in Asana.
        asana_updated (str): The last updated time of the Asana task in ISO 8601 format.
        assigned_to (str): The ID of the user to whom the task is assigned in Asana.
        created_date (str): The creation date of the task in ISO 8601 format.
        updated_date (str): The last updated date of the task in ISO 8601 format.
    """

    def __init__(
        self,
        ado_id: int,
        ado_rev: int,
        title: str,
        item_type: str,
        url: str,
        asana_gid: str = None,
        asana_updated: str = None,
        assigned_to: str = None,
        created_date: str = None,
        updated_date: str = None,
    ) -> None:
        self.ado_id = ado_id
        self.ado_rev = ado_rev
        self.title = title
        self.item_type = item_type
        self.url = url
        self.asana_gid = asana_gid
        self.asana_updated = asana_updated
        self.assigned_to = assigned_to
        self.created_date = created_date
        self.updated_date = updated_date

    def __str__(self) -> str:
        """
        Return a string representation of the object.

        :return: The string representation of the object.
        :rtype: str
        """
        return self.asana_title

    @property
    def asana_title(self) -> str:
        """
        Generate the title of an Asana object.

        Returns:
            str: The formatted title of the Asana object.
        """
        return f"{self.item_type} {self.ado_id}: {self.title}"

    @property
    def asana_notes_link(self) -> str:
        """
        Generate the notes of an Asana object.

        Returns:
            str: The formatted notes of the Asana object.
        """
        return f'<a href="{self.url}">{self.item_type} {self.ado_id}</a>: {self.title}'

    @classmethod
    def find_by_ado_id(cls, a: App, ado_id: int) -> TaskItem | None:
        """
        Find and retrieve a TaskItem by its Azure DevOps (ADO) ID.

        Args:
            a (App): The App instance.
            ado_id (int): The ADO ID of the TaskItem to find.

        Returns:
            TaskItem: The TaskItem object with the matching ADO ID.
            None: If there is no matching item.
        """
        query = Query().ado_id == ado_id
        if a.matches.contains(query):
            item = a.matches.search(query)
            return cls(**item[0])
        else:
            return None

    def save(self, a: App) -> None:
        """
        Save the TaskItem to the database.

        Args:
            a (App): The App instance.

        Returns:
            None
        """
        task_data = {
            "ado_id": self.ado_id,
            "ado_rev": self.ado_rev,
            "title": self.title,
            "item_type": self.item_type,
            "url": self.url,
            "asana_gid": self.asana_gid,
            "asana_updated": self.asana_updated,
            "assigned_to": self.assigned_to,
            "created_date": self.created_date,
            "updated_date": self.updated_date,
        }
        query = Query().ado_id == task_data["ado_id"]
        if a.matches.contains(query):
            a.matches.update(task_data, query)
        else:
            a.matches.insert(task_data)

    def is_current(self, a: App) -> bool:
        """
        Check if the current TaskItem is up-to-date with its corresponding tasks in Azure DevOps (ADO) and Asana.

        This method retrieves the corresponding tasks in ADO and Asana using the stored IDs, and compares their revision number and last updated time with the stored values. If either the ADO task's revision number or the Asana task's last updated time is different from the stored values, the TaskItem is considered not current.

        Args:
            a (App): The App instance.

        Returns:
            bool: True if the TaskItem is current, False otherwise.
        """
        ado_task = a.ado_wit_client.get_work_item(self.ado_id)
        asana_task = get_asana_task(a, self.asana_gid)

        if not ado_task or not asana_task:
            return False

        if (
            ado_task.rev != self.ado_rev
            or iso8601_utc(asana_task.modified_at) != self.asana_updated
        ):
            return False

        return True


def safe_get(obj, *attrs_keys):
    """
    Safely retrieves nested attributes from an object.

    Args:
        obj: The object to retrieve attributes from.
        *attrs_keys: Variable number of attribute keys.

    Returns:
        The value of the nested attribute if found, else None.
    """
    for attr_key in attrs_keys:
        if isinstance(obj, dict):
            obj = obj.get(attr_key)
        else:
            obj = getattr(obj, attr_key, None)
        if obj is None:
            return None
    return obj


def get_tag_by_name(a: App, workspace: str, tag: str) -> TagResponse | None:
    """
    Retrieves a tag by its name from a given workspace.

    Args:
        a (App): The Asana client instance.
        workspace (str): The ID of the workspace.
        tag (str): The name of the tag to retrieve.

    Returns:
        TagResponse | None: The tag object if found, or None if not found.
    """
    api_instance = asana.TagsApi(a.asana_client)
    try:
        # Get all tags in the workspace
        logging.info("get workspace tag '%s'", tag)
        api_response = api_instance.get_tags(workspace=workspace)

        # Iterate through the tags to find the desired tag
        for t in api_response.data:
            if t.name == tag:
                return t
        return None
    except ApiException as e:
        logging.error("Exception when calling TagsApi->get_tags: %s\n", e)


def create_tag_if_not_existing(a: App, workspace: str, tag: str) -> TagResponse:
    """
    Create a tag for a given workspace if it does not already exist.

    Args:
        a (App): The App object containing the Asana client.
        workspace (str): The ID of the workspace to create the tag in.
        tag (str): The name of the tag to create.

    Returns:
        TagResponse: The response from the API call.

    Raises:
        ApiException: If an error occurs while making the API call.
    """
    existing_tag = get_tag_by_name(a, workspace, tag)
    if existing_tag is not None:
        return existing_tag
    api_instance = asana.TagsApi(a.asana_client)
    body = asana.TagsBody({"name": tag})
    try:
        # Create a tag
        logging.info("tag '%s' not found, creating it", tag)
        api_response = api_instance.create_tag_for_workspace(body, workspace)
        return api_response.data
    except ApiException as e:
        logging.error(
            "Exception when calling TagsApi->create_tag_for_workspace: %s\n", e
        )


def get_asana_task_tags(a: App, task: TaskItem) -> list[TagResponse]:
    """
    Retrieves the tag for a given Asana task.
    """
    api_instance = asana.TagsApi(a.asana_client)

    try:
        # Get a task's tags
        api_response = api_instance.get_tags_for_task(
            task.asana_gid,
        )
        return api_response.data
    except ApiException as e:
        logging.error("Exception when calling TagsApi->get_tags_for_task: %s\n", e)


def tag_asana_item(a: App, task: TaskItem, tag: TagResponse) -> None:
    """
    Adds a tag to a given item if it is not already assigned.
    """
    api_instance = asana.TasksApi(a.asana_client)
    task_tags = get_asana_task_tags(a, task)
    if tag not in task_tags:
        # Add the tag to the task.
        try:
            logging.info("adding tag '%s' to task '%s'", tag.name, task.asana_title)
            body = asana.TagsBody({"tag": tag.gid})
            api_instance.add_tag_for_task(body, task.asana_gid)
        except ApiException as e:
            logging.error("Exception when calling TasksApi->add_tag_for_task: %s\n", e)


def read_projects() -> list:
    """
    Read projects from JSON file and return as a list.

    Returns:
        projects (list): List of projects with specific attributes.
    """
    # Initialize an empty list to store the projects
    projects = []

    # Open the JSON file and load the data
    with open(os.path.join(os.path.dirname(__package__), "data", "projects.json")) as f:
        data = json.load(f)

    # Iterate over each project in the data and append it to the projects list
    for project in data:
        projects.append(
            {
                "adoProjectName": project["adoProjectName"],
                "adoTeamName": project["adoTeamName"],
                "asanaWorkspaceName": project["asanaWorkspaceName"],
                "asanaProjectName": project["asanaProjectName"],
            }
        )

    # Return the list of projects
    return projects


def sync_project(a: App, project):
    """
    Synchronizes a project by mapping ADO work items to Asana tasks.

    Args:
        a (App): The main application object.
        project (dict): A dictionary containing information about the project to sync. It should have the following keys:
            - adoProjectName (str): The name of the ADO project.
            - adoTeamName (str): The name of the ADO team within the ADO project.
            - asanaWorkspaceName (str): The name of the Asana workspace.
            - asanaProjectName (str): The name of the Asana project within the Asana workspace.

    Returns:
        None
    """
    # Log the item being synced
    logging.info(
        f'syncing from {project["adoProjectName"]}/{project["adoTeamName"]} -> {project["asanaWorkspaceName"]}/{project["asanaProjectName"]}'
    )

    # Get the ADO project by name
    ado_project = a.ado_core_client.get_project(project["adoProjectName"])

    # Get the ADO team by name within the ADO project
    ado_team = a.ado_core_client.get_team(
        project["adoProjectName"], project["adoTeamName"]
    )

    # Get the Asana workspace ID by name
    asana_workspace_id = get_asana_workspace(a, project["asanaWorkspaceName"])

    # Get all Asana users in the workspace, this will enable user matching.
    asana_users = get_asana_users(a, asana_workspace_id)

    # Ensure the sync tag exists.
    tag = create_tag_if_not_existing(a, asana_workspace_id, "synced")

    # Get the Asana project by name within the Asana workspace
    asana_project = get_asana_project(
        a, asana_workspace_id, project["asanaProjectName"]
    )

    # Get all Asana Tasks in this project.
    logging.info(
        "Getting all Asana tasks for project %s [%s]",
        project["adoProjectName"],
        asana_project,
    )
    asana_project_tasks = get_asana_project_tasks(a, asana_project)

    # Get the backlog items for the ADO project and team
    ado_items = a.ado_work_client.get_backlog_level_work_items(
        TeamContext(team_id=ado_team.id, project_id=ado_project.id),
        "Microsoft.RequirementCategory",
    )

    # Loop through each backlog item
    for wi in ado_items.work_items:
        # Get the work item from the ID
        ado_task = a.ado_wit_client.get_work_item(wi.target.id)

        # Skip this item if is not assigned, or the assignee does not match an Asana user.
        ado_assigned = get_task_user(ado_task)
        if ado_assigned is None:
            logging.debug(
                f"{ado_task.fields['System.Title']}:skipping item as it is not assigned"
            )
            continue
        asana_matched_user = matching_user(asana_users, ado_assigned)
        if asana_matched_user is None:
            continue

        # Check if this is an already mapped item.
        item = TaskItem.find_by_ado_id(a, ado_task.id)
        if item is None:
            logging.info(f"{ado_task.fields['System.Title']}:unmapped task")
            item = TaskItem(
                ado_id=ado_task.id,
                ado_rev=ado_task.rev,
                title=ado_task.fields["System.Title"],
                item_type=ado_task.fields["System.WorkItemType"],
                created_date=iso8601_utc(datetime.utcnow()),
                updated_date=iso8601_utc(datetime.utcnow()),
                url=safe_get(
                    ado_task, "_links", "additional_properties", "html", "href"
                ),
                assigned_to=asana_matched_user.gid,
            )
            # Check if there is a matching asana task with a matching title.
            asana_task = get_asana_task_by_name(asana_project_tasks, item.asana_title)
            if asana_task is None:
                # The Asana task does not exist, create it and map the tasks
                logging.info(
                    f"{ado_task.fields['System.Title']}:no matching asana task exists, creating new task"
                )
                create_asana_task(
                    a,
                    asana_project,
                    item,
                    tag,
                )
                continue
            else:
                # The Asana task exists, map the tasks in the db
                logging.info(
                    f"{ado_task.fields['System.Title']}:found a matching asana task by name, updating task"
                )
                if asana_task is not None:
                    item.asana_gid = asana_task.gid
                update_asana_task(
                    a,
                    item,
                    tag,
                )
                continue

        # If already mapped, check if the item needs an update (ado rev is higher, or asana item is newer).
        if item.is_current(a):
            logging.info(f"{item.asana_title}:task is already up to date")
            continue

        # Update the asana task, as it is not current.
        logging.info(f"{item.asana_title}:task has been updated, updating task")
        asana_task = get_asana_task(a, item.asana_gid)
        if asana_task is None:
            logging.error(f"No Asana task found with gid: {item.asana_gid}")
            continue
        item.ado_rev = ado_task.rev
        item.title = ado_task.fields["System.Title"]
        item.item_type = ado_task.fields["System.WorkItemType"]
        item.updated_date = iso8601_utc(datetime.now())
        item.url = safe_get(ado_task, "_links", "additional_properties", "html", "href")
        item.assigned_to = asana_matched_user.gid
        item.asana_updated = iso8601_utc(asana_task.modified_at)
        update_asana_task(
            a,
            item,
            tag,
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


def matching_user(
    user_list: list[UserResponse], ado_user: ADOAssignedUser
) -> UserResponse | None:
    """
    Check if a given email exists in a list of user objects.

    Args:
        user_list (list[UserResponse]): A list of UserResponse objects representing users.
        user (ADOAssignedUser): An ADO User representation, containing display_name and email.

    Returns:
        UserResponse: The matching asana user.
        None: If no matching user is found.
    """
    for user in user_list:
        if user.email == ado_user.email or user.name == ado_user.display_name:
            return user
    return None


def get_asana_workspace(a: App, name) -> str:
    """
    Returns the workspace gid for the named Asana workspace.

    :return: Workspace gid.
    :rtype: str
    """
    api_instance = asana.WorkspacesApi(a.asana_client)
    try:
        # Get all workspaces
        api_response = api_instance.get_workspaces()
        for w in api_response.data:
            if w.name == name:
                return w.gid
    except ApiException as e:
        logging.error("Exception when calling WorkspacesApi->get_workspaces: %s\n", e)


def get_asana_project(a: App, workspace_gid, name) -> str:
    """
    Returns the project gid for the named Asana project.

    :return: Project gid.
    :rtype: str
    """
    api_instance = asana.ProjectsApi(a.asana_client)
    try:
        # Get all projects
        api_response = api_instance.get_projects(
            workspace=workspace_gid, archived=False
        )
        for p in api_response.data:
            if p.name == name:
                return p.gid
    except ApiException as e:
        logging.error("Exception when calling ProjectsApi->get_projects: %s\n", e)


def get_asana_task_by_name(task_list: list[object], task_name: str) -> object:
    """
    Returns the entire task object for the named Asana task from the given list of tasks.

    :param task_list: List of Asana tasks to search in.
    :type task_list: list[object]
    :param task_name: The name of the Asana task.
    :type task_name: str
    :return: Task object or None if no task is found.
    :rtype: object or None
    """

    for t in task_list:
        if t.name == task_name:
            return t


def get_asana_project_tasks(a: App, asana_project) -> list[object]:
    """
    Returns a list of task objects for the given project.

    :param asana_project: The gid of the Asana project.
    :type asana_project: str
    :return: Task object or None if no task is found.
    :rtype: object or None
    """
    api_instance = asana.TasksApi(a.asana_client)
    opt_fields = [
        "assignee_section",
        "due_at",
        "name",
        "completed_at",
        "tags",
        "dependents",
        "projects",
        "completed",
        "permalink_url",
        "parent",
        "assignee",
        "assignee_status",
        "num_subtasks",
        "modified_at",
        "workspace",
        "due_on",
    ]
    all_tasks = []
    offset = None
    try:
        # Get all tasks in the project
        while True:
            api_params = {
                "project": asana_project,
                "limit": a.asana_page_size,
                "opt_fields": opt_fields,
            }
            if offset:
                api_params["offset"] = offset

            api_response = api_instance.get_tasks(**api_params)

            # Append tasks to the all_tasks list
            all_tasks.extend(api_response.data)

            # Check for continuation token in the response
            offset = getattr(api_response.next_page, "offset", None)
            # if api_response.next_page != None:
            #     offset = api_response.next_page.offset
            # else:
            #     offset = None
            if not offset:
                break

        return all_tasks
    except ApiException as e:
        logging.error(
            "Exception in get_asana_project_tasks when calling TasksApi->get_tasks: %s\n"
            % e
        )


def get_asana_task(a: App, task_gid) -> object | None:
    """
    Returns the entire task object for the Asana task with the given gid in the given project.

    :param asana_project: The gid of the Asana project.
    :type asana_project: str
    :param task_gid: The name of the Asana task.
    :type task_gid: str
    :return: Task object or None if no task is found.
    :rtype: object or None
    """
    api_instance = asana.TasksApi(a.asana_client)
    try:
        # Get all tasks in the project
        opt_fields = [
            "assignee_section",
            "due_at",
            "name",
            "completed_at",
            "tags",
            "dependents",
            "projects",
            "completed",
            "permalink_url",
            "parent",
            "assignee",
            "assignee_status",
            "num_subtasks",
            "modified_at",
            "workspace",
            "due_on",
        ]
        api_response = api_instance.get_task(
            task_gid,
            opt_fields=opt_fields,
        )
        return api_response.data
    except ApiException as e:
        logging.error("Exception when calling TasksApi->get_task: %s\n", e)


def create_asana_task(
    a: App, asana_project: "str", task: "TaskItem", tag: TagResponse
) -> None:
    """
    Create an Asana task in the specified project.

    Args:
        a (app): An instance of the 'app' class that provides the connection to ADO and Asana.
        asana_project (str): The name of the Asana project to create the task in.
        task (work_item): An instance of the 'work_item' class that contains the details of the task to be created.
        tag (TagResponse): The Asana tag details to assign to the task.

    Returns:
        None
    """
    tasks_api_instance = asana.TasksApi(a.asana_client)
    body = asana.TasksBody(
        {
            "name": task.asana_title,
            "html_notes": f"<body>{task.asana_notes_link}</body>",
            "projects": [asana_project],
            "assignee": task.assigned_to,
            "tag": [tag.gid],
        }
    )
    try:
        result = tasks_api_instance.create_task(body)
        # add the match to the db.
        task.asana_gid = result.data.gid
        task.asana_updated = iso8601_utc(result.data.modified_at)
        task.updated_date = iso8601_utc(datetime.now())
        task.save(a)
    except ApiException as e:
        logging.error("Exception when calling TasksApi->create_task: %s\n", e)


def iso8601_utc(dt: datetime) -> str:
    """
    Convert a given datetime object to a string representation in ISO 8601 format with UTC timezone.

    Args:
        dt (datetime): A datetime object representing a specific date and time.

    Returns:
        str: A string representing the given datetime object in ISO 8601 format with UTC timezone.
    """
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def update_asana_task(a: App, task: TaskItem, tag: TagResponse) -> None:
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
    tasks_api_instance = asana.TasksApi(a.asana_client)
    body = asana.TasksBody(
        {
            "name": task.asana_title,
            "html_notes": f"<body>{task.asana_notes_link}</body>",
            "assignee": task.assigned_to,
        }
    )

    try:
        # Update the asana task item.
        result = tasks_api_instance.update_task(body, task.asana_gid)
        task.asana_updated = iso8601_utc(result.data.modified_at)
        task.updated_date = iso8601_utc(datetime.now())
        task.save(a)
        # Add the tag to the updated item if it does not already have it assigned.
        tag_asana_item(a, task, tag)
    except ApiException as e:
        logging.error("Exception when calling TasksApi->update_task: %s\n", e)


def get_asana_users(a: App, asana_workspace_gid: str) -> list[UserResponse]:
    """
    Retrieves a list of Asana users in a specific workspace.

    Args:
        a (app): An instance of the `app` class that provides the Asana API client.
        asana_workspace_gid (str): The ID of the Asana workspace to retrieve users from.

    Returns:
        list(asana.UserResponse): A list of `asana.UserResponse` objects representing the Asana users in the specified workspace.
    """
    users_api_instance = asana.UsersApi(a.asana_client)
    opt_fields = [
        "email",
        "name",
    ]

    try:
        api_response = users_api_instance.get_users(
            workspace=asana_workspace_gid,
            opt_fields=opt_fields,
        )
        return api_response.data
    except ApiException as e:
        logging.error("Exception when calling UsersApi->get_users: %s\n", e)

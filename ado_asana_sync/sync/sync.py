import os
import json
import asana
from asana.rest import ApiException
from azure.devops.v7_0.work.models import TeamContext
from pprint import pprint
from ado_asana_sync.sync.app import app


def sync_project(a: app, project):
    # Log the item being synced
    print(
        f'syncing from {project["adoProjectName"]}/{project["adoTeamName"]} -> {project["asanaWorkspaceName"]}/{project["asanaProjectName"]}'
    )

    # Get the ADO project by name
    ado_project = a.ado_core_client.get_project(project["adoProjectName"])
    # pprint(ado_project)

    # Get the ADO team by name within the ADO project
    ado_team = a.ado_core_client.get_team(
        project["adoProjectName"], project["adoTeamName"]
    )
    # pprint(ado_team)

    # Get the Asana workspace ID by name
    asana_workspace_id = get_asana_workspace(a, project["asanaWorkspaceName"])
    # pprint(asana_workspace_id)

    # Get the Asana project by name within the Asana workspace
    asana_project = get_asana_project(
        a, asana_workspace_id, project["asanaProjectName"]
    )
    # pprint(asana_project)

    # Get the backlog items for the ADO project and team
    ado_items = a.ado_work_client.get_backlog_level_work_items(
        TeamContext(team_id=ado_team.id, project_id=ado_project.id),
        "Microsoft.RequirementCategory",
    )
    # pprint(ado_items)

    # Loop through each backlog item
    for wi in ado_items.work_items:
        # Get the work item from the ID
        ado_task = a.ado_wit_client.get_work_item(wi.target.id)
        current_work_item = work_item(
            ado_id=ado_task.id,
            title=ado_task.fields["System.Title"],
            description=ado_task.fields.get("System.Description"),
            status=ado_task.fields["System.State"],
            type=ado_task.fields["System.WorkItemType"],
            created_date=ado_task.fields["System.CreatedDate"],
            priority=ado_task.fields["Microsoft.VSTS.Common.Priority"],
            url=ado_task.url,
        )
        # Get the corresponding Asana task by name
        asana_task = get_asana_task(a, asana_project, current_work_item.asana_title())
        if asana_task == None:
            # The Asana task does not exist, create it
            print(f"creating task {current_work_item.asana_title()}")
            create_asana_task(
                a,
                asana_project,
                current_work_item,
            )
        else:
            # The Asana task exists, update it
            print(f"updating task {current_work_item.asana_title()}")
            update_asana_task(a, asana_task.gid, current_work_item)


def read_projects() -> list:
    """Read projects from JSON file and return as list."""
    projects = []

    with open(os.path.join(os.path.dirname(__package__), "data", "projects.json")) as f:
        data = json.load(f)

    for project in data:
        projects.append(
            {
                "adoProjectName": project["adoProjectName"],
                "adoTeamName": project["adoTeamName"],
                "asanaWorkspaceName": project["asanaWorkspaceName"],
                "asanaProjectName": project["asanaProjectName"],
            }
        )
        return projects


def get_asana_workspace(a: app, name) -> str:
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
        print("Exception when calling WorkspacesApi->get_workspaces: %s\n" % e)


def get_asana_project(a: app, workspace_gid, name) -> str:
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
        print("Exception when calling ProjectsApi->get_projects: %s\n" % e)


def get_asana_task(a: app, asana_project, task_name) -> object:
    """
    Returns the entire task object for the named Asana task in the given project.

    :param asana_project: The gid of the Asana project.
    :type asana_project: str
    :param task_name: The name of the Asana task.
    :type task_name: str
    :return: Task object or None if no task is found.
    :rtype: object or None
    """
    api_instance = asana.TasksApi(a.asana_client)
    try:
        # Get all tasks in the project
        api_response = api_instance.get_tasks(project=asana_project)
        for t in api_response.data:
            if t.name == task_name:
                return t
    except ApiException as e:
        print("Exception when calling TasksApi->get_tasks_in_project: %s\n" % e)


def create_asana_task(a: app, asana_project: "str", task: "work_item"):
    """
    Create an Asana task in the specified project.

    Args:
        asana_project (str): The name of the Asana project to create the task in.
        task (work_item): The work item object containing the details of the task.

    Returns:
        None

    Raises:
        ApiException: If an error occurs while creating the task.

    """
    tasks_api_instance = asana.TasksApi(a.asana_client)
    body = asana.TasksBody(
        {
            "name": task.asana_title(),
            "due_on": task.due_date,
            "html_notes": f"<body>{task.asana_notes_link()}</body>",
            "projects": [asana_project],
        }
    )
    try:
        api_response = tasks_api_instance.create_task(body)
        # pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->create_task: %s\n" % e)


def update_asana_task(a: app, asana_task_id: "str", task: "work_item"):
    tasks_api_instance = asana.TasksApi(a.asana_client)
    body = asana.TasksBody(
        {
            "name": task.asana_title(),
            "due_on": task.due_date,
            "html_notes": f"<body>{task.asana_notes_link()}</body>",
        }
    )

    try:
        api_response = tasks_api_instance.update_task(body, asana_task_id)
        # pprint(api_response)
    except ApiException as e:
        print("Exception when calling TasksApi->update_task: %s\n" % e)


# Models
class work_item:
    # https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/work-items/get-work-item?view=azure-devops-rest-7.1&tabs=HTTP#examples
    def __init__(
        self,
        ado_id,
        title,
        type,
        status,
        description,
        url=None,
        assigned_to=None,
        priority=None,
        due_date=None,
        created_date=None,
        updated_date=None,
    ) -> None:
        self.ado_id = ado_id
        self.title = title
        self.type = type
        self.status = status
        self.description = description
        self.url = url
        self.assigned_to = assigned_to
        self.priority = priority
        self.due_date = due_date
        self.created_date = created_date
        self.updated_date = updated_date

    def __str__(self) -> str:
        """
        Return a string representation of the object.

        :return: The string representation of the object.
        :rtype: str
        """
        return self.asana_title()

    def asana_title(self) -> str:
        """
        Generate the title of an Asana object.

        Returns:
            str: The formatted title of the Asana object.
        """
        return f"{self.type} {self.ado_id}: {self.title}"

    def asana_notes_link(self) -> str:
        """
        Generate the notes of an Asana object.

        Returns:
            str: The formatted notes of the Asana object.
        """
        return f'<a href="{self.url}">{self.type} {self.ado_id}</a>: {self.title}'
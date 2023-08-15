import json
import os
import asana
from asana.rest import ApiException
from azure.devops.connection import Connection
from azure.devops.v7_0.work.models import TeamContext
from msrest.authentication import BasicAuthentication

ADO_PAT = os.environ.get('ADO_PAT')
ADO_URL = os.environ.get('ADO_URL')
ASANA_TOKEN = os.environ.get('ASANA_TOKEN')

# connect ADO
ado_credentials = BasicAuthentication('', ADO_PAT)
ado_connection = Connection(base_url=ADO_URL, creds=ado_credentials)
ado_client = ado_connection.clients.get_core_client()
ado_work_client = ado_connection.clients.get_work_client()
# connect Asana
asana_config = asana.Configuration()
asana_config.access_token = ASANA_TOKEN
asana_client = asana.ApiClient(asana_config)

def main():
    p = read_projects()
    for i in p:
        sync_project(i)

def sync_project(project):
    # Log the item being synced
    print(f'syncing from {project["adoProjectName"]}/{project["adoTeamName"]} -> {project["asanaWorkspaceName"]}/{project["asanaProjectName"]}')

    # Get the ADO project by name
    ado_project = ado_client.get_project(project["adoProjectName"])
    # print(ado_project)

    # Get the ADO team by name within the ADO project
    ado_team = ado_client.get_team(project["adoProjectName"], project["adoTeamName"])
    # print(ado_team)

    # Get the Asana workspace ID by name
    asana_workspace_id = get_asana_workspace(project["asanaWorkspaceName"])
    # print(asana_workspace_id)

    # Get the Asana project by name within the Asana workspace
    asana_project = get_asana_project(asana_workspace_id, project["asanaProjectName"])
    # print(asana_project)

    # Get the backlog items for the ADO project and team
    ado_items = ado_work_client.get_backlog_level_work_items(TeamContext(team_id=ado_team.id, project_id=ado_project.id), "Microsoft.RequirementCategory")
    print(ado_items.work_items)

    # Loop through each backlog item
        # Get the corresponding Asana task by name
        asana_task = get_asana_task(asana_project, ado_items.work_items[0].name)
        # TODO: https://github.com/asana/python-asana
        # The Asana task does not exist, create it
        # The Asana task exists, update it



def read_projects() -> object:
    """
    Reads the contents of the 'projects.json' file and returns a list of projects.

    :return: Projects as an object.
    :rtype: object
    """
    with open('projects.json', 'r') as f:
        projects = json.load(f)
    return projects

def get_asana_workspace(name) -> str:
    """
    Returns the workspace gid for the named Asana workspace.

    :return: Workspace gid.
    :rtype: str
    """
    api_instance = asana.WorkspacesApi(asana_client)
    try:
        # Get all workspaces
        api_response = api_instance.get_workspaces()
        for w in api_response.data:
            if w.name == name:
                return w.gid
    except ApiException as e:
        print("Exception when calling WorkspacesApi->get_workspaces: %s\n" % e)

def get_asana_project(workspace_gid, name) -> str:
    """
    Returns the project gid for the named Asana project.

    :return: Project gid.
    :rtype: str
    """
    api_instance = asana.ProjectsApi(asana_client)
    try:
        # Get all projects
        api_response = api_instance.get_projects(workspace=workspace_gid, archived=False)
        for p in api_response.data:
            if p.name == name:
                return p.gid
    except ApiException as e:
        print("Exception when calling ProjectsApi->get_projects: %s\n" % e)

if __name__ == "__main__":
    main()
def get_asana_task(asana_project, task_name):
    """
    Returns the task gid for the named Asana task in the given project.

    :param asana_project: The gid of the Asana project.
    :type asana_project: str
    :param task_name: The name of the Asana task.
    :type task_name: str
    :return: Task gid or None if no task is found.
    :rtype: str or None
    """
    api_instance = asana.TasksApi(asana_client)
    try:
        # Get all tasks in the project
        api_response = api_instance.get_tasks_in_project(asana_project, completed=False)
        for t in api_response.data:
            if t.name == task_name:
                return t.gid
    except ApiException as e:
        print("Exception when calling TasksApi->get_tasks_in_project: %s\n" % e)

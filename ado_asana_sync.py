import json
import os
import asana
from asana.rest import ApiException
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication

ADO_PAT = os.environ.get('ADO_PAT')
ADO_URL = os.environ.get('ADO_URL')
ASANA_TOKEN = os.environ.get('ASANA_TOKEN')

# connect ADO
ado_credentials = BasicAuthentication('', ADO_PAT)
ado_connection = Connection(base_url=ADO_URL, creds=ado_credentials)
ado_client = ado_connection.clients.get_core_client()
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
    # print(ap)

    # Get the ADO team by name within the ADO project
    ado_team = ado_client.get_team(project["adoProjectName"], project["adoTeamName"])
    # print(at)

    # Get the Asana workspace ID by name
    asana_workspace_id = get_asana_workspace(project["asanaWorkspaceName"])
    # print(asana_workspace_id)

    # Get the Asana project by name within the Asana workspace
    asana_project = get_asana_project(asana_workspace_id, project["asanaProjectName"])
    # print(asana_project)

    # Get the backlog items for the ADO project and team
    # TODO: https://github.com/microsoft/azure-devops-python-samples/blob/main/src/samples/work_item_tracking.py

    # Loop through each backlog item
        # Get the corresponding Asana task by name
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

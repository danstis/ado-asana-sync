from ado_asana_sync.sync.sync import read_projects, sync_project

p = read_projects()
for i in p:
    sync_project(i)

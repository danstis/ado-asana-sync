import logging
from ado_asana_sync.sync.sync import read_projects, sync_project
from ado_asana_sync.sync.app import app

# Create an instance of the app configuration and connect to the services.
logging.basicConfig(level=logging.INFO)
app_config = app()
app_config.connect()

p = read_projects()
for i in p:
    sync_project(app_config, i)

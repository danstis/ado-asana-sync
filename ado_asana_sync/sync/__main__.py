import logging
from ado_asana_sync.sync.sync import read_projects, sync_project
from ado_asana_sync.sync.app import App

# Create an instance of the app configuration and connect to the services.
logging.basicConfig(level=logging.INFO)
app_config = App()
try:
    app_config.connect()
except Exception as e:
    logging.error("Failed to connect: %s", e)

p = read_projects()
for i in p:
    sync_project(app_config, i)

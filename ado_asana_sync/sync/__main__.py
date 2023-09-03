import logging
import os

from .app import App

# Create an instance of the app configuration and connect to the services.
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=log_level)
app = App()
app.start()

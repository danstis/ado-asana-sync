import logging
import os

from .app import App

# Create an instance of the app configuration and connect to the services.
from logging import getLevelName

log_level = os.environ.get("LOG_LEVEL", "INFO")
if not isinstance(getLevelName(log_level), int):
    log_level = "INFO"
logging.basicConfig(level=log_level)
app = App()
app.start()

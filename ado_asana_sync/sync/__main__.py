import logging
import os

from .app import App

# Create an instance of the app configuration and connect to the services.
from logging import getLevelName

log_level = os.environ.get("LOG_LEVEL", "INFO")
if not isinstance(getLevelName(log_level), int):
    raise ValueError(f"Invalid log level: {log_level}")
logging.basicConfig(level=log_level)
app = App()
app.start()

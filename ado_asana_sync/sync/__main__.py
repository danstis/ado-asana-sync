import logging
import os
from logging import getLevelName

from .app import App
from .sync import start_sync

# _LOGGER is the logging instance for this file.
_LOGGER = logging.getLogger(__name__)

log_level = os.environ.get("LOG_LEVEL", "INFO")
if not isinstance(getLevelName(log_level), int):
    raise ValueError(f"Invalid log level: {log_level}")

logging.basicConfig(level=log_level)

_LOGGER.debug("Configuring app")
app = App()
app.connect()

_LOGGER.debug("Starting main sync process")
start_sync(app)

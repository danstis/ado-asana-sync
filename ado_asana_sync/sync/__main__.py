"""
This module contains the main entry point for the application. It sets up the logging configuration, creates an instance of
the App class, and starts the main sync process.

Environment Variables:
    LOG_LEVEL: The log level to use. Defaults to INFO.
"""

import atexit
import logging
import os
import signal
import sys
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


def cleanup_handler(_signum=None, _frame=None):
    """Handle cleanup on shutdown."""
    _LOGGER.info("Shutting down application...")
    app.close()
    _LOGGER.info("Application shutdown complete")
    sys.exit(0)


# Register cleanup handlers
atexit.register(app.close)
signal.signal(signal.SIGINT, cleanup_handler)
signal.signal(signal.SIGTERM, cleanup_handler)

try:
    _LOGGER.debug("Starting main sync process")
    start_sync(app)
except KeyboardInterrupt:
    _LOGGER.info("Received keyboard interrupt")
    cleanup_handler()
except Exception as e:
    _LOGGER.error("Unexpected error in main sync process: %s", e)
    cleanup_handler()
    raise

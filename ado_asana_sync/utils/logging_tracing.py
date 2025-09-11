"""
This package provides logging and tracing functionality for the application.
It uses the OpenTelemetry library for tracing and the logging module for logging.

The `setup_logging_and_tracing` function initializes the logger and tracer for the specified module.
It takes in the module name as an argument and returns the logger and tracer objects.

Example usage:
    from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

    # This module uses the logger and tracer instances _LOGGER and _TRACER for logging and tracing, respectively.
    _LOGGER, _TRACER = setup_logging_and_tracing(__name__)
"""

import logging
import os

from opentelemetry import trace

LOGLEVEL = os.environ.get("LOGLEVEL", "INFO").upper()


def setup_logging_and_tracing(module_name: str):
    """
    Initializes the logger and tracer for the specified module.

    Args:
        module_name (str): The name of the module to initialize the logger and tracer for.

    Returns:
        tuple: A tuple containing the logger and tracer objects.
    """
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, LOGLEVEL, logging.INFO),
    )

    logger = logging.getLogger(module_name)
    tracer = trace.get_tracer(module_name)
    logging.getLogger("azure").setLevel(logging.WARNING)
    return logger, tracer

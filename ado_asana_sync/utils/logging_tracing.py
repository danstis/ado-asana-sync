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

import os
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Optional, Dict, Any
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
    # Enhanced logging format with more context
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, LOGLEVEL, logging.INFO),
        force=True,  # Override existing configuration
    )

    logger = logging.getLogger(module_name)
    tracer = trace.get_tracer(module_name)
    
    # Suppress noisy external libraries
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    
    return logger, tracer


def generate_correlation_id() -> str:
    """
    Generate a unique correlation ID for tracking operations across systems.
    
    Returns:
        str: A unique correlation ID
    """
    return str(uuid.uuid4())[:8]


def log_with_context(logger: logging.Logger, level: int, message: str, 
                     correlation_id: Optional[str] = None, **kwargs) -> None:
    """
    Log a message with additional context information.
    
    Args:
        logger: The logger instance to use
        level: The logging level (e.g., logging.INFO)
        message: The log message
        correlation_id: Optional correlation ID for tracking
        **kwargs: Additional context information to include
    """
    context_parts = []
    
    if correlation_id:
        context_parts.append(f"correlation_id={correlation_id}")
    
    for key, value in kwargs.items():
        if value is not None:
            context_parts.append(f"{key}={value}")
    
    if context_parts:
        context_str = " | ".join(context_parts)
        full_message = f"{message} | {context_str}"
    else:
        full_message = message
    
    logger.log(level, full_message)


@contextmanager
def log_performance(logger: logging.Logger, operation_name: str, 
                   correlation_id: Optional[str] = None, **context):
    """
    Context manager for logging the performance of operations.
    
    Args:
        logger: The logger instance to use
        operation_name: Name of the operation being timed
        correlation_id: Optional correlation ID for tracking
        **context: Additional context information
    
    Example:
        with log_performance(_LOGGER, "sync_project", project_name="MyProject"):
            # Your operation here
            pass
    """
    start_time = time.time()
    operation_id = correlation_id or generate_correlation_id()
    
    log_with_context(
        logger, logging.INFO, 
        f"Starting {operation_name}",
        correlation_id=operation_id,
        **context
    )
    
    try:
        yield operation_id
    except Exception as e:
        duration = time.time() - start_time
        log_with_context(
            logger, logging.ERROR,
            f"Failed {operation_name} after {duration:.2f}s: {str(e)}",
            correlation_id=operation_id,
            duration_seconds=duration,
            error_type=type(e).__name__,
            **context
        )
        raise
    else:
        duration = time.time() - start_time
        log_with_context(
            logger, logging.INFO,
            f"Completed {operation_name} in {duration:.2f}s",
            correlation_id=operation_id,
            duration_seconds=duration,
            **context
        )


def log_api_call(logger: logging.Logger, api_name: str, method: str,
                endpoint: Optional[str] = None, correlation_id: Optional[str] = None,
                **kwargs) -> None:
    """
    Log API calls with consistent formatting.
    
    Args:
        logger: The logger instance to use
        api_name: Name of the API (e.g., "Asana", "ADO")
        method: HTTP method or API method name
        endpoint: API endpoint or resource being accessed
        correlation_id: Optional correlation ID for tracking
        **kwargs: Additional context (e.g., project_id, task_id)
    """
    log_with_context(
        logger, logging.DEBUG,
        f"API call: {api_name}.{method}",
        correlation_id=correlation_id,
        api=api_name,
        method=method,
        endpoint=endpoint,
        **kwargs
    )


def log_api_response(logger: logging.Logger, api_name: str, method: str,
                    success: bool, response_time: Optional[float] = None,
                    error: Optional[str] = None, correlation_id: Optional[str] = None,
                    **kwargs) -> None:
    """
    Log API responses with consistent formatting.
    
    Args:
        logger: The logger instance to use
        api_name: Name of the API (e.g., "Asana", "ADO")
        method: HTTP method or API method name
        success: Whether the API call was successful
        response_time: Time taken for the API call in seconds
        error: Error message if the call failed
        correlation_id: Optional correlation ID for tracking
        **kwargs: Additional context
    """
    level = logging.DEBUG if success else logging.WARNING
    status = "SUCCESS" if success else "FAILED"
    
    context = {
        "api": api_name,
        "method": method,
        "status": status,
        **kwargs
    }
    
    if response_time is not None:
        context["response_time_seconds"] = response_time
    
    if error:
        context["error"] = error
    
    message = f"API response: {api_name}.{method} - {status}"
    if response_time:
        message += f" ({response_time:.2f}s)"
    
    log_with_context(logger, level, message, correlation_id=correlation_id, **context)

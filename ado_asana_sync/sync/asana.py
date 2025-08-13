"""Contains the Asana related functions that are used in the package."""

from __future__ import annotations

import logging
import time

import asana  # type: ignore
from asana.rest import ApiException  # type: ignore

from ado_asana_sync.utils.logging_tracing import (
    setup_logging_and_tracing,
    log_api_call,
    log_api_response,
    log_with_context
)

from .app import App

# This module uses the logger and tracer instances _LOGGER and _TRACER for logging and tracing, respectively.
_LOGGER, _TRACER = setup_logging_and_tracing(__name__)


def get_asana_task(app: App, task_gid: str) -> dict | None:
    """
    Returns the entire task dict for the Asana task with the given gid.

    :param app: The application object.
    :type app: App
    :param task_gid: The gid of the Asana task.
    :type task_gid: str
    :return: Task dict or None if no task is found.
    :rtype: dict or None
    """
    with _TRACER.start_as_current_span("get_asana_task") as span:
        span.set_attributes(
            {
                "asana_workspace_name": app.asana_workspace_name,
                "task_gid": task_gid,
            }
        )
        
        log_api_call(
            _LOGGER,
            "Asana",
            "get_task",
            endpoint=f"tasks/{task_gid}",
            task_gid=task_gid,
            workspace=app.asana_workspace_name
        )
        
        api_instance = asana.TasksApi(app.asana_client)
        start_time = time.time()
        
        try:
            opts = {
                "opt_fields": (
                    "assignee_section,due_at,name,completed_at,tags,"
                    "dependents,projects,completed,permalink_url,parent,"
                    "assignee,assignee_status,num_subtasks,modified_at,"
                    "workspace,due_on"
                )
            }
            # Get the task with the given task_gid.
            api_response = api_instance.get_task(
                task_gid,
                opts,
            )
            
            response_time = time.time() - start_time
            log_api_response(
                _LOGGER,
                "Asana",
                "get_task",
                success=True,
                response_time=response_time,
                task_gid=task_gid,
                task_name=api_response.get("name", "unknown") if api_response else None
            )
            
            return api_response
        except ApiException as exception:
            response_time = time.time() - start_time
            log_api_response(
                _LOGGER,
                "Asana",
                "get_task",
                success=False,
                response_time=response_time,
                error=str(exception),
                task_gid=task_gid,
                status_code=getattr(exception, 'status', None)
            )
            return None

""" Contains the Asana related functions that are used in the package.
"""

from __future__ import annotations

import asana  # type: ignore
from asana.rest import ApiException  # type: ignore

from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

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
        api_instance = asana.TasksApi(app.asana_client)
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
            return api_response
        except ApiException as exception:
            _LOGGER.error("Exception when calling TasksApi->get_task: %s\n", exception)
            return None

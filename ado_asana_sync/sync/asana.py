""" Contains the Asana related functions that are used in the package.
"""

from __future__ import annotations

import asana  # type: ignore
from asana.rest import ApiException  # type: ignore

from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App

# This module uses the logger and tracer instances _LOGGER and _TRACER for logging and tracing, respectively.
_LOGGER, _TRACER = setup_logging_and_tracing(__name__)


def get_asana_task(app: App, task_gid: str) -> object | None:
    """
    Returns the entire task object for the Asana task with the given gid in the given project.

    :param asana_project: The gid of the Asana project.
    :type asana_project: str
    :param task_gid: The name of the Asana task.
    :type task_gid: str
    :return: Task object or None if no task is found.
    :rtype: object or None
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
            # Get all tasks in the project.
            opt_fields = [
                "assignee_section",
                "due_at",
                "name",
                "completed_at",
                "tags",
                "dependents",
                "projects",
                "completed",
                "permalink_url",
                "parent",
                "assignee",
                "assignee_status",
                "num_subtasks",
                "modified_at",
                "workspace",
                "due_on",
            ]
            api_response = api_instance.get_task(
                task_gid,
                opt_fields=opt_fields,
            )
            return api_response.data
        except ApiException as exception:
            _LOGGER.error("Exception when calling TasksApi->get_task: %s\n", exception)
            return None

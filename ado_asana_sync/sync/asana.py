""" Contains the Asana related functions that are used in the package.
"""

from __future__ import annotations

import logging

import asana
from asana.rest import ApiException

from .app import App


# _LOGGER is the logging instance for this file.
_LOGGER = logging.getLogger(__name__)


def get_asana_task(app: App, task_gid) -> object | None:
    """
    Returns the entire task object for the Asana task with the given gid in the given project.

    :param asana_project: The gid of the Asana project.
    :type asana_project: str
    :param task_gid: The name of the Asana task.
    :type task_gid: str
    :return: Task object or None if no task is found.
    :rtype: object or None
    """
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

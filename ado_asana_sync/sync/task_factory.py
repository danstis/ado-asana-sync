"""Logic for creating and saving Asana task bodies."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import asana  # type: ignore
from asana.rest import ApiException  # type: ignore

from ado_asana_sync.utils.date import iso8601_utc
from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App
from .task_item import TaskItem
from .utils import encode_url_for_asana

_LOGGER, _TRACER = setup_logging_and_tracing(__name__)

_CLOSED_STATES = {state.strip() for state in os.environ.get("CLOSED_STATES", "Closed,Removed,Done").split(",")}


def create_asana_task_body(task: TaskItem, is_initial_sync: bool = True) -> dict[str, Any]:
    """Create the request body for Asana task API calls.

    Args:
        task: TaskItem object containing task data
        is_initial_sync: Whether this is initial creation (True) or update (False)

    Returns:
        dict: Request body for Asana API
    """
    body = {
        "data": {
            "name": task.asana_title,
            "html_notes": f"<body>{task.asana_notes_link}</body>",
            "assignee": task.assigned_to,
            "completed": task.state in _CLOSED_STATES if task.state else False,
        }
    }

    if is_initial_sync and task.due_date:
        body["data"]["due_on"] = task.due_date

    return body


def _build_asana_task_body(
    task: TaskItem,
    tag: str,
    asana_project: str,
    parent_gid: str | None,
    link_custom_field_id: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "data": {
            "name": task.asana_title,
            "html_notes": f"<body>{task.asana_notes_link}</body>",
            "assignee": task.assigned_to,
            "tags": [tag],
            "completed": task.state in _CLOSED_STATES,
        },
    }

    if task.due_date:
        body["data"]["due_on"] = task.due_date

    if link_custom_field_id:
        body["data"]["custom_fields"] = {link_custom_field_id: encode_url_for_asana(task.url)}

    if parent_gid:
        body["data"]["parent"] = parent_gid
    else:
        body["data"]["projects"] = [asana_project]

    return body


def _save_created_task(app: App, task: TaskItem, result: dict) -> None:
    task.asana_gid = result["gid"]
    task.asana_updated = result["modified_at"]
    task.updated_date = iso8601_utc(datetime.now(timezone.utc))
    task.save(app)


def _retry_create_without_due_date(
    tasks_api_instance: asana.TasksApi, app: App, task: TaskItem, body: dict[str, Any], exception: ApiException
) -> None:
    if not task.due_date or not hasattr(exception, "status") or exception.status not in (400, 422):
        return

    _LOGGER.warning(
        "Due date %s may be invalid for task %s (HTTP %s), retrying without due date",
        task.due_date,
        task.asana_title,
        exception.status,
    )

    if "due_on" not in body["data"]:
        return

    del body["data"]["due_on"]
    try:
        result = tasks_api_instance.create_task(body, opts={})
        _save_created_task(app, task, result)
        _LOGGER.info("Task created successfully without due date")
    except ApiException as retry_exception:
        _LOGGER.error("Failed to create task even without due date: %s", retry_exception)

"""Asana-specific API interaction functions."""

from __future__ import annotations

import asana  # type: ignore
from asana.rest import ApiException  # type: ignore

from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .app import App
from .task_item import TaskItem

_LOGGER, _TRACER = setup_logging_and_tracing(__name__)


def get_asana_workspace(app: App, name: str) -> str:
    """Returns the workspace gid for the named Asana workspace."""
    api_instance = asana.WorkspacesApi(app.asana_client)
    try:
        api_response = api_instance.get_workspaces(opts={})
        for w in api_response:
            if w["name"] == name:
                return w["gid"]
        raise NameError(f"No workspace found with name '{name}'")
    except ApiException as exception:
        _LOGGER.error("Exception when calling WorkspacesApi->get_workspaces: %s\n", exception)
        raise ValueError(f"Call to Asana API failed: {exception}") from exception


def get_asana_project(app: App, workspace_gid: str, name: str) -> str | None:
    """Returns the project gid for the named Asana project."""
    api_instance = asana.ProjectsApi(app.asana_client)
    try:
        opts = {"workspace": workspace_gid, "archived": False, "opt_fields": "name"}
        api_response = api_instance.get_projects(opts)
        for p in api_response:
            if p["name"] == name:
                return p["gid"]
        raise NameError(f"No project found with name '{name}'")
    except ApiException as exception:
        _LOGGER.error("Exception when calling ProjectsApi->get_projects: %s\n", exception)
        return None


def get_asana_project_tasks(app: App, asana_project: str | None) -> list[dict]:
    """Return a list of task dicts for the given Asana project."""
    api_instance = asana.TasksApi(app.asana_client)
    try:
        api_params = {
            "project": asana_project,
            "limit": app.asana_page_size,
            "opt_fields": (
                "assignee_section,due_at,name,completed_at,tags,dependents,"
                "projects,completed,permalink_url,parent,assignee,"
                "assignee_status,num_subtasks,modified_at,workspace,due_on"
            ),
        }
        api_response = api_instance.get_tasks(api_params)
        return list(api_response)
    except ApiException as exception:
        _LOGGER.error(
            "Exception in get_asana_project_tasks when calling TasksApi->get_tasks: %s",
            exception,
        )
        return []


def get_asana_task_by_name(task_list: list[dict], task_name: str) -> dict | None:
    """Returns the entire task dict for the named Asana task from the given list of tasks."""
    normalized_name = task_name.strip()
    for t in task_list:
        name = t.get("name")
        if isinstance(name, str) and name.strip() == normalized_name:
            return t
    return None


def get_asana_task_tags(app: App, task: TaskItem) -> list[dict]:
    """Retrieves the tags assigned to a given Asana task."""
    with _TRACER.start_as_current_span("get_asana_task_tags"):
        api_instance = asana.TagsApi(app.asana_client)
        try:
            api_response = api_instance.get_tags_for_task(task.asana_gid, opts={})
            return list(api_response)
        except ApiException as exception:
            _LOGGER.error("Exception when calling TagsApi->get_tags_for_task: %s\n", exception)
            return []


def get_tag_by_name(app: App, workspace: str, tag: str) -> dict | None:
    """Retrieves a tag by its name from a given workspace."""
    with _TRACER.start_as_current_span("get_tag_by_name"):
        api_instance = asana.TagsApi(app.asana_client)
        try:
            _LOGGER.info("get workspace tag '%s'", tag)
            opts = {"workspace": workspace}
            api_response = api_instance.get_tags(opts)
            tags_by_name = {t["name"]: t for t in api_response}
            return tags_by_name.get(tag)
        except ApiException as exception:
            _LOGGER.error("Exception when calling TagsApi->get_tags: %s\n", exception)
            return None


def _get_deactivated_user_gids(app: App, asana_workspace_gid: str) -> set[str]:
    """Return a set of user GIDs that are deactivated in the given workspace."""
    memberships_api = asana.WorkspaceMembershipsApi(app.asana_client)
    opts = {
        "opt_fields": "is_active,user.gid",
    }
    try:
        memberships = memberships_api.get_workspace_memberships_for_workspace(asana_workspace_gid, opts)
        deactivated = set()
        for m in memberships:
            if m.get("is_active") is False:
                user = m.get("user") or {}
                user_gid = user.get("gid")
                if user_gid:
                    deactivated.add(user_gid)
        return deactivated
    except ApiException as exception:
        _LOGGER.warning(
            "Failed to fetch workspace memberships, cannot filter deactivated users: %s",
            exception,
        )
        return set()
    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOGGER.warning("Unexpected error fetching workspace memberships: %s", e)
        return set()

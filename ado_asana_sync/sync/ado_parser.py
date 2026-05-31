"""ADO-specific item parsing utilities."""

from __future__ import annotations

from dataclasses import dataclass

from azure.devops.v7_0.work_item_tracking.models import WorkItem  # type: ignore


@dataclass
class ADOAssignedUser:
    """Class to store the details of the assigned user in ADO."""

    display_name: str
    email: str


def get_task_user(task: WorkItem) -> ADOAssignedUser | None:
    """Return the email and display name of the user assigned to the Azure DevOps work item.

    If no user is assigned, return None.
    """
    assigned_to = task.fields.get("System.AssignedTo", None)
    if assigned_to is not None:
        display_name = assigned_to.get("displayName", None)
        email = assigned_to.get("uniqueName", None)
        if display_name is None or email is None:
            return None
        return ADOAssignedUser(display_name, email)
    return None

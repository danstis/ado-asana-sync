"""This module contains the TaskItem class, which represents a task item in the synchronization process between
Azure DevOps (ADO) and Asana."""

from __future__ import annotations

from html import escape
from typing import Any, Optional

from .app import App
from .asana import get_asana_task
from .utils import validate_due_date


class TaskItem:
    """
    Represents a task item in the synchronization process between Azure DevOps (ADO) and Asana.

    Each TaskItem object corresponds to a work item in ADO and a task in Asana. It contains information about the task such as
    its ID, revision number, title, type, URL, and the IDs of the corresponding Asana task and user.

    Attributes:
        ado_id (int): The ID of the task in ADO.
        ado_rev (int): The revision number of the task in ADO.
        title (str): The title of the task.
        item_type (str): The type of the task.
        url (str): The URL of the task in ADO.
        asana_gid (str): The ID of the corresponding task in Asana.
        asana_updated (str): The last updated time of the Asana task in ISO 8601 format.
        assigned_to (str): The ID of the user to whom the task is assigned in Asana.
        created_date (str): The creation date of the task in ISO 8601 format.
        updated_date (str): The last updated date of the task in ISO 8601 format.
        state (str): The item state, for example New, Active, Closed.
        due_date (str): The due date in YYYY-MM-DD format from ADO, synchronized to Asana on initial creation only.
    """

    def __init__(
        self,
        ado_id: int,
        ado_rev: int,
        title: str,
        item_type: str,
        url: str,
        asana_gid: Optional[str] = None,
        asana_updated: Optional[str] = None,
        assigned_to: Optional[str] = None,
        created_date: Optional[str] = None,
        updated_date: Optional[str] = None,
        state: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> None:
        # Validate due_date format
        if due_date is not None and not validate_due_date(due_date):
            raise ValueError(f"Invalid due_date format: {due_date}. Expected YYYY-MM-DD format or None.")

        self.ado_id = ado_id
        self.ado_rev = ado_rev
        self.title = title
        self.item_type = item_type
        self.url = url
        self.asana_gid = asana_gid
        self.asana_updated = asana_updated
        self.assigned_to = assigned_to
        self.created_date = created_date
        self.updated_date = updated_date
        self.state = state
        self.due_date = due_date

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TaskItem):
            return False
        return (
            self.ado_id == other.ado_id
            and self.ado_rev == other.ado_rev
            and self.title == other.title
            and self.item_type == other.item_type
            and self.url == other.url
            and self.asana_gid == other.asana_gid
            and self.asana_updated == other.asana_updated
            and self.assigned_to == other.assigned_to
            and self.created_date == other.created_date
            and self.updated_date == other.updated_date
            and self.state == other.state
            and self.due_date == other.due_date
        )

    def __str__(self) -> str:
        """
        Return a string representation of the object.

        :return: The string representation of the object.
        :rtype: str
        """
        return self.asana_title

    @property
    def asana_title(self) -> str:
        """
        Generate the title of an Asana object.

        Returns:
            str: The formatted title of the Asana object.
        """
        return f"{self.item_type} {self.ado_id}: {self.title}"

    @property
    def asana_notes_link(self) -> str:
        """
        Generate the notes of an Asana object.

        Returns:
            str: The formatted notes of the Asana object.
        """
        return f'<a href="{self.url}">{self.item_type} {self.ado_id}</a>: {escape(self.title)}'

    @classmethod
    def find_by_ado_id(cls, app: App, ado_id: int) -> TaskItem | None:
        """
        Find and retrieve a TaskItem by its Azure DevOps (ADO) ID.

        Args:
            a (App): The App instance.
            ado_id (int): The ADO ID of the TaskItem to find.

        Returns:
            TaskItem: The TaskItem object with the matching ADO ID.
            None: If there is no matching item.
        """

        def query_func(record):
            return record.get("ado_id") == ado_id

        if app.matches and app.matches.contains(query_func):
            items = app.matches.search(query_func)
            if items:
                # Remove doc_id before creating TaskItem
                item_data = {k: v for k, v in items[0].items() if k != "doc_id"}
                return cls(**item_data)
        return None

    @classmethod
    def search(cls, app: App, ado_id: Optional[int] = None, asana_gid: Optional[str] = None) -> TaskItem | None:
        """
        Search for a task item in the App object based on the given ADO ID or Asana GID.

        Parameters:
            a (App): The App object to search in.
            ado_id (int, optional): The ADO ID to search for. Defaults to None.
            asana_gid (str, optional): The Asana GID to search for. Defaults to None.

        Returns:
            Union[TaskItem, None]: The found TaskItem object if a match is found, otherwise None.
        """
        if ado_id is None and asana_gid is None:
            return None

        # Generate the query function based on the input.
        def query_func(record):
            return (record.get("ado_id") == ado_id) or (record.get("asana_gid") == asana_gid)

        # return the first matching item, or return None if not found.
        if app.matches and app.matches.contains(query_func):
            items = app.matches.search(query_func)
            if items:
                # Remove doc_id before creating TaskItem
                item_data = {k: v for k, v in items[0].items() if k != "doc_id"}
                return cls(**item_data)
        return None

    def save(self, app: App) -> None:
        """
        Save the TaskItem to the database.

        Args:
            a (App): The App instance.

        Returns:
            None
        """
        task_data = {
            "ado_id": self.ado_id,
            "ado_rev": self.ado_rev,
            "title": self.title,
            "item_type": self.item_type,
            "state": self.state,
            "url": self.url,
            "asana_gid": self.asana_gid,
            "asana_updated": self.asana_updated,
            "assigned_to": self.assigned_to,
            "created_date": self.created_date,
            "updated_date": self.updated_date,
            "due_date": self.due_date,
        }

        def query_func(record):
            return record.get("ado_id") == task_data["ado_id"]

        if app.matches is None:
            raise ValueError("app.matches is None")

        # SQLite database handles its own locking, but we maintain db_lock for compatibility
        with app.db_lock:
            if app.matches.contains(query_func):
                app.matches.update(task_data, query_func)
            else:
                app.matches.insert(task_data)

    def is_current(self, app: App) -> bool:
        """
        Check if the current TaskItem is up-to-date with its corresponding tasks in Azure DevOps (ADO) and Asana.

        This method retrieves the corresponding tasks in ADO and Asana using the stored IDs, and compares their revision number
        and last updated time with the stored values. If either the ADO task's revision number or the Asana task's last updated
        time is different from the stored values, the TaskItem is considered not current.

        Args:
            a (App): The App instance.

        Returns:
            bool: True if the TaskItem is current, False otherwise.
        """
        if app.ado_wit_client is None:
            return False
        ado_task = app.ado_wit_client.get_work_item(self.ado_id)
        asana_task = get_asana_task(app, self.asana_gid) if self.asana_gid else None

        if not ado_task or not asana_task:
            return False

        if ado_task.rev != self.ado_rev or (asana_task and asana_task.get("modified_at") != self.asana_updated):
            return False

        return True

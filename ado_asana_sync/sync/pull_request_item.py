"""This module contains the PullRequestItem class, which represents a pull request item in the synchronization process between
Azure DevOps (ADO) and Asana."""

from __future__ import annotations

from html import escape
from typing import Any, Optional

from .app import App
from .asana import get_asana_task
from .utils import extract_reviewer_vote


class PullRequestItem:
    """
    Represents a pull request item in the synchronization process between Azure DevOps (ADO) and Asana.

    Each PullRequestItem object corresponds to a pull request in ADO and reviewer tasks in Asana. It contains information
    about the PR such as its ID, title, and the IDs of the corresponding Asana tasks for each reviewer.

    Attributes:
        ado_pr_id (int): The ID of the pull request in ADO.
        ado_repository_id (str): The repository ID in ADO.
        title (str): The title of the pull request.
        status (str): The status of the pull request (Active, Completed, Abandoned).
        created_date (str): The creation date of the PR in ISO 8601 format.
        updated_date (str): The last updated date of the PR in ISO 8601 format.
        url (str): The URL of the pull request in ADO.
        reviewer_gid (str): The Asana user ID of the reviewer this item represents.
        reviewer_name (str): The display name of the reviewer.
        asana_gid (str): The ID of the corresponding reviewer task in Asana.
        asana_updated (str): The last updated time of the Asana task in ISO 8601 format.
        review_status (str): The review status for this reviewer (approved, waiting_for_author, etc.).
    """

    def __init__(
        self,
        ado_pr_id: int,
        ado_repository_id: str,
        title: str,
        status: str,
        url: str,
        reviewer_gid: str,
        reviewer_name: Optional[str] = None,
        asana_gid: Optional[str] = None,
        asana_updated: Optional[str] = None,
        created_date: Optional[str] = None,
        updated_date: Optional[str] = None,
        review_status: Optional[str] = None,
    ) -> None:
        self.ado_pr_id = ado_pr_id
        self.ado_repository_id = ado_repository_id
        self.title = title
        self.status = status
        self.url = url
        self.reviewer_gid = reviewer_gid
        self.reviewer_name = reviewer_name
        self.asana_gid = asana_gid
        self.asana_updated = asana_updated
        self.created_date = created_date
        self.updated_date = updated_date
        self.review_status = review_status

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PullRequestItem):
            return False
        return (
            self.ado_pr_id == other.ado_pr_id
            and self.ado_repository_id == other.ado_repository_id
            and self.title == other.title
            and self.status == other.status
            and self.url == other.url
            and self.reviewer_gid == other.reviewer_gid
            and self.reviewer_name == other.reviewer_name
            and self.asana_gid == other.asana_gid
            and self.asana_updated == other.asana_updated
            and self.created_date == other.created_date
            and self.updated_date == other.updated_date
            and self.review_status == other.review_status
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
        Generate the title of an Asana object for a pull request reviewer task.

        Returns:
            str: The formatted title of the Asana object.
        """
        if self.reviewer_name:
            return f"Pull Request {self.ado_pr_id}: {self.title} ({self.reviewer_name})"
        return f"Pull Request {self.ado_pr_id}: {self.title}"

    @property
    def asana_notes_link(self) -> str:
        """
        Generate the notes of an Asana object for a pull request reviewer task.

        Returns:
            str: The formatted notes of the Asana object.
        """
        return f'<a href="{self.url}">Pull Request {self.ado_pr_id}</a>: {escape(self.title)}'

    @classmethod
    def search(
        cls,
        app: App,
        ado_pr_id: Optional[int] = None,
        reviewer_gid: Optional[str] = None,
        asana_gid: Optional[str] = None,
    ) -> PullRequestItem | None:
        """
        Search for a pull request item in the App object based on the given ADO PR ID, reviewer GID, or Asana GID.

        Parameters:
            app (App): The App object to search in.
            ado_pr_id (int, optional): The ADO PR ID to search for. Defaults to None.
            reviewer_gid (str, optional): The reviewer GID to search for. Defaults to None.
            asana_gid (str, optional): The Asana GID to search for. Defaults to None.

        Returns:
            Union[PullRequestItem, None]: The found PullRequestItem object if a match is found, otherwise None.
        """
        if ado_pr_id is None and reviewer_gid is None and asana_gid is None:
            return None

        # Generate the query function based on the input.
        def query_func(record):
            # Check for PR ID and reviewer GID combination
            if ado_pr_id is not None and reviewer_gid is not None:
                if (record.get("ado_pr_id") == ado_pr_id and
                        record.get("reviewer_gid") == reviewer_gid):
                    return True

            # Check individual conditions
            if ado_pr_id is not None and record.get("ado_pr_id") == ado_pr_id:
                return True
            if reviewer_gid is not None and record.get("reviewer_gid") == reviewer_gid:
                return True
            if asana_gid is not None and record.get("asana_gid") == asana_gid:
                return True

            return False

        # return the first matching item, or return None if not found.
        if app.pr_matches and app.pr_matches.contains(query_func):
            items = app.pr_matches.search(query_func)
            if items:
                # Remove doc_id before creating PullRequestItem
                item_data = {k: v for k, v in items[0].items() if k != 'doc_id'}
                return cls(**item_data)
        return None

    def save(self, app: App) -> None:
        """
        Save the PullRequestItem to the database.

        Args:
            app (App): The App instance.

        Returns:
            None
        """
        pr_data = {
            "ado_pr_id": self.ado_pr_id,
            "ado_repository_id": self.ado_repository_id,
            "title": self.title,
            "status": self.status,
            "url": self.url,
            "reviewer_gid": self.reviewer_gid,
            "reviewer_name": self.reviewer_name,
            "asana_gid": self.asana_gid,
            "asana_updated": self.asana_updated,
            "created_date": self.created_date,
            "updated_date": self.updated_date,
            "review_status": self.review_status,
        }

        # Query for unique combination of PR ID and reviewer
        def unique_query_func(record):
            return (record.get("ado_pr_id") == pr_data["ado_pr_id"] and
                    record.get("reviewer_gid") == pr_data["reviewer_gid"])

        if app.pr_matches is None:
            raise ValueError("app.pr_matches is None")
        if app.db_lock is None:
            raise ValueError("app.db_lock is None")
        if app.pr_matches.contains(unique_query_func):
            with app.db_lock:
                app.pr_matches.update(pr_data, unique_query_func)
        else:
            with app.db_lock:
                app.pr_matches.insert(pr_data)

    def is_current(self, app: App, ado_pr, reviewer=None) -> bool:
        """
        Check if the current PullRequestItem is up-to-date with its corresponding PR in Azure DevOps (ADO) and Asana.

        This method compares the PR's last updated time with the stored values. If the ADO PR's last updated
        time is different from the stored values, the PullRequestItem is considered not current.

        Args:
            app (App): The App instance.
            ado_pr: The ADO pull request object.
            reviewer: The ADO reviewer object (optional, for checking review status changes).

        Returns:
            bool: True if the PullRequestItem is current, False otherwise.
        """
        asana_task = get_asana_task(app, self.asana_gid) if self.asana_gid else None

        if not ado_pr:
            return False

        # Check if PR has been updated - compare title and basic properties
        if ado_pr.title != self.title:
            return False

        if ado_pr.status != self.status:
            return False

        # Check if Asana task has been updated
        if asana_task and asana_task.get("modified_at") != self.asana_updated:
            return False

        # Check if reviewer's vote status has changed
        if reviewer is not None:
            current_review_status = extract_reviewer_vote(reviewer)
            if current_review_status != self.review_status:
                return False

        return True

"""This module contains the PullRequestItem class, which represents a pull request item in the synchronization process between
Azure DevOps (ADO) and Asana."""

from __future__ import annotations

from html import escape
from typing import Any, Callable, Optional

from ..utils.logging_tracing import setup_logging_and_tracing
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
        processing_state (str): The processing state (open, closed) to avoid redundant processing.
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
        processing_state: Optional[str] = None,
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
        self.processing_state = processing_state or "open"  # Default to open for new items

        # Validate data consistency to catch potential corruption early
        if not self.validate_data_consistency():
            # This is a critical error that indicates data corruption
            logger, _ = setup_logging_and_tracing(__name__)
            logger.error(
                "Data consistency validation failed for PR item: ado_pr_id=%s, url=%s, title='%s'. "
                "This indicates potential data corruption where PR ID and URL don't match.",
                self.ado_pr_id,
                self.url,
                self.title,
            )

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
            and self.processing_state == other.processing_state
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
    def _create_search_query(
        cls,
        ado_pr_id: Optional[int] = None,
        reviewer_gid: Optional[str] = None,
        asana_gid: Optional[str] = None,
    ) -> Callable[[dict], bool]:
        """Create a query function for database search."""

        def query_func(record: dict) -> bool:
            # Check for PR ID and reviewer GID combination first (most specific)
            if ado_pr_id is not None and reviewer_gid is not None:
                return record.get("ado_pr_id") == ado_pr_id and record.get("reviewer_gid") == reviewer_gid

            # Check individual conditions
            if ado_pr_id is not None and record.get("ado_pr_id") == ado_pr_id:
                return True
            if reviewer_gid is not None and record.get("reviewer_gid") == reviewer_gid:
                return True
            if asana_gid is not None and record.get("asana_gid") == asana_gid:
                return True

            return False

        return query_func

    @classmethod
    def _validate_search_result(cls, pr_item: PullRequestItem, ado_pr_id: Optional[int], item_data: dict) -> bool:
        """Validate that search result matches expected criteria."""
        if ado_pr_id is not None and pr_item.ado_pr_id != ado_pr_id:
            logger, _ = setup_logging_and_tracing(__name__)
            logger.warning(
                "Database corruption detected: searched for PR ID %s but got item with ID %s. "
                "This could cause title/ID mismatches. Item data: %s",
                ado_pr_id,
                pr_item.ado_pr_id,
                item_data,
            )
            return False
        return True

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

        query_func = cls._create_search_query(ado_pr_id, reviewer_gid, asana_gid)

        if app.pr_matches and app.pr_matches.contains(query_func):
            items = app.pr_matches.search(query_func)
            if items:
                # Remove doc_id before creating PullRequestItem
                item_data = {k: v for k, v in items[0].items() if k != "doc_id"}
                pr_item = cls(**item_data)

                # Validate search result for corruption
                if not cls._validate_search_result(pr_item, ado_pr_id, item_data):
                    return None  # Don't return corrupted data

                return pr_item
        return None

    def save(self, app: App) -> None:
        """
        Save the PullRequestItem to the database.

        Args:
            app (App): The App instance.

        Returns:
            None
        """
        # Validate data consistency before saving
        if not self.validate_data_consistency():
            logger, _ = setup_logging_and_tracing(__name__)
            logger.error(
                "Refusing to save PR item with inconsistent data: ado_pr_id=%s, url=%s, title='%s'",
                self.ado_pr_id,
                self.url,
                self.title,
            )
            return

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
            "processing_state": self.processing_state,
        }

        # Query for unique combination of PR ID and reviewer
        def unique_query_func(record):
            return record.get("ado_pr_id") == pr_data["ado_pr_id"] and record.get("reviewer_gid") == pr_data["reviewer_gid"]

        if app.pr_matches is None:
            raise ValueError("app.pr_matches is None")
        if app.db_lock is None:
            raise ValueError("app.db_lock is None")

        # Use a larger critical section to ensure atomicity
        with app.db_lock:
            # Clean up any corrupted records for this PR/reviewer combination first
            self._cleanup_corrupted_records(app, pr_data)

            # Now save the current record
            if app.pr_matches.contains(unique_query_func):
                app.pr_matches.update(pr_data, unique_query_func)
            else:
                app.pr_matches.insert(pr_data)

    def _cleanup_corrupted_records(self, app: App, current_pr_data: dict) -> None:
        """Clean up corrupted records that don't match current data consistency."""
        if app.pr_matches is None:
            return

        # Find all records for this PR ID
        def pr_query_func(record):
            return record.get("ado_pr_id") == current_pr_data["ado_pr_id"]

        matching_records = app.pr_matches.search(pr_query_func)

        # Handle case where matching_records might be None or empty, or a mock
        if not matching_records:
            return

        # Handle mock objects in tests
        try:
            iter(matching_records)
        except TypeError:
            # If it's not iterable (e.g., a Mock), just return
            return

        corrupted_record_count = 0
        for record in matching_records:
            if self._should_remove_record(record, current_pr_data):
                if self._remove_corrupted_record(app, record):
                    corrupted_record_count += 1

        if corrupted_record_count > 0:
            logger, _ = setup_logging_and_tracing(__name__)
            logger.info(
                "Cleaned up %d corrupted PR records for PR ID %s", corrupted_record_count, current_pr_data["ado_pr_id"]
            )

    def _should_remove_record(self, record: dict, current_pr_data: dict) -> bool:
        """Check if a record should be removed due to corruption."""
        # Skip the record we're about to save
        if record.get("reviewer_gid") == current_pr_data["reviewer_gid"]:
            return False

        try:
            # Check if this record has consistent data
            clean_record = {k: v for k, v in record.items() if k != "doc_id"}
            temp_item = PullRequestItem(**clean_record)
            return not temp_item.validate_data_consistency()
        except Exception:  # pylint: disable=broad-exception-caught
            # If we can't even create the object, it's definitely corrupted
            return True

    def _remove_corrupted_record(self, app: App, record: dict) -> bool:
        """Remove a corrupted record from the database."""
        try:

            def delete_query_func(r):
                return r.get("ado_pr_id") == record.get("ado_pr_id") and r.get("reviewer_gid") == record.get("reviewer_gid")

            app.pr_matches.remove(query_func=delete_query_func)  # type: ignore[arg-type,union-attr]
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger, _ = setup_logging_and_tracing(__name__)
            logger.error("Failed to remove corrupted record for PR ID %s: %s", record.get("ado_pr_id"), e)
            return False

    @classmethod
    def cleanup_all_corrupted_records(cls, app: App) -> int:
        """
        Clean up all corrupted PR records in the database.

        This should be called during application startup to remove any existing corrupted data.

        Args:
            app (App): The App instance.

        Returns:
            int: Number of corrupted records cleaned up.
        """
        if app.pr_matches is None:
            return 0

        all_records = app.pr_matches.all()
        corrupted_count = 0

        if app.db_lock is None:
            raise ValueError("app.db_lock is None")

        with app.db_lock:
            for record in all_records:
                if cls._is_record_corrupted(record):
                    if cls._remove_corrupted_record_static(app, record):
                        corrupted_count += 1

        if corrupted_count > 0:
            logger, _ = setup_logging_and_tracing(__name__)
            logger.info("Cleaned up %d corrupted PR records during startup", corrupted_count)

        return corrupted_count

    @classmethod
    def _is_record_corrupted(cls, record: dict) -> bool:
        """Check if a database record is corrupted."""
        try:
            clean_record = {k: v for k, v in record.items() if k != "doc_id"}
            temp_item = cls(**clean_record)
            return not temp_item.validate_data_consistency()
        except Exception:  # pylint: disable=broad-exception-caught
            return True

    @classmethod
    def _remove_corrupted_record_static(cls, app: App, record: dict) -> bool:
        """Remove a corrupted record from the database (static version)."""
        try:

            def delete_query_func(r):
                return r.get("ado_pr_id") == record.get("ado_pr_id") and r.get("reviewer_gid") == record.get("reviewer_gid")

            app.pr_matches.remove(query_func=delete_query_func)  # type: ignore[arg-type,union-attr]
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger, _ = setup_logging_and_tracing(__name__)
            logger.error("Failed to remove corrupted record for PR ID %s: %s", record.get("ado_pr_id"), e)
            return False

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

    def validate_data_consistency(self) -> bool:
        """
        Validate that the PR item's data is internally consistent.

        Specifically checks that the URL contains the same PR ID as ado_pr_id,
        which helps detect data corruption where PR ID and title don't match.

        Returns:
            bool: True if data is consistent, False otherwise.
        """
        if not self.url or not self.ado_pr_id:
            return True  # Can't validate without URL or ID

        # Extract PR ID from URL
        url_parts = self.url.split("/")
        try:
            # URL format: .../pullrequest/{pr_id}
            if "pullrequest" in url_parts:
                pr_index = url_parts.index("pullrequest")
                if pr_index + 1 < len(url_parts):
                    url_pr_id = int(url_parts[pr_index + 1])
                    return url_pr_id == self.ado_pr_id
        except (ValueError, IndexError):
            # If we can't parse the URL, assume it's valid
            return True

        return True

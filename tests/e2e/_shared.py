"""
Shared helpers for end-to-end sync tests.

These tests exercise the real sync flow with a temporary database while
patching only external ADO/Asana client boundaries.
"""

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from tests.utils.test_helpers import AsanaApiMockHelper

_RECENT_DATE = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
_OLD_ASANA_DATE = "2025-01-01T10:00:00.000Z"
_TEST_USER_ASSIGNED = {"displayName": "Test User", "uniqueName": "test@example.com"}
_ADO_BASE_URL = "https://dev.azure.com/test/project/_workitems/edit"
_GIT_BASE_URL = "https://dev.azure.com/test/project/_git/repo/pullrequest"


def make_backlog_item(item_id: int) -> MagicMock:
    """Create a mock ADO backlog item stub with a target ID."""
    item = MagicMock()
    item.target.id = item_id
    return item


def make_pr_db_record(pr_id: int, status: str = "active", processing_state: str = "open") -> dict:
    """Create a PR database record suitable for pre-seeding app.pr_matches."""
    return {
        "ado_pr_id": pr_id,
        "ado_repository_id": "repo-abc",
        "title": f"Feature PR {pr_id}",
        "status": status,
        "url": f"{_GIT_BASE_URL}/{pr_id}",
        "reviewer_gid": "user-789",
        "reviewer_name": "Test User",
        "asana_gid": f"pr_task_gid_{pr_id}",
        "asana_updated": _OLD_ASANA_DATE,
        "created_date": _OLD_ASANA_DATE,
        "updated_date": _OLD_ASANA_DATE,
        "review_status": "noVote",
        "processing_state": processing_state,
        "assignee_gid": None,
    }


def make_work_item_db_record(
    ado_id: int,
    title: str,
    state: str = "Active",
    asana_gid: str | None = None,
    ado_rev: int = 1,
) -> dict:
    """Create a work item database record suitable for pre-seeding app.matches."""
    return {
        "ado_id": ado_id,
        "ado_rev": ado_rev,
        "title": title,
        "item_type": "Task",
        "state": state,
        "url": f"{_ADO_BASE_URL}/{ado_id}",
        "asana_gid": asana_gid or f"task_gid_{ado_id}",
        "asana_updated": _OLD_ASANA_DATE,
        "assigned_to": "user-789",
        "created_date": _OLD_ASANA_DATE,
        "updated_date": _RECENT_DATE,
        "due_date": None,
    }


class E2EBase(unittest.TestCase):
    """Base class with shared setup helpers for E2E tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.asana_helper = AsanaApiMockHelper()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def connect_app(self, app, mock_dirname, mock_ado_conn, mock_asana_client):
        """Connect a real App with only external clients patched."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_conn.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()
        app.connect()
        app.asana_tag_gid = "tag-abc"

    def asana_patches(self, tasks_api):
        """Patch external Asana APIs while leaving sync logic real."""
        memberships_mock = MagicMock()
        memberships_mock.get_workspace_memberships_for_workspace.return_value = []
        return [
            patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=tasks_api),
            patch("ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=self.asana_helper.create_workspace_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=self.asana_helper.create_projects_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=self.asana_helper.create_tags_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.UsersApi", return_value=self.asana_helper.create_users_api_mock()),
            patch(
                "ado_asana_sync.sync.sync.asana.CustomFieldSettingsApi",
                return_value=self.asana_helper.create_custom_field_settings_api_mock(),
            ),
            patch("ado_asana_sync.sync.sync.asana.WorkspaceMembershipsApi", return_value=memberships_mock),
            patch("ado_asana_sync.sync.sync.asana.StoriesApi", return_value=MagicMock()),
        ]

"""Tests that `updated_date` timestamps are always stamped in UTC, never host-local wall clock.

`iso8601_utc(datetime.now())` passes a naive, host-local timestamp into a function whose
contract assumes naive input is already UTC. On any host not set to UTC, that silently
records the wrong instant. These tests drive real call sites and assert on the actual
persisted/assigned value, not on source text.
"""

import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

from tests.utils.test_helpers import AsanaApiMockHelper, TestDataBuilder


def _set_host_timezone(name: str):
    original_tz = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    return original_tz


def _restore_host_timezone(original_tz):
    if original_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original_tz
    time.tzset()


@unittest.skipIf(not hasattr(time, "tzset"), "POSIX only")
class TestUpdatedDateStampedInUtc(unittest.TestCase):
    """updated_date must reflect real UTC time regardless of the host's local timezone."""

    def setUp(self):
        import tempfile

        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _setup_asana_api_patches(self, asana_helper, tasks_api):
        return (
            patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=tasks_api),
            patch("ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=asana_helper.create_workspace_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=asana_helper.create_projects_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=asana_helper.create_tags_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.UsersApi", return_value=asana_helper.create_users_api_mock()),
            patch(
                "ado_asana_sync.sync.sync.asana.CustomFieldSettingsApi",
                return_value=asana_helper.create_custom_field_settings_api_mock(),
            ),
        )

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_update_existing_task_stamps_updated_date_in_utc(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """update_existing_task (sync.py) must stamp updated_date in real UTC, not host-local-as-UTC."""
        from ado_asana_sync.sync.sync import update_existing_task
        from ado_asana_sync.sync.task_item import TaskItem

        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        original_tz = _set_host_timezone("Pacific/Auckland")
        try:
            app = TestDataBuilder.create_real_app(self.temp_dir)
            app.connect()

            app.ado_wit_client = MagicMock()

            ado_work_item = TestDataBuilder.create_ado_work_item(item_id=3001, title="Updated Title", work_item_type="Task")
            ado_work_item.rev = 2

            existing_match = TaskItem(
                ado_id=3001,
                ado_rev=1,
                title="Old Title",
                item_type="Task",
                url="http://ado/3001",
                asana_gid="existing_gid",
                asana_updated="2025-01-01T10:00:00.000Z",
                created_date="2025-01-01T10:00:00.000Z",
                updated_date="2025-01-01T10:00:00.000Z",
            )

            mock_asana_task = TestDataBuilder.create_asana_task_data(gid="existing_gid", name="Task 3001: Old Title")
            asana_helper = AsanaApiMockHelper()
            mock_tasks_api = asana_helper.create_tasks_api_mock(tasks=[mock_asana_task], updated_task=mock_asana_task)

            try:
                from contextlib import ExitStack

                with ExitStack() as stack:
                    for patch_ctx in self._setup_asana_api_patches(asana_helper, mock_tasks_api):
                        stack.enter_context(patch_ctx)
                    with patch("ado_asana_sync.sync.sync.get_asana_task", return_value=mock_asana_task):
                        update_existing_task(app, ado_work_item, existing_match, None, "AsanaProject")

                recorded = datetime.fromisoformat(existing_match.updated_date)
                delta = abs(recorded - datetime.now(timezone.utc))
                self.assertLess(
                    delta,
                    timedelta(minutes=5),
                    f"updated_date {existing_match.updated_date} is not within 5 minutes of real UTC now "
                    "- it looks like host-local wall clock was stamped as UTC",
                )
            finally:
                app.close()
        finally:
            _restore_host_timezone(original_tz)


@unittest.skipIf(not hasattr(time, "tzset"), "POSIX only")
class TestPrUpdatedDateStampedInUtc(unittest.TestCase):
    """A PR-path updated_date call site must also stamp real UTC, not host-local-as-UTC."""

    def test_create_asana_pr_task_stamps_updated_date_in_utc(self):
        from ado_asana_sync.sync.app import App
        from ado_asana_sync.sync.pull_request_sync import create_asana_pr_task

        original_tz = _set_host_timezone("Pacific/Auckland")
        try:
            mock_app = Mock(spec=App)
            mock_app.asana_client = Mock()

            with patch("ado_asana_sync.sync.pr_asana_helpers.find_custom_field_by_name", return_value=None):
                with patch("asana.TasksApi") as mock_tasks_api_class:
                    mock_tasks_api = Mock()
                    mock_tasks_api_class.return_value = mock_tasks_api
                    mock_tasks_api.create_task.return_value = {"gid": "new-task-123", "modified_at": "2023-12-01T10:00:00Z"}

                    mock_asana_project = {"gid": "project-456"}
                    mock_pr_item = Mock()
                    mock_pr_item.asana_title = "PR 123: Test Title"
                    mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 123</a>: Test Title"
                    mock_pr_item.status = "active"
                    mock_pr_item.review_status = "waiting_for_author"
                    mock_pr_item.assignee_gid = None
                    mock_pr_item.reviewer_gid = "user-1"
                    mock_pr_item.url = "http://test.com/pr/123"
                    mock_pr_item.ado_pr_id = 123

                    create_asana_pr_task(mock_app, mock_asana_project, mock_pr_item, "tag-gid")

            recorded = datetime.fromisoformat(mock_pr_item.updated_date)
            delta = abs(recorded - datetime.now(timezone.utc))
            self.assertLess(
                delta,
                timedelta(minutes=5),
                f"updated_date {mock_pr_item.updated_date} is not within 5 minutes of real UTC now "
                "- it looks like host-local wall clock was stamped as UTC",
            )
        finally:
            _restore_host_timezone(original_tz)


if __name__ == "__main__":
    unittest.main()

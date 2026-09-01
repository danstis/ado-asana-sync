"""Tests that a failed ADO->Asana user match never un-assigns an already-synced task.

These drive the real update paths in ``sync.py`` with a real ``App`` and real
``TaskItem`` objects, mocking only the Asana API boundary.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from tests.utils.test_helpers import AsanaApiMockHelper, TestDataBuilder


class _AssignmentSafetyBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
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

    def _make_task_item(self, assigned_to="user-789"):
        from ado_asana_sync.sync.task_item import TaskItem

        return TaskItem(
            ado_id=4001,
            ado_rev=1,
            title="Old Title",
            item_type="Task",
            url="http://ado/4001",
            asana_gid="existing_gid",
            asana_updated="2025-01-01T10:00:00.000Z",
            created_date="2025-01-01T10:00:00.000Z",
            updated_date="2025-01-01T10:00:00.000Z",
            assigned_to=assigned_to,
        )


class TestUpdateExistingTaskAssignmentSafety(_AssignmentSafetyBase):
    """update_existing_task must not clear a good Asana assignee on a failed match."""

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def _run_update_existing_task(self, ado_assigned_to, mock_client, mock_conn, mock_dirname, logger_patch=False):
        from ado_asana_sync.sync.sync import update_existing_task

        mock_dirname.return_value = self.temp_dir
        mock_conn.return_value = MagicMock()
        mock_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()
        app.ado_wit_client = MagicMock()

        ado_work_item = TestDataBuilder.create_ado_work_item(
            item_id=4001,
            title="Updated Title",
            work_item_type="Task",
            assigned_to=ado_assigned_to,
        )
        ado_work_item.rev = 2
        existing_match = self._make_task_item()

        mock_asana_task = TestDataBuilder.create_asana_task_data(gid="existing_gid", name="Task 4001: Old Title")
        asana_helper = AsanaApiMockHelper()
        mock_tasks_api = asana_helper.create_tasks_api_mock(tasks=[mock_asana_task], updated_task=mock_asana_task)

        captured = {}
        try:
            with ExitStack() as stack:
                for patch_ctx in self._setup_asana_api_patches(asana_helper, mock_tasks_api):
                    stack.enter_context(patch_ctx)
                stack.enter_context(patch("ado_asana_sync.sync.sync.get_asana_task", return_value=mock_asana_task))
                logger_mock = stack.enter_context(patch("ado_asana_sync.sync.sync._LOGGER")) if logger_patch else None
                update_existing_task(app, ado_work_item, existing_match, None, "AsanaProject")
            if mock_tasks_api.update_task.call_args is not None:
                captured["body"] = mock_tasks_api.update_task.call_args[0][0]
            captured["logger"] = logger_mock
        finally:
            app.close()
        return existing_match, captured

    def test_preserves_assignee_when_match_fails(self):
        existing_match, _ = self._run_update_existing_task({"displayName": "Ghost User", "uniqueName": "ghost@nowhere.com"})
        self.assertEqual(existing_match.assigned_to, "user-789")

    def test_does_not_send_null_assignee_when_match_fails(self):
        _, captured = self._run_update_existing_task({"displayName": "Ghost User", "uniqueName": "ghost@nowhere.com"})
        self.assertEqual(captured["body"]["data"]["assignee"], "user-789")

    def test_clears_assignee_when_ado_unassigned(self):
        existing_match, captured = self._run_update_existing_task({})
        self.assertIsNone(existing_match.assigned_to)
        self.assertIsNone(captured["body"]["data"]["assignee"])

    def test_logs_warning_when_assignee_preserved(self):
        _, captured = self._run_update_existing_task(
            {"displayName": "Ghost User", "uniqueName": "ghost@nowhere.com"}, logger_patch=True
        )
        logger_mock = captured["logger"]
        self.assertTrue(
            any("could not be matched" in str(call) for call in logger_mock.warning.call_args_list),
            logger_mock.warning.call_args_list,
        )


class TestUpdateTaskIfNeededAssignmentSafety(_AssignmentSafetyBase):
    """update_task_if_needed must not clear a good Asana assignee on a failed match."""

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def _run_update_task_if_needed(self, ado_assigned_to, mock_client, mock_conn, mock_dirname):
        from ado_asana_sync.sync.sync import update_task_if_needed

        mock_dirname.return_value = self.temp_dir
        mock_conn.return_value = MagicMock()
        mock_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()
        app.ado_wit_client = MagicMock()

        ado_work_item = TestDataBuilder.create_ado_work_item(
            item_id=4001,
            title="Updated Title",
            work_item_type="Task",
            assigned_to=ado_assigned_to,
        )
        ado_work_item.rev = 2
        existing_match = self._make_task_item()

        mock_asana_task = TestDataBuilder.create_asana_task_data(gid="existing_gid", name="Task 4001: Old Title")
        asana_helper = AsanaApiMockHelper()
        mock_tasks_api = asana_helper.create_tasks_api_mock(tasks=[mock_asana_task], updated_task=mock_asana_task)

        try:
            with ExitStack() as stack:
                for patch_ctx in self._setup_asana_api_patches(asana_helper, mock_tasks_api):
                    stack.enter_context(patch_ctx)
                update_task_if_needed(app, ado_work_item, existing_match, [], "AsanaProject", asana_task=mock_asana_task)
        finally:
            app.close()
        return existing_match

    def test_preserves_assignee_when_match_fails(self):
        existing_match = self._run_update_task_if_needed({"displayName": "Ghost User", "uniqueName": "ghost@nowhere.com"})
        self.assertEqual(existing_match.assigned_to, "user-789")

    def test_clears_assignee_when_ado_unassigned(self):
        existing_match = self._run_update_task_if_needed({})
        self.assertIsNone(existing_match.assigned_to)


if __name__ == "__main__":
    unittest.main()

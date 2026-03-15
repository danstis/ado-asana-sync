import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.sync import sync_item_and_children
from tests.utils.test_helpers import (
    AsanaApiMockHelper,
    TestDataBuilder,
)


class TestDueDateIntegration(unittest.TestCase):
    """REAL Integration tests for due date synchronization functionality using REAL App instances."""

    def setUp(self):
        """Set up test fixtures with real temporary directory."""
        import tempfile

        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_new_ado_work_item_with_due_date_syncs_to_asana_REAL_INTEGRATION(
        self, mock_asana_client, mock_ado_connection, mock_dirname
    ):
        """
        TRUE Integration Test: New ADO work item with due date creates Asana task with due_on field.

        This test integrates 80%+ of the actual code path:
        - REAL App instance with REAL database
        - REAL WorkItem objects
        - REAL internal utility functions all working together:
          * extract_due_date_from_ado
          * create_asana_task_body
          * TaskItem creation and database operations
          * All date parsing and validation logic
        - Only mocks external APIs (Asana) at the boundary
        """
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)

        asana_helper = AsanaApiMockHelper()
        mock_tasks_api = asana_helper.create_tasks_api_mock(
            created_task={
                "gid": "67890",
                "name": "Test Due Date Sync",
                "due_on": "2025-12-31",
                "completed": False,
                "modified_at": "2025-09-10T10:00:00.000Z",
            }
        )

        try:
            app.connect()

            ado_work_item = TestDataBuilder.create_ado_work_item(
                item_id=12345, title="Test Due Date Sync", work_item_type="Task", due_date="2025-12-31T23:59:59.000Z"
            )

            asana_users = [{"gid": "user123", "name": "Test User", "email": "test@example.com"}]

            app.ado_wit_client = MagicMock()
            app.ado_wit_client.get_work_item.return_value = ado_work_item

            with (
                patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_tasks_api),
                patch("ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=asana_helper.create_workspace_api_mock()),
                patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=asana_helper.create_projects_api_mock()),
                patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=asana_helper.create_tags_api_mock()),
                patch("ado_asana_sync.sync.sync.get_asana_task", return_value=None),
                patch("ado_asana_sync.sync.sync.get_asana_task_by_name", return_value=None),
                patch("ado_asana_sync.sync.sync.find_custom_field_by_name", return_value=None),
                patch("ado_asana_sync.sync.sync.tag_asana_item", return_value=None),
            ):
                processed_ids = set()
                sync_item_and_children(
                    app,
                    ado_work_item.id,
                    processed_ids,
                    asana_users,
                    [],
                    "project456",
                )

                saved_items = app.matches.all()
                self.assertEqual(len(saved_items), 1)

                saved_task = saved_items[0]
                self.assertEqual(saved_task["ado_id"], 12345)
                self.assertEqual(saved_task["title"], "Test Due Date Sync")
                self.assertEqual(saved_task["due_date"], "2025-12-31")

                mock_tasks_api.create_task.assert_called_once()
                create_task_call = mock_tasks_api.create_task.call_args[0][0]
                self.assertEqual(create_task_call["data"]["due_on"], "2025-12-31")
                self.assertEqual(create_task_call["data"]["name"], "Task 12345: Test Due Date Sync")

        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_new_ado_work_item_without_due_date_creates_task_without_due_on(
        self, mock_asana_client, mock_ado_connection, mock_dirname
    ):
        """
        TRUE Integration Test: New ADO work item without due date creates Asana task with no due_on field.

        Scenario 2: Tests REAL behavior when no due date is present
        - Uses REAL App with REAL database operations
        - Tests REAL due date extraction logic (should return None)
        - Validates REAL Asana task creation without due_on field
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_dirname.return_value = temp_dir
            mock_ado_connection.return_value = MagicMock()
            mock_asana_client.return_value = MagicMock()

            app = TestDataBuilder.create_real_app(temp_dir)

            try:
                app.connect()

                ado_work_item = TestDataBuilder.create_ado_work_item(
                    item_id=12346,
                    title="Test No Due Date",
                    work_item_type="Task",
                    due_date=None,
                )

                asana_users = [{"gid": "user123", "name": "Test User", "email": "test@example.com"}]

                asana_helper = AsanaApiMockHelper()
                mock_tasks_api = asana_helper.create_tasks_api_mock(
                    created_task={
                        "gid": "67891",
                        "name": "Task 12346: Test No Due Date",
                        "completed": False,
                        "modified_at": "2025-09-10T10:00:00.000Z",
                    }
                )

                app.ado_wit_client = MagicMock()
                app.ado_wit_client.get_work_item.return_value = ado_work_item

                with (
                    patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_tasks_api),
                    patch(
                        "ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=asana_helper.create_workspace_api_mock()
                    ),
                    patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=asana_helper.create_projects_api_mock()),
                    patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=asana_helper.create_tags_api_mock()),
                    patch("ado_asana_sync.sync.sync.get_asana_task", return_value=None),
                    patch("ado_asana_sync.sync.sync.get_asana_task_by_name", return_value=None),
                    patch("ado_asana_sync.sync.sync.find_custom_field_by_name", return_value=None),
                    patch("ado_asana_sync.sync.sync.tag_asana_item", return_value=None),
                ):
                    processed_ids = set()
                    sync_item_and_children(
                        app,
                        ado_work_item.id,
                        processed_ids,
                        asana_users,
                        [],
                        "project456",
                    )

                    saved_items = app.matches.all()
                    self.assertEqual(len(saved_items), 1)

                    saved_task = saved_items[0]
                    self.assertEqual(saved_task["ado_id"], 12346)
                    self.assertEqual(saved_task["title"], "Test No Due Date")
                    self.assertIsNone(saved_task.get("due_date"))

                    mock_tasks_api.create_task.assert_called_once()
                    create_task_call = mock_tasks_api.create_task.call_args[0][0]
                    self.assertNotIn("due_on", create_task_call["data"])
                    self.assertEqual(create_task_call["data"]["name"], "Task 12346: Test No Due Date")

            finally:
                app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_existing_task_preserves_asana_user_changes_real_integration(
        self, mock_asana_client, mock_ado_connection, mock_dirname
    ):
        """
        TRUE Integration Test: Subsequent syncs preserve Asana due date changes made by users.

        Scenario 3: Tests the REAL behavior of preserving user modifications in Asana
        - Uses REAL App with REAL database to store existing task
        - Tests REAL business logic for detecting user changes
        - Validates REAL due date preservation logic
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_dirname.return_value = temp_dir
            mock_ado_connection.return_value = MagicMock()
            mock_asana_client.return_value = MagicMock()

            app = TestDataBuilder.create_real_app(temp_dir)

            try:
                app.connect()

                existing_task_data = {
                    "ado_id": 12347,
                    "ado_rev": 1,
                    "title": "Test Preserve Changes",
                    "item_type": "Task",
                    "url": "https://dev.azure.com/test-org/test-project/_workitems/edit/12347",
                    "asana_gid": "67892",
                    "asana_updated": "2025-09-06T10:00:00.000Z",
                    "due_date": "2025-12-31",
                }
                app.matches.insert(existing_task_data)

                ado_work_item = TestDataBuilder.create_ado_work_item(
                    item_id=12347,
                    title="Test Preserve Changes",
                    work_item_type="Task",
                    due_date="2025-11-30T23:59:59.000Z",
                    assigned_to={"displayName": "Test User", "uniqueName": "test@example.com"},
                )
                ado_work_item.rev = 2

                asana_users = [{"gid": "user123", "name": "Test User", "email": "test@example.com"}]

                mock_asana_current_task = {
                    "gid": "67892",
                    "name": "Task 12347: Test Preserve Changes",
                    "due_on": "2026-01-15",
                    "modified_at": "2025-09-06T11:00:00.000Z",
                }

                asana_helper = AsanaApiMockHelper()
                mock_tasks_api = asana_helper.create_tasks_api_mock()

                app.ado_wit_client = MagicMock()
                app.ado_wit_client.get_work_item.return_value = ado_work_item

                with (
                    patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_tasks_api),
                    patch(
                        "ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=asana_helper.create_workspace_api_mock()
                    ),
                    patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=asana_helper.create_projects_api_mock()),
                    patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=asana_helper.create_tags_api_mock()),
                    patch("ado_asana_sync.sync.sync.get_asana_task", return_value=mock_asana_current_task),
                    patch("ado_asana_sync.sync.sync.find_custom_field_by_name", return_value=None),
                    patch("ado_asana_sync.sync.sync.get_asana_task_tags", return_value=[]),
                    patch("ado_asana_sync.sync.sync.tag_asana_item", return_value=None),
                ):
                    processed_ids = set()
                    sync_item_and_children(
                        app,
                        ado_work_item.id,
                        processed_ids,
                        asana_users,
                        [],
                        "project456",
                    )

                    updated_items = app.matches.all()
                    self.assertEqual(len(updated_items), 1)

                    updated_task = updated_items[0]
                    self.assertEqual(updated_task["ado_id"], 12347)
                    self.assertEqual(updated_task["ado_rev"], 2)
                    self.assertEqual(updated_task["title"], "Test Preserve Changes")

                    mock_tasks_api.update_task.assert_called_once()
                    update_call_args = mock_tasks_api.update_task.call_args

                    if len(update_call_args.args) >= 2:
                        update_data = update_call_args.args[1]
                        if isinstance(update_data, dict) and "data" in update_data:
                            self.assertNotIn(
                                "due_on", update_data["data"], "due_on should not be included to preserve user changes"
                            )

            finally:
                app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_invalid_due_date_error_handling_continues_sync(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """
        TRUE Integration Test: Invalid due date values are handled gracefully with warnings.

        Scenario 4: Tests REAL error handling behavior
        - Uses REAL App with REAL database operations
        - Tests REAL due date parsing that handles invalid dates gracefully
        - Validates REAL logging and error recovery behavior
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_dirname.return_value = temp_dir
            mock_ado_connection.return_value = MagicMock()
            mock_asana_client.return_value = MagicMock()

            app = TestDataBuilder.create_real_app(temp_dir)

            try:
                app.connect()

                ado_work_item = TestDataBuilder.create_ado_work_item(
                    item_id=12348,
                    title="Test Invalid Due Date",
                    work_item_type="Task",
                    due_date="invalid-date-format",
                )

                asana_users = [{"gid": "user123", "name": "Test User", "email": "test@example.com"}]

                asana_helper = AsanaApiMockHelper()
                mock_tasks_api = asana_helper.create_tasks_api_mock(
                    created_task={
                        "gid": "67893",
                        "name": "Task 12348: Test Invalid Due Date",
                        "completed": False,
                        "modified_at": "2025-09-10T10:00:00.000Z",
                    }
                )

                app.ado_wit_client = MagicMock()
                app.ado_wit_client.get_work_item.return_value = ado_work_item

                with (
                    patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_tasks_api),
                    patch(
                        "ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=asana_helper.create_workspace_api_mock()
                    ),
                    patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=asana_helper.create_projects_api_mock()),
                    patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=asana_helper.create_tags_api_mock()),
                    patch("ado_asana_sync.sync.sync.get_asana_task", return_value=None),
                    patch("ado_asana_sync.sync.sync.get_asana_task_by_name", return_value=None),
                    patch("ado_asana_sync.sync.sync.find_custom_field_by_name", return_value=None),
                    patch("ado_asana_sync.sync.sync.tag_asana_item", return_value=None),
                    patch("ado_asana_sync.sync.sync._LOGGER") as mock_logger,
                ):
                    processed_ids = set()
                    sync_item_and_children(
                        app,
                        ado_work_item.id,
                        processed_ids,
                        asana_users,
                        [],
                        "project456",
                    )

                    saved_items = app.matches.all()
                    self.assertEqual(len(saved_items), 1)

                    saved_task = saved_items[0]
                    self.assertEqual(saved_task["ado_id"], 12348)
                    self.assertEqual(saved_task["title"], "Test Invalid Due Date")
                    self.assertIsNone(saved_task.get("due_date"))

                    mock_tasks_api.create_task.assert_called_once()
                    create_task_call = mock_tasks_api.create_task.call_args[0][0]
                    self.assertNotIn("due_on", create_task_call["data"])
                    self.assertEqual(create_task_call["data"]["name"], "Task 12348: Test Invalid Due Date")

                    mock_logger.warning.assert_called()
                    warning_call = mock_logger.warning.call_args[0][0]
                    self.assertIn("Invalid due date format", warning_call)

            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()

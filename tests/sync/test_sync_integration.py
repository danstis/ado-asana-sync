import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.sync import sync_project
from tests.utils.test_helpers import (
    AsanaApiMockHelper,
    TestDataBuilder,
)


class TestSyncIntegration(unittest.TestCase):
    """Integration tests for the sync_project functionality using REAL App instances."""

    def setUp(self):
        """Set up test fixtures with real temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        import logging
        logging.basicConfig(level=logging.DEBUG)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _setup_asana_api_patches(self, asana_helper, tasks_api):
        """Set up common Asana API patches for integration tests."""
        return (
            patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=tasks_api),
            patch("ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=asana_helper.create_workspace_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=asana_helper.create_projects_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=asana_helper.create_tags_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.UsersApi", return_value=asana_helper.create_users_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.CustomFieldSettingsApi", return_value=asana_helper.create_custom_field_settings_api_mock()),
        )

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_sync_project_creates_new_task(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """
        Integration Test: sync_project creates a new Asana task from an ADO work item.
        """
        # Set up REAL App with REAL database
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)

        # Set up Asana API mocks
        asana_helper = AsanaApiMockHelper()
        created_task = TestDataBuilder.create_asana_task_data(
            gid="new_task_gid",
            name="Task 1001: New Feature",
        )
        mock_tasks_api = asana_helper.create_tasks_api_mock(created_task=created_task)
        
        try:
            app.connect()

            # Mock ADO client responses AFTER connect
            mock_wit_client = MagicMock()
            app.ado_wit_client = mock_wit_client
            
            # Mock ADO work item
            ado_work_item = TestDataBuilder.create_ado_work_item(
                item_id=1001, 
                title="New Feature", 
                work_item_type="Task",
                assigned_to={"displayName": "Test User", "uniqueName": "test@example.com"}
            )
            mock_wit_client.get_work_item.return_value = ado_work_item
            
            # Mock backlog query response
            mock_work_client = MagicMock()
            app.ado_work_client = mock_work_client
            mock_backlog_item = MagicMock()
            mock_backlog_item.target.id = 1001
            mock_work_client.get_backlog_level_work_items.return_value.work_items = [mock_backlog_item]

            # Mock Core client for project/team resolution
            mock_core_client = MagicMock()
            app.ado_core_client = mock_core_client
            mock_core_client.get_project.return_value.id = "ado_project_id"
            mock_core_client.get_team.return_value.id = "ado_team_id"

            project_config = {
                "adoProjectName": "TestProject",
                "adoTeamName": "TestTeam",
                "asanaProjectName": "AsanaProject",
            }

            with ExitStack() as stack:
                for patch_ctx in self._setup_asana_api_patches(asana_helper, mock_tasks_api):
                    stack.enter_context(patch_ctx)
                sync_project(app, project_config)

                # Verify task was created in Asana
                mock_tasks_api.create_task.assert_called_once()
                create_call = mock_tasks_api.create_task.call_args[0][0]
                self.assertEqual(create_call["data"]["name"], "Task 1001: New Feature")

                # Verify task was saved to DB
                saved_items = app.matches.all()
                self.assertEqual(len(saved_items), 1)
                self.assertEqual(saved_items[0]["ado_id"], 1001)
                self.assertEqual(saved_items[0]["asana_gid"], "new_task_gid")

        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_sync_project_updates_existing_task(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """
        Integration Test: sync_project updates an existing Asana task when ADO item changes.
        """
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        
        app.connect()
        app.matches.insert({
            "ado_id": 1002,
            "ado_rev": 1,
            "title": "Old Title",
            "item_type": "Task",
            "url": "http://ado/1002",
            "asana_gid": "existing_gid",
            "asana_updated": "2025-01-01T10:00:00.000Z",
            "created_date": "2025-01-01T10:00:00.000Z",
            "updated_date": "2025-01-01T10:00:00.000Z",
        })

        # Mock ADO with UPDATED item
        mock_wit_client = MagicMock()
        app.ado_wit_client = mock_wit_client
        ado_work_item = TestDataBuilder.create_ado_work_item(
            item_id=1002, title="New Title", work_item_type="Task"
        )
        ado_work_item.rev = 2 # Increased revision
        mock_wit_client.get_work_item.return_value = ado_work_item

        mock_work_client = MagicMock()
        app.ado_work_client = mock_work_client
        mock_backlog_item = MagicMock()
        mock_backlog_item.target.id = 1002
        mock_work_client.get_backlog_level_work_items.return_value.work_items = [mock_backlog_item]

        mock_core_client = MagicMock()
        app.ado_core_client = mock_core_client
        mock_core_client.get_project.return_value.id = "ado_project_id"
        mock_core_client.get_team.return_value.id = "ado_team_id"

        project_config = {
            "adoProjectName": "TestProject",
            "adoTeamName": "TestTeam",
            "asanaProjectName": "AsanaProject",
        }

        asana_helper = AsanaApiMockHelper()
        # Mock existing Asana task
        mock_asana_task = TestDataBuilder.create_asana_task_data(
            gid="existing_gid",
            name="Task 1002: Old Title",
        )
        mock_tasks_api = asana_helper.create_tasks_api_mock(tasks=[mock_asana_task], updated_task=mock_asana_task)

        try:
            with ExitStack() as stack:
                for patch_ctx in self._setup_asana_api_patches(asana_helper, mock_tasks_api):
                    stack.enter_context(patch_ctx)
                sync_project(app, project_config)

                # Verify update was called
                mock_tasks_api.update_task.assert_called_once()
                update_call = mock_tasks_api.update_task.call_args[0][0]  # body is first arg
                self.assertEqual(update_call["data"]["name"], "Task 1002: New Title")

                # Verify DB updated
                saved_item = app.matches.search(lambda x: x["ado_id"] == 1002)[0]
                self.assertEqual(saved_item["title"], "New Title")
                self.assertEqual(saved_item["ado_rev"], 2)

        finally:
            app.close()

"""
Tests for App class database functionality.

This module contains tests specifically for the database-related
functionality in the App class, including SQLite initialization,
migration, and project synchronization.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.app import App


class TestAppDatabase(unittest.TestCase):
    """Test cases for App class database functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()

        # Mock environment variables to avoid validation errors
        self.env_vars = {
            "ADO_PAT": "test_pat",
            "ADO_URL": "https://dev.azure.com/test",
            "ASANA_TOKEN": "test_token",
            "ASANA_WORKSPACE_NAME": "test_workspace",
        }

    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up any created files
        for file in os.listdir(self.test_dir):
            try:
                os.remove(os.path.join(self.test_dir, file))
            except OSError:
                pass
        try:
            os.rmdir(self.test_dir)
        except OSError:
            pass

    @patch.dict(
        os.environ,
        {
            "ADO_PAT": "test_pat",
            "ADO_URL": "https://dev.azure.com/test",
            "ASANA_TOKEN": "test_token",
            "ASANA_WORKSPACE_NAME": "test_workspace",
        },
    )
    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_connect_creates_data_directory(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """Test that connect() creates the data directory if it doesn't exist.

        This test focuses on database initialization while only mocking external APIs.
        Internal file system operations and directory creation are tested realistically.
        """
        # Setup external API mocks only
        mock_dirname.return_value = self.test_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        # Create app and connect
        app = App()

        # Create a projects.json file for the sync
        data_dir = os.path.join(self.test_dir, "data")
        projects_path = os.path.join(data_dir, "projects.json")
        os.makedirs(data_dir, exist_ok=True)

        projects_data = [{"adoProjectName": "TestProject", "adoTeamName": "TestTeam", "asanaProjectName": "TestAsanaProject"}]

        with open(projects_path, "w", encoding="utf-8") as f:
            json.dump(projects_data, f)

        app.connect()

        # Verify data directory was created (real file system operation)
        self.assertTrue(os.path.exists(data_dir))

        # Verify database was initialized (integration with real database components)
        self.assertIsNotNone(app.db)
        self.assertIsNotNone(app.matches)
        self.assertIsNotNone(app.pr_matches)
        self.assertIsNotNone(app.config)

        # Clean up
        app.close()

    @patch.dict(
        os.environ,
        {
            "ADO_PAT": "test_pat",
            "ADO_URL": "https://dev.azure.com/test",
            "ASANA_TOKEN": "test_token",
            "ASANA_WORKSPACE_NAME": "test_workspace",
        },
    )
    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_connect_migrates_existing_tinydb(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """Test that connect() migrates existing TinyDB data.

        This test focuses on the database migration functionality, allowing the
        internal migration logic to work while only mocking external APIs.
        """
        # Setup external API mocks only
        mock_dirname.return_value = self.test_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        # Create existing appdata.json file
        data_dir = os.path.join(self.test_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        appdata_path = os.path.join(data_dir, "appdata.json")
        tinydb_data = {"matches": {"1": {"ado_id": 123, "title": "Test Task", "item_type": "Bug"}}}

        with open(appdata_path, "w", encoding="utf-8") as f:
            json.dump(tinydb_data, f)

        # Create projects.json
        projects_path = os.path.join(data_dir, "projects.json")
        projects_data = [{"adoProjectName": "TestProject", "adoTeamName": "TestTeam", "asanaProjectName": "TestAsanaProject"}]

        with open(projects_path, "w", encoding="utf-8") as f:
            json.dump(projects_data, f)

        # Create app and connect
        app = App()
        app.connect()

        # Verify migration occurred
        migrated_path = appdata_path + ".migrated"
        self.assertTrue(os.path.exists(migrated_path))
        self.assertFalse(os.path.exists(appdata_path))

        # Verify data was migrated
        matches = app.matches.all()
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["ado_id"], 123)
        self.assertEqual(matches[0]["title"], "Test Task")

        # Clean up
        app.close()

    @patch.dict(
        os.environ,
        {
            "ADO_PAT": "test_pat",
            "ADO_URL": "https://dev.azure.com/test",
            "ASANA_TOKEN": "test_token",
            "ASANA_WORKSPACE_NAME": "test_workspace",
        },
    )
    @patch("ado_asana_sync.sync.app.configure_azure_monitor")
    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_sync_projects_from_json(self, mock_asana_client, mock_ado_connection, mock_dirname, mock_configure):
        """Test that projects are synced from JSON on connect."""
        # Setup mocks
        mock_dirname.return_value = self.test_dir
        mock_configure.return_value = None
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        # Create projects.json
        data_dir = os.path.join(self.test_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        projects_path = os.path.join(data_dir, "projects.json")

        projects_data = [
            {"adoProjectName": "Project1", "adoTeamName": "Team1", "asanaProjectName": "AsanaProject1"},
            {"adoProjectName": "Project2", "adoTeamName": "Team2", "asanaProjectName": "AsanaProject2"},
        ]

        with open(projects_path, "w", encoding="utf-8") as f:
            json.dump(projects_data, f)

        # Create app and connect
        app = App()
        app.connect()

        # Verify projects were synced
        projects = app.db.get_projects()
        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0]["adoProjectName"], "Project1")
        self.assertEqual(projects[1]["adoProjectName"], "Project2")

        # Clean up
        app.close()

    @patch.dict(
        os.environ,
        {
            "ADO_PAT": "test_pat",
            "ADO_URL": "https://dev.azure.com/test",
            "ASANA_TOKEN": "test_token",
            "ASANA_WORKSPACE_NAME": "test_workspace",
        },
    )
    @patch("ado_asana_sync.sync.app.configure_azure_monitor")
    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_close_cleans_up_database(self, mock_asana_client, mock_ado_connection, mock_dirname, mock_configure):
        """Test that close() properly cleans up database resources."""
        # Setup mocks
        mock_dirname.return_value = self.test_dir
        mock_configure.return_value = None
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        # Create minimal projects.json
        data_dir = os.path.join(self.test_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        projects_path = os.path.join(data_dir, "projects.json")

        with open(projects_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        # Create app and connect
        app = App()
        app.connect()

        # Verify database is initialized
        self.assertIsNotNone(app.db)

        # Close and verify cleanup
        app.close()
        self.assertIsNone(app.db)

    @patch.dict(
        os.environ,
        {
            "ADO_PAT": "test_pat",
            "ADO_URL": "https://dev.azure.com/test",
            "ASANA_TOKEN": "test_token",
            "ASANA_WORKSPACE_NAME": "test_workspace",
        },
    )
    @patch("ado_asana_sync.sync.app.configure_azure_monitor")
    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_sync_projects_handles_missing_file(self, mock_asana_client, mock_ado_connection, mock_dirname, mock_configure):
        """Test that missing projects.json is handled gracefully."""
        # Setup mocks
        mock_dirname.return_value = self.test_dir
        mock_configure.return_value = None
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        # Create data directory but no projects.json
        data_dir = os.path.join(self.test_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        # Create app and connect - should not fail
        app = App()
        app.connect()

        # Verify app still works
        self.assertIsNotNone(app.db)

        # Clean up
        app.close()


if __name__ == "__main__":
    unittest.main()

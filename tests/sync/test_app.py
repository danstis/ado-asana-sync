import os
import unittest
from unittest.mock import patch

from ado_asana_sync.sync.app import App


class TestApp(unittest.TestCase):
    def test_app_instance_created_with_parameters(self):
        """Test App instance creation with explicit parameters."""
        app = App(
            ado_pat="test_pat",
            ado_url="https://dev.azure.com/test",
            asana_token="test_token",
            asana_workspace_name="test_workspace",
        )

        self.assertEqual(app.ado_pat, "test_pat")
        self.assertEqual(app.ado_url, "https://dev.azure.com/test")
        self.assertEqual(app.asana_token, "test_token")
        self.assertEqual(app.asana_workspace_name, "test_workspace")
        self.assertEqual(app.asana_page_size, 100)

        # Clients should be None until connect() is called
        self.assertIsNone(app.ado_core_client)
        self.assertIsNone(app.ado_work_client)
        self.assertIsNone(app.ado_wit_client)
        self.assertIsNone(app.asana_client)

    @patch.dict(
        os.environ,
        {
            "ADO_PAT": "env_pat",
            "ADO_URL": "https://dev.azure.com/env",
            "ASANA_TOKEN": "env_token",
            "ASANA_WORKSPACE_NAME": "env_workspace",
        },
    )
    def test_app_instance_created_from_environment(self):
        """Test App instance creation using environment variables."""
        app = App()

        self.assertEqual(app.ado_pat, "env_pat")
        self.assertEqual(app.ado_url, "https://dev.azure.com/env")
        self.assertEqual(app.asana_token, "env_token")
        self.assertEqual(app.asana_workspace_name, "env_workspace")

    def test_app_raises_error_for_missing_required_parameters(self):
        """Test that App raises ValueError when required parameters are
        missing."""
        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as context:
                App()

            # Should mention missing required environment variables
            error_message = str(context.exception)
            self.assertIn("ADO_PAT", error_message)

    def test_asana_page_size_can_be_modified(self):
        """Test that Asana page size can be modified."""
        app = App(
            ado_pat="test_pat",
            ado_url="https://dev.azure.com/test",
            asana_token="test_token",
            asana_workspace_name="test_workspace",
        )

        # Default page size
        self.assertEqual(app.asana_page_size, 100)

        # Modify page size
        app.asana_page_size = 50
        self.assertEqual(app.asana_page_size, 50)

    def test_app_close_cleans_up_database(self):
        """Test that close() method cleans up resources."""
        app = App(
            ado_pat="test_pat",
            ado_url="https://dev.azure.com/test",
            asana_token="test_token",
            asana_workspace_name="test_workspace",
        )

        # Initially no database
        self.assertIsNone(app.db)

        # Simulate having a database
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        app.db = mock_db

        # Close should clean up
        app.close()

        # Database should be closed and set to None
        mock_db.close.assert_called_once()
        self.assertIsNone(app.db)

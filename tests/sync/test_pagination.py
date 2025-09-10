import unittest
from unittest.mock import MagicMock, patch

from asana.rest import ApiException

from ado_asana_sync.sync import sync
from ado_asana_sync.sync.app import App
from ado_asana_sync.sync.sync import (
    get_asana_project_custom_fields,
    get_asana_project_tasks,
)


class TestPaginationFunctions(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(App)
        self.app.asana_client = MagicMock()
        self.app.asana_page_size = 50

    def test_get_asana_project_tasks_passes_correct_parameters(self):
        """Test that the function passes correct parameters to the API."""
        mock_api = MagicMock()
        mock_api.get_tasks.return_value = iter([{"gid": "1"}, {"gid": "2"}])

        with patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_api):
            tasks = get_asana_project_tasks(self.app, "project_123")

        # Verify the function returns the correct results
        self.assertEqual(tasks, [{"gid": "1"}, {"gid": "2"}])

        # Verify the API was called with correct parameters
        mock_api.get_tasks.assert_called_once()
        call_args = mock_api.get_tasks.call_args[0][0]
        self.assertEqual(call_args["project"], "project_123")
        self.assertEqual(call_args["limit"], 50)
        self.assertIn("assignee_section,due_at,name", call_args["opt_fields"])

    def test_get_asana_project_tasks_handles_api_exception(self):
        """Test that API exceptions are handled correctly."""
        mock_api = MagicMock()
        mock_api.get_tasks.side_effect = ApiException("API Error")

        with patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_api):
            tasks = get_asana_project_tasks(self.app, "project_123")

        # Should return empty list on API exception
        self.assertEqual(tasks, [])

    def test_get_asana_project_custom_fields_caching_logic(self):
        """Test custom fields caching logic."""
        # Clear cache and enable custom fields
        sync.CUSTOM_FIELDS_CACHE.clear()
        sync.CUSTOM_FIELDS_AVAILABLE = True

        mock_api = MagicMock()
        mock_api.get_custom_field_settings_for_project.return_value = iter([{"gid": "cf1"}])

        with patch("ado_asana_sync.sync.sync.asana.CustomFieldSettingsApi", return_value=mock_api):
            # First call should hit the API
            fields1 = get_asana_project_custom_fields(self.app, "project_123")

            # Second call should use cache
            fields2 = get_asana_project_custom_fields(self.app, "project_123")

        self.assertEqual(fields1, [{"gid": "cf1"}])
        self.assertEqual(fields2, [{"gid": "cf1"}])

        # API should only be called once due to caching
        mock_api.get_custom_field_settings_for_project.assert_called_once()

    def test_get_asana_project_custom_fields_disabled(self):
        """Test that custom fields returns empty when disabled."""
        sync.CUSTOM_FIELDS_AVAILABLE = False

        fields = get_asana_project_custom_fields(self.app, "project_123")

        self.assertEqual(fields, [])

    def test_get_asana_project_custom_fields_handles_402_exception(self):
        """Test that 402 (payment required) exception disables custom
        fields."""
        sync.CUSTOM_FIELDS_CACHE.clear()
        sync.CUSTOM_FIELDS_AVAILABLE = True

        mock_api = MagicMock()
        api_exception = ApiException("Payment required")
        api_exception.status = 402
        mock_api.get_custom_field_settings_for_project.side_effect = api_exception

        with patch("ado_asana_sync.sync.sync.asana.CustomFieldSettingsApi", return_value=mock_api):
            fields = get_asana_project_custom_fields(self.app, "project_123")

        # Should return empty list and disable custom fields for future calls
        self.assertEqual(fields, [])
        self.assertFalse(sync.CUSTOM_FIELDS_AVAILABLE)

    def test_get_asana_project_custom_fields_handles_other_api_exceptions(self):
        """Test that other API exceptions return empty list."""
        sync.CUSTOM_FIELDS_CACHE.clear()
        sync.CUSTOM_FIELDS_AVAILABLE = True

        mock_api = MagicMock()
        api_exception = ApiException("Other error")
        api_exception.status = 500
        mock_api.get_custom_field_settings_for_project.side_effect = api_exception

        with patch("ado_asana_sync.sync.sync.asana.CustomFieldSettingsApi", return_value=mock_api):
            fields = get_asana_project_custom_fields(self.app, "project_123")

        self.assertEqual(fields, [])


if __name__ == "__main__":
    unittest.main()

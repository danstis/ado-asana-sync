import unittest
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.app import App
from ado_asana_sync.sync import sync
from ado_asana_sync.sync.sync import (
    get_asana_project_tasks,
    get_asana_project_custom_fields,
)


class TestPaginationFunctions(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(App)
        self.app.asana_client = MagicMock()
        self.app.asana_page_size = 50

    def test_get_asana_project_tasks_uses_iterator(self):
        mock_api = MagicMock()
        mock_api.get_tasks.return_value = iter([{"gid": "1"}, {"gid": "2"}])
        with patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_api):
            tasks = get_asana_project_tasks(self.app, "proj1")
        self.assertEqual(tasks, [{"gid": "1"}, {"gid": "2"}])
        mock_api.get_tasks.assert_called_once()

    def test_get_asana_project_custom_fields_uses_iterator(self):
        sync.CUSTOM_FIELDS_CACHE.clear()
        sync.CUSTOM_FIELDS_AVAILABLE = True
        mock_api = MagicMock()
        mock_api.get_custom_field_settings_for_project.return_value = iter([{"gid": "cf"}])
        with patch(
            "ado_asana_sync.sync.sync.asana.CustomFieldSettingsApi",
            return_value=mock_api,
        ):
            fields = get_asana_project_custom_fields(self.app, "123")
        self.assertEqual(fields, [{"gid": "cf"}])
        mock_api.get_custom_field_settings_for_project.assert_called_once()


if __name__ == "__main__":
    unittest.main()

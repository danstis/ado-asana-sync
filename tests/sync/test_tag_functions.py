import unittest
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.app import App
from ado_asana_sync.sync.sync import (
    create_tag_if_not_existing,
    get_asana_task_tags,
    get_tag_by_name,
)
from ado_asana_sync.sync.task_item import TaskItem


class TestTagFunctions(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(App)
        self.app.asana_client = MagicMock()
        self.app.db_lock = MagicMock()
        self.app.config = MagicMock()

    def test_create_tag_returns_existing_config(self):
        self.app.config.get.return_value = {"tag_gid": "111"}
        tag = create_tag_if_not_existing(self.app, "ws", "tag")
        self.assertEqual(tag, "111")
        self.app.config.get.assert_called_once_with(doc_id=1)

    def test_get_tag_by_name_found(self):
        mock_api = MagicMock()
        mock_api.get_tags.return_value = iter([{"name": "foo", "gid": "1"}])
        with patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=mock_api):
            tag = get_tag_by_name(self.app, "ws", "foo")
        self.assertEqual(tag, {"name": "foo", "gid": "1"})

    def test_get_asana_task_tags(self):
        task = TaskItem(1, 1, "t", "Bug", "url", asana_gid="g")
        mock_api = MagicMock()
        mock_api.get_tags_for_task.return_value = iter([{"gid": "2"}])
        with patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=mock_api):
            tags = get_asana_task_tags(self.app, task)
        self.assertEqual(tags, [{"gid": "2"}])


if __name__ == "__main__":
    unittest.main()

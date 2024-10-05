import unittest
from unittest.mock import MagicMock

from ado_asana_sync.sync.app import App
from ado_asana_sync.sync.task_item import TaskItem

TEST_TASK_ITEM_1 = TaskItem(
    ado_id=1,
    ado_rev=1,
    title="Test Task",
    item_type="Bug",
    url="https://dev.azure.com/ado_org/ado_project/_workitems/edit/1",
    asana_gid="123456",
    asana_updated="2023-08-01T03:00:00.000000+00:00",
    assigned_to=None,
    created_date="2023-08-01T01:00:00.000000+00:00",
    updated_date="2023-08-01T02:00:00.000000+00:00",
)
TEST_DB_ITEM_1 = {
    "ado_id": 1,
    "ado_rev": 1,
    "title": "Test Task",
    "item_type": "Bug",
    "url": "https://dev.azure.com/ado_org/ado_project/_workitems/edit/1",
    "asana_gid": "123456",
    "asana_updated": "2023-08-01T03:00:00.000000+00:00",
    "assigned_to": None,
    "created_date": "2023-08-01T01:00:00.000000+00:00",
    "updated_date": "2023-08-01T02:00:00.000000+00:00",
}


class TestTaskItem(unittest.TestCase):
    # Tests that a TaskItem instance is created successfully with valid arguments.
    def test_task_item_str(self):
        # Call the __str__ method and check the result
        assert str(TEST_TASK_ITEM_1) == "Bug 1: Test Task"

    # Returns the TaskItem object with the matching ADO ID.
    def test_returns_task_item_with_matching_ado_id(self):
        # Create a mock App instance
        app = MagicMock(App)
        app.db_lock = MagicMock()

        with app.db_lock:
            app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        with app.db_lock:
            app.matches.contains.return_value = True
        # Mock the search method of the matches table to return a mock TaskItem object
        with app.db_lock:
            app.matches.search.return_value = [TEST_DB_ITEM_1]

        # Call the find_by_ado_id method with a valid ADO ID
        result = TaskItem.find_by_ado_id(app, 1)

        # Assert that the result is the mock TaskItem object
        self.assertEqual(result.ado_id, 1)
        self.assertEqual(result.ado_rev, 1)
        self.assertEqual(result.title, "Test Task")
        self.assertEqual(result.item_type, "Bug")
        self.assertEqual(
            result.url, "https://dev.azure.com/ado_org/ado_project/_workitems/edit/1"
        )
        self.assertEqual(result.asana_gid, "123456")
        self.assertEqual(result.asana_updated, "2023-08-01T03:00:00.000000+00:00")
        self.assertIsNone(result.assigned_to)
        self.assertEqual(result.created_date, "2023-08-01T01:00:00.000000+00:00")
        self.assertEqual(result.updated_date, "2023-08-01T02:00:00.000000+00:00")

    # Tests that None is returned if there is no matching item.
    def test_returns_task_item_with_no_matching_ado_id(self):
        # Create a mock App instance
        app = MagicMock(App)
        app.db_lock = MagicMock()

        with app.db_lock:
            app.matches = MagicMock()

        # Mock the contains method of the matches table to return False
        with app.db_lock:
            app.matches.contains.return_value = False

        # Call the find_by_ado_id method with a non-existing ADO ID
        result = TaskItem.find_by_ado_id(app, 1)

        # Assert that the result is None
        self.assertIsNone(result)

    # Test that the search method returns None if the given ADO ID and Asana GID are None.
    def test_returns_none_if_ado_id_and_asana_gid_are_none(self):
        # Create a mock App instance
        app = MagicMock(App)
        app.db_lock = MagicMock()

        with app.db_lock:
            app.matches = MagicMock()

        # Call the search method with None for both ado_id and asana_gid
        result = TaskItem.search(app, None, None)  # NOSONAR

        # Assert that the result is None
        self.assertIsNone(result)

    # Test that the search method returns a matching task by ado_id when one exists.
    def test_search_with_valid_ado_id(self):
        # Create a mock App instance
        app = MagicMock(App)
        app.db_lock = MagicMock()

        with app.db_lock:
            app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        with app.db_lock:
            app.matches.contains.return_value = True
        # Mock the search method of the matches table to return a mock TaskItem object
        with app.db_lock:
            app.matches.search.return_value = [TEST_DB_ITEM_1]

        # Call the search method with an ado_id.
        result = TaskItem.search(app, ado_id=1)

        self.assertEqual(result, TEST_TASK_ITEM_1)

    # Test that the search method returns a matching task by asana_guid when one exists.
    def test_search_with_valid_asana_guid(self):
        # Create a mock App instance
        app = MagicMock(App)
        app.db_lock = MagicMock()

        with app.db_lock:
            app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        with app.db_lock:
            app.matches.contains.return_value = True
        # Mock the search method of the matches table to return a mock TaskItem object
        with app.db_lock:
            app.matches.search.return_value = [TEST_DB_ITEM_1]

        # Call the search method with an ado_id.
        result = TaskItem.search(app, asana_gid="123456")

        self.assertEqual(result, TEST_TASK_ITEM_1)

    # Test that the search method returns none when searching a task by ado_id that does not exist.
    def test_search_with_invalid_ado_id(self):
        # Create a mock App instance
        app = MagicMock(App)
        app.db_lock = MagicMock()

        with app.db_lock:
            app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        with app.db_lock:
            app.matches.contains.return_value = False

        # Call the search method with an ado_id.
        result = TaskItem.search(app, ado_id=5)

        self.assertIsNone(result)

    # Test that the search method returns none when searching a task by asana_guid that does not exist.
    def test_search_with_invalid_asana_guid(self):
        # Create a mock App instance
        app = MagicMock(App)
        app.db_lock = MagicMock()

        with app.db_lock:
            app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        with app.db_lock:
            app.matches.contains.return_value = False

        # Call the search method with an ado_id.
        result = TaskItem.search(app, asana_gid="987654")

        self.assertIsNone(result)

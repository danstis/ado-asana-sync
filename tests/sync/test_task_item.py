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

        app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        app.matches.contains.return_value = True
        # Mock the search method of the matches table to return a mock TaskItem object
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

        app.matches = MagicMock()

        # Mock the contains method of the matches table to return False
        app.matches.contains.return_value = False

        # Call the find_by_ado_id method with a non-existing ADO ID
        result = TaskItem.find_by_ado_id(app, 1)

        # Assert that the result is None
        self.assertIsNone(result)

    # Test that the search method returns None if the given ADO ID and Asana GID are None.
    def test_returns_none_if_ado_id_and_asana_gid_are_none(self):
        # Create a mock App instance
        app = MagicMock(App)

        app.matches = MagicMock()

        # Call the search method with None for both ado_id and asana_gid
        result = TaskItem.search(app, None, None)  # NOSONAR

        # Assert that the result is None
        self.assertIsNone(result)

    # Test that the search method returns a matching task by ado_id when one exists.
    def test_search_with_valid_ado_id(self):
        # Create a mock App instance
        app = MagicMock(App)

        app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        app.matches.contains.return_value = True
        # Mock the search method of the matches table to return a mock TaskItem object
        app.matches.search.return_value = [TEST_DB_ITEM_1]

        # Call the search method with an ado_id.
        result = TaskItem.search(app, ado_id=1)

        self.assertEqual(result, TEST_TASK_ITEM_1)

    # Test that the search method returns a matching task by asana_guid when one exists.
    def test_search_with_valid_asana_guid(self):
        # Create a mock App instance
        app = MagicMock(App)

        app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        app.matches.contains.return_value = True
        # Mock the search method of the matches table to return a mock TaskItem object
        app.matches.search.return_value = [TEST_DB_ITEM_1]

        # Call the search method with an ado_id.
        result = TaskItem.search(app, asana_gid="123456")

        self.assertEqual(result, TEST_TASK_ITEM_1)

    # Test that the search method returns none when searching a task by ado_id that does not exist.
    def test_search_with_invalid_ado_id(self):
        # Create a mock App instance
        app = MagicMock(App)

        app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        app.matches.contains.return_value = False

        # Call the search method with an ado_id.
        result = TaskItem.search(app, ado_id=5)

        self.assertIsNone(result)

    # Test that the search method returns none when searching a task by asana_guid that does not exist.
    def test_search_with_invalid_asana_guid(self):
        # Create a mock App instance
        app = MagicMock(App)

        app.matches = MagicMock()

        # Mock the contains method of the matches table to return True
        app.matches.contains.return_value = False

        # Call the search method with an ado_id.
        result = TaskItem.search(app, asana_gid="987654")

        self.assertIsNone(result)

    def test_search_filters_doc_id_from_database_results(self):
        """Regression test: Ensure doc_id is filtered out when creating TaskItem from database results."""
        app = MagicMock()
        app.matches = MagicMock()
        app.matches.contains.return_value = True
        
        # Mock database result that includes doc_id (this would cause constructor error if not filtered)
        mock_db_result = {
            "ado_id": 123,
            "ado_rev": 5,
            "title": "Test Task",
            "item_type": "Bug",
            "url": "https://example.com/123",
            "asana_gid": "asana-123",
            "asana_updated": "2023-12-01T10:00:00Z",
            "assigned_to": "user-456",
            "created_date": "2023-12-01T09:00:00Z",
            "updated_date": "2023-12-01T10:00:00Z",
            "doc_id": 999  # This should be filtered out
        }
        app.matches.search.return_value = [mock_db_result]
        
        # This should not raise an error about unexpected doc_id argument
        result = TaskItem.search(app, ado_id=123)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.ado_id, 123)
        self.assertEqual(result.title, "Test Task")
        # Verify doc_id is not present in the created object
        self.assertFalse(hasattr(result, 'doc_id'))

    def test_find_by_ado_id_filters_doc_id_from_database_results(self):
        """Regression test: Ensure doc_id is filtered out in find_by_ado_id method."""
        app = MagicMock()
        app.matches = MagicMock()
        app.matches.contains.return_value = True
        
        # Mock database result with doc_id
        mock_db_result = {
            "ado_id": 456,
            "ado_rev": 3,
            "title": "Another Test Task",
            "item_type": "User Story",
            "url": "https://example.com/456",
            "doc_id": 777  # This should be filtered out
        }
        app.matches.search.return_value = [mock_db_result]
        
        # This should not raise an error about unexpected doc_id argument
        result = TaskItem.find_by_ado_id(app, 456)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.ado_id, 456)
        self.assertEqual(result.title, "Another Test Task")
        # Verify doc_id is not present in the created object
        self.assertFalse(hasattr(result, 'doc_id'))

    def test_search_returns_none_when_items_list_empty(self):
        """Test that search returns None when matches.search returns empty list."""
        app = MagicMock()
        app.matches = MagicMock()
        app.matches.contains.return_value = True
        app.matches.search.return_value = []  # Empty list
        
        result = TaskItem.search(app, ado_id=123)
        
        self.assertIsNone(result)

    def test_find_by_ado_id_returns_none_when_items_list_empty(self):
        """Test that find_by_ado_id returns None when matches.search returns empty list."""
        app = MagicMock()
        app.matches = MagicMock()
        app.matches.contains.return_value = True
        app.matches.search.return_value = []  # Empty list
        
        result = TaskItem.find_by_ado_id(app, 123)
        
        self.assertIsNone(result)

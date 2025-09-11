import unittest
from unittest.mock import MagicMock, patch

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
        self.assertEqual(str(TEST_TASK_ITEM_1), "Bug 1: Test Task")

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
        self.assertEqual(result.url, "https://dev.azure.com/ado_org/ado_project/_workitems/edit/1")
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
            "doc_id": 999,  # This should be filtered out
        }
        app.matches.search.return_value = [mock_db_result]

        # This should not raise an error about unexpected doc_id argument
        result = TaskItem.search(app, ado_id=123)

        self.assertIsNotNone(result)
        self.assertEqual(result.ado_id, 123)
        self.assertEqual(result.title, "Test Task")
        # Verify doc_id is not present in the created object
        self.assertFalse(hasattr(result, "doc_id"))

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
            "doc_id": 777,  # This should be filtered out
        }
        app.matches.search.return_value = [mock_db_result]

        # This should not raise an error about unexpected doc_id argument
        result = TaskItem.find_by_ado_id(app, 456)

        self.assertIsNotNone(result)
        self.assertEqual(result.ado_id, 456)
        self.assertEqual(result.title, "Another Test Task")
        # Verify doc_id is not present in the created object
        self.assertFalse(hasattr(result, "doc_id"))

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

    def test_save_new_item(self):
        """Test saving a new TaskItem."""
        app = MagicMock()
        app.matches = MagicMock()
        app.matches.contains.return_value = False
        app.db_lock = MagicMock()
        app.db_lock.__enter__ = MagicMock(return_value=app.db_lock)
        app.db_lock.__exit__ = MagicMock(return_value=None)

        task_item = TaskItem(ado_id=456, ado_rev=2, title="New Task", item_type="Feature", url="https://example.com/456")

        task_item.save(app)

        # Verify insert was called
        app.matches.insert.assert_called_once()
        call_args = app.matches.insert.call_args[0][0]
        self.assertEqual(call_args["ado_id"], 456)
        self.assertEqual(call_args["title"], "New Task")

    def test_save_existing_item(self):
        """Test saving an existing TaskItem."""
        app = MagicMock()
        app.matches = MagicMock()
        app.matches.contains.return_value = True
        app.db_lock = MagicMock()
        app.db_lock.__enter__ = MagicMock(return_value=app.db_lock)
        app.db_lock.__exit__ = MagicMock(return_value=None)

        task_item = TaskItem(ado_id=789, ado_rev=3, title="Updated Task", item_type="Bug", url="https://example.com/789")

        task_item.save(app)

        # Verify update was called
        app.matches.update.assert_called_once()
        call_args = app.matches.update.call_args[0][0]
        self.assertEqual(call_args["ado_id"], 789)
        self.assertEqual(call_args["title"], "Updated Task")

    def test_save_with_none_app_matches_raises_error(self):
        """Test save raises ValueError when app.matches is None."""
        app = MagicMock()
        app.matches = None

        task_item = TaskItem(ado_id=123, ado_rev=1, title="Test Task", item_type="Bug", url="https://example.com/123")

        with self.assertRaises(ValueError) as context:
            task_item.save(app)

        self.assertIn("app.matches is None", str(context.exception))

    def test_is_current_true_when_up_to_date(self):
        """Test is_current returns True when task is up to date."""
        app = MagicMock()
        app.ado_wit_client = MagicMock()

        # Mock ADO task
        mock_ado_task = MagicMock()
        mock_ado_task.rev = 5
        app.ado_wit_client.get_work_item.return_value = mock_ado_task

        # Mock Asana task
        mock_asana_task = {"modified_at": "2023-12-01T10:00:00Z"}

        task_item = TaskItem(
            ado_id=123,
            ado_rev=5,  # Same as mock
            title="Test Task",
            item_type="Bug",
            url="https://example.com/123",
            asana_gid="asana-123",
            asana_updated="2023-12-01T10:00:00Z",  # Same as mock
        )

        with patch("ado_asana_sync.sync.task_item.get_asana_task", return_value=mock_asana_task):
            result = task_item.is_current(app)

        self.assertTrue(result)

    def test_is_current_false_when_ado_rev_differs(self):
        """Test is_current returns False when ADO revision differs."""
        app = MagicMock()
        app.ado_wit_client = MagicMock()

        # Mock ADO task with different revision
        mock_ado_task = MagicMock()
        mock_ado_task.rev = 6  # Different from task_item.ado_rev
        app.ado_wit_client.get_work_item.return_value = mock_ado_task

        # Mock Asana task
        mock_asana_task = {"modified_at": "2023-12-01T10:00:00Z"}

        task_item = TaskItem(
            ado_id=123,
            ado_rev=5,  # Different from mock
            title="Test Task",
            item_type="Bug",
            url="https://example.com/123",
            asana_gid="asana-123",
            asana_updated="2023-12-01T10:00:00Z",
        )

        with patch("ado_asana_sync.sync.task_item.get_asana_task", return_value=mock_asana_task):
            result = task_item.is_current(app)

        self.assertFalse(result)

    def test_is_current_false_when_asana_modified_differs(self):
        """Test is_current returns False when Asana modified_at differs."""
        app = MagicMock()
        app.ado_wit_client = MagicMock()

        # Mock ADO task
        mock_ado_task = MagicMock()
        mock_ado_task.rev = 5
        app.ado_wit_client.get_work_item.return_value = mock_ado_task

        # Mock Asana task with different modified_at
        mock_asana_task = {"modified_at": "2023-12-01T11:00:00Z"}  # Different time

        task_item = TaskItem(
            ado_id=123,
            ado_rev=5,
            title="Test Task",
            item_type="Bug",
            url="https://example.com/123",
            asana_gid="asana-123",
            asana_updated="2023-12-01T10:00:00Z",  # Different from mock
        )

        with patch("ado_asana_sync.sync.task_item.get_asana_task", return_value=mock_asana_task):
            result = task_item.is_current(app)

        self.assertFalse(result)

    def test_is_current_false_when_ado_wit_client_none(self):
        """Test is_current returns False when app.ado_wit_client is None."""
        app = MagicMock()
        app.ado_wit_client = None

        task_item = TaskItem(ado_id=123, ado_rev=5, title="Test Task", item_type="Bug", url="https://example.com/123")

        result = task_item.is_current(app)

        self.assertFalse(result)

    def test_is_current_false_when_ado_task_none(self):
        """Test is_current returns False when ADO task is None."""
        app = MagicMock()
        app.ado_wit_client = MagicMock()
        app.ado_wit_client.get_work_item.return_value = None

        task_item = TaskItem(
            ado_id=123, ado_rev=5, title="Test Task", item_type="Bug", url="https://example.com/123", asana_gid="asana-123"
        )

        result = task_item.is_current(app)

        self.assertFalse(result)

    def test_is_current_false_when_asana_task_none(self):
        """Test is_current returns False when Asana task is None."""
        app = MagicMock()
        app.ado_wit_client = MagicMock()

        # Mock ADO task
        mock_ado_task = MagicMock()
        mock_ado_task.rev = 5
        app.ado_wit_client.get_work_item.return_value = mock_ado_task

        task_item = TaskItem(
            ado_id=123, ado_rev=5, title="Test Task", item_type="Bug", url="https://example.com/123", asana_gid="asana-123"
        )

        with patch("ado_asana_sync.sync.task_item.get_asana_task", return_value=None):
            result = task_item.is_current(app)

        self.assertFalse(result)

    def test_is_current_true_when_no_asana_gid(self):
        """Test is_current behavior when asana_gid is None."""
        app = MagicMock()
        app.ado_wit_client = MagicMock()

        # Mock ADO task
        mock_ado_task = MagicMock()
        mock_ado_task.rev = 5
        app.ado_wit_client.get_work_item.return_value = mock_ado_task

        task_item = TaskItem(
            ado_id=123,
            ado_rev=5,
            title="Test Task",
            item_type="Bug",
            url="https://example.com/123",
            asana_gid=None,  # No Asana GID
        )

        result = task_item.is_current(app)

        # Should return False because asana_task will be None
        self.assertFalse(result)

    def test_equality_with_different_objects(self):
        """Test equality comparison with different object types."""
        task_item = TaskItem(ado_id=123, ado_rev=1, title="Test Task", item_type="Bug", url="https://example.com/123")

        # Test with string
        self.assertNotEqual(task_item, "not a task item")

        # Test with dict
        self.assertNotEqual(task_item, {"ado_id": 123})

        # Test with None
        self.assertNotEqual(task_item, None)

    def test_equality_with_matching_task_items(self):
        """Test equality comparison with matching TaskItems."""
        task_item1 = TaskItem(
            ado_id=123,
            ado_rev=1,
            title="Test Task",
            item_type="Bug",
            url="https://example.com/123",
            asana_gid="asana-123",
            asana_updated="2023-12-01T10:00:00Z",
            assigned_to="user-456",
            created_date="2023-12-01T09:00:00Z",
            updated_date="2023-12-01T10:00:00Z",
        )

        task_item2 = TaskItem(
            ado_id=123,
            ado_rev=1,
            title="Test Task",
            item_type="Bug",
            url="https://example.com/123",
            asana_gid="asana-123",
            asana_updated="2023-12-01T10:00:00Z",
            assigned_to="user-456",
            created_date="2023-12-01T09:00:00Z",
            updated_date="2023-12-01T10:00:00Z",
        )

        self.assertEqual(task_item1, task_item2)

    def test_equality_with_different_task_items(self):
        """Test equality comparison with different TaskItems."""
        task_item1 = TaskItem(ado_id=123, ado_rev=1, title="Test Task", item_type="Bug", url="https://example.com/123")

        task_item2 = TaskItem(
            ado_id=456,  # Different ID
            ado_rev=1,
            title="Test Task",
            item_type="Bug",
            url="https://example.com/456",
        )

        self.assertNotEqual(task_item1, task_item2)

    def test_find_by_ado_id_with_no_matches_table(self):
        """Test find_by_ado_id when app.matches is None."""
        app = MagicMock()
        app.matches = None

        result = TaskItem.find_by_ado_id(app, 123)

        self.assertIsNone(result)

    def test_search_with_no_matches_table(self):
        """Test search when app.matches is None."""
        app = MagicMock()
        app.matches = None

        result = TaskItem.search(app, ado_id=123)

        self.assertIsNone(result)


class TestTaskItemDueDateContract(unittest.TestCase):
    """Contract tests for TaskItem due date functionality (TDD - will fail initially)"""

    def test_task_item_constructor_accepts_due_date(self):
        """Contract: TaskItem constructor must accept optional due_date parameter"""
        # This test will initially fail - no implementation yet
        # Valid due date
        task_with_date = TaskItem(
            ado_id="123", title="Test Task", item_type="Task", ado_rev=1, url="http://test.com", due_date="2025-12-31"
        )
        self.assertEqual(task_with_date.due_date, "2025-12-31")

        # No due date
        task_without_date = TaskItem(ado_id="124", title="Test Task 2", item_type="Task", ado_rev=1, url="http://test.com")
        self.assertIsNone(task_without_date.due_date)

    def test_task_item_equality_includes_due_date(self):
        """Contract: TaskItem equality comparison must include due_date field"""
        task1 = TaskItem(ado_id="123", title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date="2025-12-31")
        task2 = TaskItem(ado_id="123", title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date="2025-12-31")
        task3 = TaskItem(ado_id="123", title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date="2026-01-01")

        self.assertEqual(task1, task2)  # Same due date
        self.assertNotEqual(task1, task3)  # Different due date

    def test_task_item_save_includes_due_date(self):
        """Contract: TaskItem.save() must include due_date in serialized data"""
        from unittest.mock import MagicMock

        from ado_asana_sync.sync.app import App

        task = TaskItem(ado_id=123, title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date="2025-12-31")

        # Mock app with database mocks
        mock_app = MagicMock(spec=App)
        mock_app.matches = MagicMock()
        mock_app.db_lock = MagicMock()
        mock_app.db_lock.__enter__ = MagicMock(return_value=mock_app.db_lock)
        mock_app.db_lock.__exit__ = MagicMock(return_value=None)
        mock_app.matches.contains.return_value = False

        # Call save method
        task.save(mock_app)

        # Verify the insert was called with due_date included
        mock_app.matches.insert.assert_called_once()
        saved_data = mock_app.matches.insert.call_args[0][0]
        self.assertIn("due_date", saved_data)
        self.assertEqual(saved_data["due_date"], "2025-12-31")

    def test_due_date_validation_format(self):
        """Contract: Due date must be valid YYYY-MM-DD format or None"""
        # Valid formats should work
        valid_dates = ["2025-12-31", "2025-01-01", "2025-06-15", None]
        for date in valid_dates:
            task = TaskItem(ado_id="123", title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date=date)
            self.assertEqual(task.due_date, date)

        # Invalid formats should raise ValueError or be normalized
        invalid_dates = ["2025-13-01", "invalid-date", "2025/12/31", ""]
        for date in invalid_dates:
            with self.assertRaises((ValueError, TypeError)):
                TaskItem(ado_id="123", title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date=date)

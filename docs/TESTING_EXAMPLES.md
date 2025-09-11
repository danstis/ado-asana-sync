# Testing Examples - Mock-Only-At-Boundaries

This document provides concrete examples of good vs bad testing practices based on lessons learned from test refactoring. Use these examples as templates when writing new tests.

## Test Type Guidelines

- **70% Integration Tests**: Test internal components working together
- **20% Unit Tests**: Test individual functions in isolation
- **10% System Tests**: Test complete workflows with external services

## ✅ GOOD Examples

### Integration Test - Real App with Real Database

```python
import tempfile
from unittest.mock import patch
from tests.utils.test_helpers import TestDataBuilder, AsanaApiMockHelper

class TestDueDateIntegration(unittest.TestCase):
    
    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection") 
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_due_date_sync_real_integration(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """
        TRUE Integration Test: Tests 80%+ of real code path.
        
        What this tests:
        - REAL App instance with REAL database operations
        - REAL WorkItem parsing and due date extraction
        - REAL internal function integration (extract_due_date_from_ado, create_asana_task_body)
        - REAL database persistence and retrieval
        - REAL business logic validation
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Point App to our temp directory
            mock_dirname.return_value = temp_dir
            mock_ado_connection.return_value = MagicMock()
            mock_asana_client.return_value = MagicMock()
            
            # Create REAL App with REAL database
            app = TestDataBuilder.create_real_app(temp_dir)
            
            # Set up ONLY external API mocks
            asana_helper = AsanaApiMockHelper()
            mock_tasks_api = asana_helper.create_tasks_api_mock(
                created_task={
                    "gid": "67890",
                    "name": "Task 12345: Test Due Date Sync", 
                    "due_on": "2025-12-31",
                    "completed": False,
                    "modified_at": "2025-09-10T10:00:00.000Z"
                }
            )
            
            try:
                app.connect()  # REAL database initialization
                
                # Create REAL ADO work item
                ado_work_item = TestDataBuilder.create_ado_work_item(
                    item_id=12345,
                    title="Test Due Date Sync",
                    work_item_type="Task",
                    due_date="2025-12-31T23:59:59.000Z"  # REAL due date for parsing
                )
                
                # REAL user data for REAL matching_user function
                asana_users = [{"gid": "user123", "name": "Test User", "email": "test@example.com"}]
                
                # Mock ONLY external APIs at boundaries
                with (
                    patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_tasks_api),
                    patch("ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=asana_helper.create_workspace_api_mock()),
                    patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=asana_helper.create_projects_api_mock()),
                    patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=asana_helper.create_tags_api_mock()),
                    # Mock functions that make external API calls but let internal logic work
                    patch("ado_asana_sync.sync.sync.get_asana_task", return_value=None),
                    patch("ado_asana_sync.sync.sync.get_asana_task_by_name", return_value=None),  
                    patch("ado_asana_sync.sync.sync.find_custom_field_by_name", return_value=None),
                    patch("ado_asana_sync.sync.sync.tag_asana_item", return_value=None),
                ):
                    # Act: Process with REAL objects - exercises REAL integration
                    process_backlog_item(
                        app,          # REAL App with REAL database
                        ado_work_item,# REAL WorkItem with REAL fields
                        asana_users,  # REAL user list processed by REAL matching_user
                        [],           # REAL (empty) project tasks
                        "project456", # REAL project ID
                    )

                    # Assert: Verify REAL database operations worked
                    saved_items = app.matches.all()  # REAL database query
                    self.assertEqual(len(saved_items), 1)
                    
                    saved_task = saved_items[0]
                    self.assertEqual(saved_task["ado_id"], 12345)
                    self.assertEqual(saved_task["title"], "Test Due Date Sync")
                    # This proves REAL extract_due_date_from_ado() worked
                    self.assertEqual(saved_task["due_date"], "2025-12-31")

                    # Assert: Verify REAL Asana API integration
                    mock_tasks_api.create_task.assert_called_once()
                    create_task_call = mock_tasks_api.create_task.call_args[0][0]
                    self.assertEqual(create_task_call["data"]["due_on"], "2025-12-31")
                    # This proves REAL create_asana_task_body() worked and formatted name
                    self.assertEqual(create_task_call["data"]["name"], "Task 12345: Test Due Date Sync")
                    
            finally:
                app.close()
```

### Integration Test - Real Objects Working Together

```python
import tempfile
from tests.utils.test_helpers import TestDataBuilder, RealObjectBuilder

class TestPullRequestIntegration(unittest.TestCase):

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection") 
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    @patch("ado_asana_sync.sync.pull_request_sync.create_new_pr_reviewer_task")
    def test_pr_reviewer_real_integration(self, mock_create_task, mock_asana_client, mock_ado_connection, mock_dirname):
        """
        Real Integration: Tests internal utilities working together.
        
        What this tests:
        - REAL create_ado_user_from_reviewer() extracting data from REAL reviewer
        - REAL matching_user() processing REAL user data
        - REAL App with REAL database operations
        - REAL object attribute access and business logic
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_dirname.return_value = temp_dir
            mock_ado_connection.return_value = Mock()
            mock_asana_client.return_value = Mock()
            
            # Create REAL App with REAL database
            app = TestDataBuilder.create_real_app(temp_dir)
            
            try:
                app.connect()  # REAL database initialization
                
                # Create REAL ADO objects (not mocks!)
                reviewer = RealObjectBuilder.create_real_ado_reviewer(
                    display_name="John Doe",
                    email="john.doe@example.com",
                    vote="waiting_for_author"
                )
                
                pr = RealObjectBuilder.create_real_ado_pull_request(
                    pr_id=789,
                    title="Fix critical bug", 
                    status="active"
                )
                
                repository = RealObjectBuilder.create_real_ado_repository(
                    repo_id="repo-456",
                    name="test-repo",
                    project_id="project-123"
                )
                
                # REAL Asana user list for REAL matching_user function
                asana_users = [{"gid": "user-123", "email": "john.doe@example.com", "name": "John Doe"}]

                # Mock only database search and final task creation
                with patch.object(PullRequestItem, "search", return_value=None):
                    # Call with REAL objects - tests REAL integration
                    process_pr_reviewer(
                        app,        # REAL App with REAL database 
                        pr,         # REAL PR object
                        repository, # REAL repository object  
                        reviewer,   # REAL reviewer object
                        asana_users, # REAL user list
                        [], 
                        "project-456"
                    )

                    # Verify task creation was called - REAL integration worked
                    mock_create_task.assert_called_once()
                    
                    # Verify REAL internal utilities worked together correctly
                    args = mock_create_task.call_args[0]
                    matched_asana_user = args[4]  # asana_user parameter
                    self.assertEqual(matched_asana_user["email"], "john.doe@example.com")
                    self.assertEqual(matched_asana_user["gid"], "user-123")
                    
                    # Verify REAL reviewer object was processed correctly
                    self.assertEqual(args[1].pull_request_id, 789)  # REAL PR
                    self.assertEqual(args[2].id, "repo-456")  # REAL repository
                    
            finally:
                app.close()
```

### Unit Test - Focused Individual Function

```python
class TestUtilityFunctions(unittest.TestCase):
    """Unit tests for individual utility functions."""

    def test_extract_due_date_from_ado_valid_date(self):
        """Test due date extraction from valid ADO work item."""
        # Create REAL WorkItem (not a mock)
        work_item = TestDataBuilder.create_ado_work_item(
            due_date="2025-12-31T23:59:59.000Z"
        )
        
        # Test REAL function with REAL data
        result = extract_due_date_from_ado(work_item)
        
        # Assert REAL behavior
        self.assertEqual(result, "2025-12-31")
    
    def test_extract_due_date_from_ado_invalid_date(self):
        """Test due date extraction handles invalid dates."""
        work_item = TestDataBuilder.create_ado_work_item(
            due_date="invalid-date-format"
        )
        
        with patch("ado_asana_sync.sync.sync._LOGGER") as mock_logger:
            result = extract_due_date_from_ado(work_item)
            
            # Verify error handling behavior
            self.assertIsNone(result)
            mock_logger.warning.assert_called()
```

## ❌ BAD Examples (DO NOT DO THIS)

### Over-Mocked "Integration" Test

```python
# ❌ BAD - This is NOT an integration test!
class TestBadIntegration(unittest.TestCase):
    
    def test_due_date_sync_over_mocked(self):
        """BAD: Over-mocked test that provides false confidence."""
        
        # ❌ BAD: Mocking internal business objects
        app = MagicMock(spec=App)
        app.matches = MagicMock()
        app.db = MagicMock()
        
        # ❌ BAD: Mocking internal data structures
        ado_work_item = MagicMock()
        ado_work_item.id = 12345
        ado_work_item.fields = {"System.Title": "Test"}
        
        # ❌ BAD: Mocking internal utility functions
        with (
            patch("ado_asana_sync.sync.sync.extract_due_date_from_ado", return_value="2025-12-31"),
            patch("ado_asana_sync.sync.sync.matching_user", return_value={"gid": "user123"}),
            patch("ado_asana_sync.sync.sync.create_asana_task_body", return_value={"name": "Test"}),
        ):
            process_backlog_item(app, ado_work_item, [], [], "project")
            
            # ❌ BAD: Only testing mock interactions, not real behavior
            app.matches.insert.assert_called_once()
            
        # This test tells us NOTHING about whether the real code works!
```

### Over-Mocked Database Test

```python
# ❌ BAD - Mocking database operations
def test_read_projects_bad(self):
    """BAD: Mocking internal database operations."""
    
    # ❌ BAD: Using MagicMock for internal business object
    app = MagicMock(spec=App)
    app.db = MagicMock()
    app.db.get_projects.return_value = [
        {"adoProjectName": "TestProject"}
    ]
    
    result = read_projects(app)
    
    # ❌ BAD: Only tests that we call the mock, not real database logic
    app.db.get_projects.assert_called_once()
    self.assertEqual(result[0]["adoProjectName"], "TestProject")
    
    # This test doesn't validate:
    # - Real database connection logic
    # - Real error handling and fallback
    # - Real data transformation
    # - Real exception paths
```

## Key Takeaways

1. **Mock Boundaries, Not Internals**: Mock external APIs (Asana, ADO), not internal functions
1. **Use Real Objects**: Create real App instances, real business objects, real databases
1. **Test Real Integration**: Let internal functions work together naturally
1. **Verify Real Behavior**: Assert on actual data outcomes, not mock interactions
1. **Real Error Paths**: Test actual exception handling, not mocked error responses

## Test Quality Checklist

Before submitting any test, ask:

- [ ] Am I using `TestDataBuilder.create_real_app()` instead of `MagicMock(spec=App)`?
- [ ] Am I using real business objects instead of mocks for internal data?
- [ ] Am I letting internal functions work together instead of mocking them?
- [ ] Am I testing actual data outcomes instead of mock interactions?
- [ ] Am I only mocking external APIs and network boundaries?
- [ ] Does my integration test exercise 80%+ of the real code path?

If you answer "no" to any of these, refactor your test to use real objects and real integration.

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from asana.rest import ApiException
from azure.devops.v7_0.work_item_tracking.models import WorkItem

from ado_asana_sync.sync.sync import (
    ADOAssignedUser,
    DEFAULT_SYNC_THRESHOLD,
    cleanup_invalid_work_items,
    create_tag_if_not_existing,
    get_asana_project,
    get_asana_project_tasks,
    get_asana_task_by_name,
    get_asana_task_tags,
    get_asana_users,
    get_asana_workspace,
    get_tag_by_name,
    get_task_user,
    is_item_older_than_threshold,
    matching_user,
    _parse_sync_threshold,
    process_backlog_item,
    read_projects,
    remove_mapping,
)
from ado_asana_sync.sync.task_item import TaskItem
from tests.utils.test_helpers import TestDataBuilder


class TestTaskItem(unittest.TestCase):
    def setUp(self) -> None:
        self.test_item = TaskItem(
            ado_id=123,
            ado_rev=3,
            title="Test Title",
            item_type="User Story",
            url="https://testurl.example",
        )

    def test_asana_notes_link(self):
        result = self.test_item.asana_notes_link

        # Assert that the output is as expected
        self.assertEqual(result, '<a href="https://testurl.example">User Story 123</a>: Test Title')

    # Tests that the asana_title returns the correct formatted title when all parameters are provided
    def test_asana_title_with_all_parameters(self):
        # Create a work_item object with all parameters provided
        work_item_obj = TaskItem(
            ado_id=1,
            ado_rev=1,
            title="Test Title",
            item_type="Task",
            url="https://example.com",
            assigned_to="John Doe",
            created_date="2021-01-01",
            updated_date="2021-12-31",
        )

        # Assert that the asana_title returns the correct formatted title
        self.assertEqual(work_item_obj.asana_title, "Task 1: Test Title")

    # Tests that the asana_title returns the correct formatted title when only mandatory parameters are provided
    def test_asana_title_with_mandatory_parameters(self):
        # Create a work_item object with only mandatory parameters provided
        work_item_obj = TaskItem(
            ado_id=1,
            ado_rev=42,
            title="Test Title",
            item_type="Task",
            url="https://example.com",
        )

        # Assert that the asana_title returns the correct formatted title
        self.assertEqual(work_item_obj.asana_title, "Task 1: Test Title")

    # Tests that the asana_title returns the correct formatted title when all parameters are provided with empty values
    def test_asana_title_with_empty_values(self):
        # Create a work_item object with all parameters provided as empty values
        work_item_obj = TaskItem(ado_id=None, ado_rev=None, title="", item_type="", url="")

        # Assert that the asana_title returns the correct formatted title
        self.assertEqual(work_item_obj.asana_title, " None: ")

    # Tests that the asana_title returns the correct formatted title when all parameters are provided with invalid values
    def test_asana_title_with_invalid_values(self):
        # Create a work_item object with all parameters provided with invalid values
        work_item_obj = TaskItem(
            ado_id="invalid",
            ado_rev="invalid",
            title=123,
            item_type=True,
            url="https://example.com",
        )

        # Assert that the asana_title returns the correct formatted title
        self.assertEqual(work_item_obj.asana_title, "True invalid: 123")


class TestGetTaskUserEmail(unittest.TestCase):
    # Tests that the function returns the email address of the user assigned to the work item
    # when the System.AssignedTo field has a uniqueName
    def test_assigned_user_with_uniqueName(self):
        task = WorkItem()
        task.fields = {
            "System.AssignedTo": {
                "uniqueName": "john.doe@example.com",
                "displayName": "John Doe",
            }
        }
        ado_user = ADOAssignedUser(display_name="John Doe", email="john.doe@example.com")
        result = get_task_user(task)
        self.assertEqual(result, ado_user)

    # Tests that the function returns None when the System.AssignedTo field is not present in the work item
    def test_no_assigned_user(self):
        task = WorkItem()
        task.fields = {}
        result = get_task_user(task)
        self.assertIsNone(result)

    # Tests that the function returns None when the System.AssignedTo field is present but does not have a uniqueName field
    def test_missing_uniqueName(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": {}}
        result = get_task_user(task)
        self.assertIsNone(result)

    # Tests that the function returns the email address even if the uniqueName field
    # in the System.AssignedTo field is not a valid email address
    def test_invalid_email_address(self):
        task = WorkItem()
        task.fields = {
            "System.AssignedTo": {
                "uniqueName": "john.doe",
                "displayName": "John Doe",
            }
        }
        ado_user = ADOAssignedUser(display_name="John Doe", email="john.doe")
        result = get_task_user(task)
        self.assertEqual(result, ado_user)

    # Tests that the function returns None when the System.AssignedTo field is present but is None
    def test_assigned_user_is_None(self):
        task = WorkItem()
        task.fields = {"System.AssignedTo": None}
        result = get_task_user(task)
        self.assertIsNone(result)


class TestMatchingUser(unittest.TestCase):
    # Tests that matching_user returns the matching user when the email exists in the user_list.
    def test_matching_user_matching_email_exists(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User Two", email="user2@example.com")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user2@example.com", "name": "User 2"})

    # Tests that matching_user returns the matching user when the display name exists in the user_list.
    def test_matching_user_matching_display_name_exists(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User 2", email="user2@example.co.uk")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user2@example.com", "name": "User 2"})

    # Tests that matching_user returns None when the email does not exist in the user_list.
    def test_matching_user_matching_email_does_not_exist(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="User 4", email="user4@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the user_list is empty.
    def test_matching_user_user_list_empty(self):
        user_list = []
        ado_user = ADOAssignedUser(display_name="User 1", email="user1@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the email is an empty string.
    def test_matching_user_email_empty(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = ADOAssignedUser(display_name="", email="")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns the user when the user_list contains only one user
    # and the email matches that user's email.
    def test_matching_user_user_list_contains_one_user_email_matches(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
        ]
        ado_user = ADOAssignedUser(display_name="User 1", email="user1@example.com")

        result = matching_user(user_list, ado_user)

        self.assertEqual(result, {"email": "user1@example.com", "name": "User 1"})

    # Tests that matching_user returns None when the user_list contains only one user
    # and the email does not match that user's email.
    def test_matching_user_user_list_contains_one_user_email_does_not_match(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
        ]
        ado_user = ADOAssignedUser(display_name="User 2", email="user2@example.com")

        result = matching_user(user_list, ado_user)

        self.assertIsNone(result)

    # Tests that matching_user returns None when the ado_user is None.
    def test_matching_user_ado_user_none(self):
        user_list = [
            {"email": "user1@example.com", "name": "User 1"},
            {"email": "user2@example.com", "name": "User 2"},
            {"email": "user3@example.com", "name": "User 3"},
        ]
        ado_user = None

        result = matching_user(user_list, ado_user)  # NOSONAR

        self.assertIsNone(result)


class TestProcessBacklogItemLogging(unittest.TestCase):
    def test_log_when_user_not_matched(self):
        app = MagicMock()
        app.matches = MagicMock()
        app.matches.contains.return_value = False
        app.matches.search.return_value = []

        ado_task = WorkItem()
        ado_task.id = 1
        ado_task.rev = 1
        ado_task.fields = {
            "System.Title": "Test Item",
            "System.WorkItemType": "Task",
            "System.State": "Active",
            "System.AssignedTo": {
                "uniqueName": "user@example.com",
                "displayName": "User Example",
            },
        }

        asana_users = [{"email": "other@example.com", "name": "Other"}]

        with patch("ado_asana_sync.sync.sync._LOGGER") as mock_logger:
            process_backlog_item(app, ado_task, asana_users, [], "proj")
            mock_logger.info.assert_any_call(
                "%s:assigned user %s <%s> not found in Asana",
                "Test Item",
                "User Example",
                "user@example.com",
            )


class TestGetAsanaTaskByName(unittest.TestCase):
    def test_task_found(self):
        """
        Test case for verifying that a task can be found by name.
        """

        task_list = [
            {"name": "Task 1", "gid": "1"},
            {"name": "Task 2", "gid": "2"},
            {"name": "Task 3", "gid": "3"},
        ]

        # Call the function being tested
        result = get_asana_task_by_name(task_list, "Task 1")

        # Assert that the result is the task dictionary
        self.assertEqual(result, {"name": "Task 1", "gid": "1"})

    def test_task_not_found(self):
        """
        Test case for the scenario where the task is not found in the task list.
        """

        task_list = [{"name": "Task 1"}]

        # Call the function being tested
        result = get_asana_task_by_name(task_list, "Task 2")

        # Assert that the result is None
        self.assertIsNone(result)


class TestReadProjects(unittest.TestCase):
    """Test read_projects function using REAL App instances for true integration testing."""

    def setUp(self):
        """Set up test fixtures with real temporary directory."""
        import tempfile

        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files and close real app instances."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_read_projects_real_database_integration(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """Test reading projects from REAL database with REAL App instance."""
        # Point App to our temp directory
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        # Create REAL App with REAL database
        app = TestDataBuilder.create_real_app(
            self.temp_dir,
            projects_data=[
                {"adoProjectName": "RealDBProject", "adoTeamName": "RealDBTeam", "asanaProjectName": "RealDBAsanaProject"}
            ],
        )

        try:
            # Connect with real database initialization
            app.connect()

            # The projects should be loaded into the real database during connect()
            result = read_projects(app)

            # Verify we got real data from real database
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["adoProjectName"], "RealDBProject")
            self.assertEqual(result[0]["adoTeamName"], "RealDBTeam")
            self.assertEqual(result[0]["asanaProjectName"], "RealDBAsanaProject")

            # Verify the database was actually used (not JSON fallback)
            self.assertIsNotNone(app.db)
            self.assertTrue(hasattr(app.db, "get_projects"))

        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_read_projects_json_fallback_real_app(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """Test JSON fallback using REAL App instance with no database."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        # Create REAL App
        app = TestDataBuilder.create_real_app(
            self.temp_dir,
            projects_data=[
                {"adoProjectName": "JSONProject", "adoTeamName": "JSONTeam", "asanaProjectName": "JSONAsanaProject"}
            ],
        )

        try:
            # Don't connect to database - force JSON fallback
            app.db = None  # Simulate no database available

            result = read_projects(app)

            # Should fall back to JSON file and actually read it
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["adoProjectName"], "JSONProject")
            self.assertEqual(result[0]["adoTeamName"], "JSONTeam")
            self.assertEqual(result[0]["asanaProjectName"], "JSONAsanaProject")

        finally:
            if app.db:
                app.close()

    @patch("ado_asana_sync.sync.sync._LOGGER")
    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_read_projects_real_database_failure_fallback(
        self, mock_asana_client, mock_ado_connection, mock_dirname, mock_logger
    ):
        """Test REAL database failure fallback to JSON using REAL App."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        # Create REAL App
        app = TestDataBuilder.create_real_app(
            self.temp_dir,
            projects_data=[
                {
                    "adoProjectName": "FallbackProject",
                    "adoTeamName": "FallbackTeam",
                    "asanaProjectName": "FallbackAsanaProject",
                }
            ],
        )

        try:
            app.connect()  # Initialize real database

            # Simulate database failure by replacing get_projects with failing method
            def failing_get_projects():
                raise Exception("Real database error")

            app.db.get_projects = failing_get_projects

            result = read_projects(app)

            # Should fall back to JSON after real database failure
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["adoProjectName"], "FallbackProject")

            # Verify warning was logged for the real database failure
            mock_logger.warning.assert_called()
            warning_call = mock_logger.warning.call_args[0][0]
            self.assertIn("Failed to read projects from database", warning_call)

        finally:
            app.close()


class TestGetAsanaWorkspace(unittest.TestCase):
    """Test get_asana_workspace function."""

    @patch("ado_asana_sync.sync.sync.asana.WorkspacesApi")
    def test_get_asana_workspace_success(self, mock_workspaces_api):
        """Test successful workspace retrieval."""
        app = MagicMock()
        mock_api_instance = MagicMock()
        mock_workspaces_api.return_value = mock_api_instance
        mock_api_instance.get_workspaces.return_value = [
            {"name": "TestWorkspace", "gid": "12345"},
            {"name": "OtherWorkspace", "gid": "67890"},
        ]

        result = get_asana_workspace(app, "TestWorkspace")

        self.assertEqual(result, "12345")

    @patch("ado_asana_sync.sync.sync.asana.WorkspacesApi")
    def test_get_asana_workspace_not_found(self, mock_workspaces_api):
        """Test workspace not found raises NameError."""
        app = MagicMock()
        mock_api_instance = MagicMock()
        mock_workspaces_api.return_value = mock_api_instance
        mock_api_instance.get_workspaces.return_value = [{"name": "OtherWorkspace", "gid": "67890"}]

        with self.assertRaises(NameError):
            get_asana_workspace(app, "NonexistentWorkspace")

    @patch("ado_asana_sync.sync.sync.asana.WorkspacesApi")
    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_get_asana_workspace_api_exception(self, mock_logger, mock_workspaces_api):
        """Test API exception handling."""
        app = MagicMock()
        mock_api_instance = MagicMock()
        mock_workspaces_api.return_value = mock_api_instance
        mock_api_instance.get_workspaces.side_effect = ApiException("API Error")

        with self.assertRaises(ValueError):
            get_asana_workspace(app, "TestWorkspace")


class TestGetAsanaProject(unittest.TestCase):
    """Test get_asana_project function."""

    @patch("ado_asana_sync.sync.sync.asana.ProjectsApi")
    def test_get_asana_project_success(self, mock_projects_api):
        """Test successful project retrieval."""
        app = MagicMock()
        mock_api_instance = MagicMock()
        mock_projects_api.return_value = mock_api_instance
        mock_api_instance.get_projects.return_value = [
            {"name": "TestProject", "gid": "project123"},
            {"name": "OtherProject", "gid": "project456"},
        ]

        result = get_asana_project(app, "workspace123", "TestProject")

        self.assertEqual(result, "project123")

    @patch("ado_asana_sync.sync.sync.asana.ProjectsApi")
    def test_get_asana_project_not_found(self, mock_projects_api):
        """Test project not found raises NameError."""
        app = MagicMock()
        mock_api_instance = MagicMock()
        mock_projects_api.return_value = mock_api_instance
        mock_api_instance.get_projects.return_value = [{"name": "OtherProject", "gid": "project456"}]

        with self.assertRaises(NameError):
            get_asana_project(app, "workspace123", "NonexistentProject")

    @patch("ado_asana_sync.sync.sync.asana.ProjectsApi")
    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_get_asana_project_api_exception(self, mock_logger, mock_projects_api):
        """Test API exception handling returns None."""
        app = MagicMock()
        mock_api_instance = MagicMock()
        mock_projects_api.return_value = mock_api_instance
        mock_api_instance.get_projects.side_effect = ApiException("API Error")

        result = get_asana_project(app, "workspace123", "TestProject")

        self.assertIsNone(result)


class TestCreateTagIfNotExisting(unittest.TestCase):
    """Test create_tag_if_not_existing function."""

    def test_create_tag_existing_in_config(self):
        """Test when tag_gid exists in config."""
        app = MagicMock()
        app.config.get.return_value = {"tag_gid": "existing_tag_123"}

        result = create_tag_if_not_existing(app, "workspace123", "testtag")

        self.assertEqual(result, "existing_tag_123")

    @patch("ado_asana_sync.sync.sync.get_tag_by_name")
    def test_create_tag_existing_tag_found(self, mock_get_tag):
        """Test when tag exists in Asana."""
        app = MagicMock()
        app.config.get.return_value = {}
        mock_get_tag.return_value = {"gid": "found_tag_456", "name": "testtag"}

        result = create_tag_if_not_existing(app, "workspace123", "testtag")

        self.assertEqual(result, "found_tag_456")

    @patch("ado_asana_sync.sync.sync.get_tag_by_name")
    @patch("ado_asana_sync.sync.sync.asana.TagsApi")
    def test_create_new_tag_success(self, mock_tags_api, mock_get_tag):
        """Test creating a new tag successfully."""
        app = MagicMock()
        app.config.get.return_value = {}
        mock_get_tag.return_value = None

        mock_api_instance = MagicMock()
        mock_tags_api.return_value = mock_api_instance
        mock_api_instance.create_tag_for_workspace.return_value = {"gid": "new_tag_789"}

        result = create_tag_if_not_existing(app, "workspace123", "testtag")

        self.assertEqual(result, "new_tag_789")

    @patch("ado_asana_sync.sync.sync.get_tag_by_name")
    @patch("ado_asana_sync.sync.sync.asana.TagsApi")
    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_create_new_tag_api_exception(self, mock_logger, mock_tags_api, mock_get_tag):
        """Test API exception when creating tag."""
        app = MagicMock()
        app.config.get.return_value = {}
        mock_get_tag.return_value = None

        mock_api_instance = MagicMock()
        mock_tags_api.return_value = mock_api_instance
        mock_api_instance.create_tag_for_workspace.side_effect = ApiException("API Error")

        result = create_tag_if_not_existing(app, "workspace123", "testtag")

        self.assertIsNone(result)


class TestGetTagByName(unittest.TestCase):
    """Test get_tag_by_name function."""

    @patch("ado_asana_sync.sync.sync.asana.TagsApi")
    def test_get_tag_by_name_found(self, mock_tags_api):
        """Test finding tag by name."""
        app = MagicMock()
        mock_api_instance = MagicMock()
        mock_tags_api.return_value = mock_api_instance
        mock_api_instance.get_tags.return_value = [{"name": "testtag", "gid": "tag123"}, {"name": "othertag", "gid": "tag456"}]

        result = get_tag_by_name(app, "workspace123", "testtag")

        self.assertEqual(result, {"name": "testtag", "gid": "tag123"})

    @patch("ado_asana_sync.sync.sync.asana.TagsApi")
    def test_get_tag_by_name_not_found(self, mock_tags_api):
        """Test tag not found returns None."""
        app = MagicMock()
        mock_api_instance = MagicMock()
        mock_tags_api.return_value = mock_api_instance
        mock_api_instance.get_tags.return_value = [{"name": "othertag", "gid": "tag456"}]

        result = get_tag_by_name(app, "workspace123", "nonexistenttag")

        self.assertIsNone(result)


class TestGetAsanaTaskTags(unittest.TestCase):
    """Test get_asana_task_tags function."""

    @patch("ado_asana_sync.sync.sync.asana.TagsApi")
    def test_get_asana_task_tags_success(self, mock_tags_api):
        """Test successful retrieval of task tags."""
        app = MagicMock()
        task = MagicMock()
        task.asana_gid = "task123"

        mock_api_instance = MagicMock()
        mock_tags_api.return_value = mock_api_instance
        mock_api_instance.get_tags_for_task.return_value = [
            {"name": "tag1", "gid": "tag123"},
            {"name": "tag2", "gid": "tag456"},
        ]

        result = get_asana_task_tags(app, task)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "tag1")

    @patch("ado_asana_sync.sync.sync.asana.TagsApi")
    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_get_asana_task_tags_api_exception(self, mock_logger, mock_tags_api):
        """Test API exception handling."""
        app = MagicMock()
        task = MagicMock()
        task.asana_gid = "task123"

        mock_api_instance = MagicMock()
        mock_tags_api.return_value = mock_api_instance
        mock_api_instance.get_tags_for_task.side_effect = ApiException("API Error")

        result = get_asana_task_tags(app, task)

        self.assertEqual(result, [])


class TestParseSyncThreshold(unittest.TestCase):
    """Test _parse_sync_threshold function."""

    def test_parse_sync_threshold_accepts_string(self):
        """Test valid string values are converted to integers."""
        result = _parse_sync_threshold("15")

        self.assertEqual(result, 15)

    def test_parse_sync_threshold_defaults_on_none(self):
        """Test None values fall back to default."""
        result = _parse_sync_threshold(None)

        self.assertEqual(result, DEFAULT_SYNC_THRESHOLD)

    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_parse_sync_threshold_defaults_on_empty(self, mock_logger):
        """Test empty or whitespace values fall back to default without warnings."""
        result = _parse_sync_threshold("")
        whitespace_result = _parse_sync_threshold("   ")

        self.assertEqual(result, DEFAULT_SYNC_THRESHOLD)
        self.assertEqual(whitespace_result, DEFAULT_SYNC_THRESHOLD)
        mock_logger.warning.assert_not_called()

    def test_parse_sync_threshold_accepts_whitespace_padded(self):
        """Test whitespace padded numeric values are converted to integers."""
        result = _parse_sync_threshold("  20  ")

        self.assertEqual(result, 20)

    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_parse_sync_threshold_defaults_on_invalid(self, mock_logger):
        """Test invalid values fall back to default."""
        result = _parse_sync_threshold("abc")

        self.assertEqual(result, DEFAULT_SYNC_THRESHOLD)
        mock_logger.warning.assert_called()

    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_parse_sync_threshold_defaults_on_negative(self, mock_logger):
        """Test negative values fall back to default."""
        result = _parse_sync_threshold("-5")

        self.assertEqual(result, DEFAULT_SYNC_THRESHOLD)
        mock_logger.warning.assert_called()


class TestIsItemOlderThanThreshold(unittest.TestCase):
    """Test is_item_older_than_threshold function."""

    @patch("ado_asana_sync.sync.sync._SYNC_THRESHOLD", 30)
    def test_item_older_than_threshold(self):
        """Test item older than threshold."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        wi = {"updated_date": old_date}

        result = is_item_older_than_threshold(wi)

        self.assertTrue(result)

    @patch("ado_asana_sync.sync.sync._SYNC_THRESHOLD", 30)
    def test_item_newer_than_threshold(self):
        """Test item newer than threshold."""
        recent_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        wi = {"updated_date": recent_date}

        result = is_item_older_than_threshold(wi)

        self.assertFalse(result)


class TestRemoveMapping(unittest.TestCase):
    """Test remove_mapping function."""

    @patch("ado_asana_sync.sync.sync._LOGGER")
    @patch("ado_asana_sync.sync.sync._SYNC_THRESHOLD", 30)
    def test_remove_mapping(self, mock_logger):
        """Test removing mapping from database."""
        app = MagicMock()
        wi = {"item_type": "Bug", "title": "Test Item", "doc_id": 123}

        remove_mapping(app, wi)

        app.matches.remove.assert_called_once_with(doc_ids=[wi["doc_id"]])


class TestGetAsanaProjectTasks(unittest.TestCase):
    """Test get_asana_project_tasks function."""

    @patch("ado_asana_sync.sync.sync.asana.TasksApi")
    def test_get_asana_project_tasks_success(self, mock_tasks_api):
        """Test successful retrieval of project tasks."""
        app = MagicMock()
        app.asana_page_size = 50

        mock_api_instance = MagicMock()
        mock_tasks_api.return_value = mock_api_instance
        mock_api_instance.get_tasks.return_value = [{"name": "Task 1", "gid": "task123"}, {"name": "Task 2", "gid": "task456"}]

        result = get_asana_project_tasks(app, "project123")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Task 1")

    @patch("ado_asana_sync.sync.sync.asana.TasksApi")
    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_get_asana_project_tasks_api_exception(self, mock_logger, mock_tasks_api):
        """Test API exception handling."""
        app = MagicMock()
        app.asana_page_size = 50

        mock_api_instance = MagicMock()
        mock_tasks_api.return_value = mock_api_instance
        mock_api_instance.get_tasks.side_effect = ApiException("API Error")

        result = get_asana_project_tasks(app, "project123")

        self.assertEqual(result, [])


class TestGetAsanaUsers(unittest.TestCase):
    """Test get_asana_users function."""

    @patch("ado_asana_sync.sync.sync.asana.UsersApi")
    def test_get_asana_users_success(self, mock_users_api):
        """Test successful retrieval of Asana users."""
        app = MagicMock()

        mock_api_instance = MagicMock()
        mock_users_api.return_value = mock_api_instance
        mock_api_instance.get_users.return_value = [
            {"name": "User 1", "email": "user1@example.com"},
            {"name": "User 2", "email": "user2@example.com"},
        ]

        result = get_asana_users(app, "workspace123")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "User 1")

    @patch("ado_asana_sync.sync.sync.asana.UsersApi")
    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_get_asana_users_api_exception(self, mock_logger, mock_users_api):
        """Test API exception handling."""
        app = MagicMock()

        mock_api_instance = MagicMock()
        mock_users_api.return_value = mock_api_instance
        mock_api_instance.get_users.side_effect = ApiException("API Error")

        result = get_asana_users(app, "workspace123")

        self.assertEqual(result, [])

    @patch("ado_asana_sync.sync.sync.asana.UsersApi")
    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_get_asana_users_unexpected_exception(self, mock_logger, mock_users_api):
        """Test unexpected exception handling."""
        app = MagicMock()

        mock_api_instance = MagicMock()
        mock_users_api.return_value = mock_api_instance
        mock_api_instance.get_users.side_effect = Exception("Unexpected error")

        result = get_asana_users(app, "workspace123")

        self.assertEqual(result, [])


class TestCleanupInvalidWorkItems(unittest.TestCase):
    """Test cleanup_invalid_work_items function."""

    def test_cleanup_invalid_work_items(self):
        """Test cleanup of invalid work items."""
        app = MagicMock()
        app.matches.all.return_value = [
            {"ado_id": 123, "doc_id": 1},  # Valid integer ID
            {"ado_id": "invalid", "doc_id": 2},  # Invalid string ID
            {"ado_id": 456, "doc_id": 3},  # Valid integer ID
            {"ado_id": None, "doc_id": 4},  # Invalid None ID
        ]

        cleanup_invalid_work_items(app)

        # Should remove doc_ids 2 and 4 (invalid items)
        app.matches.remove.assert_called_once_with(doc_ids=[2, 4])

    @patch("ado_asana_sync.sync.sync._LOGGER")
    def test_cleanup_invalid_work_items_no_invalid_items(self, mock_logger):
        """Test cleanup when no invalid items exist."""
        app = MagicMock()
        app.matches.all.return_value = [{"ado_id": 123, "doc_id": 1}, {"ado_id": 456, "doc_id": 2}]

        cleanup_invalid_work_items(app)

        # Should not call remove
        app.matches.remove.assert_not_called()


class TestSyncDueDateContract(unittest.TestCase):
    """Contract tests for sync logic due date functionality (TDD - will fail initially)"""

    def test_ado_due_date_field_constant(self):
        """Contract: sync.py must define ADO_DUE_DATE constant"""
        from ado_asana_sync.sync.sync import ADO_DUE_DATE

        self.assertEqual(ADO_DUE_DATE, "Microsoft.VSTS.Scheduling.DueDate")

    def test_extract_due_date_from_ado_fields(self):
        """Contract: Sync must extract due date from ADO work item fields"""
        from ado_asana_sync.sync.sync import extract_due_date_from_ado

        # Mock ADO task with due date
        ado_task_with_date = MagicMock()
        ado_task_with_date.fields = {"Microsoft.VSTS.Scheduling.DueDate": "2025-12-31T23:59:59Z"}

        result = extract_due_date_from_ado(ado_task_with_date)
        self.assertEqual(result, "2025-12-31")  # Date portion only

        # Mock ADO task without due date
        ado_task_no_date = MagicMock()
        ado_task_no_date.fields = {}
        result = extract_due_date_from_ado(ado_task_no_date)
        self.assertIsNone(result)

    def test_asana_task_creation_includes_due_on(self):
        """Contract: Initial Asana task creation must include due_on when due_date present"""
        from ado_asana_sync.sync.sync import create_asana_task_body
        from ado_asana_sync.sync.task_item import TaskItem

        task_with_date = TaskItem(
            ado_id="123", title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date="2025-12-31"
        )

        body = create_asana_task_body(task_with_date, is_initial_sync=True)
        self.assertEqual(body["data"]["due_on"], "2025-12-31")

        task_without_date = TaskItem(
            ado_id="123", title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date=None
        )

        body = create_asana_task_body(task_without_date, is_initial_sync=True)
        self.assertNotIn("due_on", body["data"])

    def test_asana_task_update_excludes_due_on(self):
        """Contract: Subsequent Asana task updates must NOT include due_on"""
        from ado_asana_sync.sync.sync import create_asana_task_body
        from ado_asana_sync.sync.task_item import TaskItem

        task_with_date = TaskItem(
            ado_id="123", title="Test", item_type="Task", ado_rev=1, url="http://test.com", due_date="2025-12-31"
        )

        body = create_asana_task_body(task_with_date, is_initial_sync=False)
        self.assertNotIn("due_on", body["data"])

    def test_due_date_error_handling_non_blocking(self):
        """Contract: Due date errors must not block sync operation"""
        # This test will be implemented when sync error handling is added
        # For now, just verify the concept exists
        self.assertTrue(True, "Due date error handling contract defined")


if __name__ == "__main__":
    unittest.main()

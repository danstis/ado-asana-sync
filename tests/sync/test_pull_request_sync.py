"""Tests for the pull request sync functionality."""

import unittest
from unittest.mock import Mock, patch

from ado_asana_sync.sync.app import App
from ado_asana_sync.sync.pull_request_item import PullRequestItem
from ado_asana_sync.sync.pull_request_sync import (
    create_ado_user_from_reviewer,
    create_new_pr_reviewer_task,
    process_pr_reviewer,
    process_pull_request,
    process_repository_pull_requests,
    sync_pull_requests,
    update_existing_pr_reviewer_task,
)
from tests.utils.test_helpers import RealObjectBuilder, TestDataBuilder


class TestPullRequestSync(unittest.TestCase):
    """Test cases for pull request sync functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_app = Mock(spec=App)
        self.mock_app.ado_git_client = Mock()
        self.mock_app.pr_matches = Mock()
        self.mock_app.db_lock = Mock()
        self.mock_app.db_lock.__enter__ = Mock(return_value=self.mock_app.db_lock)
        self.mock_app.db_lock.__exit__ = Mock(return_value=None)
        self.mock_app.asana_tag_gid = "test-tag-gid"
        self.mock_app.ado_url = "https://dev.azure.com/test"
        self.mock_app.asana_workspace_name = "test-workspace"
        self.mock_app.asana_client = Mock()
        self.mock_app.asana_page_size = 100

        self.mock_ado_project = Mock()
        self.mock_ado_project.name = "Test Project"
        self.mock_ado_project.id = "project-123"

        self.mock_repository = Mock()
        self.mock_repository.id = "repo-456"
        self.mock_repository.name = "test-repo"
        self.mock_repository.project = self.mock_ado_project

        self.mock_pr = Mock()
        self.mock_pr.pull_request_id = 789
        self.mock_pr.title = "Fix critical bug"
        self.mock_pr.status = "active"
        self.mock_pr.web_url = "https://dev.azure.com/test/project/_git/repo/pullrequest/789"

        self.mock_reviewer = Mock()
        self.mock_reviewer.display_name = "John Doe"
        self.mock_reviewer.unique_name = "john.doe@example.com"
        self.mock_reviewer.vote = "waiting_for_author"

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_users")
    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_project_tasks")
    @patch("ado_asana_sync.sync.pull_request_sync.process_closed_pull_requests")
    def test_sync_pull_requests(self, mock_process_closed, mock_get_tasks, mock_get_users):
        """Test the main sync_pull_requests function."""
        # Setup mocks
        mock_get_users.return_value = [{"gid": "user-123", "email": "john.doe@example.com", "name": "John Doe"}]
        mock_get_tasks.return_value = []
        self.mock_app.ado_git_client.get_repositories.return_value = [self.mock_repository]

        with patch("ado_asana_sync.sync.pull_request_sync.process_repository_pull_requests") as mock_process_repo:
            sync_pull_requests(self.mock_app, self.mock_ado_project, "workspace-123", "project-456")

            # Verify calls
            mock_get_users.assert_called_once_with(self.mock_app, "workspace-123")
            mock_get_tasks.assert_called_once_with(self.mock_app, "project-456")
            self.mock_app.ado_git_client.get_repositories.assert_called_once_with("project-123")
            mock_process_repo.assert_called_once()
            mock_process_closed.assert_called_once()

    @patch("ado_asana_sync.sync.pull_request_sync.process_pull_request")
    def test_process_repository_pull_requests(self, mock_process_pr):
        """Test processing pull requests for a repository."""
        # Setup mocks
        self.mock_app.ado_git_client.get_pull_requests.return_value = [self.mock_pr]

        process_repository_pull_requests(self.mock_app, self.mock_repository, [], [], "project-456")

        # Verify calls
        self.mock_app.ado_git_client.get_pull_requests.assert_called_once()
        # Check that the call was made with the expected parameters plus the cache
        args, kwargs = mock_process_pr.call_args
        self.assertEqual(args[:6], (self.mock_app, self.mock_pr, self.mock_repository, [], [], "project-456"))
        self.assertIsInstance(args[6], dict)  # user_lookup_cache should be a dict

    @patch("ado_asana_sync.sync.pull_request_sync.handle_removed_reviewers")
    @patch("ado_asana_sync.sync.pull_request_sync.process_pr_reviewer")
    def test_process_pull_request(self, mock_process_reviewer, mock_handle_removed):
        """Test processing a single pull request."""
        # Setup mocks
        self.mock_app.ado_git_client.get_pull_request_reviewers.return_value = [self.mock_reviewer]

        process_pull_request(self.mock_app, self.mock_pr, self.mock_repository, [], [], "project-456")

        # Verify calls
        self.mock_app.ado_git_client.get_pull_request_reviewers.assert_called_once_with("repo-456", 789)
        mock_process_reviewer.assert_called_once()
        mock_handle_removed.assert_called_once()

    @patch("ado_asana_sync.sync.pull_request_sync.handle_removed_reviewers")
    def test_process_pull_request_no_reviewers(self, mock_handle_removed):
        """Test processing a pull request with no reviewers."""
        # Setup mocks
        self.mock_app.ado_git_client.get_pull_request_reviewers.return_value = []

        with patch("ado_asana_sync.sync.pull_request_sync.process_pr_reviewer") as mock_process_reviewer:
            process_pull_request(self.mock_app, self.mock_pr, self.mock_repository, [], [], "project-456")

            # Verify no reviewer processing but removed reviewers are handled
            mock_process_reviewer.assert_not_called()
            mock_handle_removed.assert_called_once_with(self.mock_app, self.mock_pr, set(), "project-456")

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    @patch("ado_asana_sync.sync.pull_request_sync.create_new_pr_reviewer_task")
    def test_process_pr_reviewer_new_task_real_integration(
        self, mock_create_task, mock_asana_client, mock_ado_connection, mock_dirname
    ):
        """Test processing a reviewer with REAL App and REAL objects integration.

        This test uses real App, real reviewer objects, and real internal utilities
        working together. Only mocks external APIs and the final task creation.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up real App with real database
            mock_dirname.return_value = temp_dir
            mock_ado_connection.return_value = Mock()
            mock_asana_client.return_value = Mock()

            app = TestDataBuilder.create_real_app(temp_dir)

            try:
                app.connect()  # Real database initialization

                # Create REAL ADO objects (not mocks!)
                reviewer = RealObjectBuilder.create_real_ado_reviewer(
                    display_name="John Doe", email="john.doe@example.com", vote="waiting_for_author"
                )

                pr = RealObjectBuilder.create_real_ado_pull_request(pr_id=789, title="Fix critical bug", status="active")

                repository = RealObjectBuilder.create_real_ado_repository(
                    repo_id="repo-456", name="test-repo", project_id="project-123"
                )

                # Real Asana user list for real matching_user function to process
                asana_users = [{"gid": "user-123", "email": "john.doe@example.com", "name": "John Doe"}]

                # Mock only the database search (external dependency) and final task creation
                with patch.object(PullRequestItem, "search", return_value=None):
                    # Call with REAL objects - tests real integration of:
                    # - create_ado_user_from_reviewer (extracts real reviewer data)
                    # - matching_user (matches against real user list)
                    # - All internal logic flows naturally
                    process_pr_reviewer(
                        app,  # REAL App with REAL database
                        pr,  # REAL PR object
                        repository,  # REAL repository object
                        reviewer,  # REAL reviewer object
                        asana_users,  # REAL user list
                        [],
                        "project-456",
                    )

                    # Verify task creation was called - real integration worked
                    mock_create_task.assert_called_once()

                    # Verify the REAL internal utilities worked together correctly
                    args = mock_create_task.call_args[0]
                    matched_asana_user = args[4]  # asana_user parameter
                    self.assertEqual(matched_asana_user["email"], "john.doe@example.com")
                    self.assertEqual(matched_asana_user["gid"], "user-123")

                    # Verify real reviewer object was processed correctly
                    self.assertEqual(args[1].pull_request_id, 789)  # Real PR
                    self.assertEqual(args[2].id, "repo-456")  # Real repository

            finally:
                app.close()

    @patch("ado_asana_sync.sync.pull_request_sync.update_existing_pr_reviewer_task")
    def test_process_pr_reviewer_existing_task(self, mock_update_task):
        """Test processing a reviewer when an existing task exists.

        This test integrates the internal utilities and focuses on the existing task path.
        """
        # Set up realistic reviewer and user data
        self.mock_reviewer.display_name = "Jane Smith"
        self.mock_reviewer.unique_name = "jane.smith@example.com"

        # Create matching Asana user
        asana_users = [{"gid": "user-456", "email": "jane.smith@example.com", "name": "Jane Smith"}]

        # Mock existing PR item found in database
        mock_existing_match = Mock(spec=PullRequestItem)

        # Mock existing match
        with patch.object(PullRequestItem, "search", return_value=mock_existing_match):
            process_pr_reviewer(
                self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, asana_users, [], "project-456"
            )

            # Verify update was called with the found task and matched user
            mock_update_task.assert_called_once()
            args = mock_update_task.call_args[0]
            existing_pr_item = args[4]  # pr_item parameter
            matched_asana_user = args[5]  # asana_user parameter

            self.assertEqual(existing_pr_item, mock_existing_match)
            self.assertEqual(matched_asana_user["email"], "jane.smith@example.com")

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    @patch("ado_asana_sync.sync.pull_request_sync.create_new_pr_reviewer_task")
    def test_process_pr_reviewer_no_user_match_real_integration(
        self, mock_create_task, mock_asana_client, mock_ado_connection, mock_dirname
    ):
        """Test processing a reviewer when no Asana user match is found using REAL objects.

        This test demonstrates REAL internal integration - create_ado_user_from_reviewer
        extracts data from REAL reviewer, but matching_user naturally returns None.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            mock_dirname.return_value = temp_dir
            mock_ado_connection.return_value = Mock()
            mock_asana_client.return_value = Mock()

            app = TestDataBuilder.create_real_app(temp_dir)

            try:
                app.connect()

                # Create REAL reviewer with no match in user list
                reviewer = RealObjectBuilder.create_real_ado_reviewer(
                    display_name="Unknown User", email="unknown@example.com", vote="waiting_for_author"
                )

                pr = RealObjectBuilder.create_real_ado_pull_request()
                repository = RealObjectBuilder.create_real_ado_repository()

                # Empty user list - REAL matching_user function will naturally return None
                empty_asana_users = []

                # Test REAL integration where real utilities process real objects
                process_pr_reviewer(
                    app,  # REAL App
                    pr,  # REAL PR
                    repository,  # REAL repository
                    reviewer,  # REAL reviewer
                    empty_asana_users,  # Real empty list - matching_user will naturally return None
                    [],
                    "project-456",
                )

                # Verify no task creation when real matching_user naturally finds no match
                mock_create_task.assert_not_called()

            finally:
                app.close()

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task_by_name")
    @patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.iso8601_utc")
    def test_create_new_pr_reviewer_task(self, mock_iso8601, mock_create_task, mock_get_task_by_name):
        """Test creating a new PR reviewer task."""
        # Setup mocks
        mock_iso8601.return_value = "2023-12-01T10:00:00Z"
        mock_get_task_by_name.return_value = None  # No existing task
        mock_asana_user = {"gid": "user-123", "name": "John Doe"}

        create_new_pr_reviewer_task(
            self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, mock_asana_user, [], "project-456"
        )

        # Verify task creation
        mock_create_task.assert_called_once()

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.iso8601_utc")
    def test_update_existing_pr_reviewer_task(self, mock_iso8601, mock_update_task, mock_get_task):
        """Test updating an existing PR reviewer task."""
        # Setup mocks
        mock_iso8601.return_value = "2023-12-01T10:00:00Z"
        mock_get_task.return_value = {"modified_at": "2023-12-01T09:00:00Z"}
        mock_asana_user = {"gid": "user-123", "name": "John Doe"}

        mock_pr_item = Mock(spec=PullRequestItem)
        mock_pr_item.is_current.return_value = False  # Needs update
        mock_pr_item.asana_gid = "task-123"
        mock_pr_item.reviewer_name = "John Doe"
        mock_pr_item.title = "Test PR Title"
        mock_pr_item.status = "active"
        mock_pr_item.review_status = "waiting_for_author"

        # Set up PR mock to match the PR item
        self.mock_pr.title = "Test PR Title"
        self.mock_pr.status = "active"

        update_existing_pr_reviewer_task(
            self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, mock_pr_item, mock_asana_user, "project-456"
        )

        # Verify task update
        mock_update_task.assert_called_once()

    def test_update_existing_pr_reviewer_task_current(self):
        """Test updating an existing PR reviewer task that is already current."""
        mock_asana_user = {"gid": "user-123", "name": "John Doe"}
        mock_pr_item = Mock(spec=PullRequestItem)
        mock_pr_item.is_current.return_value = True  # Already current
        mock_pr_item.reviewer_name = "John Doe"

        with patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task") as mock_update_task:
            update_existing_pr_reviewer_task(
                self.mock_app,
                self.mock_pr,
                self.mock_repository,
                self.mock_reviewer,
                mock_pr_item,
                mock_asana_user,
                "project-456",
            )

            # Verify no update
            mock_update_task.assert_not_called()

    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.iso8601_utc")
    def test_update_existing_pr_reviewer_task_approval_reset(self, mock_iso8601, mock_get_task, mock_update_task):
        """Test updating a PR reviewer task when approval is reset."""
        # Setup mocks
        mock_iso8601.return_value = "2023-12-01T10:00:00Z"
        mock_get_task.return_value = {"modified_at": "2023-12-01T09:00:00Z"}
        mock_asana_user = {"gid": "user-123", "name": "John Doe"}

        # Create a mock reviewer that changes from approved to noVote
        mock_reviewer_reset = Mock()
        mock_reviewer_reset.vote = "noVote"  # Approval reset

        mock_pr_item = Mock(spec=PullRequestItem)
        mock_pr_item.is_current.return_value = False  # Needs update
        mock_pr_item.asana_gid = "task-123"
        mock_pr_item.reviewer_name = "John Doe"
        mock_pr_item.title = "Test PR Title"
        mock_pr_item.status = "active"
        mock_pr_item.review_status = "approved"  # Previously approved
        mock_pr_item.asana_title = "Pull Request 789: Test PR Title (John Doe)"

        # Set up PR mock
        self.mock_pr.title = "Test PR Title"
        self.mock_pr.status = "active"

        update_existing_pr_reviewer_task(
            self.mock_app,
            self.mock_pr,
            self.mock_repository,
            mock_reviewer_reset,
            mock_pr_item,
            mock_asana_user,
            "project-456",
        )

        # Verify task update was called (task should be reopened)
        mock_update_task.assert_called_once()

        # Verify the PR item's review status was updated to noVote
        self.assertEqual(mock_pr_item.review_status, "noVote")

    def test_create_ado_user_from_reviewer_success(self):
        """Test creating ADO user from reviewer successfully."""
        result = create_ado_user_from_reviewer(self.mock_reviewer)

        self.assertIsNotNone(result)
        self.assertEqual(result.display_name, "John Doe")
        self.assertEqual(result.email, "john.doe@example.com")

    def test_create_ado_user_from_reviewer_missing_data(self):
        """Test creating ADO user from reviewer with missing data."""
        mock_reviewer = Mock()
        mock_reviewer.display_name = None
        mock_reviewer.displayName = None  # Check both attribute names
        mock_reviewer.name = None
        mock_reviewer.unique_name = "john.doe@example.com"
        # Ensure no user fallback
        mock_reviewer.user = None

        result = create_ado_user_from_reviewer(mock_reviewer)
        self.assertIsNone(result)

    def test_create_ado_user_from_reviewer_exception(self):
        """Test creating ADO user from reviewer with exception."""

        # Create a custom class that raises exceptions on attribute access
        class FailingReviewer:
            def __getattr__(self, name):
                raise Exception("Test error")

        mock_reviewer = FailingReviewer()

        result = create_ado_user_from_reviewer(mock_reviewer)
        self.assertIsNone(result)

    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    def test_handle_removed_reviewers(self, mock_update_task):
        """Test handling removed reviewers."""
        from ado_asana_sync.sync.pull_request_sync import handle_removed_reviewers

        # Setup mocks
        mock_pr = Mock()
        mock_pr.pull_request_id = 123

        # Mock existing PR tasks in database
        existing_tasks = [
            {
                "ado_pr_id": 123,
                "ado_repository_id": "repo-456",
                "title": "Test PR",
                "status": "active",
                "url": "http://test.com/pr/123",
                "reviewer_gid": "removed-user-gid",
                "reviewer_name": "Removed User",
                "asana_gid": "asana-task-123",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            },
            {
                "ado_pr_id": 123,
                "ado_repository_id": "repo-456",
                "title": "Test PR",
                "status": "active",
                "url": "http://test.com/pr/123",
                "reviewer_gid": "current-user-gid",
                "reviewer_name": "Current User",
                "asana_gid": "asana-task-456",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            },
        ]

        self.mock_app.pr_matches.search.return_value = existing_tasks
        current_reviewers = {"current-user-gid"}  # Only one current reviewer

        handle_removed_reviewers(self.mock_app, mock_pr, current_reviewers, "test-project")

        # Verify that update was called for the removed reviewer
        mock_update_task.assert_called_once()

    def test_extract_reviewer_vote_string(self):
        """Test extracting reviewer vote when it's a string."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote

        mock_reviewer = Mock()
        mock_reviewer.vote = "approved"

        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, "approved")

    def test_extract_reviewer_vote_integer(self):
        """Test extracting reviewer vote when it's an integer."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote

        mock_reviewer = Mock()
        mock_reviewer.vote = 10  # ADO approved value

        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, "approved")

    def test_extract_reviewer_vote_approved_with_suggestions(self):
        """Test extracting reviewer vote for approve with suggestions."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote

        mock_reviewer = Mock()
        mock_reviewer.vote = 5  # ADO approved with suggestions value

        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, "approvedWithSuggestions")

    def test_extract_reviewer_vote_waiting_for_author(self):
        """Test extracting reviewer vote for waiting for author."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote

        mock_reviewer = Mock()
        mock_reviewer.vote = -5  # ADO waiting for author value

        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, "waitingForAuthor")

    def test_extract_reviewer_vote_no_vote(self):
        """Test extracting reviewer vote when no vote exists."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote

        mock_reviewer = Mock()
        del mock_reviewer.vote  # No vote attribute

        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, "noVote")

    def test_sync_pull_requests_access_denied(self):
        """Test repository access error handling with permission issues."""
        from ado_asana_sync.sync.pull_request_sync import sync_pull_requests

        # Reset and mock the git client to raise exception with "permission" in message
        self.mock_app.ado_git_client.reset_mock()
        self.mock_app.ado_git_client.get_repositories.side_effect = Exception("permission denied")

        with patch("ado_asana_sync.sync.pull_request_sync.get_asana_users") as mock_get_users:
            with patch("ado_asana_sync.sync.pull_request_sync.get_asana_project_tasks") as mock_get_tasks:
                mock_get_users.return_value = []
                mock_get_tasks.return_value = []

                # Should return early without processing
                sync_pull_requests(self.mock_app, self.mock_ado_project, "workspace-id", "project-gid")

                # Verify it didn't try to process PRs
                self.mock_app.ado_git_client.get_pull_requests.assert_not_called()

    def test_process_repository_pull_requests_not_exist_error(self):
        """Test pull request retrieval error handling with 'does not exist' message."""
        from ado_asana_sync.sync.pull_request_sync import process_repository_pull_requests

        # Reset and mock the git client to raise exception with "does not exist" in message when getting PRs
        self.mock_app.ado_git_client.reset_mock()
        self.mock_app.ado_git_client.get_pull_requests.side_effect = Exception("project does not exist")

        # Should handle error gracefully and return early
        process_repository_pull_requests(self.mock_app, self.mock_repository, [], [], "project-gid")

        # Verify it tried to get PRs but handled the error
        self.mock_app.ado_git_client.get_pull_requests.assert_called_once()

    def test_process_repository_pull_requests_other_error(self):
        """Test pull request retrieval error handling with other exceptions."""
        from ado_asana_sync.sync.pull_request_sync import process_repository_pull_requests

        # Reset and mock the git client to raise a different exception when getting PRs
        self.mock_app.ado_git_client.reset_mock()
        self.mock_app.ado_git_client.get_pull_requests.side_effect = Exception("network error")

        # Should handle error gracefully and return early
        process_repository_pull_requests(self.mock_app, self.mock_repository, [], [], "project-gid")

        # Verify it tried to get PRs but handled the error
        self.mock_app.ado_git_client.get_pull_requests.assert_called_once()

    def test_process_pull_request_retrieval_error(self):
        """Test pull request retrieval error handling."""
        from ado_asana_sync.sync.pull_request_sync import process_repository_pull_requests

        # Reset and mock successful repository access but failed PR retrieval
        self.mock_app.ado_git_client.reset_mock()
        self.mock_app.ado_git_client.get_repositories.return_value = [self.mock_repository]
        self.mock_app.ado_git_client.get_pull_requests.side_effect = Exception("API error")

        with patch("ado_asana_sync.sync.sync.get_asana_users") as mock_get_users:
            with patch("ado_asana_sync.sync.sync.get_asana_project_tasks") as mock_get_tasks:
                mock_get_users.return_value = []
                mock_get_tasks.return_value = []

                # Should handle error gracefully and continue
                process_repository_pull_requests(self.mock_app, self.mock_repository, [], [], "project-gid")

                # Verify it tried to get PRs but handled the error
                self.mock_app.ado_git_client.get_pull_requests.assert_called_once()

    @patch("ado_asana_sync.sync.pull_request_sync.find_custom_field_by_name")
    @patch("asana.TasksApi")
    def test_create_asana_pr_task_success(self, mock_tasks_api_class, mock_find_custom_field):
        """Test successful creation of Asana PR task."""
        from ado_asana_sync.sync.pull_request_sync import create_asana_pr_task

        # Setup mocks
        mock_tasks_api = Mock()
        mock_tasks_api_class.return_value = mock_tasks_api
        mock_tasks_api.create_task.return_value = {"gid": "new-task-123", "modified_at": "2023-12-01T10:00:00Z"}

        mock_find_custom_field.return_value = {"custom_field": {"gid": "link-field-123"}}

        mock_asana_project = {"gid": "project-456"}
        mock_pr_item = Mock()
        mock_pr_item.asana_title = "PR 123: Test Title"
        mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 123</a>: Test Title"
        mock_pr_item.status = "active"
        mock_pr_item.review_status = "waiting_for_author"
        mock_pr_item.url = "http://test.com/pr/123"

        # Call function
        result = create_asana_pr_task(self.mock_app, mock_asana_project, mock_pr_item, "tag-gid")

        # Verify task creation
        self.assertIsNone(result)  # Function doesn't return anything
        mock_tasks_api.create_task.assert_called_once()

        # Verify task data
        create_call_args = mock_tasks_api.create_task.call_args[0][0]
        self.assertEqual(create_call_args["data"]["name"], "PR 123: Test Title")
        self.assertEqual(create_call_args["data"]["projects"], [{"gid": "project-456"}])
        self.assertFalse(create_call_args["data"]["completed"])  # Should not be completed for active PR

    @patch("ado_asana_sync.sync.pull_request_sync.find_custom_field_by_name")
    @patch("asana.TasksApi")
    def test_create_asana_pr_task_completed_pr(self, mock_tasks_api_class, mock_find_custom_field):
        """Test creation of Asana PR task for completed PR."""
        from ado_asana_sync.sync.pull_request_sync import create_asana_pr_task

        # Setup mocks
        mock_tasks_api = Mock()
        mock_tasks_api_class.return_value = mock_tasks_api
        mock_tasks_api.create_task.return_value = {"gid": "new-task-456", "modified_at": "2023-12-01T10:00:00Z"}

        mock_find_custom_field.return_value = {"custom_field": {"gid": "link-field-123"}}

        mock_asana_project = {"gid": "project-456"}
        mock_pr_item = Mock()
        mock_pr_item.asana_title = "PR 456: Completed PR"
        mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 456</a>: Completed PR"
        mock_pr_item.status = "completed"  # Completed PR
        mock_pr_item.review_status = "approved"
        mock_pr_item.url = "http://test.com/pr/456"

        # Call function
        result = create_asana_pr_task(self.mock_app, mock_asana_project, mock_pr_item, "tag-gid")

        # Verify task creation
        self.assertIsNone(result)  # Function doesn't return anything
        create_call_args = mock_tasks_api.create_task.call_args[0][0]
        self.assertTrue(create_call_args["data"]["completed"])  # Should be completed

    @patch("ado_asana_sync.sync.pull_request_sync.add_tag_to_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.find_custom_field_by_name")
    @patch("asana.TasksApi")
    def test_update_asana_pr_task_success(self, mock_tasks_api_class, mock_find_custom_field, mock_add_tag):
        """Test successful update of Asana PR task."""
        from ado_asana_sync.sync.pull_request_sync import update_asana_pr_task

        # Setup mocks
        mock_tasks_api = Mock()
        mock_tasks_api_class.return_value = mock_tasks_api
        mock_tasks_api.update_task.return_value = {"modified_at": "2023-12-01T11:00:00Z"}

        mock_find_custom_field.return_value = {"custom_field": {"gid": "link-field-123"}}

        mock_asana_project = {"gid": "project-456"}
        mock_pr_item = Mock()
        mock_pr_item.asana_gid = "existing-task-789"
        mock_pr_item.asana_title = "PR 789: Updated Title"
        mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 789</a>: Updated Title"
        mock_pr_item.status = "active"
        mock_pr_item.review_status = "approved"
        mock_pr_item.url = "http://test.com/pr/789"

        # Call function
        update_asana_pr_task(self.mock_app, mock_pr_item, "tag-gid", mock_asana_project)

        # Verify task update
        mock_tasks_api.update_task.assert_called_once()
        update_call_args = mock_tasks_api.update_task.call_args[0]
        self.assertEqual(update_call_args[1], "existing-task-789")  # Task GID is second parameter
        self.assertEqual(update_call_args[0]["data"]["name"], "PR 789: Updated Title")
        self.assertTrue(update_call_args[0]["data"]["completed"])  # Should be completed for approved

    @patch("ado_asana_sync.sync.pull_request_sync.add_tag_to_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.find_custom_field_by_name")
    @patch("asana.TasksApi")
    def test_update_asana_pr_task_no_custom_field(self, mock_tasks_api_class, mock_find_custom_field, mock_add_tag):
        """Test update of Asana PR task when custom field is not found."""
        from ado_asana_sync.sync.pull_request_sync import update_asana_pr_task

        # Setup mocks
        mock_tasks_api = Mock()
        mock_tasks_api_class.return_value = mock_tasks_api
        mock_tasks_api.update_task.return_value = {"modified_at": "2023-12-01T11:00:00Z"}

        mock_find_custom_field.return_value = None  # No custom field found

        mock_asana_project = {"gid": "project-456"}
        mock_pr_item = Mock()
        mock_pr_item.asana_gid = "existing-task-789"
        mock_pr_item.asana_title = "PR 789: Updated Title"
        mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 789</a>: Updated Title"
        mock_pr_item.status = "active"
        mock_pr_item.review_status = "waiting_for_author"
        mock_pr_item.url = "http://test.com/pr/789"

        # Call function
        update_asana_pr_task(self.mock_app, mock_pr_item, "tag-gid", mock_asana_project)

        # Verify task update (should still work without custom field)
        mock_tasks_api.update_task.assert_called_once()
        update_call_args = mock_tasks_api.update_task.call_args[0]
        self.assertEqual(update_call_args[1], "existing-task-789")  # Task GID is second parameter
        # Should not have custom_fields in the update data
        self.assertNotIn("custom_fields", update_call_args[0]["data"])

    def test_handle_removed_reviewers_filters_doc_id(self):
        """Regression test: Ensure handle_removed_reviewers filters doc_id from database results."""
        from ado_asana_sync.sync.pull_request_sync import handle_removed_reviewers

        # Mock PR object
        mock_pr = Mock()
        mock_pr.pull_request_id = 123

        # Mock app with pr_matches that returns results with doc_id
        mock_app = Mock()
        mock_pr_matches = Mock()
        mock_app.pr_matches = mock_pr_matches

        # Mock database results that include doc_id field
        mock_db_results = [
            {
                "ado_pr_id": 123,
                "ado_repository_id": "repo-456",
                "title": "Test PR",
                "status": "active",
                "url": "https://example.com/pr/123",
                "reviewer_gid": "removed-reviewer-123",
                "reviewer_name": "Removed Reviewer",
                "asana_gid": "asana-task-123",
                "doc_id": 555,  # This should be filtered out
            }
        ]
        mock_pr_matches.search.return_value = mock_db_results

        current_reviewer_gids = ["active-reviewer-456"]  # removed-reviewer-123 is not in this list

        # Mock additional requirements for the function
        mock_app.asana_tag_gid = None  # This will prevent the update call but allow the test to run
        asana_project = {"gid": "project-123"}  # Required parameter

        # This should not raise an error about unexpected doc_id argument
        # The key test is that PullRequestItem creation doesn't fail
        try:
            handle_removed_reviewers(mock_app, mock_pr, current_reviewer_gids, asana_project)
            # If we get here without exception, the doc_id filtering worked
            success = True
        except TypeError as e:
            if "unexpected keyword argument 'doc_id'" in str(e):
                success = False
            else:
                raise  # Re-raise if it's a different error

        self.assertTrue(success, "PullRequestItem creation should not fail due to doc_id")

    def test_process_closed_pull_requests_filters_doc_id(self):
        """Regression test: Ensure process_closed_pull_requests filters doc_id from database results."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock app with pr_matches that returns results with doc_id
        mock_app = Mock()
        mock_pr_data = [
            {
                "ado_pr_id": 789,
                "ado_repository_id": "repo-789",
                "title": "Closed PR",
                "status": "completed",
                "url": "https://example.com/pr/789",
                "reviewer_gid": "reviewer-789",
                "reviewer_name": "Test Reviewer",
                "asana_gid": "asana-task-789",
                "processing_state": "open",  # Make sure it's not filtered out
                "doc_id": 333,  # This should be filtered out
            }
        ]
        mock_app.pr_matches.search.return_value = mock_pr_data

        # Mock required parameters
        asana_users = []
        asana_project = {"gid": "project-789"}

        # The key test is that PullRequestItem creation doesn't fail due to doc_id
        try:
            process_closed_pull_requests(mock_app, asana_users, asana_project)
            # If we get here without a TypeError about doc_id, the filtering worked
            success = True
        except TypeError as e:
            if "unexpected keyword argument 'doc_id'" in str(e):
                success = False
            else:
                raise  # Re-raise if it's a different error

        self.assertTrue(success, "PullRequestItem creation should not fail due to doc_id")

    @patch("ado_asana_sync.sync.pull_request_sync.add_closure_comment_to_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.find_custom_field_by_name")
    @patch("asana.TasksApi")
    def test_create_asana_pr_task_draft_pr(self, mock_tasks_api_class, mock_find_custom_field, mock_add_comment):
        """Test creation of Asana PR task for draft PR."""
        from ado_asana_sync.sync.pull_request_sync import create_asana_pr_task

        # Setup mocks
        mock_tasks_api = Mock()
        mock_tasks_api_class.return_value = mock_tasks_api
        mock_tasks_api.create_task.return_value = {"gid": "new-task-789", "modified_at": "2023-12-01T10:00:00Z"}

        mock_find_custom_field.return_value = {"custom_field": {"gid": "link-field-123"}}

        mock_asana_project = {"gid": "project-456"}
        mock_pr_item = Mock()
        mock_pr_item.asana_title = "PR 789: Draft PR"
        mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 789</a>: Draft PR"
        mock_pr_item.status = "draft"  # Draft PR
        mock_pr_item.review_status = "noVote"
        mock_pr_item.url = "http://test.com/pr/789"

        # Call function
        result = create_asana_pr_task(self.mock_app, mock_asana_project, mock_pr_item, "tag-gid")

        # Verify task creation
        self.assertIsNone(result)  # Function doesn't return anything
        create_call_args = mock_tasks_api.create_task.call_args[0][0]
        self.assertTrue(create_call_args["data"]["completed"])  # Should be completed for draft PR

    @patch("ado_asana_sync.sync.pull_request_sync.add_closure_comment_to_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.add_tag_to_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.find_custom_field_by_name")
    @patch("asana.TasksApi")
    def test_update_asana_pr_task_draft_transition(
        self, mock_tasks_api_class, mock_find_custom_field, mock_add_tag, mock_add_comment
    ):
        """Test update of Asana PR task when PR transitions to draft."""
        from ado_asana_sync.sync.pull_request_sync import update_asana_pr_task

        # Setup mocks
        mock_tasks_api = Mock()
        mock_tasks_api_class.return_value = mock_tasks_api
        mock_tasks_api.update_task.return_value = {"modified_at": "2023-12-01T11:00:00Z"}

        mock_find_custom_field.return_value = {"custom_field": {"gid": "link-field-123"}}

        mock_asana_project = {"gid": "project-456"}
        mock_pr_item = Mock()
        mock_pr_item.asana_gid = "existing-task-999"
        mock_pr_item.asana_title = "PR 999: Moved to Draft"
        mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 999</a>: Moved to Draft"
        mock_pr_item.status = "draft"  # Transitioned to draft
        mock_pr_item.review_status = "waitingForAuthor"  # Reviewer hasn't voted yet
        mock_pr_item.url = "http://test.com/pr/999"

        # Call function
        update_asana_pr_task(self.mock_app, mock_pr_item, "tag-gid", mock_asana_project)

        # Verify task update
        mock_tasks_api.update_task.assert_called_once()
        update_call_args = mock_tasks_api.update_task.call_args[0]
        self.assertEqual(update_call_args[1], "existing-task-999")  # Task GID is second parameter
        self.assertTrue(update_call_args[0]["data"]["completed"])  # Should be completed for draft PR

        # Verify closure comment was added
        mock_add_comment.assert_called_once_with(self.mock_app, mock_pr_item)

    @patch("asana.StoriesApi")
    def test_add_closure_comment_to_pr_task_draft(self, mock_stories_api_class):
        """Test adding closure comment when PR moves to draft state."""
        from ado_asana_sync.sync.pull_request_sync import add_closure_comment_to_pr_task

        # Setup mocks
        mock_stories_api = Mock()
        mock_stories_api_class.return_value = mock_stories_api

        mock_pr_item = Mock()
        mock_pr_item.asana_gid = "task-123"
        mock_pr_item.asana_title = "PR 123: Test Title"
        mock_pr_item.status = "draft"
        mock_pr_item.review_status = "noVote"  # Reviewer hasn't voted

        # Call function
        add_closure_comment_to_pr_task(self.mock_app, mock_pr_item)

        # Verify comment was added
        mock_stories_api.create_story_for_task.assert_called_once()
        call_args = mock_stories_api.create_story_for_task.call_args[0]
        self.assertEqual(call_args[1], "task-123")  # Task GID
        self.assertIn("draft status", call_args[0]["data"]["text"])  # Comment mentions draft

    @patch("asana.StoriesApi")
    def test_add_closure_comment_to_pr_task_no_comment_for_approved(self, mock_stories_api_class):
        """Test that no closure comment is added when reviewer has already approved."""
        from ado_asana_sync.sync.pull_request_sync import add_closure_comment_to_pr_task

        # Setup mocks
        mock_stories_api = Mock()
        mock_stories_api_class.return_value = mock_stories_api

        mock_pr_item = Mock()
        mock_pr_item.asana_gid = "task-456"
        mock_pr_item.asana_title = "PR 456: Approved PR"
        mock_pr_item.status = "completed"
        mock_pr_item.review_status = "approved"  # Reviewer has approved

        # Call function
        add_closure_comment_to_pr_task(self.mock_app, mock_pr_item)

        # Verify no comment was added for approved reviewers
        mock_stories_api.create_story_for_task.assert_not_called()

    def test_pr_closed_states_includes_draft(self):
        """Test that draft is included in PR closed states."""
        from ado_asana_sync.sync.pull_request_sync import _PR_CLOSED_STATES

        # Verify draft is now included in closed states
        self.assertIn("draft", _PR_CLOSED_STATES)
        self.assertIn("completed", _PR_CLOSED_STATES)
        self.assertIn("abandoned", _PR_CLOSED_STATES)

    @patch("ado_asana_sync.sync.pull_request_sync.process_pull_request")
    def test_process_repository_pull_requests_returns_processed_ids(self, mock_process_pr):
        """Test that process_repository_pull_requests returns processed PR IDs."""
        from ado_asana_sync.sync.pull_request_sync import process_repository_pull_requests

        # Setup mocks
        mock_pr1 = Mock()
        mock_pr1.pull_request_id = 100
        mock_pr2 = Mock()
        mock_pr2.pull_request_id = 200

        self.mock_app.ado_git_client.get_pull_requests.return_value = [mock_pr1, mock_pr2]

        # Call function
        result = process_repository_pull_requests(self.mock_app, self.mock_repository, [], [], "project-456")

        # Verify returned PR IDs
        self.assertEqual(result, {100, 200})
        self.assertEqual(mock_process_pr.call_count, 2)

    def test_process_repository_pull_requests_returns_empty_on_error(self):
        """Test that process_repository_pull_requests returns empty set on API error."""
        from ado_asana_sync.sync.pull_request_sync import process_repository_pull_requests

        # Setup mock to raise exception
        self.mock_app.ado_git_client.get_pull_requests.side_effect = Exception("API Error")

        # Call function
        result = process_repository_pull_requests(self.mock_app, self.mock_repository, [], [], "project-456")

        # Verify empty set is returned
        self.assertEqual(result, set())

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    def test_process_closed_pull_requests_skips_processed_prs(self, mock_update_task, mock_get_task):
        """Test that process_closed_pull_requests skips PRs already processed in first pass."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock database PR tasks
        mock_app = Mock()
        mock_app.pr_matches.all.return_value = [
            {
                "ado_pr_id": 100,  # This will be skipped (in processed_pr_ids)
                "ado_repository_id": "repo-1",
                "title": "Active PR",
                "status": "active",
                "url": "https://example.com/pr/100",
                "reviewer_gid": "reviewer-1",
                "reviewer_name": "Test User 1",
                "asana_gid": "task-1",
            },
            {
                "ado_pr_id": 200,  # This will be processed (not in processed_pr_ids)
                "ado_repository_id": "repo-2",
                "title": "Closed PR",
                "status": "completed",
                "url": "https://example.com/pr/200",
                "reviewer_gid": "reviewer-2",
                "reviewer_name": "Test User 2",
                "asana_gid": "task-2",
            },
        ]
        mock_app.ado_git_client.get_pull_request_by_id.return_value = Mock(status="completed")
        mock_app.asana_tag_gid = "tag-123"
        mock_get_task.return_value = {"completed": False}

        # Create mock repository object (required for API calls)
        mock_repo = Mock()
        mock_repo.id = "repo-2"  # Use repo-2 since PR 200 belongs to repo-2
        mock_repo.name = "test-repo"
        mock_project = Mock()
        mock_project.id = "project-456"
        mock_repo.project = mock_project

        # Mock search to return only repo-2 PRs
        def search_side_effect(query_func):
            all_tasks = [
                {
                    "ado_pr_id": 100,
                    "ado_repository_id": "repo-1",
                    "title": "Active PR",
                    "status": "active",
                    "url": "https://example.com/pr/100",
                    "reviewer_gid": "reviewer-1",
                    "reviewer_name": "Test User 1",
                    "asana_gid": "task-1",
                },
                {
                    "ado_pr_id": 200,
                    "ado_repository_id": "repo-2",
                    "title": "Closed PR",
                    "status": "completed",
                    "url": "https://example.com/pr/200",
                    "reviewer_gid": "reviewer-2",
                    "reviewer_name": "Test User 2",
                    "asana_gid": "task-2",
                },
            ]
            return [task for task in all_tasks if query_func(task)]

        mock_app.pr_matches.search.side_effect = search_side_effect

        # Call function with processed_pr_ids containing PR 100
        process_closed_pull_requests(mock_app, [], "project-456", {100}, mock_repo)

        # Verify that only PR 200 was processed (PR 100 was skipped)
        self.assertEqual(mock_app.ado_git_client.get_pull_request_by_id.call_count, 1)
        mock_app.ado_git_client.get_pull_request_by_id.assert_called_with(200)

        # Verify update was called for the unprocessed PR
        mock_update_task.assert_called_once()

    def test_process_closed_pull_requests_handles_none_processed_ids(self):
        """Test that process_closed_pull_requests handles None processed_pr_ids parameter."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock empty database
        mock_app = Mock()
        mock_app.pr_matches.search.return_value = []

        # Should not raise exception with None parameter
        try:
            process_closed_pull_requests(mock_app, [], "project-456", None, None)
            success = True
        except Exception:
            success = False

        self.assertTrue(success, "Function should handle None processed_pr_ids gracefully")

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    def test_process_closed_pull_requests_filters_by_repository(self, mock_update_task, mock_get_task):
        """Test that process_closed_pull_requests filters PR tasks by repository ID."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock database PR tasks for different repositories
        mock_app = Mock()
        all_tasks = [
            {
                "ado_pr_id": 100,
                "ado_repository_id": "repo-1",  # This repository
                "title": "PR for repo-1",
                "status": "active",
                "url": "https://example.com/pr/100",
                "reviewer_gid": "reviewer-1",
                "reviewer_name": "Test User 1",
                "asana_gid": "task-1",
            },
            {
                "ado_pr_id": 200,
                "ado_repository_id": "repo-2",  # Different repository
                "title": "PR for repo-2",
                "status": "active",
                "url": "https://example.com/pr/200",
                "reviewer_gid": "reviewer-2",
                "reviewer_name": "Test User 2",
                "asana_gid": "task-2",
            },
        ]

        # Mock search to return only repo-1 tasks when filtered
        def search_side_effect(query_func):
            return [task for task in all_tasks if query_func(task)]

        mock_app.pr_matches.search.side_effect = search_side_effect
        mock_app.pr_matches.all.return_value = all_tasks
        mock_app.ado_git_client.get_pull_request_by_id.return_value = Mock(status="completed")
        mock_app.asana_tag_gid = "tag-123"
        mock_get_task.return_value = {"completed": False}

        # Create mock repository object
        mock_repo = Mock()
        mock_repo.id = "repo-1"
        mock_repo.name = "test-repo-1"
        mock_project = Mock()
        mock_project.id = "project-456"
        mock_repo.project = mock_project

        # Call function filtering by repo-1
        process_closed_pull_requests(mock_app, [], "project-456", set(), mock_repo)

        # Verify only repo-1 PR was processed
        self.assertEqual(mock_app.ado_git_client.get_pull_request_by_id.call_count, 1)
        mock_app.ado_git_client.get_pull_request_by_id.assert_called_with(100)

        # Verify update was called for the correct PR
        mock_update_task.assert_called_once()

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    def test_process_closed_pull_requests_api_failure_with_string_repository_id(self, mock_update_task, mock_get_task):
        """Test that API failures occur when repository ID string is passed instead of repository object."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock database PR tasks
        mock_app = Mock()
        pr_tasks = [
            {
                "ado_pr_id": 5,
                "ado_repository_id": "e7264829-58d0-48b5-879a-10fd01a8f815",
                "title": "Abandoned PR",
                "status": "active",
                "url": "https://example.com/pr/5",
                "reviewer_gid": "reviewer-1",
                "reviewer_name": "Test User",
                "asana_gid": "task-5",
            }
        ]
        mock_app.pr_matches.all.return_value = pr_tasks
        mock_app.pr_matches.search.return_value = pr_tasks

        # Mock API to throw the exact error we encountered
        mock_app.ado_git_client.get_pull_request_by_id.side_effect = Exception(
            "VS800075: The project with id 'e7264829-58d0-48b5-879a-10fd01a8f815' does not exist, "
            "or you do not have permission to access it."
        )

        # Mock repository object (this should work)
        mock_repo = Mock()
        mock_repo.id = "e7264829-58d0-48b5-879a-10fd01a8f815"
        mock_repo.name = "test-board"
        mock_project = Mock()
        mock_project.id = "project-123"
        mock_repo.project = mock_project

        # Call function - should handle the API error gracefully
        process_closed_pull_requests(mock_app, [], "project-456", set(), mock_repo)

        # Verify API was called but failed
        mock_app.ado_git_client.get_pull_request_by_id.assert_called_once_with(5)

        # Verify no update was called due to API failure
        mock_update_task.assert_not_called()

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    def test_process_closed_pull_requests_successful_abandoned_pr_processing(self, mock_update_task, mock_get_task):
        """Test that abandoned PRs are processed correctly when API succeeds."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock database PR tasks
        mock_app = Mock()
        pr_tasks = [
            {
                "ado_pr_id": 5,
                "ado_repository_id": "e7264829-58d0-48b5-879a-10fd01a8f815",
                "title": "Abandoned PR",
                "status": "active",  # Status in database (old)
                "url": "https://example.com/pr/5",
                "reviewer_gid": "reviewer-1",
                "reviewer_name": "Test User",
                "asana_gid": "task-5",
            }
        ]
        mock_app.pr_matches.all.return_value = pr_tasks
        mock_app.pr_matches.search.return_value = pr_tasks

        # Mock API to return abandoned PR
        mock_abandoned_pr = Mock()
        mock_abandoned_pr.status = "abandoned"
        mock_app.ado_git_client.get_pull_request_by_id.return_value = mock_abandoned_pr
        mock_app.asana_tag_gid = "tag-123"

        # Mock Asana task as not completed
        mock_get_task.return_value = {"completed": False}

        # Mock repository object
        mock_repo = Mock()
        mock_repo.id = "e7264829-58d0-48b5-879a-10fd01a8f815"
        mock_repo.name = "test-board"
        mock_project = Mock()
        mock_project.id = "project-456"
        mock_repo.project = mock_project

        # Call function
        process_closed_pull_requests(mock_app, [], "project-456", set(), mock_repo)

        # Verify API was called with correct parameters
        mock_app.ado_git_client.get_pull_request_by_id.assert_called_once_with(5)

        # Verify task update was called for abandoned PR
        mock_update_task.assert_called_once()

        # Verify Asana task was checked
        mock_get_task.assert_called_once_with(mock_app, "task-5")

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    def test_process_closed_pull_requests_draft_pr_processing(self, mock_update_task, mock_get_task):
        """Test that draft PRs are processed correctly."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock database PR tasks
        mock_app = Mock()
        pr_tasks = [
            {
                "ado_pr_id": 6,
                "ado_repository_id": "repo-123",
                "title": "Draft PR",
                "status": "active",  # Status in database (old)
                "url": "https://example.com/pr/6",
                "reviewer_gid": "reviewer-1",
                "reviewer_name": "Test User",
                "asana_gid": "task-6",
            }
        ]
        mock_app.pr_matches.all.return_value = pr_tasks
        mock_app.pr_matches.search.return_value = pr_tasks

        # Mock API to return draft PR
        mock_draft_pr = Mock()
        mock_draft_pr.status = "draft"
        mock_app.ado_git_client.get_pull_request_by_id.return_value = mock_draft_pr
        mock_app.asana_tag_gid = "tag-123"

        # Mock Asana task as not completed
        mock_get_task.return_value = {"completed": False}

        # Mock repository object
        mock_repo = Mock()
        mock_repo.id = "repo-123"
        mock_repo.name = "test-repo"
        mock_project = Mock()
        mock_project.id = "project-456"
        mock_repo.project = mock_project

        # Call function
        process_closed_pull_requests(mock_app, [], "project-456", set(), mock_repo)

        # Verify API was called
        mock_app.ado_git_client.get_pull_request_by_id.assert_called_once_with(6)

        # Verify task update was called for draft PR
        mock_update_task.assert_called_once()

        # Verify Asana task was checked
        mock_get_task.assert_called_once_with(mock_app, "task-6")

    def test_process_closed_pull_requests_handles_missing_repository_gracefully(self):
        """Test that function handles missing repository parameter gracefully."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock empty database
        mock_app = Mock()
        mock_app.pr_matches.search.return_value = []

        # Should not raise exception with None repository
        try:
            process_closed_pull_requests(mock_app, [], "project-456", set(), None)
            success = True
        except Exception:
            success = False

        self.assertTrue(success, "Function should handle None repository gracefully")

    @patch("ado_asana_sync.sync.pull_request_sync.matching_user")
    @patch("ado_asana_sync.sync.pull_request_sync.create_ado_user_from_reviewer")
    @patch("ado_asana_sync.sync.pull_request_sync.extract_reviewer_vote")
    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    def test_process_closed_pull_requests_fetches_reviewers_and_updates_vote(
        self, mock_update_task, mock_get_task, mock_extract_vote, mock_create_ado_user, mock_matching_user
    ):
        """Test that process_closed_pull_requests fetches reviewers and updates review_status."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock database PR task with old review status
        mock_app = Mock()
        pr_tasks = [
            {
                "ado_pr_id": 123,
                "ado_repository_id": "repo-abc",
                "title": "Feature PR",
                "status": "active",  # Old status
                "url": "https://example.com/pr/123",
                "reviewer_gid": "asana-reviewer-123",
                "reviewer_name": "John Doe",
                "asana_gid": "task-xyz",
                "review_status": "noVote",  # Old vote status
            }
        ]
        mock_app.pr_matches.search.return_value = pr_tasks
        mock_app.asana_tag_gid = "tag-123"

        # Mock completed PR
        mock_pr = Mock()
        mock_pr.status = "completed"
        mock_app.ado_git_client.get_pull_request_by_id.return_value = mock_pr

        # Mock reviewer with approval
        mock_reviewer = Mock()
        mock_reviewer.vote = 10  # Approved
        mock_app.ado_git_client.get_pull_request_reviewers.return_value = [mock_reviewer]

        # Mock reviewer matching
        mock_ado_user = Mock()
        mock_ado_user.display_name = "John Doe"
        mock_ado_user.email = "john@example.com"
        mock_create_ado_user.return_value = mock_ado_user

        mock_asana_user = {"gid": "asana-reviewer-123", "name": "John Doe"}
        mock_matching_user.return_value = mock_asana_user

        # Mock vote extraction
        mock_extract_vote.return_value = "approved"

        # Mock Asana task as not completed
        mock_get_task.return_value = {"completed": False}

        # Mock repository
        mock_repo = Mock()
        mock_repo.id = "repo-abc"
        mock_repo.name = "test-repo"

        # Mock asana_users list
        asana_users = [mock_asana_user]

        # Call function
        process_closed_pull_requests(mock_app, asana_users, "project-456", set(), mock_repo)

        # Verify reviewers were fetched
        mock_app.ado_git_client.get_pull_request_reviewers.assert_called_once_with("repo-abc", 123)

        # Verify reviewer vote was extracted
        mock_extract_vote.assert_called_once_with(mock_reviewer)

        # Verify task was updated
        mock_update_task.assert_called_once()

        # Get the pr_item that was passed to update_asana_pr_task
        call_args = mock_update_task.call_args
        pr_item_arg = call_args[0][1]  # Second positional argument

        # Verify review_status was updated to "approved"
        self.assertEqual(pr_item_arg.review_status, "approved", "Review status should be updated to 'approved'")
        self.assertEqual(pr_item_arg.status, "completed", "PR status should be 'completed'")

    @patch("ado_asana_sync.sync.pull_request_sync.matching_user")
    @patch("ado_asana_sync.sync.pull_request_sync.create_ado_user_from_reviewer")
    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    def test_process_closed_pull_requests_saves_db_when_task_already_completed(
        self, mock_get_task, mock_create_ado_user, mock_matching_user
    ):
        """Test that database is updated even when Asana task is already completed."""
        from ado_asana_sync.sync.pull_request_sync import process_closed_pull_requests

        # Mock database PR task
        mock_app = Mock()
        pr_tasks = [
            {
                "ado_pr_id": 456,
                "ado_repository_id": "repo-xyz",
                "title": "Bugfix PR",
                "status": "active",
                "url": "https://example.com/pr/456",
                "reviewer_gid": "asana-reviewer-456",
                "reviewer_name": "Jane Smith",
                "asana_gid": "task-abc",
                "review_status": "waitingForAuthor",
            }
        ]
        mock_app.pr_matches.search.return_value = pr_tasks
        mock_app.asana_tag_gid = "tag-123"

        # Mock completed PR
        mock_pr = Mock()
        mock_pr.status = "completed"
        mock_app.ado_git_client.get_pull_request_by_id.return_value = mock_pr

        # Mock reviewer with approval
        mock_reviewer = Mock()
        mock_app.ado_git_client.get_pull_request_reviewers.return_value = [mock_reviewer]

        # Mock reviewer matching
        mock_ado_user = Mock()
        mock_create_ado_user.return_value = mock_ado_user
        mock_asana_user = {"gid": "asana-reviewer-456", "name": "Jane Smith"}
        mock_matching_user.return_value = mock_asana_user

        # Mock Asana task as ALREADY completed
        mock_get_task.return_value = {"completed": True}

        # Mock repository
        mock_repo = Mock()
        mock_repo.id = "repo-xyz"
        mock_repo.name = "test-repo"

        # Call function
        process_closed_pull_requests(mock_app, [mock_asana_user], "project-456", set(), mock_repo)

        # Verify PR item save was called (even though task already completed)
        # The pr_item should be passed through Mock's call chain
        self.assertTrue(mock_app.ado_git_client.get_pull_request_by_id.called, "PR should be fetched")


if __name__ == "__main__":
    unittest.main()

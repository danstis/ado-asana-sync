"""Tests for the pull request sync functionality."""

import unittest
from unittest.mock import Mock, patch, MagicMock

from ado_asana_sync.sync.pull_request_sync import (
    sync_pull_requests,
    process_repository_pull_requests,
    process_pull_request,
    process_pr_reviewer,
    create_new_pr_reviewer_task,
    update_existing_pr_reviewer_task,
    create_ado_user_from_reviewer,
)
from ado_asana_sync.sync.app import App
from ado_asana_sync.sync.pull_request_item import PullRequestItem


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

    @patch('ado_asana_sync.sync.sync.get_asana_users')
    @patch('ado_asana_sync.sync.sync.get_asana_project_tasks')
    @patch('ado_asana_sync.sync.pull_request_sync.process_closed_pull_requests')
    def test_sync_pull_requests(self, mock_process_closed, mock_get_tasks, mock_get_users):
        """Test the main sync_pull_requests function."""
        # Setup mocks
        mock_get_users.return_value = [{"gid": "user-123", "email": "john.doe@example.com", "name": "John Doe"}]
        mock_get_tasks.return_value = []
        self.mock_app.ado_git_client.get_repositories.return_value = [self.mock_repository]

        with patch('ado_asana_sync.sync.pull_request_sync.process_repository_pull_requests') as mock_process_repo:
            sync_pull_requests(self.mock_app, self.mock_ado_project, "workspace-123", "project-456")

            # Verify calls
            mock_get_users.assert_called_once_with(self.mock_app, "workspace-123")
            mock_get_tasks.assert_called_once_with(self.mock_app, "project-456")
            self.mock_app.ado_git_client.get_repositories.assert_called_once_with("project-123")
            mock_process_repo.assert_called_once()
            mock_process_closed.assert_called_once()

    @patch('ado_asana_sync.sync.pull_request_sync.process_pull_request')
    def test_process_repository_pull_requests(self, mock_process_pr):
        """Test processing pull requests for a repository."""
        # Setup mocks
        self.mock_app.ado_git_client.get_pull_requests.return_value = [self.mock_pr]

        process_repository_pull_requests(
            self.mock_app, self.mock_repository, [], [], "project-456"
        )

        # Verify calls
        self.mock_app.ado_git_client.get_pull_requests.assert_called_once()
        mock_process_pr.assert_called_once_with(
            self.mock_app, self.mock_pr, self.mock_repository, [], [], "project-456"
        )

    @patch('ado_asana_sync.sync.pull_request_sync.handle_removed_reviewers')
    @patch('ado_asana_sync.sync.pull_request_sync.process_pr_reviewer')
    def test_process_pull_request(self, mock_process_reviewer, mock_handle_removed):
        """Test processing a single pull request."""
        # Setup mocks
        self.mock_app.ado_git_client.get_pull_request_reviewers.return_value = [self.mock_reviewer]

        process_pull_request(
            self.mock_app, self.mock_pr, self.mock_repository, [], [], "project-456"
        )

        # Verify calls
        self.mock_app.ado_git_client.get_pull_request_reviewers.assert_called_once_with(
            "repo-456", 789
        )
        mock_process_reviewer.assert_called_once()
        mock_handle_removed.assert_called_once()

    @patch('ado_asana_sync.sync.pull_request_sync.handle_removed_reviewers')
    def test_process_pull_request_no_reviewers(self, mock_handle_removed):
        """Test processing a pull request with no reviewers."""
        # Setup mocks
        self.mock_app.ado_git_client.get_pull_request_reviewers.return_value = []

        with patch('ado_asana_sync.sync.pull_request_sync.process_pr_reviewer') as mock_process_reviewer:
            process_pull_request(
                self.mock_app, self.mock_pr, self.mock_repository, [], [], "project-456"
            )

            # Verify no reviewer processing but removed reviewers are handled
            mock_process_reviewer.assert_not_called()
            mock_handle_removed.assert_called_once_with(self.mock_app, self.mock_pr, set(), "project-456")

    @patch('ado_asana_sync.sync.pull_request_sync.create_ado_user_from_reviewer')
    @patch('ado_asana_sync.sync.sync.matching_user')
    @patch('ado_asana_sync.sync.pull_request_sync.create_new_pr_reviewer_task')
    def test_process_pr_reviewer_new_task(self, mock_create_task, mock_matching_user, mock_create_user):
        """Test processing a reviewer when no existing task exists."""
        # Setup mocks
        mock_ado_user = Mock()
        mock_ado_user.display_name = "John Doe"
        mock_ado_user.email = "john.doe@example.com"
        mock_create_user.return_value = mock_ado_user

        mock_asana_user = {"gid": "user-123", "email": "john.doe@example.com", "name": "John Doe"}
        mock_matching_user.return_value = mock_asana_user

        # Mock no existing match
        with patch.object(PullRequestItem, 'search', return_value=None):
            process_pr_reviewer(
                self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, [], [], "project-456"
            )

            # Verify calls
            mock_create_user.assert_called_once_with(self.mock_reviewer)
            mock_matching_user.assert_called_once_with([], mock_ado_user)
            mock_create_task.assert_called_once()

    @patch('ado_asana_sync.sync.pull_request_sync.create_ado_user_from_reviewer')
    @patch('ado_asana_sync.sync.sync.matching_user')
    @patch('ado_asana_sync.sync.pull_request_sync.update_existing_pr_reviewer_task')
    def test_process_pr_reviewer_existing_task(self, mock_update_task, mock_matching_user, mock_create_user):
        """Test processing a reviewer when an existing task exists."""
        # Setup mocks
        mock_ado_user = Mock()
        mock_ado_user.display_name = "John Doe"
        mock_ado_user.email = "john.doe@example.com"
        mock_create_user.return_value = mock_ado_user

        mock_asana_user = {"gid": "user-123", "email": "john.doe@example.com", "name": "John Doe"}
        mock_matching_user.return_value = mock_asana_user

        mock_existing_match = Mock(spec=PullRequestItem)
        
        # Mock existing match
        with patch.object(PullRequestItem, 'search', return_value=mock_existing_match):
            process_pr_reviewer(
                self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, [], [], "project-456"
            )

            # Verify calls
            mock_create_user.assert_called_once_with(self.mock_reviewer)
            mock_matching_user.assert_called_once_with([], mock_ado_user)
            mock_update_task.assert_called_once()

    @patch('ado_asana_sync.sync.pull_request_sync.create_ado_user_from_reviewer')
    def test_process_pr_reviewer_no_user_match(self, mock_create_user):
        """Test processing a reviewer when no Asana user match is found."""
        # Setup mocks
        mock_ado_user = Mock()
        mock_ado_user.display_name = "John Doe"
        mock_ado_user.email = "john.doe@example.com"
        mock_create_user.return_value = mock_ado_user

        with patch('ado_asana_sync.sync.sync.matching_user', return_value=None):
            with patch('ado_asana_sync.sync.pull_request_sync.create_new_pr_reviewer_task') as mock_create_task:
                process_pr_reviewer(
                    self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, [], [], "project-456"
                )

                # Verify no task creation
                mock_create_task.assert_not_called()

    @patch('ado_asana_sync.sync.sync.get_asana_task_by_name')
    @patch('ado_asana_sync.sync.pull_request_sync.create_asana_pr_task')
    @patch('ado_asana_sync.sync.pull_request_sync.iso8601_utc')
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

    @patch('ado_asana_sync.sync.pull_request_sync.get_asana_task')
    @patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task')
    @patch('ado_asana_sync.sync.pull_request_sync.iso8601_utc')
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

        with patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task') as mock_update_task:
            update_existing_pr_reviewer_task(
                self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, mock_pr_item, mock_asana_user, "project-456"
            )

            # Verify no update
            mock_update_task.assert_not_called()

    @patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task')
    @patch('ado_asana_sync.sync.pull_request_sync.get_asana_task')
    @patch('ado_asana_sync.sync.pull_request_sync.iso8601_utc')
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
            self.mock_app, self.mock_pr, self.mock_repository, mock_reviewer_reset, 
            mock_pr_item, mock_asana_user, "project-456"
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

    @patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task')
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
            }
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
        mock_reviewer.vote = 'approved'
        
        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, 'approved')

    def test_extract_reviewer_vote_integer(self):
        """Test extracting reviewer vote when it's an integer."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote
        
        mock_reviewer = Mock()
        mock_reviewer.vote = 10  # ADO approved value
        
        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, 'approved')

    def test_extract_reviewer_vote_approved_with_suggestions(self):
        """Test extracting reviewer vote for approve with suggestions."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote
        
        mock_reviewer = Mock()
        mock_reviewer.vote = 5  # ADO approved with suggestions value
        
        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, 'approvedWithSuggestions')

    def test_extract_reviewer_vote_waiting_for_author(self):
        """Test extracting reviewer vote for waiting for author."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote
        
        mock_reviewer = Mock()
        mock_reviewer.vote = -5  # ADO waiting for author value
        
        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, 'waitingForAuthor')

    def test_extract_reviewer_vote_no_vote(self):
        """Test extracting reviewer vote when no vote exists."""
        from ado_asana_sync.sync.pull_request_sync import extract_reviewer_vote
        
        mock_reviewer = Mock()
        del mock_reviewer.vote  # No vote attribute
        
        result = extract_reviewer_vote(mock_reviewer)
        self.assertEqual(result, 'noVote')

    def test_sync_pull_requests_access_denied(self):
        """Test repository access error handling with permission issues."""
        from ado_asana_sync.sync.pull_request_sync import sync_pull_requests
        
        # Reset and mock the git client to raise exception with "permission" in message
        self.mock_app.ado_git_client.reset_mock()
        self.mock_app.ado_git_client.get_repositories.side_effect = Exception("permission denied")
        
        with patch('ado_asana_sync.sync.sync.get_asana_users') as mock_get_users:
            with patch('ado_asana_sync.sync.sync.get_asana_project_tasks') as mock_get_tasks:
                mock_get_users.return_value = []
                mock_get_tasks.return_value = []
                
                # Should return early without processing
                sync_pull_requests(
                    self.mock_app, self.mock_ado_project, "workspace-id", "project-gid"
                )
                
                # Verify it didn't try to process PRs
                self.mock_app.ado_git_client.get_pull_requests.assert_not_called()

    def test_process_repository_pull_requests_not_exist_error(self):
        """Test pull request retrieval error handling with 'does not exist' message."""
        from ado_asana_sync.sync.pull_request_sync import process_repository_pull_requests
        
        # Reset and mock the git client to raise exception with "does not exist" in message when getting PRs
        self.mock_app.ado_git_client.reset_mock()
        self.mock_app.ado_git_client.get_pull_requests.side_effect = Exception("project does not exist")
        
        # Should handle error gracefully and return early
        process_repository_pull_requests(
            self.mock_app, self.mock_repository, [], [], "project-gid"
        )
        
        # Verify it tried to get PRs but handled the error
        self.mock_app.ado_git_client.get_pull_requests.assert_called_once()

    def test_process_repository_pull_requests_other_error(self):
        """Test pull request retrieval error handling with other exceptions."""
        from ado_asana_sync.sync.pull_request_sync import process_repository_pull_requests
        
        # Reset and mock the git client to raise a different exception when getting PRs
        self.mock_app.ado_git_client.reset_mock()
        self.mock_app.ado_git_client.get_pull_requests.side_effect = Exception("network error")
        
        # Should handle error gracefully and return early
        process_repository_pull_requests(
            self.mock_app, self.mock_repository, [], [], "project-gid"
        )
        
        # Verify it tried to get PRs but handled the error
        self.mock_app.ado_git_client.get_pull_requests.assert_called_once()

    def test_process_pull_request_retrieval_error(self):
        """Test pull request retrieval error handling."""
        from ado_asana_sync.sync.pull_request_sync import process_repository_pull_requests
        
        # Reset and mock successful repository access but failed PR retrieval
        self.mock_app.ado_git_client.reset_mock()
        self.mock_app.ado_git_client.get_repositories.return_value = [self.mock_repository]
        self.mock_app.ado_git_client.get_pull_requests.side_effect = Exception("API error")
        
        with patch('ado_asana_sync.sync.sync.get_asana_users') as mock_get_users:
            with patch('ado_asana_sync.sync.sync.get_asana_project_tasks') as mock_get_tasks:
                mock_get_users.return_value = []
                mock_get_tasks.return_value = []
                
                # Should handle error gracefully and continue
                process_repository_pull_requests(
                    self.mock_app, self.mock_repository, [], [], "project-gid"
                )
                
                # Verify it tried to get PRs but handled the error
                self.mock_app.ado_git_client.get_pull_requests.assert_called_once()

    @patch('ado_asana_sync.sync.sync.find_custom_field_by_name')
    @patch('asana.TasksApi')
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

    @patch('ado_asana_sync.sync.sync.find_custom_field_by_name')
    @patch('asana.TasksApi')
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

    @patch('ado_asana_sync.sync.pull_request_sync.add_tag_to_pr_task')
    @patch('ado_asana_sync.sync.sync.find_custom_field_by_name')
    @patch('asana.TasksApi')
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

    @patch('ado_asana_sync.sync.pull_request_sync.add_tag_to_pr_task')
    @patch('ado_asana_sync.sync.sync.find_custom_field_by_name')
    @patch('asana.TasksApi')
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


if __name__ == "__main__":
    unittest.main()
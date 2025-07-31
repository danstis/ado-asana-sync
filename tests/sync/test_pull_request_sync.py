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

    @patch('ado_asana_sync.sync.pull_request_sync.get_asana_users')
    @patch('ado_asana_sync.sync.pull_request_sync.get_asana_project_tasks')
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
    @patch('ado_asana_sync.sync.pull_request_sync.matching_user')
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
    @patch('ado_asana_sync.sync.pull_request_sync.matching_user')
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

        with patch('ado_asana_sync.sync.pull_request_sync.matching_user', return_value=None):
            with patch('ado_asana_sync.sync.pull_request_sync.create_new_pr_reviewer_task') as mock_create_task:
                process_pr_reviewer(
                    self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, [], [], "project-456"
                )

                # Verify no task creation
                mock_create_task.assert_not_called()

    @patch('ado_asana_sync.sync.pull_request_sync.get_asana_task_by_name')
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

        with patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task') as mock_update_task:
            update_existing_pr_reviewer_task(
                self.mock_app, self.mock_pr, self.mock_repository, self.mock_reviewer, mock_pr_item, mock_asana_user, "project-456"
            )

            # Verify no update
            mock_update_task.assert_not_called()

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
        mock_reviewer.unique_name = "john.doe@example.com"

        result = create_ado_user_from_reviewer(mock_reviewer)
        self.assertIsNone(result)

    def test_create_ado_user_from_reviewer_exception(self):
        """Test creating ADO user from reviewer with exception."""
        mock_reviewer = Mock()
        mock_reviewer.display_name = Mock(side_effect=Exception("Test error"))

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


if __name__ == "__main__":
    unittest.main()
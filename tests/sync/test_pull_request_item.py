"""Tests for the PullRequestItem class."""

import unittest
from unittest.mock import Mock, patch

from ado_asana_sync.sync.app import App
from ado_asana_sync.sync.pull_request_item import PullRequestItem


class TestPullRequestItem(unittest.TestCase):
    """Test cases for the PullRequestItem class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_app = Mock(spec=App)
        self.mock_app.pr_matches = Mock()
        self.mock_app.db_lock = Mock()

        self.pr_item = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="Update documentation",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/123",
            reviewer_gid="asana-user-789",
            reviewer_name="Dan Anstis",
            asana_gid="asana-task-101",
            asana_updated="2023-12-01T10:00:00Z",
            created_date="2023-12-01T09:00:00Z",
            updated_date="2023-12-01T10:00:00Z",
            review_status="waiting_for_author",
        )

    def test_init(self):
        """Test PullRequestItem initialization."""
        self.assertEqual(self.pr_item.ado_pr_id, 123)
        self.assertEqual(self.pr_item.ado_repository_id, "repo-456")
        self.assertEqual(self.pr_item.title, "Update documentation")
        self.assertEqual(self.pr_item.status, "active")
        self.assertEqual(self.pr_item.reviewer_gid, "asana-user-789")
        self.assertEqual(self.pr_item.reviewer_name, "Dan Anstis")
        self.assertEqual(self.pr_item.asana_gid, "asana-task-101")
        self.assertEqual(self.pr_item.review_status, "waiting_for_author")

    def test_equality(self):
        """Test PullRequestItem equality comparison."""
        other_item = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="Update documentation",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/123",
            reviewer_gid="asana-user-789",
            reviewer_name="Dan Anstis",
            asana_gid="asana-task-101",
            asana_updated="2023-12-01T10:00:00Z",
            created_date="2023-12-01T09:00:00Z",
            updated_date="2023-12-01T10:00:00Z",
            review_status="waiting_for_author",
        )

        different_item = PullRequestItem(
            ado_pr_id=456,
            ado_repository_id="repo-789",
            title="Different title",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/456",
            reviewer_gid="asana-user-999",
            reviewer_name="Different User",
        )

        self.assertEqual(self.pr_item, other_item)
        self.assertNotEqual(self.pr_item, different_item)
        self.assertNotEqual(self.pr_item, "not a pr item")

    def test_str_representation(self):
        """Test string representation."""
        expected = "Pull Request 123: Update documentation (Dan Anstis)"
        self.assertEqual(str(self.pr_item), expected)

    def test_asana_title(self):
        """Test asana_title property."""
        expected = "Pull Request 123: Update documentation (Dan Anstis)"
        self.assertEqual(self.pr_item.asana_title, expected)

    def test_asana_title_without_reviewer_name(self):
        """Test asana_title property when reviewer_name is None."""
        pr_item_no_name = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="Update documentation",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/123",
            reviewer_gid="asana-user-789",
            reviewer_name=None,
        )
        expected = "Pull Request 123: Update documentation"
        self.assertEqual(pr_item_no_name.asana_title, expected)

    def test_asana_notes_link(self):
        """Test asana_notes_link property."""
        expected = '<a href="https://dev.azure.com/test/project/_git/repo/pullrequest/123">Pull Request 123</a>: Update documentation'
        self.assertEqual(self.pr_item.asana_notes_link, expected)

    def test_asana_notes_link_escapes_html(self):
        """Test that asana_notes_link properly escapes HTML in title."""
        pr_item = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="Fix <script>alert('xss')</script> vulnerability",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/123",
            reviewer_gid="asana-user-789",
        )
        
        expected = '<a href="https://dev.azure.com/test/project/_git/repo/pullrequest/123">Pull Request 123</a>: Fix &lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt; vulnerability'
        self.assertEqual(pr_item.asana_notes_link, expected)

    @patch('ado_asana_sync.sync.pull_request_item.Query')
    def test_search_by_pr_id_and_reviewer(self, mock_query):
        """Test searching by PR ID and reviewer GID."""
        # Setup mocks
        mock_query_instance = Mock()
        mock_query.return_value = mock_query_instance
        self.mock_app.pr_matches.contains.return_value = True
        self.mock_app.pr_matches.search.return_value = [
            {
                "ado_pr_id": 123,
                "ado_repository_id": "repo-456",
                "title": "Update documentation",
                "status": "active",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/123",
                "reviewer_gid": "asana-user-789",
                "reviewer_name": "Dan Anstis",
                "asana_gid": "asana-task-101",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            }
        ]

        result = PullRequestItem.search(self.mock_app, ado_pr_id=123, reviewer_gid="asana-user-789")

        self.assertIsInstance(result, PullRequestItem)
        self.assertEqual(result.ado_pr_id, 123)
        self.assertEqual(result.reviewer_gid, "asana-user-789")

    @patch('ado_asana_sync.sync.pull_request_item.Query')
    def test_search_not_found(self, mock_query):
        """Test searching when no match is found."""
        mock_query_instance = Mock()
        mock_query.return_value = mock_query_instance
        self.mock_app.pr_matches.contains.return_value = False

        result = PullRequestItem.search(self.mock_app, ado_pr_id=999)

        self.assertIsNone(result)

    def test_search_no_parameters(self):
        """Test searching with no parameters returns None."""
        result = PullRequestItem.search(self.mock_app)
        self.assertIsNone(result)

    @patch('ado_asana_sync.sync.pull_request_item.Query')
    def test_save_new_item(self, mock_query):
        """Test saving a new PullRequestItem."""
        # Setup mocks
        mock_query_instance = Mock()
        mock_query.return_value = mock_query_instance
        self.mock_app.pr_matches.contains.return_value = False

        self.pr_item.save(self.mock_app)

        # Verify insert was called
        self.mock_app.pr_matches.insert.assert_called_once()
        call_args = self.mock_app.pr_matches.insert.call_args[0][0]
        self.assertEqual(call_args["ado_pr_id"], 123)
        self.assertEqual(call_args["reviewer_gid"], "asana-user-789")
        self.assertEqual(call_args["reviewer_name"], "Dan Anstis")

    @patch('ado_asana_sync.sync.pull_request_item.Query')
    def test_save_existing_item(self, mock_query):
        """Test saving an existing PullRequestItem."""
        # Setup mocks
        mock_query_instance = Mock()
        mock_query.return_value = mock_query_instance
        self.mock_app.pr_matches.contains.return_value = True

        self.pr_item.save(self.mock_app)

        # Verify update was called
        self.mock_app.pr_matches.update.assert_called_once()
        call_args = self.mock_app.pr_matches.update.call_args[0][0]
        self.assertEqual(call_args["ado_pr_id"], 123)
        self.assertEqual(call_args["reviewer_gid"], "asana-user-789")
        self.assertEqual(call_args["reviewer_name"], "Dan Anstis")

    @patch('ado_asana_sync.sync.asana.get_asana_task')
    def test_is_current_true(self, mock_get_asana_task):
        """Test is_current returns True when item is up to date."""
        mock_ado_pr = Mock()
        mock_ado_pr.last_merge_commit = Mock()
        mock_ado_pr.last_merge_commit.date = "2023-12-01T10:00:00Z"

        mock_asana_task = {"modified_at": "2023-12-01T10:00:00Z"}
        mock_get_asana_task.return_value = mock_asana_task

        self.pr_item.updated_date = "2023-12-01T10:00:00Z"
        self.pr_item.asana_updated = "2023-12-01T10:00:00Z"

        result = self.pr_item.is_current(self.mock_app, mock_ado_pr)
        self.assertTrue(result)

    @patch('ado_asana_sync.sync.asana.get_asana_task')
    def test_is_current_false_no_ado_pr(self, mock_get_asana_task):
        """Test is_current returns False when ADO PR is None."""
        result = self.pr_item.is_current(self.mock_app, None)
        self.assertFalse(result)

    @patch('ado_asana_sync.sync.asana.get_asana_task')
    def test_is_current_false_asana_updated(self, mock_get_asana_task):
        """Test is_current returns False when Asana task has been updated."""
        mock_ado_pr = Mock()
        mock_ado_pr.last_merge_commit = Mock()
        mock_ado_pr.last_merge_commit.date = "2023-12-01T10:00:00Z"

        mock_asana_task = {"modified_at": "2023-12-01T11:00:00Z"}  # Different time
        mock_get_asana_task.return_value = mock_asana_task

        self.pr_item.updated_date = "2023-12-01T10:00:00Z"
        self.pr_item.asana_updated = "2023-12-01T10:00:00Z"

        result = self.pr_item.is_current(self.mock_app, mock_ado_pr)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
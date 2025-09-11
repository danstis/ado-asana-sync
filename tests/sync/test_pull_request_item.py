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
        self.mock_app.db_lock.__enter__ = Mock(return_value=self.mock_app.db_lock)
        self.mock_app.db_lock.__exit__ = Mock(return_value=None)
        self.mock_app.asana_workspace_name = "test-workspace"
        self.mock_app.asana_client = Mock()

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
        expected = (
            '<a href="https://dev.azure.com/test/project/_git/repo/pullrequest/123">Pull Request 123</a>: Update documentation'
        )
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

        expected = (
            '<a href="https://dev.azure.com/test/project/_git/repo/pullrequest/123">Pull Request 123</a>: '
            "Fix &lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt; vulnerability"
        )
        self.assertEqual(pr_item.asana_notes_link, expected)

    def test_search_by_pr_id_and_reviewer(self):
        """Test searching by PR ID and reviewer GID."""
        # Setup mocks
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

    def test_search_not_found(self):
        """Test searching when no match is found."""
        self.mock_app.pr_matches.contains.return_value = False

        result = PullRequestItem.search(self.mock_app, ado_pr_id=999)

        self.assertIsNone(result)

    def test_search_no_parameters(self):
        """Test searching with no parameters returns None."""
        result = PullRequestItem.search(self.mock_app)
        self.assertIsNone(result)

    def test_search_by_pr_id_only(self):
        """Test searching by PR ID only."""
        self.mock_app.pr_matches.contains.return_value = True
        self.mock_app.pr_matches.search.return_value = [
            {
                "ado_pr_id": 456,
                "ado_repository_id": "repo-789",
                "title": "Feature addition",
                "status": "active",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/456",
                "reviewer_gid": "asana-user-111",
                "reviewer_name": "Jane Doe",
                "asana_gid": "asana-task-202",
                "asana_updated": "2023-12-02T10:00:00Z",
                "created_date": "2023-12-02T09:00:00Z",
                "updated_date": "2023-12-02T10:00:00Z",
                "review_status": "approved",
            }
        ]

        result = PullRequestItem.search(self.mock_app, ado_pr_id=456)

        self.assertIsInstance(result, PullRequestItem)
        self.assertEqual(result.ado_pr_id, 456)
        self.assertEqual(result.title, "Feature addition")

    def test_search_by_reviewer_gid_only(self):
        """Test searching by reviewer GID only."""
        self.mock_app.pr_matches.contains.return_value = True
        self.mock_app.pr_matches.search.return_value = [
            {
                "ado_pr_id": 789,
                "ado_repository_id": "repo-123",
                "title": "Bug fix",
                "status": "completed",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/789",
                "reviewer_gid": "asana-user-333",
                "reviewer_name": "Bob Smith",
                "asana_gid": "asana-task-303",
                "asana_updated": "2023-12-03T10:00:00Z",
                "created_date": "2023-12-03T09:00:00Z",
                "updated_date": "2023-12-03T10:00:00Z",
                "review_status": "rejected",
            }
        ]

        result = PullRequestItem.search(self.mock_app, reviewer_gid="asana-user-333")

        self.assertIsInstance(result, PullRequestItem)
        self.assertEqual(result.reviewer_gid, "asana-user-333")
        self.assertEqual(result.reviewer_name, "Bob Smith")

    def test_search_by_asana_gid_only(self):
        """Test searching by Asana GID only."""
        self.mock_app.pr_matches.contains.return_value = True
        self.mock_app.pr_matches.search.return_value = [
            {
                "ado_pr_id": 999,
                "ado_repository_id": "repo-555",
                "title": "Documentation update",
                "status": "active",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/999",
                "reviewer_gid": "asana-user-444",
                "reviewer_name": "Alice Johnson",
                "asana_gid": "asana-task-404",
                "asana_updated": "2023-12-04T10:00:00Z",
                "created_date": "2023-12-04T09:00:00Z",
                "updated_date": "2023-12-04T10:00:00Z",
                "review_status": "waiting_for_author",
            }
        ]

        result = PullRequestItem.search(self.mock_app, asana_gid="asana-task-404")

        self.assertIsInstance(result, PullRequestItem)
        self.assertEqual(result.asana_gid, "asana-task-404")
        self.assertEqual(result.title, "Documentation update")

    def test_save_new_item(self):
        """Test saving a new PullRequestItem."""
        # Setup mocks
        self.mock_app.pr_matches.contains.return_value = False

        self.pr_item.save(self.mock_app)

        # Verify insert was called
        self.mock_app.pr_matches.insert.assert_called_once()
        call_args = self.mock_app.pr_matches.insert.call_args[0][0]
        self.assertEqual(call_args["ado_pr_id"], 123)
        self.assertEqual(call_args["reviewer_gid"], "asana-user-789")
        self.assertEqual(call_args["reviewer_name"], "Dan Anstis")

    def test_save_existing_item(self):
        """Test saving an existing PullRequestItem."""
        # Setup mocks
        self.mock_app.pr_matches.contains.return_value = True

        self.pr_item.save(self.mock_app)

        # Verify update was called
        self.mock_app.pr_matches.update.assert_called_once()
        call_args = self.mock_app.pr_matches.update.call_args[0][0]
        self.assertEqual(call_args["ado_pr_id"], 123)
        self.assertEqual(call_args["reviewer_gid"], "asana-user-789")
        self.assertEqual(call_args["reviewer_name"], "Dan Anstis")

    @patch("ado_asana_sync.sync.pull_request_item.get_asana_task")
    def test_is_current_true(self, mock_get_asana_task):
        """Test is_current returns True when item is up to date."""
        mock_ado_pr = Mock()
        mock_ado_pr.title = "Update documentation"  # Match the PR item title
        mock_ado_pr.status = "active"  # Match the PR item status
        mock_ado_pr.last_merge_commit = Mock()
        mock_ado_pr.last_merge_commit.date = "2023-12-01T10:00:00Z"

        mock_asana_task = {"modified_at": "2023-12-01T10:00:00Z"}
        mock_get_asana_task.return_value = mock_asana_task

        self.pr_item.updated_date = "2023-12-01T10:00:00Z"
        self.pr_item.asana_updated = "2023-12-01T10:00:00Z"

        result = self.pr_item.is_current(self.mock_app, mock_ado_pr)
        self.assertTrue(result)

    @patch("ado_asana_sync.sync.pull_request_item.get_asana_task")
    def test_is_current_false_no_ado_pr(self, mock_get_asana_task):
        """Test is_current returns False when ADO PR is None."""
        result = self.pr_item.is_current(self.mock_app, None)
        self.assertFalse(result)

    @patch("ado_asana_sync.sync.pull_request_item.get_asana_task")
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

    @patch("ado_asana_sync.sync.pull_request_item.get_asana_task")
    def test_is_current_false_review_status_changed(self, mock_get_asana_task):
        """Test is_current returns False when reviewer's vote status has changed."""
        mock_ado_pr = Mock()
        mock_ado_pr.title = "Update documentation"  # Match the PR item title
        mock_ado_pr.status = "active"  # Match the PR item status

        mock_reviewer = Mock()
        mock_reviewer.vote = "approved"  # Current reviewer vote is approved

        # Mock Asana task as not updated
        mock_get_asana_task.return_value = {"modified_at": "2023-12-01T10:00:00Z"}

        # Set up PR item with different review status
        self.pr_item.review_status = "noVote"  # Stored status is noVote
        self.pr_item.asana_updated = "2023-12-01T10:00:00Z"

        result = self.pr_item.is_current(self.mock_app, mock_ado_pr, mock_reviewer)
        self.assertFalse(result)  # Should return False because review status changed

    @patch("ado_asana_sync.sync.pull_request_item.get_asana_task")
    def test_is_current_true_with_matching_review_status(self, mock_get_asana_task):
        """Test is_current returns True when reviewer's vote status matches."""
        mock_ado_pr = Mock()
        mock_ado_pr.title = "Update documentation"  # Match the PR item title
        mock_ado_pr.status = "active"  # Match the PR item status

        mock_reviewer = Mock()
        mock_reviewer.vote = "approved"  # Current reviewer vote is approved

        # Mock Asana task as not updated
        mock_get_asana_task.return_value = {"modified_at": "2023-12-01T10:00:00Z"}

        # Set up PR item with matching review status
        self.pr_item.review_status = "approved"  # Stored status matches current
        self.pr_item.asana_updated = "2023-12-01T10:00:00Z"

        result = self.pr_item.is_current(self.mock_app, mock_ado_pr, mock_reviewer)
        self.assertTrue(result)  # Should return True because everything matches

    def test_search_filters_doc_id_from_database_results(self):
        """Regression test: Ensure doc_id is filtered out when creating PullRequestItem from database results."""
        # Setup mocks
        self.mock_app.pr_matches.contains.return_value = True

        # Mock database result that includes doc_id (this would cause constructor error if not filtered)
        mock_db_result = {
            "ado_pr_id": 789,
            "ado_repository_id": "repo-789",
            "title": "Test PR",
            "status": "active",
            "url": "https://example.com/pr/789",
            "reviewer_gid": "reviewer-123",
            "reviewer_name": "Test Reviewer",
            "asana_gid": "asana-789",
            "asana_updated": "2023-12-01T10:00:00Z",
            "created_date": "2023-12-01T09:00:00Z",
            "updated_date": "2023-12-01T10:00:00Z",
            "review_status": "waiting_for_author",
            "doc_id": 888,  # This should be filtered out
        }
        self.mock_app.pr_matches.search.return_value = [mock_db_result]

        # This should not raise an error about unexpected doc_id argument
        result = PullRequestItem.search(self.mock_app, ado_pr_id=789)

        self.assertIsNotNone(result)
        self.assertEqual(result.ado_pr_id, 789)
        self.assertEqual(result.title, "Test PR")
        # Verify doc_id is not present in the created object
        self.assertFalse(hasattr(result, "doc_id"))

    def test_search_with_multiple_criteria_filters_doc_id(self):
        """Regression test: Ensure doc_id filtering works with multiple search criteria."""
        # Setup mocks
        self.mock_app.pr_matches.contains.return_value = True

        # Mock database result with doc_id
        mock_db_result = {
            "ado_pr_id": 999,
            "ado_repository_id": "repo-999",
            "title": "Another Test PR",
            "status": "completed",
            "url": "https://example.com/pr/999",
            "reviewer_gid": "reviewer-456",
            "reviewer_name": "Another Reviewer",
            "asana_gid": "asana-999",
            "doc_id": 111,  # This should be filtered out
        }
        self.mock_app.pr_matches.search.return_value = [mock_db_result]

        # Test search with both PR ID and reviewer GID
        result = PullRequestItem.search(self.mock_app, ado_pr_id=999, reviewer_gid="reviewer-456")

        self.assertIsNotNone(result)
        self.assertEqual(result.ado_pr_id, 999)
        self.assertEqual(result.reviewer_gid, "reviewer-456")
        # Verify doc_id is not present in the created object
        self.assertFalse(hasattr(result, "doc_id"))

    def test_save_with_none_app_pr_matches_raises_error(self):
        """Test save raises ValueError when app.pr_matches is None."""
        mock_app = Mock()
        mock_app.pr_matches = None

        with self.assertRaises(ValueError) as context:
            self.pr_item.save(mock_app)

        self.assertIn("app.pr_matches is None", str(context.exception))

    def test_save_with_none_app_db_lock_raises_error(self):
        """Test save raises ValueError when app.db_lock is None."""
        mock_app = Mock()
        mock_app.pr_matches = Mock()
        mock_app.pr_matches.contains.return_value = False
        mock_app.db_lock = None

        with self.assertRaises(ValueError) as context:
            self.pr_item.save(mock_app)

        self.assertIn("app.db_lock is None", str(context.exception))

    def test_search_returns_none_when_no_items_found(self):
        """Test search returns None when pr_matches.search returns empty list."""
        self.mock_app.pr_matches.contains.return_value = True
        self.mock_app.pr_matches.search.return_value = []

        result = PullRequestItem.search(self.mock_app, ado_pr_id=123)

        self.assertIsNone(result)

    def test_search_returns_none_when_pr_matches_is_none(self):
        """Test search returns None when app.pr_matches is None."""
        mock_app = Mock()
        mock_app.pr_matches = None

        result = PullRequestItem.search(mock_app, ado_pr_id=123)

        self.assertIsNone(result)

    @patch("ado_asana_sync.sync.pull_request_item.get_asana_task")
    def test_is_current_false_title_changed(self, mock_get_asana_task):
        """Test is_current returns False when PR title has changed."""
        mock_ado_pr = Mock()
        mock_ado_pr.title = "Different Title"  # Different from PR item title
        mock_ado_pr.status = "active"

        mock_get_asana_task.return_value = {"modified_at": "2023-12-01T10:00:00Z"}
        self.pr_item.asana_updated = "2023-12-01T10:00:00Z"

        result = self.pr_item.is_current(self.mock_app, mock_ado_pr)

        self.assertFalse(result)

    @patch("ado_asana_sync.sync.pull_request_item.get_asana_task")
    def test_is_current_false_status_changed(self, mock_get_asana_task):
        """Test is_current returns False when PR status has changed."""
        mock_ado_pr = Mock()
        mock_ado_pr.title = "Update documentation"  # Match the PR item title
        mock_ado_pr.status = "completed"  # Different from PR item status

        mock_get_asana_task.return_value = {"modified_at": "2023-12-01T10:00:00Z"}
        self.pr_item.asana_updated = "2023-12-01T10:00:00Z"

        result = self.pr_item.is_current(self.mock_app, mock_ado_pr)

        self.assertFalse(result)

    def test_is_current_false_asana_gid_none(self):
        """Test is_current with asana_gid None."""
        mock_ado_pr = Mock()
        mock_ado_pr.title = "Update documentation"
        mock_ado_pr.status = "active"

        # Create PR item without asana_gid
        pr_item_no_asana = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="Update documentation",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/123",
            reviewer_gid="asana-user-789",
            reviewer_name="Dan Anstis",
            asana_gid=None,
        )

        result = pr_item_no_asana.is_current(self.mock_app, mock_ado_pr)

        self.assertTrue(result)  # Should return True when asana_gid is None

    def test_init_with_minimal_parameters(self):
        """Test PullRequestItem initialization with minimal required parameters."""
        pr_item = PullRequestItem(
            ado_pr_id=999,
            ado_repository_id="repo-999",
            title="Minimal PR",
            status="active",
            url="https://example.com/pr/999",
            reviewer_gid="reviewer-999",
        )

        self.assertEqual(pr_item.ado_pr_id, 999)
        self.assertEqual(pr_item.ado_repository_id, "repo-999")
        self.assertEqual(pr_item.title, "Minimal PR")
        self.assertEqual(pr_item.status, "active")
        self.assertEqual(pr_item.url, "https://example.com/pr/999")
        self.assertEqual(pr_item.reviewer_gid, "reviewer-999")
        self.assertIsNone(pr_item.reviewer_name)
        self.assertIsNone(pr_item.asana_gid)
        self.assertIsNone(pr_item.asana_updated)
        self.assertIsNone(pr_item.created_date)
        self.assertIsNone(pr_item.updated_date)
        self.assertIsNone(pr_item.review_status)

    def test_hash_consistency(self):
        """Test that equal objects have consistent behavior."""
        pr_item1 = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="Test PR",
            status="active",
            url="https://example.com/pr/123",
            reviewer_gid="reviewer-789",
        )

        pr_item2 = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="Test PR",
            status="active",
            url="https://example.com/pr/123",
            reviewer_gid="reviewer-789",
        )

        # Test equality
        self.assertEqual(pr_item1, pr_item2)

        # Test that they have same string representation
        self.assertEqual(str(pr_item1), str(pr_item2))

    def test_search_query_logic_comprehensive(self):
        """Test the search query logic comprehensively."""
        # Setup mocks with different scenarios
        self.mock_app.pr_matches.contains.return_value = True

        # Test case: Search with PR ID and reviewer GID (both match)
        mock_db_result = {
            "ado_pr_id": 123,
            "ado_repository_id": "repo-456",
            "title": "Test PR",
            "status": "active",
            "url": "https://example.com/pr/123",
            "reviewer_gid": "reviewer-789",
            "reviewer_name": "Test Reviewer",
            "asana_gid": "asana-123",
        }
        self.mock_app.pr_matches.search.return_value = [mock_db_result]

        # This should find the item because both PR ID and reviewer GID match
        result = PullRequestItem.search(self.mock_app, ado_pr_id=123, reviewer_gid="reviewer-789")
        self.assertIsNotNone(result)
        self.assertEqual(result.ado_pr_id, 123)
        self.assertEqual(result.reviewer_gid, "reviewer-789")


if __name__ == "__main__":
    unittest.main()

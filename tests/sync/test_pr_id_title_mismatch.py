"""Tests to reproduce and fix PR ID and title mismatch issue.

This test suite addresses issue where PR tasks are created with mismatched
ID and title combinations, e.g., "Pull Request 123: test PR" but with
link to PR 456 instead of PR 123.
"""

import time
import unittest
from threading import Thread
from unittest.mock import Mock, patch

from ado_asana_sync.sync.app import App
from ado_asana_sync.sync.pull_request_item import PullRequestItem
from ado_asana_sync.sync.pull_request_sync import (
    update_existing_pr_reviewer_task,
)


class TestPRIdTitleMismatch(unittest.TestCase):
    """Test cases to reproduce and fix PR ID/title mismatch issues."""

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

        self.mock_repository = Mock()
        self.mock_repository.id = "repo-456"
        self.mock_repository.name = "test-repo"
        self.mock_repository.project = Mock()
        self.mock_repository.project.name = "Test Project"

    def test_pr_item_preserves_original_data_on_creation(self):
        """Test that PullRequestItem preserves original PR data correctly."""
        # Create a PullRequestItem with specific data
        pr_item = PullRequestItem(
            ado_pr_id=100,
            ado_repository_id="repo-123",
            title="test PR",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/100",
            reviewer_gid="reviewer-gid-1",
            reviewer_name="Test Reviewer",
        )

        # Verify the asana_title combines the correct ID and title
        expected_title = "Pull Request 100: test PR (Test Reviewer)"
        self.assertEqual(pr_item.asana_title, expected_title)
        self.assertEqual(pr_item.ado_pr_id, 100)
        self.assertEqual(pr_item.title, "test PR")

    def test_multiple_pr_items_maintain_separate_state(self):
        """Test that multiple PullRequestItem objects maintain separate state."""
        # Create two different PR items that simulate the reported issue
        pr_item_a = PullRequestItem(
            ado_pr_id=100,
            ado_repository_id="repo-123",
            title="test PR",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/100",
            reviewer_gid="reviewer-gid-1",
            reviewer_name="Reviewer A",
        )

        pr_item_b = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="another test pr",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/123",
            reviewer_gid="reviewer-gid-2",
            reviewer_name="Reviewer B",
        )

        # Verify each item maintains its own correct data
        self.assertEqual(pr_item_a.asana_title, "Pull Request 100: test PR (Reviewer A)")
        self.assertEqual(pr_item_b.asana_title, "Pull Request 123: another test pr (Reviewer B)")

        # Verify URLs are correct
        self.assertIn("pullrequest/100", pr_item_a.url)
        self.assertIn("pullrequest/123", pr_item_b.url)

    def test_database_record_corruption_detection(self):
        """Test detection of corrupted database records where ID and title don't match."""
        # Test case 1: URL and PR ID match (this should be valid)
        valid_record = {
            "ado_pr_id": 123,
            "ado_repository_id": "repo-456",
            "title": "test PR",
            "status": "active",
            "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/123",  # URL matches ID
            "reviewer_gid": "reviewer-gid-1",
            "reviewer_name": "Test Reviewer",
        }

        valid_pr_item = PullRequestItem(**valid_record)
        self.assertTrue(valid_pr_item.validate_data_consistency())

        # Test case 2: URL and PR ID don't match (this indicates corruption)
        corrupted_record = {
            "ado_pr_id": 123,  # This ID
            "ado_repository_id": "repo-456",
            "title": "test PR",  # But this title from a different PR
            "status": "active",
            "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/100",  # URL points to different PR!
            "reviewer_gid": "reviewer-gid-1",
            "reviewer_name": "Test Reviewer",
        }

        corrupted_pr_item = PullRequestItem(**corrupted_record)
        self.assertFalse(corrupted_pr_item.validate_data_consistency())

        # This would create the problematic title: "Pull Request 123: test PR"
        # but the URL points to PR 100, indicating data corruption
        problematic_title = corrupted_pr_item.asana_title
        self.assertEqual(problematic_title, "Pull Request 123: test PR (Test Reviewer)")
        self.assertIn("pullrequest/100", corrupted_pr_item.url)  # URL doesn't match ID

    @patch("ado_asana_sync.sync.pull_request_sync.get_asana_task")
    @patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync.iso8601_utc")
    def test_title_update_doesnt_corrupt_other_items(self, mock_iso8601, mock_update_task, mock_get_task):
        """Test that updating one PR's title doesn't affect other PR items."""
        mock_iso8601.return_value = "2023-12-01T10:00:00Z"
        mock_get_task.return_value = {"modified_at": "2023-12-01T09:00:00Z"}

        # Create first PR item
        pr_item_1 = PullRequestItem(
            ado_pr_id=100,
            ado_repository_id="repo-123",
            title="original title",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/100",
            reviewer_gid="reviewer-gid-1",
            reviewer_name="Reviewer 1",
            asana_gid="asana-task-1",
        )

        # Create second PR item
        pr_item_2 = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="different title",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/123",
            reviewer_gid="reviewer-gid-2",
            reviewer_name="Reviewer 2",
            asana_gid="asana-task-2",
        )

        # Mock ADO PR objects with updated titles
        mock_pr_1 = Mock()
        mock_pr_1.pull_request_id = 100
        mock_pr_1.title = "updated title for PR 100"
        mock_pr_1.status = "active"

        mock_pr_2 = Mock()
        mock_pr_2.pull_request_id = 123
        mock_pr_2.title = "updated title for PR 123"
        mock_pr_2.status = "active"

        mock_reviewer = Mock()
        mock_reviewer.vote = "waiting_for_author"
        mock_asana_user = {"gid": "user-123", "name": "Test User"}

        # Update first PR item
        pr_item_1.is_current = Mock(return_value=False)
        update_existing_pr_reviewer_task(
            self.mock_app, mock_pr_1, self.mock_repository, mock_reviewer, pr_item_1, mock_asana_user, "project-456"
        )

        # Update second PR item
        pr_item_2.is_current = Mock(return_value=False)
        update_existing_pr_reviewer_task(
            self.mock_app, mock_pr_2, self.mock_repository, mock_reviewer, pr_item_2, mock_asana_user, "project-456"
        )

        # Verify each item has the correct title and ID combination
        self.assertEqual(pr_item_1.ado_pr_id, 100)
        self.assertEqual(pr_item_1.title, "updated title for PR 100")
        self.assertEqual(pr_item_1.asana_title, "Pull Request 100: updated title for PR 100 (Reviewer 1)")

        self.assertEqual(pr_item_2.ado_pr_id, 123)
        self.assertEqual(pr_item_2.title, "updated title for PR 123")
        self.assertEqual(pr_item_2.asana_title, "Pull Request 123: updated title for PR 123 (Reviewer 2)")

    def test_database_search_returns_correct_pr_item(self):
        """Test that database search returns the correct PR item for a given PR ID and reviewer."""
        # Mock database search results that could be problematic
        mock_search_results = [
            {
                "ado_pr_id": 100,
                "ado_repository_id": "repo-123",
                "title": "test PR",
                "status": "active",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/100",
                "reviewer_gid": "reviewer-gid-1",
                "reviewer_name": "Test Reviewer",
                "asana_gid": "asana-task-100",
            }
        ]

        self.mock_app.pr_matches.contains.return_value = True
        self.mock_app.pr_matches.search.return_value = mock_search_results

        # Search for specific PR and reviewer combination
        result = PullRequestItem.search(self.mock_app, ado_pr_id=100, reviewer_gid="reviewer-gid-1")

        # Verify we get the correct PR item
        self.assertIsNotNone(result)
        self.assertEqual(result.ado_pr_id, 100)
        self.assertEqual(result.title, "test PR")
        self.assertEqual(result.reviewer_gid, "reviewer-gid-1")
        self.assertEqual(result.asana_title, "Pull Request 100: test PR (Test Reviewer)")

    def test_database_search_rejects_corrupted_data(self):
        """Test that database search rejects corrupted records."""
        # Mock database search results that return wrong PR ID
        corrupted_search_results = [
            {
                "ado_pr_id": 999,  # Wrong PR ID!
                "ado_repository_id": "repo-123",
                "title": "test PR",
                "status": "active",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/999",
                "reviewer_gid": "reviewer-gid-1",
                "reviewer_name": "Test Reviewer",
                "asana_gid": "asana-task-999",
            }
        ]

        self.mock_app.pr_matches.contains.return_value = True
        self.mock_app.pr_matches.search.return_value = corrupted_search_results

        # Search for specific PR ID but get back wrong data
        result = PullRequestItem.search(
            self.mock_app,
            ado_pr_id=100,  # Looking for PR 100
            reviewer_gid="reviewer-gid-1",
        )

        # Should return None because the returned data is corrupted
        self.assertIsNone(result)

    def test_cross_project_contamination_prevention(self):
        """Test that PR items from different projects don't contaminate each other."""
        # This is a simpler test that verifies PR items are independent
        # Create two PR items from different projects
        pr_item_a = PullRequestItem(
            ado_pr_id=100,
            ado_repository_id="project-a-repo",
            title="test PR",
            status="active",
            url="https://dev.azure.com/test/projectA/_git/repo/pullrequest/100",
            reviewer_gid="reviewer-gid-1",
            reviewer_name="Reviewer A",
        )

        pr_item_b = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="project-b-repo",
            title="another test pr",
            status="active",
            url="https://dev.azure.com/test/projectB/_git/repo/pullrequest/123",
            reviewer_gid="reviewer-gid-2",
            reviewer_name="Reviewer B",
        )

        # Verify that each item maintains its correct data independently
        self.assertEqual(pr_item_a.ado_pr_id, 100)
        self.assertEqual(pr_item_a.title, "test PR")
        self.assertEqual(pr_item_a.asana_title, "Pull Request 100: test PR (Reviewer A)")

        self.assertEqual(pr_item_b.ado_pr_id, 123)
        self.assertEqual(pr_item_b.title, "another test pr")
        self.assertEqual(pr_item_b.asana_title, "Pull Request 123: another test pr (Reviewer B)")

        # Most importantly, verify there's no cross-contamination
        self.assertNotEqual(pr_item_b.ado_pr_id, 100)  # Should not have Project A's ID
        self.assertNotEqual(pr_item_b.title, "test PR")  # Should not have Project A's title
        self.assertNotEqual(pr_item_a.ado_pr_id, 123)  # Should not have Project B's ID
        self.assertNotEqual(pr_item_a.title, "another test pr")  # Should not have Project B's title

    def test_concurrent_pr_processing_isolation(self):
        """Test that concurrent processing of different PRs maintains data isolation."""
        # This test simulates concurrent access that could lead to data races
        results = {}
        errors = []

        def process_pr_worker(pr_id, title, worker_id):
            """Worker function to simulate concurrent PR processing."""
            try:
                pr_item = PullRequestItem(
                    ado_pr_id=pr_id,
                    ado_repository_id=f"repo-{pr_id}",
                    title=title,
                    status="active",
                    url=f"https://dev.azure.com/test/project/_git/repo/pullrequest/{pr_id}",
                    reviewer_gid=f"reviewer-{worker_id}",
                    reviewer_name=f"Reviewer {worker_id}",
                )

                # Simulate some processing time
                time.sleep(0.01)

                # Store results for verification
                results[worker_id] = {
                    "pr_id": pr_item.ado_pr_id,
                    "title": pr_item.title,
                    "asana_title": pr_item.asana_title,
                    "url": pr_item.url,
                }

            except Exception as e:
                errors.append(f"Worker {worker_id}: {e}")

        # Create threads to simulate concurrent processing
        threads = []
        test_data = [
            (100, "test PR", "worker1"),
            (123, "another test pr", "worker2"),
            (456, "third pr title", "worker3"),
            (789, "fourth pr title", "worker4"),
        ]

        for pr_id, title, worker_id in test_data:
            thread = Thread(target=process_pr_worker, args=(pr_id, title, worker_id))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")

        # Verify each worker got the correct data
        self.assertEqual(len(results), 4)

        # Check each result
        self.assertEqual(results["worker1"]["pr_id"], 100)
        self.assertEqual(results["worker1"]["title"], "test PR")
        self.assertIn("Pull Request 100: test PR", results["worker1"]["asana_title"])

        self.assertEqual(results["worker2"]["pr_id"], 123)
        self.assertEqual(results["worker2"]["title"], "another test pr")
        self.assertIn("Pull Request 123: another test pr", results["worker2"]["asana_title"])

        self.assertEqual(results["worker3"]["pr_id"], 456)
        self.assertEqual(results["worker3"]["title"], "third pr title")
        self.assertIn("Pull Request 456: third pr title", results["worker3"]["asana_title"])

        self.assertEqual(results["worker4"]["pr_id"], 789)
        self.assertEqual(results["worker4"]["title"], "fourth pr title")
        self.assertIn("Pull Request 789: fourth pr title", results["worker4"]["asana_title"])

        # Verify no cross-contamination occurred
        for worker_id, result in results.items():
            for other_worker_id, other_result in results.items():
                if worker_id != other_worker_id:
                    # Ensure this worker's data doesn't match other worker's data incorrectly
                    self.assertNotEqual(
                        result["pr_id"], other_result["pr_id"], f"Workers {worker_id} and {other_worker_id} have same PR ID"
                    )

    def test_corrupted_data_cleanup_on_save(self):
        """Test that corrupted data is cleaned up when saving valid data."""
        # Mock app with corrupted data in the database
        corrupted_records = [
            {
                "ado_pr_id": 123,
                "ado_repository_id": "repo-456",
                "title": "test PR",
                "status": "active",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/100",  # Wrong URL!
                "reviewer_gid": "reviewer-gid-1",
                "reviewer_name": "Test Reviewer",
                "asana_gid": "asana-task-123",
            }
        ]

        self.mock_app.pr_matches.search.return_value = corrupted_records
        self.mock_app.pr_matches.contains.return_value = False  # No existing record for new item
        self.mock_app.pr_matches.remove = Mock()

        # Create a valid PR item to save
        valid_pr_item = PullRequestItem(
            ado_pr_id=123,
            ado_repository_id="repo-456",
            title="test PR",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/123",  # Correct URL
            reviewer_gid="reviewer-gid-2",  # Different reviewer
            reviewer_name="Another Reviewer",
        )

        # Save the valid item (should trigger cleanup)
        valid_pr_item.save(self.mock_app)

        # Verify that the corrupted record was removed
        self.mock_app.pr_matches.remove.assert_called()
        self.mock_app.pr_matches.insert.assert_called_once()

    def test_corrupted_data_cleanup_startup(self):
        """Test the startup cleanup of all corrupted records."""
        # Mock corrupted records in database
        corrupted_records = [
            {
                "ado_pr_id": 123,
                "ado_repository_id": "repo-456",
                "title": "test PR",
                "status": "active",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/100",  # Wrong URL
                "reviewer_gid": "reviewer-gid-1",
                "reviewer_name": "Test Reviewer",
                "asana_gid": "asana-task-123",
            },
            {
                "ado_pr_id": 456,
                "ado_repository_id": "repo-789",
                "title": "valid PR",
                "status": "active",
                "url": "https://dev.azure.com/test/project/_git/repo/pullrequest/456",  # Correct URL
                "reviewer_gid": "reviewer-gid-2",
                "reviewer_name": "Valid Reviewer",
                "asana_gid": "asana-task-456",
            },
        ]

        self.mock_app.pr_matches.all.return_value = corrupted_records
        self.mock_app.pr_matches.remove = Mock()

        # Run startup cleanup
        cleaned_count = PullRequestItem.cleanup_all_corrupted_records(self.mock_app)

        # Should clean up only the corrupted record
        self.assertEqual(cleaned_count, 1)
        self.mock_app.pr_matches.remove.assert_called_once()

    def test_asana_title_property_immutability(self):
        """Test that asana_title property always reflects current object state."""
        pr_item = PullRequestItem(
            ado_pr_id=100,
            ado_repository_id="repo-123",
            title="original title",
            status="active",
            url="https://dev.azure.com/test/project/_git/repo/pullrequest/100",
            reviewer_gid="reviewer-gid-1",
            reviewer_name="Test Reviewer",
        )

        # Initial state
        initial_title = pr_item.asana_title
        self.assertEqual(initial_title, "Pull Request 100: original title (Test Reviewer)")

        # Update the title (simulating what happens in update_existing_pr_reviewer_task)
        pr_item.title = "updated title"

        # Verify asana_title reflects the change
        updated_title = pr_item.asana_title
        self.assertEqual(updated_title, "Pull Request 100: updated title (Test Reviewer)")

        # Verify ID hasn't changed
        self.assertEqual(pr_item.ado_pr_id, 100)

        # The key insight: the asana_title property should ALWAYS use the current
        # values of ado_pr_id and title, not some cached version


if __name__ == "__main__":
    unittest.main()

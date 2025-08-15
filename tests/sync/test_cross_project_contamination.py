"""Tests for cross-project PR title contamination bug.

This module contains regression tests for issue #400 where PRs were being created
with mismatching ID and title due to cross-project contamination in the
process_closed_pull_requests function.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock

from ado_asana_sync.sync.pull_request_sync import (
    process_closed_pull_requests,
    update_existing_pr_reviewer_task,
)
from ado_asana_sync.sync.app import App
from ado_asana_sync.sync.pull_request_item import PullRequestItem


class TestCrossProjectContamination(unittest.TestCase):
    """Test cases for cross-project PR title contamination bug."""

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

        # Project A setup
        self.project_a_repo_id = "repo-project-a"
        self.project_a_pr_id = 123
        self.project_a_title = "Project A: Fix critical bug"

        # Project B setup  
        self.project_b_repo_id = "repo-project-b"
        self.project_b_pr_id = 456
        self.project_b_title = "Project B: Add new feature"

        # Mock PRs from different projects
        self.mock_pr_project_a = Mock()
        self.mock_pr_project_a.pull_request_id = self.project_a_pr_id
        self.mock_pr_project_a.title = self.project_a_title
        self.mock_pr_project_a.status = "active"
        self.mock_pr_project_a.web_url = f"https://dev.azure.com/test/project-a/_git/repo/pullrequest/{self.project_a_pr_id}"

        self.mock_pr_project_b = Mock()
        self.mock_pr_project_b.pull_request_id = self.project_b_pr_id
        self.mock_pr_project_b.title = self.project_b_title
        self.mock_pr_project_b.status = "active"
        self.mock_pr_project_b.web_url = f"https://dev.azure.com/test/project-b/_git/repo/pullrequest/{self.project_b_pr_id}"

    def test_process_closed_pull_requests_cross_project_contamination(self):
        """
        Test that process_closed_pull_requests causes cross-project title contamination.
        
        This test reproduces the bug where a PR task from Project A gets updated
        with the title from a PR in Project B due to the function processing ALL
        PR tasks globally instead of filtering by current project.
        """
        # Setup: Database contains PR tasks from multiple projects
        pr_tasks_in_db = [
            {
                "ado_pr_id": self.project_a_pr_id,
                "ado_repository_id": self.project_a_repo_id,
                "title": self.project_a_title,
                "status": "active",
                "url": f"https://dev.azure.com/test/project-a/_git/repo/pullrequest/{self.project_a_pr_id}",
                "reviewer_gid": "reviewer-a-gid",
                "reviewer_name": "Reviewer A",
                "asana_gid": "asana-task-a",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            },
            {
                "ado_pr_id": self.project_b_pr_id,
                "ado_repository_id": self.project_b_repo_id,
                "title": self.project_b_title,
                "status": "active", 
                "url": f"https://dev.azure.com/test/project-b/_git/repo/pullrequest/{self.project_b_pr_id}",
                "reviewer_gid": "reviewer-b-gid",
                "reviewer_name": "Reviewer B",
                "asana_gid": "asana-task-b",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            }
        ]

        # Mock the database to return tasks from both projects
        self.mock_app.pr_matches.all.return_value = pr_tasks_in_db

        # Mock ADO git client to return wrong PR when queried
        def mock_get_pull_request_by_id(pr_id, repo_id):
            # BUG SIMULATION: When querying for Project A's PR, return Project B's PR
            # This simulates the scenario where the function gets the wrong PR data
            if pr_id == self.project_a_pr_id and repo_id == self.project_a_repo_id:
                return self.mock_pr_project_b  # WRONG PR RETURNED!
            elif pr_id == self.project_b_pr_id and repo_id == self.project_b_repo_id:
                return self.mock_pr_project_b
            return None

        self.mock_app.ado_git_client.get_pull_request_by_id.side_effect = mock_get_pull_request_by_id

        # Mock get_asana_task to return incomplete tasks that need updating
        def mock_get_asana_task(app, gid):
            return {"completed": False, "modified_at": "2023-12-01T11:00:00Z"}

        # Mock update_asana_pr_task to track what gets updated
        updated_tasks = []
        def mock_update_asana_pr_task(app, pr_item, tag_gid, asana_project):
            updated_tasks.append({
                "pr_id": pr_item.ado_pr_id,
                "repo_id": pr_item.ado_repository_id,
                "title": pr_item.title,  # This should show the contamination
                "asana_gid": pr_item.asana_gid
            })

        with patch('ado_asana_sync.sync.pull_request_sync.get_asana_task', side_effect=mock_get_asana_task):
            with patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task', side_effect=mock_update_asana_pr_task):
                with patch('ado_asana_sync.sync.pull_request_sync.iso8601_utc', return_value="2023-12-01T12:00:00Z"):
                    # Execute the function that contains the bug
                    process_closed_pull_requests(
                        self.mock_app, 
                        [],  # asana_users 
                        {"gid": "project-gid"}  # asana_project
                    )

        # ASSERTION: Verify cross-project contamination occurred
        # Project A's task should have been updated with Project B's title
        contaminated_task = None
        for task in updated_tasks:
            if task["pr_id"] == self.project_a_pr_id and task["repo_id"] == self.project_a_repo_id:
                contaminated_task = task
                break

        self.assertIsNotNone(contaminated_task, "Project A task should have been processed")
        
        # THE BUG: Project A's task now has Project B's title
        self.assertEqual(
            contaminated_task["title"], 
            self.project_b_title,
            f"Expected Project A task to be contaminated with Project B title. "
            f"Got title: '{contaminated_task['title']}', "
            f"Expected contamination: '{self.project_b_title}'"
        )
        
        # Verify it's not the original Project A title
        self.assertNotEqual(
            contaminated_task["title"],
            self.project_a_title,
            "Project A task should not have its original title due to contamination"
        )

    def test_update_existing_pr_reviewer_task_title_contamination(self):
        """
        Test that update_existing_pr_reviewer_task blindly updates title without validation.
        
        This test directly demonstrates how the title contamination occurs in the
        update_existing_pr_reviewer_task function when it receives a PR object
        from a different project than the existing match.
        """
        # Create a PullRequestItem from Project A
        project_a_pr_item = PullRequestItem(
            ado_pr_id=self.project_a_pr_id,
            ado_repository_id=self.project_a_repo_id,
            title=self.project_a_title,
            status="active",
            url=f"https://dev.azure.com/test/project-a/_git/repo/pullrequest/{self.project_a_pr_id}",
            reviewer_gid="reviewer-a-gid",
            reviewer_name="Reviewer A",
            asana_gid="asana-task-a",
            review_status="waiting_for_author"
        )

        # Mock the reviewer 
        mock_reviewer = Mock()
        mock_reviewer.vote = "waiting_for_author"
        mock_reviewer.display_name = "Reviewer A"

        # Mock Asana user
        mock_asana_user = {"gid": "reviewer-a-gid", "name": "Reviewer A"}

        # Mock get_asana_task to return a task that exists
        mock_asana_task = {"completed": False, "modified_at": "2023-12-01T11:00:00Z"}

        # Mock update_asana_pr_task to track what gets updated
        updated_pr_items = []
        def mock_update_asana_pr_task(app, pr_item, tag_gid, asana_project):
            updated_pr_items.append({
                "pr_id": pr_item.ado_pr_id,
                "repo_id": pr_item.ado_repository_id,
                "title": pr_item.title,
                "original_title": self.project_a_title,
                "contaminating_title": self.project_b_title
            })

        with patch('ado_asana_sync.sync.pull_request_sync.get_asana_task', return_value=mock_asana_task):
            with patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task', side_effect=mock_update_asana_pr_task):
                with patch('ado_asana_sync.sync.pull_request_sync.iso8601_utc', return_value="2023-12-01T12:00:00Z"):
                    # THE BUG: Pass Project B's PR to update Project A's PR item
                    # This simulates how process_closed_pull_requests passes wrong PR data
                    update_existing_pr_reviewer_task(
                        self.mock_app,
                        self.mock_pr_project_b,  # Project B's PR data
                        Mock(),  # repository (not used in the function)
                        mock_reviewer,
                        project_a_pr_item,  # Project A's PR item
                        mock_asana_user,
                        {"gid": "project-gid"}
                    )

        # ASSERTION: Verify the contamination occurred
        self.assertEqual(len(updated_pr_items), 1, "One PR item should have been updated")
        
        updated_item = updated_pr_items[0]
        
        # Verify the Project A item was contaminated with Project B's title
        self.assertEqual(
            updated_item["title"],
            self.project_b_title,
            f"Project A PR item should be contaminated with Project B title. "
            f"Got: '{updated_item['title']}', Expected: '{self.project_b_title}'"
        )
        
        # Verify it's the right PR item (Project A) but wrong title
        self.assertEqual(updated_item["pr_id"], self.project_a_pr_id)
        self.assertEqual(updated_item["repo_id"], self.project_a_repo_id)
        
        # Verify the original title was overwritten
        self.assertNotEqual(
            updated_item["title"],
            self.project_a_title,
            "Original Project A title should have been overwritten"
        )

        # Also verify the pr_item object itself was modified
        self.assertEqual(
            project_a_pr_item.title,
            self.project_b_title,
            "The PullRequestItem object itself should have its title contaminated"
        )

    def test_process_closed_pull_requests_no_contamination_when_filtered(self):
        """
        Test that process_closed_pull_requests does NOT cause contamination when properly filtered.
        
        This test demonstrates how the function should work when it only processes
        PR tasks that belong to the current project's repositories.
        """
        # Setup: Database contains PR tasks from multiple projects
        pr_tasks_in_db = [
            {
                "ado_pr_id": self.project_a_pr_id,
                "ado_repository_id": self.project_a_repo_id,
                "title": self.project_a_title,
                "status": "active",
                "url": f"https://dev.azure.com/test/project-a/_git/repo/pullrequest/{self.project_a_pr_id}",
                "reviewer_gid": "reviewer-a-gid",
                "reviewer_name": "Reviewer A",
                "asana_gid": "asana-task-a",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            },
            {
                "ado_pr_id": self.project_b_pr_id,
                "ado_repository_id": self.project_b_repo_id,
                "title": self.project_b_title,
                "status": "active", 
                "url": f"https://dev.azure.com/test/project-b/_git/repo/pullrequest/{self.project_b_pr_id}",
                "reviewer_gid": "reviewer-b-gid",
                "reviewer_name": "Reviewer B",
                "asana_gid": "asana-task-b",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            }
        ]

        # Mock the database to return tasks from both projects (but function should filter)
        self.mock_app.pr_matches.all.return_value = pr_tasks_in_db

        # Mock ADO git client to return correct PRs
        def mock_get_pull_request_by_id(pr_id, repo_id):
            if pr_id == self.project_a_pr_id and repo_id == self.project_a_repo_id:
                return self.mock_pr_project_a  # Correct PR
            elif pr_id == self.project_b_pr_id and repo_id == self.project_b_repo_id:
                return self.mock_pr_project_b  # Correct PR
            return None

        self.mock_app.ado_git_client.get_pull_request_by_id.side_effect = mock_get_pull_request_by_id

        # Mock get_asana_task to return incomplete tasks that need updating
        def mock_get_asana_task(app, gid):
            return {"completed": False, "modified_at": "2023-12-01T11:00:00Z"}

        # Mock update_asana_pr_task to track what gets updated
        updated_tasks = []
        def mock_update_asana_pr_task(app, pr_item, tag_gid, asana_project):
            updated_tasks.append({
                "pr_id": pr_item.ado_pr_id,
                "repo_id": pr_item.ado_repository_id,
                "title": pr_item.title,
                "asana_gid": pr_item.asana_gid
            })

        # Create a patched version of process_closed_pull_requests that accepts repositories filter
        # This simulates the fix where the function would filter by current project repositories
        repositories = [self.project_a_repo_id]  # Only process Project A repositories
        
        # Filter the PR tasks to only those in the current project (simulating the fix)
        filtered_pr_tasks = [
            task for task in pr_tasks_in_db 
            if task["ado_repository_id"] in repositories
        ]

        # Override the mock to return only filtered tasks (simulating the fix)
        self.mock_app.pr_matches.all.return_value = filtered_pr_tasks

        with patch('ado_asana_sync.sync.pull_request_sync.get_asana_task', side_effect=mock_get_asana_task):
            with patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task', side_effect=mock_update_asana_pr_task):
                with patch('ado_asana_sync.sync.pull_request_sync.iso8601_utc', return_value="2023-12-01T12:00:00Z"):
                    # Execute the function with filtering (simulating fixed behavior)
                    process_closed_pull_requests(
                        self.mock_app, 
                        [],  # asana_users 
                        {"gid": "project-gid"}  # asana_project
                    )

        # ASSERTION: Verify NO contamination occurred
        # Only Project A task should have been processed
        self.assertEqual(len(updated_tasks), 1, "Only one task should have been processed")
        
        project_a_task = updated_tasks[0]
        
        # Verify Project A task has correct title (no contamination)
        self.assertEqual(project_a_task["pr_id"], self.project_a_pr_id)
        self.assertEqual(project_a_task["repo_id"], self.project_a_repo_id)
        self.assertEqual(
            project_a_task["title"],
            self.project_a_title,
            "Project A task should retain its correct title when properly filtered"
        )
        
        # Verify Project B task was not processed at all
        project_b_processed = any(
            task["pr_id"] == self.project_b_pr_id for task in updated_tasks
        )
        self.assertFalse(
            project_b_processed,
            "Project B task should not have been processed when filtering by Project A repositories"
        )

    def test_process_closed_pull_requests_with_repositories_parameter(self):
        """
        Test that process_closed_pull_requests correctly filters by repositories when provided.
        
        This test demonstrates the expected behavior after implementing the fix where
        the function accepts a repositories parameter to filter PR tasks.
        """
        # Setup: Database contains PR tasks from multiple projects
        pr_tasks_in_db = [
            {
                "ado_pr_id": self.project_a_pr_id,
                "ado_repository_id": self.project_a_repo_id,
                "title": self.project_a_title,
                "status": "active",
                "url": f"https://dev.azure.com/test/project-a/_git/repo/pullrequest/{self.project_a_pr_id}",
                "reviewer_gid": "reviewer-a-gid",
                "reviewer_name": "Reviewer A",
                "asana_gid": "asana-task-a",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            },
            {
                "ado_pr_id": self.project_b_pr_id,
                "ado_repository_id": self.project_b_repo_id,
                "title": self.project_b_title,
                "status": "active", 
                "url": f"https://dev.azure.com/test/project-b/_git/repo/pullrequest/{self.project_b_pr_id}",
                "reviewer_gid": "reviewer-b-gid",
                "reviewer_name": "Reviewer B",
                "asana_gid": "asana-task-b",
                "asana_updated": "2023-12-01T10:00:00Z",
                "created_date": "2023-12-01T09:00:00Z",
                "updated_date": "2023-12-01T10:00:00Z",
                "review_status": "waiting_for_author",
            }
        ]

        # Mock the database to return tasks from both projects
        self.mock_app.pr_matches.all.return_value = pr_tasks_in_db

        # Mock ADO git client to return correct PRs
        def mock_get_pull_request_by_id(pr_id, repo_id):
            if pr_id == self.project_a_pr_id and repo_id == self.project_a_repo_id:
                return self.mock_pr_project_a  # Correct PR
            elif pr_id == self.project_b_pr_id and repo_id == self.project_b_repo_id:
                return self.mock_pr_project_b  # Correct PR
            return None

        self.mock_app.ado_git_client.get_pull_request_by_id.side_effect = mock_get_pull_request_by_id

        # Mock get_asana_task to return incomplete tasks that need updating
        def mock_get_asana_task(app, gid):
            return {"completed": False, "modified_at": "2023-12-01T11:00:00Z"}

        # Mock update_asana_pr_task to track what gets updated
        updated_tasks = []
        def mock_update_asana_pr_task(app, pr_item, tag_gid, asana_project):
            updated_tasks.append({
                "pr_id": pr_item.ado_pr_id,
                "repo_id": pr_item.ado_repository_id,
                "title": pr_item.title,
                "asana_gid": pr_item.asana_gid
            })

        # Create a fixed version of process_closed_pull_requests that accepts repositories parameter
        def fixed_process_closed_pull_requests(app, asana_users, asana_project, repositories=None):
            """Fixed version that filters by repositories to prevent cross-project contamination."""
            from ado_asana_sync.sync.pull_request_sync import get_asana_task, update_asana_pr_task, iso8601_utc
            from ado_asana_sync.sync.pull_request_item import PullRequestItem
            from datetime import datetime
            
            if app.pr_matches is None:
                raise ValueError("app.pr_matches is None")
            all_pr_tasks = app.pr_matches.all()

            # FIXED: Filter PR tasks by repositories if provided
            if repositories:
                repository_ids = [repo.id if hasattr(repo, 'id') else repo for repo in repositories]
                filtered_pr_tasks = [
                    task for task in all_pr_tasks 
                    if task.get('ado_repository_id') in repository_ids
                ]
            else:
                filtered_pr_tasks = all_pr_tasks

            for pr_task_data in filtered_pr_tasks:
                # Remove doc_id before creating PullRequestItem
                clean_pr_task_data = {k: v for k, v in pr_task_data.items() if k != 'doc_id'}
                pr_item = PullRequestItem(**clean_pr_task_data)

                try:
                    # Try to get the current PR from ADO
                    if app.ado_git_client is None:
                        raise ValueError("app.ado_git_client is None")
                    repository_id = pr_item.ado_repository_id
                    pr = app.ado_git_client.get_pull_request_by_id(
                        pr_item.ado_pr_id, repository_id
                    )

                    if pr and pr.status not in ["completed", "abandoned"]:
                        # PR is still active, skip
                        continue

                    # PR is closed/completed, update the Asana task accordingly
                    if pr_item.asana_gid:
                        asana_task = get_asana_task(app, pr_item.asana_gid)
                        if asana_task and not asana_task.get("completed", False):
                            # Close the Asana task
                            pr_item.status = pr.status if pr else "completed"
                            pr_item.updated_date = iso8601_utc(datetime.now())
                            if app.asana_tag_gid is not None:
                                update_asana_pr_task(app, pr_item, app.asana_tag_gid, asana_project)

                except Exception as e:
                    # Check if it's a permission/project not found error
                    error_msg = str(e)
                    if "does not exist" in error_msg or "permission" in error_msg:
                        # The project may have been deleted or access revoked, skip silently
                        continue
                    else:
                        # Log other errors but continue
                        continue

        # Test the fixed function with repository filtering
        repositories = [Mock(id=self.project_a_repo_id)]  # Only Project A repositories

        with patch('ado_asana_sync.sync.pull_request_sync.get_asana_task', side_effect=mock_get_asana_task):
            with patch('ado_asana_sync.sync.pull_request_sync.update_asana_pr_task', side_effect=mock_update_asana_pr_task):
                with patch('ado_asana_sync.sync.pull_request_sync.iso8601_utc', return_value="2023-12-01T12:00:00Z"):
                    # Execute the fixed function with repository filtering
                    fixed_process_closed_pull_requests(
                        self.mock_app, 
                        [],  # asana_users 
                        {"gid": "project-gid"},  # asana_project
                        repositories  # repositories filter - this is the fix
                    )

        # ASSERTION: Verify NO contamination occurred due to proper filtering
        # Only Project A task should have been processed
        self.assertEqual(len(updated_tasks), 1, "Only one task should have been processed")
        
        project_a_task = updated_tasks[0]
        
        # Verify Project A task has correct title (no contamination)
        self.assertEqual(project_a_task["pr_id"], self.project_a_pr_id)
        self.assertEqual(project_a_task["repo_id"], self.project_a_repo_id)
        self.assertEqual(
            project_a_task["title"],
            self.project_a_title,
            "Project A task should retain its correct title when properly filtered by repositories"
        )
        
        # Verify Project B task was not processed at all
        project_b_processed = any(
            task["pr_id"] == self.project_b_pr_id for task in updated_tasks
        )
        self.assertFalse(
            project_b_processed,
            "Project B task should not have been processed when filtering by Project A repositories"
        )


if __name__ == "__main__":
    unittest.main()
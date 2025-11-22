"""
Test utilities to reduce repetitive mocking patterns.

This module provides shared fixtures and utilities for testing,
specifically focused on reducing excessive external API mocking repetition
while maintaining proper isolation of external dependencies.
"""

from typing import Any, Dict, List
from unittest.mock import MagicMock


class AsanaApiMockHelper:
    """Helper class to create consistent Asana API mocks across tests."""

    def __init__(self):
        """Initialize the helper with default mock responses."""
        self.default_workspace = {"name": "test_workspace", "gid": "workspace-123"}
        self.default_project = {"name": "AsanaProject", "gid": "project-456"}
        self.default_user = {"name": "Test User", "email": "test@example.com", "gid": "user-789"}
        self.default_tag = {"name": "TestTag", "gid": "tag-abc"}

    def create_workspace_api_mock(self, workspaces: List[Dict[str, Any]] = None):
        """Create a mock WorkspacesApi with default or custom workspaces."""
        if workspaces is None:
            workspaces = [self.default_workspace]

        mock_api = MagicMock()
        mock_api.get_workspaces.return_value = workspaces
        return mock_api

    def create_projects_api_mock(self, projects: List[Dict[str, Any]] = None):
        """Create a mock ProjectsApi with default or custom projects."""
        if projects is None:
            projects = [self.default_project]

        mock_api = MagicMock()
        mock_api.get_projects.return_value = projects
        return mock_api

    def create_users_api_mock(self, users: List[Dict[str, Any]] = None):
        """Create a mock UsersApi with default or custom users."""
        if users is None:
            users = [self.default_user]

        mock_api = MagicMock()
        mock_api.get_users.return_value = users
        return mock_api

    def create_tags_api_mock(self, tags: List[Dict[str, Any]] = None, created_tag: Dict[str, Any] = None):
        """Create a mock TagsApi with default or custom tags and creation response."""
        if tags is None:
            tags = [self.default_tag]
        if created_tag is None:
            created_tag = self.default_tag

        mock_api = MagicMock()
        mock_api.get_tags.return_value = tags
        mock_api.create_tag_for_workspace.return_value = created_tag
        mock_api.get_tags_for_task.return_value = tags
        return mock_api

    def create_tasks_api_mock(
        self, tasks: List[Dict[str, Any]] = None, created_task: Dict[str, Any] = None, updated_task: Dict[str, Any] = None
    ):
        """Create a mock TasksApi with default or custom responses."""
        default_task = {"gid": "task-123", "name": "Test Task", "completed": False, "modified_at": "2025-01-01T00:00:00.000Z"}

        if tasks is None:
            tasks = [default_task]
        if created_task is None:
            created_task = default_task
        if updated_task is None:
            updated_task = default_task

        mock_api = MagicMock()
        mock_api.get_tasks.return_value = tasks
        mock_api.create_task.return_value = created_task
        mock_api.update_task.return_value = updated_task
        return mock_api

    def create_custom_field_settings_api_mock(self, custom_fields: List[Dict[str, Any]] = None):
        """Create a mock CustomFieldSettingsApi with default or custom responses."""
        if custom_fields is None:
            custom_fields = []

        mock_api = MagicMock()
        mock_api.get_custom_field_settings_for_project.return_value = custom_fields
        return mock_api


class TestDataBuilder:
    """Builder class for creating consistent test data structures."""

    @staticmethod
    def create_ado_work_item(
        item_id: int = 12345,
        title: str = "Test Work Item",
        work_item_type: str = "Task",
        due_date: str = None,
        assigned_to: Dict[str, str] = None,
    ):
        """Create a mock ADO WorkItem with consistent structure."""
        from azure.devops.v7_0.work_item_tracking.models import WorkItem

        if assigned_to is None:
            assigned_to = {"displayName": "Test User", "uniqueName": "test@example.com"}

        work_item = WorkItem()
        work_item.id = item_id
        work_item.rev = 1
        work_item.fields = {
            "System.Title": title,
            "System.WorkItemType": work_item_type,
            "System.State": "New",
            "System.AssignedTo": assigned_to,
        }

        if due_date:
            work_item.fields["Microsoft.VSTS.Scheduling.DueDate"] = due_date

        work_item.url = f"https://dev.azure.com/test-org/test-project/_workitems/edit/{item_id}"
        work_item._links = {
            "additional_properties": {
                "html": {"href": f"https://dev.azure.com/test-org/test-project/_workitems/edit/{item_id}"}
            }
        }

        return work_item

    @staticmethod
    def create_asana_task_data(
        gid: str = "task-123",
        name: str = "Test Task",
        completed: bool = False,
        modified_at: str = "2025-01-01T10:00:00.000Z",
        due_on: str = None,
    ):
        """Create mock Asana task data with consistent structure."""
        task_data = {
            "gid": gid,
            "name": name,
            "completed": completed,
            "modified_at": modified_at,
        }
        
        if due_on:
            task_data["due_on"] = due_on
            
        return task_data

    @staticmethod
    def create_real_app(temp_dir: str, projects_data: List[Dict] = None):
        """Create a REAL App instance with real database in temp directory."""
        import json
        import os

        from ado_asana_sync.sync.app import App

        if projects_data is None:
            projects_data = [
                {"adoProjectName": "TestProject", "adoTeamName": "TestTeam", "asanaProjectName": "TestAsanaProject"}
            ]

        # Create real data directory and projects file
        data_dir = os.path.join(temp_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        projects_path = os.path.join(data_dir, "projects.json")

        with open(projects_path, "w", encoding="utf-8") as f:
            json.dump(projects_data, f)

        # Create REAL App instance
        app = App(
            ado_pat="test_pat",
            ado_url="https://dev.azure.com/test",
            asana_token="test_token",
            asana_workspace_name="test_workspace",
        )

        return app

    @staticmethod
    def create_app_mock(has_database: bool = True):
        """Create a consistent App mock with standard configuration.

        DEPRECATED: Use create_real_app() instead for better integration testing.
        """
        from ado_asana_sync.sync.app import App

        app = MagicMock(spec=App)
        app.asana_tag_gid = "tag-123"
        app.asana_workspace_name = "test-workspace"
        app.asana_page_size = 100

        # Set up database mocks
        if has_database:
            app.db = MagicMock()
        else:
            app.db = None

        app.matches = MagicMock()
        app.matches.contains = MagicMock(return_value=False)
        app.matches.insert = MagicMock()
        app.matches.update = MagicMock()
        app.matches.search = MagicMock(return_value=[])

        # Set up lock context manager
        app.db_lock = MagicMock()
        app.db_lock.__enter__ = MagicMock(return_value=app.db_lock)
        app.db_lock.__exit__ = MagicMock(return_value=None)

        return app


class RealObjectBuilder:
    """Builder for creating real objects for true integration testing."""

    @staticmethod
    def create_real_ado_reviewer(
        display_name: str = "John Doe", email: str = "john.doe@example.com", vote: str = "waiting_for_author"
    ):
        """Create a real-ish ADO reviewer object (not a mock)."""

        # Create a simple object that behaves like ADO reviewer
        class ADOReviewer:
            def __init__(self, display_name, email, vote):
                self.display_name = display_name
                self.unique_name = email
                self.vote = vote

        return ADOReviewer(display_name, email, vote)

    @staticmethod
    def create_real_ado_repository(repo_id: str = "repo-123", name: str = "test-repo", project_id: str = "project-456"):
        """Create a real-ish ADO repository object."""

        class ADORepository:
            def __init__(self, repo_id, name, project_id):
                self.id = repo_id
                self.name = name
                # Create nested project object
                self.project = type("Project", (), {"id": project_id, "name": f"Project-{project_id}"})()

        return ADORepository(repo_id, name, project_id)

    @staticmethod
    def create_real_ado_pull_request(pr_id: int = 123, title: str = "Test PR", status: str = "active"):
        """Create a real-ish ADO pull request object."""

        class ADOPullRequest:
            def __init__(self, pr_id, title, status):
                self.pull_request_id = pr_id
                self.title = title
                self.status = status
                self.web_url = f"https://dev.azure.com/test/project/_git/repo/pullrequest/{pr_id}"

        return ADOPullRequest(pr_id, title, status)


def create_minimal_external_api_patches():
    """
    Create minimal patches for external APIs that should always be mocked.

    Returns a list of patch objects that can be used in test contexts.
    Use this for tests that only need to isolate external API calls
    without excessive internal mocking.
    """
    from unittest.mock import patch

    return [
        patch("asana.WorkspacesApi"),
        patch("asana.ProjectsApi"),
        patch("asana.UsersApi"),
        patch("asana.TagsApi"),
        patch("asana.TasksApi"),
        patch("asana.StoriesApi"),
    ]

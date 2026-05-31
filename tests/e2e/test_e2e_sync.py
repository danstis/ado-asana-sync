"""
Comprehensive end-to-end tests for the ADO-Asana sync workflow.

Tests validate the complete synchronization workflow using isolated temporary
databases and mocked API endpoints. Non-destructive: only temporary directories
are used and cleaned up after each test.

Sync scenarios covered:
    Work Items:
    - New ADO item → Asana task created
    - ADO item updated → Asana task updated
    - ADO item closed → Asana task completed
    - ADO item reopened → Asana task uncompleted
    - ADO subtask hierarchy → parent-child relationships maintained
    - Preexisting Asana task → matched without creating duplicate

    Pull Requests:
    - PR opened → reviewer task created
    - PR closed → reviewer task completed
    - PR reopened → reviewer task uncompleted
    - PR reviewer status changed → Asana task updated
"""

import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.sync import sync_project
from tests.utils.test_helpers import AsanaApiMockHelper, RealObjectBuilder, TestDataBuilder

_RECENT_DATE = "2026-05-30T10:00:00.000Z"
_OLD_ASANA_DATE = "2025-01-01T10:00:00.000Z"
_TEST_USER_ASSIGNED = {"displayName": "Test User", "uniqueName": "test@example.com"}
_ADO_BASE_URL = "https://dev.azure.com/test/project/_workitems/edit"
_GIT_BASE_URL = "https://dev.azure.com/test/project/_git/repo/pullrequest"


def _make_backlog_item(item_id: int) -> MagicMock:
    """Create a mock ADO backlog item stub with a target ID."""
    item = MagicMock()
    item.target.id = item_id
    return item


def _make_pr_db_record(pr_id: int, status: str = "active", processing_state: str = "open") -> dict:
    """Create a PR database record suitable for pre-seeding app.pr_matches."""
    return {
        "ado_pr_id": pr_id,
        "ado_repository_id": "repo-abc",
        "title": f"Feature PR {pr_id}",
        "status": status,
        "url": f"{_GIT_BASE_URL}/{pr_id}",
        "reviewer_gid": "user-789",
        "reviewer_name": "Test User",
        "asana_gid": f"pr_task_gid_{pr_id}",
        "asana_updated": _OLD_ASANA_DATE,
        "created_date": _OLD_ASANA_DATE,
        "updated_date": _OLD_ASANA_DATE,
        "review_status": "noVote",
        "processing_state": processing_state,
        "assignee_gid": None,
    }


def _make_work_item_db_record(
    ado_id: int,
    title: str,
    state: str = "Active",
    asana_gid: str = None,
    ado_rev: int = 1,
) -> dict:
    """Create a work item database record suitable for pre-seeding app.matches."""
    return {
        "ado_id": ado_id,
        "ado_rev": ado_rev,
        "title": title,
        "item_type": "Task",
        "state": state,
        "url": f"{_ADO_BASE_URL}/{ado_id}",
        "asana_gid": asana_gid or f"task_gid_{ado_id}",
        "asana_updated": _OLD_ASANA_DATE,
        "assigned_to": "user-789",
        "created_date": _OLD_ASANA_DATE,
        "updated_date": _RECENT_DATE,
        "due_date": None,
    }


class _E2EBase(unittest.TestCase):
    """Base class with shared setup helpers for E2E tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.asana_helper = AsanaApiMockHelper()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _connect_app(self, app, mock_dirname, mock_ado_conn, mock_asana_client):
        mock_dirname.return_value = self.temp_dir
        mock_ado_conn.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()
        app.connect()
        app.asana_tag_gid = "tag-abc"

    def _asana_patches(self, tasks_api):
        memberships_mock = MagicMock()
        memberships_mock.get_workspace_memberships_for_workspace.return_value = []
        return [
            patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=tasks_api),
            patch("ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=self.asana_helper.create_workspace_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=self.asana_helper.create_projects_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=self.asana_helper.create_tags_api_mock()),
            patch("ado_asana_sync.sync.sync.asana.UsersApi", return_value=self.asana_helper.create_users_api_mock()),
            patch(
                "ado_asana_sync.sync.sync.asana.CustomFieldSettingsApi",
                return_value=self.asana_helper.create_custom_field_settings_api_mock(),
            ),
            patch("ado_asana_sync.sync.sync.asana.WorkspaceMembershipsApi", return_value=memberships_mock),
            patch("ado_asana_sync.sync.sync.asana.StoriesApi", return_value=MagicMock()),
        ]


class TestE2ESyncWorkItems(_E2EBase):
    """E2E tests for ADO-Asana work item synchronization scenarios."""

    def setUp(self):
        super().setUp()
        self.project_config = {
            "adoProjectName": "TestProject",
            "adoTeamName": "TestTeam",
            "asanaProjectName": "AsanaProject",
        }

    def _setup_ado_clients(self, app):
        mock_core = MagicMock()
        mock_core.get_project.return_value.id = "ado_project_id"
        mock_core.get_team.return_value.id = "ado_team_id"
        app.ado_core_client = mock_core

        mock_work = MagicMock()
        app.ado_work_client = mock_work

        mock_wit = MagicMock()
        app.ado_wit_client = mock_wit

        mock_git = MagicMock()
        mock_git.get_repositories.return_value = []
        app.ado_git_client = mock_git

        return mock_core, mock_work, mock_wit, mock_git

    def _set_backlog(self, mock_work, item_ids):
        if not item_ids:
            mock_work.get_backlog_level_work_items.return_value.work_items = None
        else:
            mock_work.get_backlog_level_work_items.return_value.work_items = [_make_backlog_item(i) for i in item_ids]

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_new_work_item_creates_asana_task(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: A new ADO work item is synced and a new Asana task is created."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        _, mock_work, mock_wit, _ = self._setup_ado_clients(app)

        ado_item = TestDataBuilder.create_ado_work_item(item_id=1001, title="New Feature", assigned_to=_TEST_USER_ASSIGNED)
        mock_wit.get_work_item.return_value = ado_item
        self._set_backlog(mock_work, [1001])

        created_task = TestDataBuilder.create_asana_task_data(gid="new_task_gid", name="Task 1001: New Feature")
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[], created_task=created_task)

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                sync_project(app, self.project_config)

            tasks_api.create_task.assert_called_once()
            body = tasks_api.create_task.call_args[0][0]
            self.assertEqual(body["data"]["name"], "Task 1001: New Feature")
            self.assertFalse(body["data"]["completed"])

            saved = app.matches.all()
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["ado_id"], 1001)
            self.assertEqual(saved[0]["asana_gid"], "new_task_gid")
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_work_item_update_syncs_title_change(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: An updated ADO work item title is reflected in the Asana task."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        _, mock_work, mock_wit, _ = self._setup_ado_clients(app)

        app.matches.insert(_make_work_item_db_record(1002, "Old Title", asana_gid="existing_gid"))

        updated_ado_item = TestDataBuilder.create_ado_work_item(
            item_id=1002, title="Updated Title", assigned_to=_TEST_USER_ASSIGNED
        )
        updated_ado_item.rev = 2
        mock_wit.get_work_item.return_value = updated_ado_item
        self._set_backlog(mock_work, [1002])

        existing_asana = TestDataBuilder.create_asana_task_data(gid="existing_gid", modified_at=_OLD_ASANA_DATE)
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[existing_asana], updated_task=existing_asana)
        tasks_api.get_task.return_value = existing_asana

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                sync_project(app, self.project_config)

            tasks_api.update_task.assert_called()
            update_body = tasks_api.update_task.call_args[0][0]
            self.assertEqual(update_body["data"]["name"], "Task 1002: Updated Title")

            saved = app.matches.search(lambda x: x["ado_id"] == 1002)
            self.assertEqual(saved[0]["title"], "Updated Title")
            self.assertEqual(saved[0]["ado_rev"], 2)
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_work_item_close_completes_asana_task(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: A work item removed from the ADO backlog (closed) marks the Asana task completed."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        _, mock_work, mock_wit, _ = self._setup_ado_clients(app)

        app.matches.insert(_make_work_item_db_record(1003, "Close Me", asana_gid="close_gid"))

        closed_item = TestDataBuilder.create_ado_work_item(item_id=1003, title="Close Me", assigned_to=_TEST_USER_ASSIGNED)
        closed_item.rev = 2
        closed_item.fields["System.State"] = "Closed"
        mock_wit.get_work_item.return_value = closed_item
        self._set_backlog(mock_work, [])

        asana_task = TestDataBuilder.create_asana_task_data(gid="close_gid", modified_at=_OLD_ASANA_DATE, completed=False)
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[], updated_task=asana_task)
        tasks_api.get_task.return_value = asana_task

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                sync_project(app, self.project_config)

            tasks_api.update_task.assert_called()
            update_body = tasks_api.update_task.call_args[0][0]
            self.assertTrue(update_body["data"]["completed"])
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_work_item_reopen_uncompletes_asana_task(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: Reopening a previously closed ADO work item marks the Asana task as incomplete."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        _, mock_work, mock_wit, _ = self._setup_ado_clients(app)

        app.matches.insert(_make_work_item_db_record(1004, "Reopened Task", state="Closed", asana_gid="reopen_gid"))

        reopened_item = TestDataBuilder.create_ado_work_item(
            item_id=1004, title="Reopened Task", assigned_to=_TEST_USER_ASSIGNED
        )
        reopened_item.rev = 2
        reopened_item.fields["System.State"] = "Active"
        mock_wit.get_work_item.return_value = reopened_item
        self._set_backlog(mock_work, [1004])

        asana_task = TestDataBuilder.create_asana_task_data(gid="reopen_gid", modified_at=_OLD_ASANA_DATE, completed=True)
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[asana_task], updated_task=asana_task)
        tasks_api.get_task.return_value = asana_task

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                sync_project(app, self.project_config)

            tasks_api.update_task.assert_called()
            update_body = tasks_api.update_task.call_args[0][0]
            self.assertFalse(update_body["data"]["completed"])
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_subtask_hierarchy_parent_child_linked(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: ADO parent-child work item relationships are maintained as Asana subtasks."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        _, mock_work, mock_wit, _ = self._setup_ado_clients(app)

        child_relation = MagicMock()
        child_relation.rel = "System.LinkTypes.Hierarchy-Forward"
        child_relation.url = "https://dev.azure.com/test/project/_apis/wit/workItems/2002"

        parent_item = TestDataBuilder.create_ado_work_item(item_id=2001, title="Parent Task", assigned_to=_TEST_USER_ASSIGNED)
        parent_item.relations = [child_relation]

        child_item = TestDataBuilder.create_ado_work_item(item_id=2002, title="Child Task", assigned_to=_TEST_USER_ASSIGNED)
        child_item.relations = None

        def _get_work_item(item_id, expand=None):
            return parent_item if item_id == 2001 else child_item

        mock_wit.get_work_item.side_effect = _get_work_item
        self._set_backlog(mock_work, [2001])

        parent_created = TestDataBuilder.create_asana_task_data(gid="parent_gid", name="Task 2001: Parent Task")
        child_created = TestDataBuilder.create_asana_task_data(gid="child_gid", name="Task 2002: Child Task")

        def _create_task_side_effect(body, opts=None):
            name = body["data"].get("name", "")
            return parent_created if "2001" in name else child_created

        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[])
        tasks_api.create_task.side_effect = _create_task_side_effect

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                sync_project(app, self.project_config)

            self.assertEqual(tasks_api.create_task.call_count, 2)

            child_call = next(c for c in tasks_api.create_task.call_args_list if "Task 2002" in c[0][0]["data"]["name"])
            self.assertIn("parent", child_call[0][0]["data"])
            self.assertEqual(child_call[0][0]["data"]["parent"], "parent_gid")

            saved_ids = {r["ado_id"] for r in app.matches.all()}
            self.assertIn(2001, saved_ids)
            self.assertIn(2002, saved_ids)
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_preexisting_asana_task_matched_without_duplicate(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: A new ADO item is linked to an existing Asana task by name without creating a duplicate."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        _, mock_work, mock_wit, _ = self._setup_ado_clients(app)

        ado_item = TestDataBuilder.create_ado_work_item(
            item_id=3001, title="Existing Feature", assigned_to=_TEST_USER_ASSIGNED
        )
        mock_wit.get_work_item.return_value = ado_item
        self._set_backlog(mock_work, [3001])

        preexisting = TestDataBuilder.create_asana_task_data(
            gid="preexisting_gid",
            name="Task 3001: Existing Feature",
            modified_at="2025-06-01T10:00:00.000Z",
        )
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[preexisting], updated_task=preexisting)
        tasks_api.get_task.return_value = preexisting

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                sync_project(app, self.project_config)

            tasks_api.create_task.assert_not_called()
            tasks_api.update_task.assert_called()

            saved = app.matches.search(lambda x: x["ado_id"] == 3001)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["asana_gid"], "preexisting_gid")
        finally:
            app.close()


class TestE2ESyncPullRequests(_E2EBase):
    """E2E tests for ADO-Asana pull request synchronization scenarios."""

    def setUp(self):
        super().setUp()
        self.asana_workspace_id = "workspace-123"
        self.asana_project = "project-456"
        self.ado_project = MagicMock(id="proj-id", name="TestProject")

    def _connect_app_for_pr(self, app, mock_dirname, mock_ado_conn, mock_asana_client):
        self._connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        app.pr_sync_cache = {"custom_fields": {}, "asana_tasks": {}}

    def _setup_git_client(self, app, repos=None, active_prs=None, reviewers=None, pr_by_id=None):
        mock_git = MagicMock()
        mock_git.get_repositories.return_value = repos or []
        mock_git.get_pull_requests.return_value = active_prs or []
        mock_git.get_pull_request_reviewers.return_value = reviewers or []
        if pr_by_id is not None:
            mock_git.get_pull_request_by_id.return_value = pr_by_id
        app.ado_git_client = mock_git
        return mock_git

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_pr_open_creates_reviewer_task(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: Opening a PR with a reviewer creates a corresponding Asana reviewer task."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app_for_pr(app, mock_dirname, mock_ado_conn, mock_asana_client)

        repo = RealObjectBuilder.create_real_ado_repository(repo_id="repo-abc", name="test-repo")
        pr = RealObjectBuilder.create_real_ado_pull_request(pr_id=100, title="Add Feature X", status="active")
        reviewer = RealObjectBuilder.create_real_ado_reviewer(display_name="Test User", email="test@example.com", vote=0)
        self._setup_git_client(app, repos=[repo], active_prs=[pr], reviewers=[reviewer])

        created_pr_task = TestDataBuilder.create_asana_task_data(
            gid="pr_task_gid_100", name="Pull Request 100: Add Feature X (Test User)"
        )
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[], created_task=created_pr_task)

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                from ado_asana_sync.sync.pr_sync_core import sync_pull_requests  # noqa: PLC0415

                sync_pull_requests(app, self.ado_project, self.asana_workspace_id, self.asana_project)

            tasks_api.create_task.assert_called_once()
            call_body = tasks_api.create_task.call_args[0][0]
            self.assertIn("Test User", call_body["data"]["name"])
            self.assertFalse(call_body["data"]["completed"])

            pr_records = app.pr_matches.all()
            self.assertEqual(len(pr_records), 1)
            self.assertEqual(pr_records[0]["ado_pr_id"], 100)
            self.assertEqual(pr_records[0]["processing_state"], "open")
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_pr_close_completes_reviewer_task(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: A PR that moves to 'completed' status closes the Asana reviewer task."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app_for_pr(app, mock_dirname, mock_ado_conn, mock_asana_client)

        app.pr_matches.insert(_make_pr_db_record(101, status="active", processing_state="open"))

        repo = RealObjectBuilder.create_real_ado_repository(repo_id="repo-abc", name="test-repo")
        completed_pr = RealObjectBuilder.create_real_ado_pull_request(pr_id=101, title="Feature PR 101", status="completed")
        reviewer = RealObjectBuilder.create_real_ado_reviewer(display_name="Test User", email="test@example.com", vote=0)
        self._setup_git_client(app, repos=[repo], active_prs=[], reviewers=[reviewer], pr_by_id=completed_pr)

        asana_task = {"gid": "pr_task_gid_101", "modified_at": _OLD_ASANA_DATE, "completed": False}
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[])
        tasks_api.get_task.return_value = asana_task

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                from ado_asana_sync.sync.pr_sync_core import sync_pull_requests  # noqa: PLC0415

                sync_pull_requests(app, self.ado_project, self.asana_workspace_id, self.asana_project)

            tasks_api.update_task.assert_called()
            update_body = tasks_api.update_task.call_args[0][0]
            self.assertTrue(update_body["data"]["completed"])
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_pr_reopen_uncompletes_reviewer_task(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: Reactivating a previously completed PR marks the reviewer Asana task as incomplete."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app_for_pr(app, mock_dirname, mock_ado_conn, mock_asana_client)

        app.pr_matches.insert(_make_pr_db_record(102, status="abandoned", processing_state="closed"))

        repo = RealObjectBuilder.create_real_ado_repository(repo_id="repo-abc", name="test-repo")
        active_pr = RealObjectBuilder.create_real_ado_pull_request(pr_id=102, title="Feature PR 102", status="active")
        reviewer = RealObjectBuilder.create_real_ado_reviewer(display_name="Test User", email="test@example.com", vote=0)
        self._setup_git_client(app, repos=[repo], active_prs=[active_pr], reviewers=[reviewer])

        asana_task = {"gid": "pr_task_gid_102", "modified_at": _OLD_ASANA_DATE, "completed": True}
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[])
        tasks_api.get_task.return_value = asana_task

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                from ado_asana_sync.sync.pr_sync_core import sync_pull_requests  # noqa: PLC0415

                sync_pull_requests(app, self.ado_project, self.asana_workspace_id, self.asana_project)

            tasks_api.update_task.assert_called()
            update_body = tasks_api.update_task.call_args[0][0]
            self.assertFalse(update_body["data"]["completed"])
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_pr_reviewer_status_update_syncs_vote_change(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: A reviewer changing their vote on a PR updates the linked Asana task."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self._connect_app_for_pr(app, mock_dirname, mock_ado_conn, mock_asana_client)

        app.pr_matches.insert(_make_pr_db_record(103, status="active", processing_state="open"))

        repo = RealObjectBuilder.create_real_ado_repository(repo_id="repo-abc", name="test-repo")
        active_pr = RealObjectBuilder.create_real_ado_pull_request(pr_id=103, title="Feature PR 103", status="active")
        reviewer_with_new_vote = RealObjectBuilder.create_real_ado_reviewer(
            display_name="Test User", email="test@example.com", vote=-5
        )
        self._setup_git_client(app, repos=[repo], active_prs=[active_pr], reviewers=[reviewer_with_new_vote])

        asana_task = {"gid": "pr_task_gid_103", "modified_at": _OLD_ASANA_DATE, "completed": False}
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[])
        tasks_api.get_task.return_value = asana_task

        try:
            with ExitStack() as stack:
                for p in self._asana_patches(tasks_api):
                    stack.enter_context(p)
                from ado_asana_sync.sync.pr_sync_core import sync_pull_requests  # noqa: PLC0415

                sync_pull_requests(app, self.ado_project, self.asana_workspace_id, self.asana_project)

            tasks_api.update_task.assert_called()
            update_body = tasks_api.update_task.call_args[0][0]
            self.assertFalse(update_body["data"]["completed"])

            pr_record = app.pr_matches.search(lambda x: x["ado_pr_id"] == 103)[0]
            self.assertEqual(pr_record["review_status"], "waitingForAuthor")
        finally:
            app.close()

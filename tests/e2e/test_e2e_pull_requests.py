"""End-to-end tests for pull request synchronization scenarios."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from tests.e2e._shared import _OLD_ASANA_DATE, E2EBase, make_pr_db_record
from tests.utils.test_helpers import RealObjectBuilder, TestDataBuilder


class TestE2ESyncPullRequests(E2EBase):
    """E2E tests for ADO-Asana pull request synchronization scenarios."""

    def setUp(self):
        super().setUp()
        self.asana_workspace_id = "workspace-123"
        self.asana_project = "project-456"
        self.ado_project = MagicMock(id="proj-id", name="TestProject")

    def _connect_app_for_pr(self, app, mock_dirname, mock_ado_conn, mock_asana_client):
        self.connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
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
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
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

        app.pr_matches.insert(make_pr_db_record(101, status="active", processing_state="open"))

        repo = RealObjectBuilder.create_real_ado_repository(repo_id="repo-abc", name="test-repo")
        completed_pr = RealObjectBuilder.create_real_ado_pull_request(pr_id=101, title="Feature PR 101", status="completed")
        reviewer = RealObjectBuilder.create_real_ado_reviewer(display_name="Test User", email="test@example.com", vote=0)
        self._setup_git_client(app, repos=[repo], active_prs=[], reviewers=[reviewer], pr_by_id=completed_pr)

        asana_task = {"gid": "pr_task_gid_101", "modified_at": _OLD_ASANA_DATE, "completed": False}
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[])
        tasks_api.get_task.return_value = asana_task

        try:
            with ExitStack() as stack:
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
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

        app.pr_matches.insert(make_pr_db_record(102, status="abandoned", processing_state="closed"))

        repo = RealObjectBuilder.create_real_ado_repository(repo_id="repo-abc", name="test-repo")
        active_pr = RealObjectBuilder.create_real_ado_pull_request(pr_id=102, title="Feature PR 102", status="active")
        reviewer = RealObjectBuilder.create_real_ado_reviewer(display_name="Test User", email="test@example.com", vote=0)
        self._setup_git_client(app, repos=[repo], active_prs=[active_pr], reviewers=[reviewer])

        asana_task = {"gid": "pr_task_gid_102", "modified_at": _OLD_ASANA_DATE, "completed": True}
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[])
        tasks_api.get_task.return_value = asana_task

        try:
            with ExitStack() as stack:
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
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

        app.pr_matches.insert(make_pr_db_record(103, status="active", processing_state="open"))

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
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
                from ado_asana_sync.sync.pr_sync_core import sync_pull_requests  # noqa: PLC0415

                sync_pull_requests(app, self.ado_project, self.asana_workspace_id, self.asana_project)

            tasks_api.update_task.assert_called()
            update_body = tasks_api.update_task.call_args[0][0]
            self.assertFalse(update_body["data"]["completed"])

            pr_record = app.pr_matches.search(lambda x: x["ado_pr_id"] == 103)[0]
            self.assertEqual(pr_record["review_status"], "waitingForAuthor")
        finally:
            app.close()

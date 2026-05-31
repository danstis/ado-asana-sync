"""End-to-end tests for work item synchronization scenarios."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.sync import sync_project
from tests.e2e._shared import _OLD_ASANA_DATE, _TEST_USER_ASSIGNED, E2EBase, make_backlog_item, make_work_item_db_record
from tests.utils.test_helpers import TestDataBuilder


class TestE2ESyncWorkItems(E2EBase):
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

        return mock_work, mock_wit

    def _set_backlog(self, mock_work, item_ids):
        if not item_ids:
            mock_work.get_backlog_level_work_items.return_value.work_items = None
        else:
            mock_work.get_backlog_level_work_items.return_value.work_items = [make_backlog_item(i) for i in item_ids]

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_new_work_item_creates_asana_task(self, mock_asana_client, mock_ado_conn, mock_dirname):
        """E2E: A new ADO work item is synced and a new Asana task is created."""
        app = TestDataBuilder.create_real_app(self.temp_dir)
        self.connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        mock_work, mock_wit = self._setup_ado_clients(app)

        ado_item = TestDataBuilder.create_ado_work_item(item_id=1001, title="New Feature", assigned_to=_TEST_USER_ASSIGNED)
        mock_wit.get_work_item.return_value = ado_item
        self._set_backlog(mock_work, [1001])

        created_task = TestDataBuilder.create_asana_task_data(gid="new_task_gid", name="Task 1001: New Feature")
        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[], created_task=created_task)

        try:
            with ExitStack() as stack:
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
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
        self.connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        mock_work, mock_wit = self._setup_ado_clients(app)

        app.matches.insert(make_work_item_db_record(1002, "Old Title", asana_gid="existing_gid"))

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
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
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
        self.connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        mock_work, mock_wit = self._setup_ado_clients(app)

        app.matches.insert(make_work_item_db_record(1003, "Close Me", asana_gid="close_gid"))

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
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
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
        self.connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        mock_work, mock_wit = self._setup_ado_clients(app)

        app.matches.insert(make_work_item_db_record(1004, "Reopened Task", state="Closed", asana_gid="reopen_gid"))

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
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
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
        self.connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        mock_work, mock_wit = self._setup_ado_clients(app)

        child_relation = MagicMock()
        child_relation.rel = "System.LinkTypes.Hierarchy-Forward"
        child_relation.url = "https://dev.azure.com/test/project/_apis/wit/workItems/2002"

        parent_item = TestDataBuilder.create_ado_work_item(item_id=2001, title="Parent Task", assigned_to=_TEST_USER_ASSIGNED)
        parent_item.relations = [child_relation]

        child_item = TestDataBuilder.create_ado_work_item(item_id=2002, title="Child Task", assigned_to=_TEST_USER_ASSIGNED)
        child_item.relations = None

        def get_work_item(item_id, expand=None):
            return parent_item if item_id == 2001 else child_item

        mock_wit.get_work_item.side_effect = get_work_item
        self._set_backlog(mock_work, [2001])

        parent_created = TestDataBuilder.create_asana_task_data(gid="parent_gid", name="Task 2001: Parent Task")
        child_created = TestDataBuilder.create_asana_task_data(gid="child_gid", name="Task 2002: Child Task")

        def create_task_side_effect(body, opts=None):
            name = body["data"].get("name", "")
            return parent_created if "2001" in name else child_created

        tasks_api = self.asana_helper.create_tasks_api_mock(tasks=[])
        tasks_api.create_task.side_effect = create_task_side_effect

        try:
            with ExitStack() as stack:
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
                sync_project(app, self.project_config)

            self.assertEqual(tasks_api.create_task.call_count, 2)

            child_call = next(
                call for call in tasks_api.create_task.call_args_list if "Task 2002" in call[0][0]["data"]["name"]
            )
            self.assertIn("parent", child_call[0][0]["data"])
            self.assertEqual(child_call[0][0]["data"]["parent"], "parent_gid")

            saved_ids = {record["ado_id"] for record in app.matches.all()}
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
        self.connect_app(app, mock_dirname, mock_ado_conn, mock_asana_client)
        mock_work, mock_wit = self._setup_ado_clients(app)

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
                for patch_ctx in self.asana_patches(tasks_api):
                    stack.enter_context(patch_ctx)
                sync_project(app, self.project_config)

            tasks_api.create_task.assert_not_called()
            tasks_api.update_task.assert_called()

            saved = app.matches.search(lambda x: x["ado_id"] == 3001)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["asana_gid"], "preexisting_gid")
        finally:
            app.close()

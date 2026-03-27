"""Integration tests for delta sync feature using real App + real Database."""

from __future__ import annotations

import logging
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from tests.utils.test_helpers import TestDataBuilder
from tests.utils.test_helpers import iso as _iso

# TestDataBuilder.create_real_app inserts this project via projects.json → _sync_projects_from_json
_PROJECT = "TestProject"
_TEAM = "TestTeam"


class TestDeltaSyncDatabaseMethods(unittest.TestCase):
    """Integration tests for schema v3 migration and checkpoint DB methods."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        logging.basicConfig(level=logging.DEBUG)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_schema_v3_migration_adds_columns(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """Schema migration adds last_sync_at and last_full_sync_at to projects table."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()

        try:
            with app.db.get_connection() as conn:
                cursor = conn.execute("PRAGMA table_info(projects)")
                columns = {row[1] for row in cursor.fetchall()}
            self.assertIn("last_sync_at", columns)
            self.assertIn("last_full_sync_at", columns)
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_get_checkpoint_returns_nulls_for_new_project(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """get_sync_checkpoint returns None values for a project never synced."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()

        try:
            # _PROJECT/_TEAM already inserted by app.connect() via _sync_projects_from_json
            checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            self.assertIsNone(checkpoint["last_sync_at"])
            self.assertIsNone(checkpoint["last_full_sync_at"])
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_set_and_get_checkpoint_round_trip(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """set_sync_checkpoint then get_sync_checkpoint returns stored values."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()

        try:
            run_time = _iso(datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc))
            app.db.set_sync_checkpoint(_PROJECT, _TEAM, run_time, full_scan=True)

            checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            self.assertEqual(checkpoint["last_sync_at"], run_time)
            self.assertEqual(checkpoint["last_full_sync_at"], run_time)
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_set_checkpoint_incremental_does_not_update_full_sync_at(  # noqa: E501
        self, mock_asana_client, mock_ado_connection, mock_dirname
    ):
        """set_sync_checkpoint with full_scan=False does not update last_full_sync_at."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()

        try:
            full_time = _iso(datetime(2026, 3, 15, 8, 0, 0, tzinfo=timezone.utc))
            app.db.set_sync_checkpoint(_PROJECT, _TEAM, full_time, full_scan=True)

            incremental_time = _iso(datetime(2026, 3, 15, 9, 0, 0, tzinfo=timezone.utc))
            app.db.set_sync_checkpoint(_PROJECT, _TEAM, incremental_time, full_scan=False)

            checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            self.assertEqual(checkpoint["last_sync_at"], incremental_time)
            # last_full_sync_at should NOT be updated
            self.assertEqual(checkpoint["last_full_sync_at"], full_time)
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_sync_projects_preserves_checkpoints(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """sync_projects_from_json preserves last_sync_at and last_full_sync_at on update."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()

        try:
            # Project already exists (inserted by app.connect()); set a checkpoint
            run_time = _iso(datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc))
            app.db.set_sync_checkpoint(_PROJECT, _TEAM, run_time, full_scan=True)

            # Re-sync projects with updated asana name (simulates config change + restart)
            app.db.sync_projects_from_json(
                [{"adoProjectName": _PROJECT, "adoTeamName": _TEAM, "asanaProjectName": "NewAsanaProject"}]
            )

            checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            # Checkpoint must be preserved
            self.assertEqual(checkpoint["last_sync_at"], run_time)
            self.assertEqual(checkpoint["last_full_sync_at"], run_time)

            # Asana project name must be updated
            projects = app.db.get_projects()
            self.assertEqual(projects[0]["asanaProjectName"], "NewAsanaProject")
        finally:
            app.close()


class TestFirstRunAndForceFullSync(unittest.TestCase):
    """Integration tests for first-run and force-full-sync behavior."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_first_run_triggers_full_scan_and_records_checkpoint(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """First run with NULL checkpoint: determine_sync_mode returns full, checkpoint recorded after sync."""
        from ado_asana_sync.sync.sync import determine_sync_mode

        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()

        try:
            # Project already inserted; checkpoint is NULL on first run
            checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            mode, since = determine_sync_mode(checkpoint, force_full=False, overlap_minutes=5)
            self.assertEqual(mode, "full")
            self.assertIsNone(since)

            # Simulate recording checkpoint after first full run
            run_time = _iso(datetime.now(timezone.utc))
            app.db.set_sync_checkpoint(_PROJECT, _TEAM, run_time, full_scan=True)

            checkpoint2 = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            self.assertIsNotNone(checkpoint2["last_sync_at"])
            self.assertIsNotNone(checkpoint2["last_full_sync_at"])

            # Next run should use incremental (last_full_sync_at < 24h ago)
            mode2, _ = determine_sync_mode(checkpoint2, force_full=False, overlap_minutes=5)
            self.assertEqual(mode2, "incremental")
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_force_full_sync_overrides_existing_checkpoint(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """FORCE_FULL_SYNC=True overrides existing checkpoint and forces full scan."""
        from ado_asana_sync.sync.sync import determine_sync_mode

        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()

        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()

        try:
            run_time = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
            app.db.set_sync_checkpoint(_PROJECT, _TEAM, run_time, full_scan=True)

            checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            mode, since = determine_sync_mode(checkpoint, force_full=True, overlap_minutes=5)
            self.assertEqual(mode, "full")
            self.assertIsNone(since)
        finally:
            app.close()


class TestSyncProjectIncrementalMode(unittest.TestCase):
    """Integration tests for incremental sync mode (FR-002: WIQL-based ADO fetch).

    Incremental mode:
    - Uses query_by_wiql instead of get_backlog_level_work_items
    - Always fetches full Asana task list (architectural requirement for name-based lookup)
    - Skips process_closed_items (only safe after a full backlog scan)
    - Falls back to full backlog fetch if WIQL raises an exception
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_app_with_incremental_checkpoint(self, mock_dirname, mock_ado_connection, mock_asana_client):
        """Create app with a recent checkpoint so determine_sync_mode picks incremental."""
        mock_dirname.return_value = self.temp_dir
        mock_ado_connection.return_value = MagicMock()
        mock_asana_client.return_value = MagicMock()
        app = TestDataBuilder.create_real_app(self.temp_dir)
        app.connect()
        recent = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
        app.db.set_sync_checkpoint(_PROJECT, _TEAM, recent, full_scan=True)
        return app

    def _common_patches(self, stack, asana_helper, mock_tasks_api):
        """Enter patches for Asana API clients shared by all tests in this class."""
        stack.enter_context(patch("ado_asana_sync.sync.sync.asana.TasksApi", return_value=mock_tasks_api))
        stack.enter_context(
            patch("ado_asana_sync.sync.sync.asana.WorkspacesApi", return_value=asana_helper.create_workspace_api_mock())
        )
        stack.enter_context(
            patch("ado_asana_sync.sync.sync.asana.ProjectsApi", return_value=asana_helper.create_projects_api_mock())
        )
        stack.enter_context(
            patch("ado_asana_sync.sync.sync.asana.UsersApi", return_value=asana_helper.create_users_api_mock())
        )
        stack.enter_context(patch("ado_asana_sync.sync.sync.asana.TagsApi", return_value=asana_helper.create_tags_api_mock()))

    def _setup_ado_clients(self, app, wiql_ids=None):
        """Configure mock ADO clients. wiql_ids sets query_by_wiql result IDs."""
        app.ado_core_client = MagicMock()
        app.ado_core_client.get_project.return_value.id = "proj-id"
        app.ado_core_client.get_team.return_value.id = "team-id"
        mock_work_client = MagicMock()
        mock_work_client.get_backlog_level_work_items.return_value.work_items = []
        app.ado_work_client = mock_work_client
        mock_wit_client = MagicMock()
        if wiql_ids is not None:
            mock_wi_refs = [MagicMock(id=i) for i in wiql_ids]
            mock_wit_client.query_by_wiql.return_value.work_items = mock_wi_refs
        app.ado_wit_client = mock_wit_client
        return mock_work_client, mock_wit_client

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_incremental_mode_calls_wiql_not_backlog(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """FR-002: In incremental mode, query_by_wiql is called instead of get_backlog_level_work_items."""
        from contextlib import ExitStack

        from tests.utils.test_helpers import AsanaApiMockHelper

        app = self._make_app_with_incremental_checkpoint(mock_dirname, mock_ado_connection, mock_asana_client)
        asana_helper = AsanaApiMockHelper()

        try:
            mock_work_client, mock_wit_client = self._setup_ado_clients(app, wiql_ids=[])
            project_config = {"adoProjectName": _PROJECT, "adoTeamName": _TEAM, "asanaProjectName": "AsanaProject"}

            with ExitStack() as stack:
                stack.enter_context(patch("ado_asana_sync.sync.sync.get_asana_project_tasks", return_value=[]))
                self._common_patches(stack, asana_helper, asana_helper.create_tasks_api_mock())
                from ado_asana_sync.sync.sync import sync_project

                sync_project(app, project_config)

            mock_wit_client.query_by_wiql.assert_called_once()
            mock_work_client.get_backlog_level_work_items.assert_not_called()
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_incremental_mode_uses_full_asana_task_fetch(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """Asana task fetch is always full in incremental mode (name-based lookup requires it)."""
        from contextlib import ExitStack

        from tests.utils.test_helpers import AsanaApiMockHelper

        app = self._make_app_with_incremental_checkpoint(mock_dirname, mock_ado_connection, mock_asana_client)
        asana_helper = AsanaApiMockHelper()

        try:
            self._setup_ado_clients(app, wiql_ids=[])
            project_config = {"adoProjectName": _PROJECT, "adoTeamName": _TEAM, "asanaProjectName": "AsanaProject"}

            with ExitStack() as stack:
                mock_full_fetch = stack.enter_context(
                    patch("ado_asana_sync.sync.sync.get_asana_project_tasks", return_value=[])
                )
                self._common_patches(stack, asana_helper, asana_helper.create_tasks_api_mock())
                from ado_asana_sync.sync.sync import sync_project

                sync_project(app, project_config)

            mock_full_fetch.assert_called_once()
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_incremental_mode_skips_process_closed_items(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """process_closed_items is NOT called in incremental mode.

        In incremental mode, processed_item_ids contains only changed items.
        Calling process_closed_items would incorrectly treat all unchanged mapped
        items as closed. The daily full scan handles actual closures.
        """
        from contextlib import ExitStack

        from tests.utils.test_helpers import AsanaApiMockHelper

        app = self._make_app_with_incremental_checkpoint(mock_dirname, mock_ado_connection, mock_asana_client)
        asana_helper = AsanaApiMockHelper()

        try:
            self._setup_ado_clients(app, wiql_ids=[])
            project_config = {"adoProjectName": _PROJECT, "adoTeamName": _TEAM, "asanaProjectName": "AsanaProject"}

            with ExitStack() as stack:
                stack.enter_context(patch("ado_asana_sync.sync.sync.get_asana_project_tasks", return_value=[]))
                mock_closed = stack.enter_context(patch("ado_asana_sync.sync.sync.process_closed_items"))
                self._common_patches(stack, asana_helper, asana_helper.create_tasks_api_mock())
                from ado_asana_sync.sync.sync import sync_project

                sync_project(app, project_config)

            mock_closed.assert_not_called()
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_incremental_checkpoint_recorded_with_full_scan_false(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """After a clean incremental run, last_full_sync_at is NOT updated."""
        from contextlib import ExitStack

        from tests.utils.test_helpers import AsanaApiMockHelper

        app = self._make_app_with_incremental_checkpoint(mock_dirname, mock_ado_connection, mock_asana_client)
        asana_helper = AsanaApiMockHelper()

        # Record the existing full_sync_at before the incremental run
        prior_checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
        prior_full_sync_at = prior_checkpoint["last_full_sync_at"]

        try:
            self._setup_ado_clients(app, wiql_ids=[])
            project_config = {"adoProjectName": _PROJECT, "adoTeamName": _TEAM, "asanaProjectName": "AsanaProject"}

            with ExitStack() as stack:
                stack.enter_context(patch("ado_asana_sync.sync.sync.get_asana_project_tasks", return_value=[]))
                self._common_patches(stack, asana_helper, asana_helper.create_tasks_api_mock())
                from ado_asana_sync.sync.sync import sync_project

                sync_project(app, project_config)

            after_checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            # last_sync_at updated
            self.assertIsNotNone(after_checkpoint["last_sync_at"])
            # last_full_sync_at must NOT change after an incremental run
            self.assertEqual(after_checkpoint["last_full_sync_at"], prior_full_sync_at)
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_wiql_exception_falls_back_to_full_backlog(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """When query_by_wiql raises, fall back to get_backlog_level_work_items and log a warning."""
        from contextlib import ExitStack

        from tests.utils.test_helpers import AsanaApiMockHelper

        app = self._make_app_with_incremental_checkpoint(mock_dirname, mock_ado_connection, mock_asana_client)
        asana_helper = AsanaApiMockHelper()

        try:
            mock_work_client, mock_wit_client = self._setup_ado_clients(app, wiql_ids=[])
            mock_wit_client.query_by_wiql.side_effect = Exception("WIQL unavailable")
            project_config = {"adoProjectName": _PROJECT, "adoTeamName": _TEAM, "asanaProjectName": "AsanaProject"}

            with ExitStack() as stack:
                stack.enter_context(patch("ado_asana_sync.sync.sync.get_asana_project_tasks", return_value=[]))
                self._common_patches(stack, asana_helper, asana_helper.create_tasks_api_mock())
                with self.assertLogs("ado_asana_sync.sync.sync", level="WARNING") as log_ctx:
                    from ado_asana_sync.sync.sync import sync_project

                    sync_project(app, project_config)

            mock_work_client.get_backlog_level_work_items.assert_called_once()
            self.assertTrue(any("falling back to full backlog scan" in m for m in log_ctx.output))
        finally:
            app.close()

    @patch("ado_asana_sync.sync.app.os.path.dirname")
    @patch("ado_asana_sync.sync.app.Connection")
    @patch("ado_asana_sync.sync.app.asana.ApiClient")
    def test_wiql_fallback_records_checkpoint_as_full_scan(self, mock_asana_client, mock_ado_connection, mock_dirname):
        """After WIQL fallback to full backlog, checkpoint is recorded with full_scan=True."""
        from contextlib import ExitStack

        from tests.utils.test_helpers import AsanaApiMockHelper

        app = self._make_app_with_incremental_checkpoint(mock_dirname, mock_ado_connection, mock_asana_client)
        asana_helper = AsanaApiMockHelper()

        prior_full_sync_at = app.db.get_sync_checkpoint(_PROJECT, _TEAM)["last_full_sync_at"]

        try:
            mock_work_client, mock_wit_client = self._setup_ado_clients(app, wiql_ids=[])
            mock_wit_client.query_by_wiql.side_effect = Exception("WIQL unavailable")
            project_config = {"adoProjectName": _PROJECT, "adoTeamName": _TEAM, "asanaProjectName": "AsanaProject"}

            with ExitStack() as stack:
                stack.enter_context(patch("ado_asana_sync.sync.sync.get_asana_project_tasks", return_value=[]))
                self._common_patches(stack, asana_helper, asana_helper.create_tasks_api_mock())
                from ado_asana_sync.sync.sync import sync_project

                sync_project(app, project_config)

            after_checkpoint = app.db.get_sync_checkpoint(_PROJECT, _TEAM)
            # Fallback ran a full scan, so last_full_sync_at must be refreshed
            self.assertNotEqual(after_checkpoint["last_full_sync_at"], prior_full_sync_at)
        finally:
            app.close()

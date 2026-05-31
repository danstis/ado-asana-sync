import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.dry_run import DryRunReport
from ado_asana_sync.sync.sync import create_asana_task, remove_mapping, start_sync, update_asana_task


class _ExecutorStub:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def map(self, func, apps, projects):
        for app, project in zip(apps, projects, strict=False):
            func(app, project)


class TestRuntimeModes(unittest.TestCase):
    @patch("ado_asana_sync.sync.sync.sleep")
    @patch("ado_asana_sync.sync.sync.sync_project")
    @patch("ado_asana_sync.sync.sync.read_projects", return_value=[{"adoProjectName": "A", "adoTeamName": "B"}])
    @patch("ado_asana_sync.sync.sync.create_tag_if_not_existing", return_value="tag-gid")
    @patch("ado_asana_sync.sync.sync.get_asana_workspace", return_value="workspace-gid")
    @patch("ado_asana_sync.sync.sync.concurrent.futures.ThreadPoolExecutor", return_value=_ExecutorStub())
    def test_start_sync_run_once_exits_after_single_cycle(
        self,
        _mock_executor,
        _mock_workspace,
        _mock_tag,
        mock_read_projects,
        mock_sync_project,
        mock_sleep,
    ):
        app = MagicMock()
        app.asana_workspace_name = "workspace"
        app.asana_tag_name = "synced"
        app.run_once = True
        app.dry_run = False
        app.sleep_time = 30

        start_sync(app)

        mock_read_projects.assert_called_once_with(app)
        mock_sync_project.assert_called_once()
        mock_sleep.assert_not_called()

    def test_dry_run_report_logs_summary(self):
        report = DryRunReport()
        report.record_task_create(ado_id=101, title="Create task")
        report.record_task_update(ado_id=102, title="Update task")
        report.record_task_close(ado_id=103, title="Close task")
        report.record_pr_create(ado_pr_id=201, title="Create PR task")
        report.record_pr_update(ado_pr_id=202, title="Update PR task")
        report.record_pr_close(ado_pr_id=203, title="Close PR task")

        stream = StringIO()
        with patch("ado_asana_sync.sync.dry_run._LOGGER") as mock_logger:
            mock_logger.info.side_effect = lambda message, *args: stream.write(message % args if args else message)
            report.log_summary()

        output = stream.getvalue()
        self.assertIn("tasks create=1 update=1 close=1", output)
        self.assertIn("pull_requests create=1 update=1 close=1", output)
        self.assertIn("101", output)
        self.assertIn("203", output)

    @patch("ado_asana_sync.sync.sync.find_custom_field_by_name", return_value=None)
    @patch("asana.TasksApi")
    def test_create_asana_task_dry_run_skips_asana_write(self, mock_tasks_api_class, _mock_custom_field):
        app = MagicMock()
        app.dry_run = True
        app.dry_run_report = DryRunReport()
        task = SimpleNamespace(
            ado_id=321,
            title="New task",
            asana_title="Task 321: New task",
            asana_notes_link="note",
            assigned_to=None,
            state="New",
            due_date=None,
            url="https://example.com/321",
            asana_gid=None,
        )

        create_asana_task(app, "project-gid", task, "tag-gid")

        mock_tasks_api_class.return_value.create_task.assert_not_called()
        self.assertEqual(task.asana_gid, "dry-run-task-321")
        self.assertEqual(app.dry_run_report.task_create_ids, [321])

    @patch("ado_asana_sync.sync.sync.find_custom_field_by_name", return_value=None)
    @patch("ado_asana_sync.sync.sync.tag_asana_item")
    @patch("asana.TasksApi")
    def test_update_asana_task_dry_run_skips_asana_write(self, mock_tasks_api_class, _mock_tag, _mock_custom_field):
        app = MagicMock()
        app.dry_run = True
        app.dry_run_report = DryRunReport()
        task = MagicMock()
        task.ado_id = 654
        task.title = "Updated task"
        task.asana_title = "Task 654: Updated task"
        task.asana_notes_link = "note"
        task.assigned_to = None
        task.state = "Active"
        task.url = "https://example.com/654"
        task.asana_gid = "asana-654"

        update_asana_task(app, task, "tag-gid", "project-gid")

        mock_tasks_api_class.return_value.update_task.assert_not_called()
        task.save.assert_not_called()
        self.assertEqual(app.dry_run_report.task_update_ids, [654])

    def test_remove_mapping_dry_run_skips_database_write(self):
        app = MagicMock()
        app.dry_run = True
        app.dry_run_report = DryRunReport()
        wi = {"ado_id": 777, "item_type": "Bug", "title": "Old item", "doc_id": 12}

        remove_mapping(app, wi)

        app.matches.remove.assert_not_called()
        self.assertEqual(app.dry_run_report.task_close_ids, [777])

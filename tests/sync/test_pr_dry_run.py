import unittest
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.dry_run import DryRunReport
from ado_asana_sync.sync.pull_request_sync import create_asana_pr_task, update_asana_pr_task


class TestPullRequestDryRun(unittest.TestCase):
    @patch("ado_asana_sync.sync.pr_asana_helpers.find_custom_field_by_name", return_value=None)
    @patch("asana.TasksApi")
    def test_create_asana_pr_task_dry_run_skips_write(self, mock_tasks_api_class, _mock_custom_field):
        app = MagicMock()
        app.dry_run = True
        app.dry_run_report = DryRunReport()
        pr_item = MagicMock()
        pr_item.ado_pr_id = 901
        pr_item.title = "PR create"
        pr_item.asana_title = "PR 901: PR create"
        pr_item.asana_notes_link = "note"
        pr_item.status = "active"
        pr_item.review_status = "waitingForAuthor"
        pr_item.url = "https://example.com/pr/901"
        pr_item.reviewer_gid = "user-1"
        pr_item.asana_gid = None

        create_asana_pr_task(app, "project-gid", pr_item, "tag-gid")

        mock_tasks_api_class.return_value.create_task.assert_not_called()
        pr_item.save.assert_not_called()
        self.assertEqual(pr_item.asana_gid, "dry-run-pr-901")
        self.assertEqual(app.dry_run_report.pr_create_ids, [901])

    @patch("ado_asana_sync.sync.pr_asana_helpers.add_closure_comment_to_pr_task")
    @patch("ado_asana_sync.sync.pr_asana_helpers.add_tag_to_pr_task")
    @patch("ado_asana_sync.sync.pr_asana_helpers.find_custom_field_by_name", return_value=None)
    @patch("asana.TasksApi")
    def test_update_asana_pr_task_dry_run_records_close(
        self,
        mock_tasks_api_class,
        _mock_custom_field,
        _mock_add_tag,
        _mock_add_comment,
    ):
        app = MagicMock()
        app.dry_run = True
        app.dry_run_report = DryRunReport()
        pr_item = MagicMock()
        pr_item.ado_pr_id = 902
        pr_item.title = "PR close"
        pr_item.asana_gid = "asana-pr-902"
        pr_item.asana_title = "PR 902: PR close"
        pr_item.asana_notes_link = "note"
        pr_item.status = "completed"
        pr_item.review_status = "approved"
        pr_item.url = "https://example.com/pr/902"
        pr_item.reviewer_gid = "user-2"

        update_asana_pr_task(app, pr_item, "tag-gid", "project-gid")

        mock_tasks_api_class.return_value.update_task.assert_not_called()
        pr_item.save.assert_not_called()
        self.assertEqual(app.dry_run_report.pr_close_ids, [902])

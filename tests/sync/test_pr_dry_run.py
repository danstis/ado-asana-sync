import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.dry_run import DryRunReport
from ado_asana_sync.sync.pr_processor import create_new_pr_reviewer_task, update_existing_pr_reviewer_task
from ado_asana_sync.sync.pull_request_item import PullRequestItem
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

    @patch("ado_asana_sync.sync.pr_processor.extract_reviewer_vote", return_value="waitingForAuthor")
    @patch("ado_asana_sync.sync.pr_processor.update_asana_pr_task")
    @patch("ado_asana_sync.sync.pr_processor.PullRequestItem.save")
    @patch(
        "ado_asana_sync.sync.pr_processor.get_asana_task_by_name",
        return_value={"gid": "asana-pr-903", "modified_at": "2026-05-31T04:00:00Z"},
    )
    def test_create_new_pr_reviewer_task_dry_run_skips_local_save_for_existing_task(
        self,
        _mock_get_task,
        mock_save,
        mock_update_task,
        _mock_vote,
    ):
        app = MagicMock()
        app.dry_run = True
        app.ado_url = "https://dev.azure.com/example"
        app.asana_tag_gid = "tag-gid"
        pr = SimpleNamespace(
            pull_request_id=903,
            title="Existing PR",
            status="active",
            web_url="https://example.com/pr/903",
        )
        repository = SimpleNamespace(
            id="repo-1",
            name="repo",
            project=SimpleNamespace(name="project"),
        )

        create_new_pr_reviewer_task(
            app,
            pr,
            repository,
            reviewer=MagicMock(),
            asana_matched_user={"gid": "user-3", "name": "Reviewer"},
            asana_project_tasks=[],
            asana_project="project-gid",
        )

        mock_save.assert_not_called()
        mock_update_task.assert_called_once()

    @patch("ado_asana_sync.sync.pr_processor.extract_reviewer_vote", return_value="waitingForAuthor")
    @patch("ado_asana_sync.sync.pr_processor.update_asana_pr_task")
    @patch("ado_asana_sync.sync.pr_processor._get_cached_asana_task", return_value={"modified_at": "2026-05-31T04:00:00Z"})
    @patch("ado_asana_sync.sync.pr_processor.PullRequestItem.save")
    def test_update_existing_pr_reviewer_task_dry_run_skips_reviewer_name_save(
        self,
        mock_save,
        _mock_cached_task,
        mock_update_task,
        _mock_vote,
    ):
        app = MagicMock()
        app.dry_run = True
        app.asana_tag_gid = "tag-gid"
        pr = SimpleNamespace(
            pull_request_id=904,
            title="PR needing reviewer backfill",
            status="active",
        )
        existing_match = PullRequestItem(
            ado_pr_id=904,
            ado_repository_id="repo-1",
            title="PR needing reviewer backfill",
            status="active",
            url="https://example.com/pr/904",
            reviewer_gid="user-4",
            reviewer_name=None,
            asana_gid="asana-pr-904",
            asana_updated="2026-05-31T04:00:00Z",
            review_status="waitingForAuthor",
        )

        update_existing_pr_reviewer_task(
            app,
            pr,
            _repository=MagicMock(),
            reviewer=MagicMock(),
            existing_match=existing_match,
            asana_matched_user={"gid": "user-4", "name": "Reviewer Four"},
            asana_project="project-gid",
        )

        self.assertEqual(existing_match.reviewer_name, "Reviewer Four")
        mock_save.assert_not_called()
        mock_update_task.assert_called_once()

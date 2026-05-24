"""Tests for ADO group/container reviewer fallback handling."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ado_asana_sync.sync.pull_request_item import PullRequestItem
from ado_asana_sync.sync.pull_request_sync import (
    _handle_group_reviewer,
    _resolve_group_reviewer_default_user,
    is_group_reviewer,
)
from tests.utils.test_helpers import RealObjectBuilder, TestDataBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(temp_dir: str, strategy: str = "ignore", default_user: str = "") -> object:
    """Create a real App instance wired with group reviewer config."""
    env_patch = {
        "GROUP_REVIEWER_STRATEGY": strategy,
        "GROUP_REVIEWER_DEFAULT_USER": default_user,
    }
    with patch.dict(os.environ, env_patch, clear=False):
        app = TestDataBuilder.create_real_app(temp_dir)

    # Wire database tables manually (connect() calls Azure/Asana — mock those)
    from ado_asana_sync.database import Database

    db_path = os.path.join(temp_dir, "test.db")
    app.db = Database(db_path)
    app.matches = app.db.table("matches")
    app.pr_matches = app.db.table("pr_matches")
    app.config = app.db.table("config")
    app.asana_tag_gid = "tag-gid-123"
    app.ado_url = "https://dev.azure.com/testorg"

    # Propagate strategy fields that __init__ would have set under the patch
    app.group_reviewer_strategy = strategy if strategy in {"ignore", "default_user", "unassigned_task"} else "ignore"
    app.group_reviewer_default_user = default_user
    if app.group_reviewer_strategy == "default_user" and not default_user:
        app.group_reviewer_strategy = "ignore"

    return app


def _make_pr(pr_id: int = 42, title: str = "My PR", status: str = "active"):
    return RealObjectBuilder.create_real_ado_pull_request(pr_id, title, status)


def _make_repo():
    return RealObjectBuilder.create_real_ado_repository()


# ---------------------------------------------------------------------------
# 1. is_group_reviewer detection
# ---------------------------------------------------------------------------


class TestIsGroupReviewer(unittest.TestCase):
    def test_is_container_flag_true(self):
        reviewer = RealObjectBuilder.create_real_ado_group_reviewer(is_container=True)
        self.assertTrue(is_group_reviewer(reviewer))

    def test_is_container_flag_false_no_other_signals(self):
        reviewer = RealObjectBuilder.create_real_ado_reviewer(display_name="Jane Doe", email="jane@example.com")
        self.assertFalse(is_group_reviewer(reviewer))

    def test_display_name_bracket_pattern(self):
        reviewer = RealObjectBuilder.create_real_ado_group_reviewer(
            display_name="[MyProject]\\Contributors", is_container=False
        )
        self.assertTrue(is_group_reviewer(reviewer))

    def test_display_name_without_bracket_pattern_not_group(self):
        reviewer = RealObjectBuilder.create_real_ado_reviewer(display_name="John Doe", email="john@example.com")
        self.assertFalse(is_group_reviewer(reviewer))

    def test_vstfs_unique_name_with_backslash_display(self):
        """Reviewer with a vsid-style unique_name and backslash in display name is a group."""

        class ReviewerObj:
            display_name = "Project\\MyTeam"
            unique_name = "vstfs:///Classification/TeamProject/abc"
            is_container = False

        self.assertTrue(is_group_reviewer(ReviewerObj()))

    def test_individual_reviewer_with_backslash_domain_not_group(self):
        """DOMAIN\\user with a proper email unique_name should not be detected as group."""

        class ReviewerObj:
            display_name = "CORP\\john.doe"
            unique_name = "john.doe@corp.com"
            is_container = False

        self.assertFalse(is_group_reviewer(ReviewerObj()))


# ---------------------------------------------------------------------------
# 2. Config loading via App.__init__
# ---------------------------------------------------------------------------


class TestGroupReviewerConfig(unittest.TestCase):
    def test_default_strategy_is_ignore(self):
        env = {}
        env.pop("GROUP_REVIEWER_STRATEGY", None)
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_app(tmp)
        self.assertEqual(app.group_reviewer_strategy, "ignore")

    def test_valid_strategy_unassigned_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_app(tmp, strategy="unassigned_task")
        self.assertEqual(app.group_reviewer_strategy, "unassigned_task")

    def test_valid_strategy_default_user_with_user_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_app(tmp, strategy="default_user", default_user="fallback@example.com")
        self.assertEqual(app.group_reviewer_strategy, "default_user")
        self.assertEqual(app.group_reviewer_default_user, "fallback@example.com")

    def test_invalid_strategy_falls_back_to_ignore(self):
        with patch.dict(os.environ, {"GROUP_REVIEWER_STRATEGY": "nonsense"}, clear=False):
            from ado_asana_sync.sync.app import App

            with patch("ado_asana_sync.sync.app.configure_azure_monitor"):
                app = App(
                    ado_pat="p",
                    ado_url="https://dev.azure.com/x",
                    asana_token="t",
                    asana_workspace_name="ws",
                )
                self.assertEqual(app.group_reviewer_strategy, "ignore")

    def test_default_user_strategy_without_user_falls_back_to_ignore(self):
        env = {"GROUP_REVIEWER_STRATEGY": "default_user", "GROUP_REVIEWER_DEFAULT_USER": ""}
        with patch.dict(os.environ, env, clear=False):
            from ado_asana_sync.sync.app import App

            with patch("ado_asana_sync.sync.app.configure_azure_monitor"):
                app = App(
                    ado_pat="p",
                    ado_url="https://dev.azure.com/x",
                    asana_token="t",
                    asana_workspace_name="ws",
                )
                self.assertEqual(app.group_reviewer_strategy, "ignore")


# ---------------------------------------------------------------------------
# 3. _resolve_group_reviewer_default_user
# ---------------------------------------------------------------------------


class TestResolveGroupReviewerDefaultUser(unittest.TestCase):
    USERS = [
        {"gid": "gid-alice", "name": "Alice Smith", "email": "alice@example.com"},
        {"gid": "gid-bob", "name": "Bob Jones", "email": "bob@example.com"},
    ]

    def test_resolve_by_email(self):
        result = _resolve_group_reviewer_default_user(self.USERS, "alice@example.com")
        self.assertIsNotNone(result)
        self.assertEqual(result["gid"], "gid-alice")

    def test_resolve_by_email_case_insensitive(self):
        result = _resolve_group_reviewer_default_user(self.USERS, "ALICE@EXAMPLE.COM")
        self.assertIsNotNone(result)
        self.assertEqual(result["gid"], "gid-alice")

    def test_resolve_by_gid(self):
        result = _resolve_group_reviewer_default_user(self.USERS, "gid-bob")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Bob Jones")

    def test_resolve_by_display_name(self):
        result = _resolve_group_reviewer_default_user(self.USERS, "alice smith")
        self.assertIsNotNone(result)
        self.assertEqual(result["gid"], "gid-alice")

    def test_no_match_returns_none(self):
        result = _resolve_group_reviewer_default_user(self.USERS, "nobody@example.com")
        self.assertIsNone(result)

    def test_empty_ref_returns_none(self):
        result = _resolve_group_reviewer_default_user(self.USERS, "")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 4. _handle_group_reviewer — strategy behaviour
# ---------------------------------------------------------------------------


ASANA_USERS = [
    {"gid": "user-gid-fallback", "name": "Fallback User", "email": "fallback@example.com"},
]


class TestHandleGroupReviewer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pr = _make_pr(pr_id=99)
        self.repo = _make_repo()
        self.reviewer = RealObjectBuilder.create_real_ado_group_reviewer(display_name="[TestProject]\\Reviewers")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _app(self, strategy="ignore", default_user=""):
        return _make_app(self.tmp, strategy=strategy, default_user=default_user)

    def test_ignore_strategy_creates_no_task(self):
        app = self._app(strategy="ignore")
        with patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create:
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_create.assert_not_called()

    def test_unassigned_task_strategy_creates_task(self):
        app = self._app(strategy="unassigned_task")
        with patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create:
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_create.assert_called_once()
            pr_item_arg = mock_create.call_args[0][2]
            self.assertEqual(pr_item_arg.reviewer_gid, "group:[TestProject]\\Reviewers")
            self.assertIsNone(pr_item_arg.assignee_gid)

    def test_default_user_strategy_creates_task_with_assignee(self):
        app = self._app(strategy="default_user", default_user="fallback@example.com")
        with patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create:
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_create.assert_called_once()
            pr_item_arg = mock_create.call_args[0][2]
            self.assertEqual(pr_item_arg.assignee_gid, "user-gid-fallback")

    def test_default_user_strategy_missing_user_skips(self):
        app = self._app(strategy="default_user", default_user="nobody@example.com")
        # Override fallback so the strategy is actually active for this edge case
        app.group_reviewer_strategy = "default_user"
        app.group_reviewer_default_user = "nobody@example.com"
        with patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create:
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_create.assert_not_called()

    def test_synthetic_gid_starts_with_group_prefix(self):
        app = self._app(strategy="unassigned_task")
        with patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create:
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_create.assert_called_once()
            pr_item_arg = mock_create.call_args[0][2]
            self.assertTrue(pr_item_arg.reviewer_gid.startswith("group:"))

    def test_existing_task_is_updated_not_recreated(self):
        """If a DB record already exists for the synthetic GID, we update instead of recreating."""
        app = self._app(strategy="unassigned_task")
        synthetic_gid = "group:[TestProject]\\Reviewers"
        pr_url = f"https://dev.azure.com/testorg/Project-repo-123/_git/test-repo/pullrequest/{self.pr.pull_request_id}"

        # Store with an old title so the handler detects a title change and calls update
        existing = PullRequestItem(
            ado_pr_id=self.pr.pull_request_id,
            ado_repository_id=self.repo.id,
            title="Old PR Title",
            status=self.pr.status,
            url=pr_url,
            reviewer_gid=synthetic_gid,
            reviewer_name="Group: [TestProject]\\Reviewers",
            asana_gid="existing-asana-gid",
        )
        existing.save(app)

        with (
            patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create,
            patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task") as mock_update,
        ):
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_create.assert_not_called()
            mock_update.assert_called_once()

    def test_existing_task_updated_when_status_changes_not_title(self):
        """Regression: status change alone must trigger an update even if title is unchanged."""
        app = self._app(strategy="unassigned_task")
        synthetic_gid = "group:[TestProject]\\Reviewers"
        pr_url = f"https://dev.azure.com/testorg/Project-repo-123/_git/test-repo/pullrequest/{self.pr.pull_request_id}"

        # Store with same title as self.pr but different status
        existing = PullRequestItem(
            ado_pr_id=self.pr.pull_request_id,
            ado_repository_id=self.repo.id,
            title=self.pr.title,
            status="completed",  # different from self.pr.status ("active")
            url=pr_url,
            reviewer_gid=synthetic_gid,
            reviewer_name="Group: [TestProject]\\Reviewers",
            asana_gid="existing-asana-gid",
        )
        existing.save(app)

        with (
            patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create,
            patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task") as mock_update,
        ):
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_create.assert_not_called()
            mock_update.assert_called_once()

    def test_individual_reviewer_is_not_a_group_reviewer(self):
        individual = RealObjectBuilder.create_real_ado_reviewer(display_name="Jane Doe", email="jane@example.com")
        self.assertFalse(is_group_reviewer(individual))

    def test_existing_task_with_no_asana_gid_recovered_via_name_search(self):
        """When existing_match.asana_gid is None and a task is found by name, it must be linked and updated."""
        app = self._app(strategy="unassigned_task")
        synthetic_gid = "group:[TestProject]\\Reviewers"
        pr_url = f"https://dev.azure.com/testorg/Project-repo-123/_git/test-repo/pullrequest/{self.pr.pull_request_id}"

        existing = PullRequestItem(
            ado_pr_id=self.pr.pull_request_id,
            ado_repository_id=self.repo.id,
            title="Old PR Title",
            status=self.pr.status,
            url=pr_url,
            reviewer_gid=synthetic_gid,
            reviewer_name="Group: [TestProject]\\Reviewers",
            asana_gid=None,  # task creation previously failed
        )
        existing.save(app)

        found_task = {"gid": "recovered-asana-gid", "modified_at": "2026-01-01T00:00:00Z"}
        with (
            patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create,
            patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task") as mock_update,
            patch("ado_asana_sync.sync.pull_request_sync.get_asana_task_by_name", return_value=found_task),
        ):
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_create.assert_not_called()
            mock_update.assert_called_once()
            pr_item_arg = mock_update.call_args[0][1]
            self.assertEqual(pr_item_arg.asana_gid, "recovered-asana-gid")

    def test_existing_task_with_no_asana_gid_recreated_when_not_found_by_name(self):
        """When existing_match.asana_gid is None and no task found by name, a new task must be created."""
        app = self._app(strategy="unassigned_task")
        synthetic_gid = "group:[TestProject]\\Reviewers"
        pr_url = f"https://dev.azure.com/testorg/Project-repo-123/_git/test-repo/pullrequest/{self.pr.pull_request_id}"

        existing = PullRequestItem(
            ado_pr_id=self.pr.pull_request_id,
            ado_repository_id=self.repo.id,
            title="Old PR Title",
            status=self.pr.status,
            url=pr_url,
            reviewer_gid=synthetic_gid,
            reviewer_name="Group: [TestProject]\\Reviewers",
            asana_gid=None,
        )
        existing.save(app)

        with (
            patch("ado_asana_sync.sync.pull_request_sync.create_asana_pr_task") as mock_create,
            patch("ado_asana_sync.sync.pull_request_sync.update_asana_pr_task") as mock_update,
            patch("ado_asana_sync.sync.pull_request_sync.get_asana_task_by_name", return_value=None),
        ):
            _handle_group_reviewer(app, self.pr, self.repo, self.reviewer, ASANA_USERS, [], "proj-gid")
            mock_update.assert_not_called()
            mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# 6. current_reviewer_gids: unresolvable default_user is excluded
# ---------------------------------------------------------------------------


class TestCurrentReviewerGidsDefaultUserFallback(unittest.TestCase):
    """Regression: unresolvable default_user must not add a synthetic GID to current_reviewer_gids.

    If the GID were added, handle_removed_reviewers would treat the group as still
    active and never close stale tasks for it.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pr = _make_pr(pr_id=55)
        self.repo = _make_repo()
        self.group_reviewer = RealObjectBuilder.create_real_ado_group_reviewer(display_name="[Proj]\\Team")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _app(self, strategy="ignore", default_user=""):
        return _make_app(self.tmp, strategy=strategy, default_user=default_user)

    @patch("ado_asana_sync.sync.pull_request_sync.handle_removed_reviewers")
    @patch("ado_asana_sync.sync.pull_request_sync._handle_group_reviewer")
    def test_unresolvable_default_user_excluded_from_current_gids(self, mock_handle_group, mock_handle_removed):
        """When default_user cannot be resolved, the group GID must NOT appear in current_reviewer_gids."""
        from ado_asana_sync.sync.pull_request_sync import process_pull_request

        app = self._app(strategy="default_user", default_user="nobody@example.com")
        app.group_reviewer_strategy = "default_user"
        app.group_reviewer_default_user = "nobody@example.com"
        app.ado_git_client = MagicMock()
        app.ado_git_client.get_pull_request_reviewers.return_value = [self.group_reviewer]

        process_pull_request(app, self.pr, self.repo, [], [], "proj-gid")

        mock_handle_removed.assert_called_once()
        _, _, current_gids, _ = mock_handle_removed.call_args[0]
        self.assertNotIn("group:[Proj]\\Team", current_gids)

    @patch("ado_asana_sync.sync.pull_request_sync.handle_removed_reviewers")
    @patch("ado_asana_sync.sync.pull_request_sync._handle_group_reviewer")
    def test_resolvable_default_user_included_in_current_gids(self, mock_handle_group, mock_handle_removed):
        """When default_user resolves successfully, the group GID must appear in current_reviewer_gids."""
        from ado_asana_sync.sync.pull_request_sync import process_pull_request

        asana_users = [{"gid": "gid-fallback", "name": "Fallback User", "email": "fallback@example.com"}]
        app = self._app(strategy="default_user", default_user="fallback@example.com")
        app.group_reviewer_strategy = "default_user"
        app.group_reviewer_default_user = "fallback@example.com"
        app.ado_git_client = MagicMock()
        app.ado_git_client.get_pull_request_reviewers.return_value = [self.group_reviewer]

        process_pull_request(app, self.pr, self.repo, asana_users, [], "proj-gid")

        mock_handle_removed.assert_called_once()
        _, _, current_gids, _ = mock_handle_removed.call_args[0]
        self.assertIn("group:[Proj]\\Team", current_gids)


# ---------------------------------------------------------------------------
# 5. update_asana_pr_task assignee clearing for group tasks
# ---------------------------------------------------------------------------


class TestUpdateAsanaPrTaskGroupAssignee(unittest.TestCase):
    """Regression tests for explicit null assignee on group reviewer tasks."""

    def _make_mock_app(self):
        from unittest.mock import MagicMock

        import asana

        mock_app = MagicMock()
        mock_app.asana_client = MagicMock(spec=asana.ApiClient)
        return mock_app

    @patch("ado_asana_sync.sync.pull_request_sync.add_tag_to_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync._get_cached_custom_field")
    @patch("asana.TasksApi")
    def test_group_task_with_no_assignee_sends_null(self, mock_tasks_api_class, mock_get_field, mock_add_tag):
        """When assignee_gid is None on a group task, the update must send assignee=None to clear it."""
        from unittest.mock import Mock

        from ado_asana_sync.sync.pull_request_sync import update_asana_pr_task

        mock_tasks_api = Mock()
        mock_tasks_api_class.return_value = mock_tasks_api
        mock_tasks_api.update_task.return_value = {"modified_at": "2026-01-01T00:00:00Z"}
        mock_get_field.return_value = None

        mock_pr_item = Mock()
        mock_pr_item.asana_gid = "task-gid-group"
        mock_pr_item.asana_title = "PR 1: Group review"
        mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 1</a>"
        mock_pr_item.status = "active"
        mock_pr_item.review_status = "noVote"
        mock_pr_item.url = "http://test.com/pr/1"
        mock_pr_item.reviewer_gid = "group:[Proj]\\Reviewers"
        mock_pr_item.assignee_gid = None  # unassigned_task strategy

        update_asana_pr_task(self._make_mock_app(), mock_pr_item, "tag-gid", {"gid": "proj-gid"})

        update_call_args = mock_tasks_api.update_task.call_args[0]
        self.assertIn("assignee", update_call_args[0]["data"])
        self.assertIsNone(update_call_args[0]["data"]["assignee"])

    @patch("ado_asana_sync.sync.pull_request_sync.add_tag_to_pr_task")
    @patch("ado_asana_sync.sync.pull_request_sync._get_cached_custom_field")
    @patch("asana.TasksApi")
    def test_group_task_with_assignee_gid_sends_it(self, mock_tasks_api_class, mock_get_field, mock_add_tag):
        """When assignee_gid is set on a group task, it must be forwarded in the update."""
        from unittest.mock import Mock

        from ado_asana_sync.sync.pull_request_sync import update_asana_pr_task

        mock_tasks_api = Mock()
        mock_tasks_api_class.return_value = mock_tasks_api
        mock_tasks_api.update_task.return_value = {"modified_at": "2026-01-01T00:00:00Z"}
        mock_get_field.return_value = None

        mock_pr_item = Mock()
        mock_pr_item.asana_gid = "task-gid-group"
        mock_pr_item.asana_title = "PR 2: Group review"
        mock_pr_item.asana_notes_link = "<a href='http://test.com'>PR 2</a>"
        mock_pr_item.status = "active"
        mock_pr_item.review_status = "noVote"
        mock_pr_item.url = "http://test.com/pr/2"
        mock_pr_item.reviewer_gid = "group:[Proj]\\Reviewers"
        mock_pr_item.assignee_gid = "user-gid-fallback"  # default_user strategy

        update_asana_pr_task(self._make_mock_app(), mock_pr_item, "tag-gid", {"gid": "proj-gid"})

        update_call_args = mock_tasks_api.update_task.call_args[0]
        self.assertEqual(update_call_args[0]["data"]["assignee"], "user-gid-fallback")

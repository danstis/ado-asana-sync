"""Unit tests for delta sync: determine_sync_mode and get_ado_work_items_modified_since."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from ado_asana_sync.sync.sync import determine_sync_mode, get_ado_work_items_modified_since


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class TestDetermineSyncMode(unittest.TestCase):
    """Unit tests for determine_sync_mode() covering all 4 decision branches."""

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def test_force_full_overrides_existing_checkpoint(self):
        """Branch 1: force_full=True always returns full mode."""
        checkpoint = {
            "last_sync_at": _iso(self._now() - timedelta(minutes=10)),
            "last_full_sync_at": _iso(self._now() - timedelta(hours=1)),
        }
        mode, since = determine_sync_mode(checkpoint, force_full=True, overlap_minutes=5)
        self.assertEqual(mode, "full")
        self.assertIsNone(since)

    def test_null_checkpoint_triggers_full_scan(self):
        """Branch 2: last_sync_at=None triggers full scan."""
        checkpoint = {"last_sync_at": None, "last_full_sync_at": None}
        mode, since = determine_sync_mode(checkpoint, force_full=False, overlap_minutes=5)
        self.assertEqual(mode, "full")
        self.assertIsNone(since)

    def test_daily_full_due_when_last_full_is_null(self):
        """Branch 3a: last_full_sync_at=None triggers full scan."""
        checkpoint = {
            "last_sync_at": _iso(self._now() - timedelta(minutes=10)),
            "last_full_sync_at": None,
        }
        mode, since = determine_sync_mode(checkpoint, force_full=False, overlap_minutes=5)
        self.assertEqual(mode, "full")
        self.assertIsNone(since)

    def test_daily_full_due_when_last_full_over_24h_ago(self):
        """Branch 3b: last_full_sync_at older than 24h triggers full scan."""
        checkpoint = {
            "last_sync_at": _iso(self._now() - timedelta(minutes=10)),
            "last_full_sync_at": _iso(self._now() - timedelta(hours=25)),
        }
        mode, since = determine_sync_mode(checkpoint, force_full=False, overlap_minutes=5)
        self.assertEqual(mode, "full")
        self.assertIsNone(since)

    def test_incremental_mode_with_overlap(self):
        """Branch 4: recent checkpoint yields incremental mode with correct fetch boundary."""
        last_sync = self._now() - timedelta(minutes=30)
        checkpoint = {
            "last_sync_at": _iso(last_sync),
            "last_full_sync_at": _iso(self._now() - timedelta(hours=1)),
        }
        mode, since = determine_sync_mode(checkpoint, force_full=False, overlap_minutes=5)
        self.assertEqual(mode, "incremental")
        self.assertIsNotNone(since)
        # fetch_since should be last_sync_at - 5 minutes
        expected_since = last_sync - timedelta(minutes=5)
        # Allow 1 second tolerance
        self.assertAlmostEqual(since.timestamp(), expected_since.timestamp(), delta=1.0)


class TestGetAdoWorkItemsModifiedSince(unittest.TestCase):
    """Unit tests for get_ado_work_items_modified_since() (FR-002 WIQL helper)."""

    def _make_app(self, work_items):
        """Return a mock App whose ado_wit_client.query_by_wiql returns work_items."""
        app = MagicMock()
        result = MagicMock()
        result.work_items = work_items
        app.ado_wit_client.query_by_wiql.return_value = result
        return app

    def test_returns_list_of_ids(self):
        """Normal case: WIQL returns work item references; function returns their IDs."""
        refs = [MagicMock(id=101), MagicMock(id=202), MagicMock(id=303)]
        app = self._make_app(refs)
        since = datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc)

        ids = get_ado_work_items_modified_since(app, "MyProject", since)

        self.assertEqual(ids, [101, 202, 303])
        app.ado_wit_client.query_by_wiql.assert_called_once()
        call_args = app.ado_wit_client.query_by_wiql.call_args
        # Verify the query contains the project name and the formatted date
        wiql_obj = call_args[0][0]
        self.assertIn("MyProject", wiql_obj.query)
        self.assertIn("2026-03-18T10:00:00Z", wiql_obj.query)
        # Verify top=20000 is passed
        self.assertEqual(call_args[1].get("top") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["top"], 20000)

    def test_returns_empty_list_when_no_changes(self):
        """Zero results: WIQL returns empty list; function returns empty list."""
        app = self._make_app([])
        since = datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc)

        ids = get_ado_work_items_modified_since(app, "MyProject", since)

        self.assertEqual(ids, [])

    def test_handles_none_work_items(self):
        """WIQL result has work_items=None; function returns empty list (no crash)."""
        app = self._make_app(None)
        since = datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc)

        ids = get_ado_work_items_modified_since(app, "MyProject", since)

        self.assertEqual(ids, [])

    def test_raises_when_wit_client_is_none(self):
        """Raises ValueError when ado_wit_client is not initialised."""
        app = MagicMock()
        app.ado_wit_client = None
        since = datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc)

        with self.assertRaises(ValueError):
            get_ado_work_items_modified_since(app, "MyProject", since)

    def test_date_formatted_without_microseconds(self):
        """Since datetime with microseconds is formatted as YYYY-MM-DDTHH:MM:SSZ."""
        app = self._make_app([])
        since = datetime(2026, 3, 18, 10, 5, 30, 123456, tzinfo=timezone.utc)

        get_ado_work_items_modified_since(app, "Proj", since)

        wiql_obj = app.ado_wit_client.query_by_wiql.call_args[0][0]
        # Microseconds must not appear; Z suffix required
        self.assertIn("2026-03-18T10:05:30Z", wiql_obj.query)
        self.assertNotIn("123456", wiql_obj.query)

    def test_project_name_apostrophe_is_escaped(self):
        """Single quotes in project_name are doubled to prevent WIQL parse errors."""
        app = self._make_app([])
        since = datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc)

        get_ado_work_items_modified_since(app, "O'Brien Project", since)

        wiql_obj = app.ado_wit_client.query_by_wiql.call_args[0][0]
        self.assertIn("O''Brien Project", wiql_obj.query)
        # Unescaped apostrophe must not appear in the project name position
        self.assertNotIn("'O'Brien", wiql_obj.query)

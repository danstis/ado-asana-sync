"""Unit tests for delta sync determine_sync_mode function."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ado_asana_sync.sync.sync import determine_sync_mode


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

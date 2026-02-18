"""Tests for scripts/validate_asana_users.py helper behavior."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from asana.rest import ApiException

from scripts.validate_asana_users import _fetch_recent_user_removal_events, _is_truthy


class TestValidateAsanaUsersHelpers(unittest.TestCase):
    def test_is_truthy_parses_common_values(self) -> None:
        self.assertTrue(_is_truthy("1"))
        self.assertTrue(_is_truthy(" true "))
        self.assertTrue(_is_truthy("YES"))
        self.assertTrue(_is_truthy("on"))
        self.assertFalse(_is_truthy("0"))
        self.assertFalse(_is_truthy("false"))

    @patch("scripts.validate_asana_users.asana.AuditLogAPIApi")
    def test_fetch_recent_user_removal_events_filters_candidates(self, mock_audit_api: MagicMock) -> None:
        mock_api_instance = MagicMock()
        mock_audit_api.return_value = mock_api_instance
        mock_api_instance.get_audit_log_events.return_value = [
            {
                "event_type": "user_deprovisioned",
                "resource_type": "user",
                "created_at": "2026-01-01T00:00:00.000Z",
            },
            {
                "event_type": "workspace_setting_changed",
                "resource_type": "workspace",
                "created_at": "2026-01-01T00:00:00.000Z",
            },
        ]

        result = _fetch_recent_user_removal_events(MagicMock(), "123", 90)

        self.assertIsNotNone(result)
        self.assertEqual(len(result or []), 1)
        self.assertEqual((result or [])[0]["event_type"], "user_deprovisioned")

    @patch("scripts.validate_asana_users.asana.AuditLogAPIApi")
    def test_fetch_recent_user_removal_events_returns_none_on_api_exception(self, mock_audit_api: MagicMock) -> None:
        mock_api_instance = MagicMock()
        mock_audit_api.return_value = mock_api_instance
        mock_api_instance.get_audit_log_events.side_effect = ApiException("forbidden")

        result = _fetch_recent_user_removal_events(MagicMock(), "123", 90)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

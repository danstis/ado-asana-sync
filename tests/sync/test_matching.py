"""Tests for the tiered ADO/Asana user matching ladder."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ado_asana_sync.sync.ado_parser import ADOAssignedUser
from ado_asana_sync.sync.matching import matching_user


class TestTieredMatching(unittest.TestCase):
    """Exercise the real matching_user ladder (never mocked)."""

    def test_local_part_matches_across_domains(self):
        users = [{"gid": "1", "email": "john.doe@maindomain.com", "name": "John Doe"}]
        ado_user = ADOAssignedUser("Johnathan Doe", "john.doe@seconddomain.com")

        result = matching_user(users, ado_user)

        self.assertIsNotNone(result)
        self.assertEqual(result["gid"], "1")

    def test_exact_email_wins_over_local_part(self):
        users = [
            {"gid": "1", "email": "john.doe@other.com", "name": "J D"},
            {"gid": "2", "email": "john.doe@maindomain.com", "name": "John Doe"},
        ]
        ado_user = ADOAssignedUser("John Doe", "john.doe@maindomain.com")

        result = matching_user(users, ado_user)

        self.assertEqual(result["gid"], "2")

    def test_local_part_wins_over_name(self):
        user_a = {"gid": "1", "email": "john.doe@other.com", "name": "Someone Else"}
        user_b = {"gid": "2", "email": "nobody@x.com", "name": "John Doe"}
        ado_user = ADOAssignedUser("John Doe", "john.doe@seconddomain.com")

        result = matching_user([user_b, user_a], ado_user)

        self.assertEqual(result["gid"], "1")

    def test_name_match_is_whitespace_trimmed(self):
        users = [{"gid": "1", "email": "someone@asana.com", "name": "  John   Doe "}]
        ado_user = ADOAssignedUser("John Doe", "j.doe@ado.com")

        result = matching_user(users, ado_user)

        self.assertEqual(result["gid"], "1")

    def test_name_match_handles_last_comma_first(self):
        users = [{"gid": "1", "email": "someone@asana.com", "name": "Doe, John"}]
        ado_user = ADOAssignedUser("John Doe", "j.doe@ado.com")

        result = matching_user(users, ado_user)

        self.assertEqual(result["gid"], "1")

    @patch("ado_asana_sync.sync.matching._LOGGER")
    def test_local_part_collision_returns_none(self, mock_logger):
        users = [
            {"gid": "1", "email": "john.doe@a.com", "name": "John Doe"},
            {"gid": "2", "email": "john.doe@b.com", "name": "Johnny Doe"},
        ]
        ado_user = ADOAssignedUser("Different Name", "john.doe@c.com")

        result = matching_user(users, ado_user)

        self.assertIsNone(result)
        mock_logger.warning.assert_called()

    def test_name_collision_returns_none(self):
        users = [
            {"gid": "1", "email": "a@a.com", "name": "John Doe"},
            {"gid": "2", "email": "b@b.com", "name": "John Doe"},
        ]
        ado_user = ADOAssignedUser("John Doe", "john.doe@ado.com")

        result = matching_user(users, ado_user)

        self.assertIsNone(result)

    def test_empty_ado_email_does_not_match_on_local_part(self):
        users = [{"gid": "1", "email": "user1@example.com", "name": "User One"}]
        ado_user = ADOAssignedUser("", "")

        result = matching_user(users, ado_user)

        self.assertIsNone(result)

    def test_non_email_unique_name_falls_through_to_name(self):
        users = [{"gid": "1", "email": "j.doe@asana.com", "name": "John Doe"}]
        ado_user = ADOAssignedUser("John Doe", "CONTOSO\\jdoe")

        result = matching_user(users, ado_user)

        self.assertEqual(result["gid"], "1")

    def test_strategy_exact_disables_local_part(self):
        users = [{"gid": "1", "email": "john.doe@maindomain.com", "name": "John Doe"}]
        ado_user = ADOAssignedUser("Johnathan Doe", "john.doe@seconddomain.com")

        result = matching_user(users, ado_user, strategy="exact")

        self.assertIsNone(result)

    def test_strategy_prefix_disables_name_rule(self):
        users = [{"gid": "1", "email": "someone@asana.com", "name": "  John   Doe "}]
        ado_user = ADOAssignedUser("John Doe", "j.doe@ado.com")

        result = matching_user(users, ado_user, strategy="prefix")

        self.assertIsNone(result)

    @patch("ado_asana_sync.sync.matching._LOGGER")
    def test_matched_rule_is_logged(self, mock_logger):
        users = [{"gid": "1", "email": "john.doe@maindomain.com", "name": "John Doe"}]
        ado_user = ADOAssignedUser("Johnathan Doe", "john.doe@seconddomain.com")

        matching_user(users, ado_user)

        mock_logger.info.assert_called()
        logged_args = mock_logger.info.call_args[0]
        self.assertIn("email_local_part", logged_args)

    @patch("ado_asana_sync.sync.matching._LOGGER")
    def test_invalid_strategy_falls_back_to_name(self, mock_logger):
        users = [{"gid": "1", "email": "john.doe@maindomain.com", "name": "John Doe"}]
        ado_user = ADOAssignedUser("Johnathan Doe", "john.doe@seconddomain.com")

        result = matching_user(users, ado_user, strategy="bogus")

        self.assertEqual(result["gid"], "1")
        mock_logger.warning.assert_called()

    def test_exact_email_match_is_not_logged_as_fuzzy(self):
        users = [{"gid": "1", "email": "john.doe@maindomain.com", "name": "John Doe"}]
        ado_user = ADOAssignedUser("John Doe", "JOHN.DOE@maindomain.com")

        with patch("ado_asana_sync.sync.matching._LOGGER") as mock_logger:
            result = matching_user(users, ado_user)

        self.assertEqual(result["gid"], "1")
        mock_logger.info.assert_not_called()


if __name__ == "__main__":
    unittest.main()

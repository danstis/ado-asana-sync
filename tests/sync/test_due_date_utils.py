import unittest
from unittest.mock import MagicMock, patch


class TestDueDateUtilities(unittest.TestCase):
    """Unit tests for due date conversion and utility functions."""

    def test_extract_due_date_from_ado_with_valid_datetime(self):
        """
        Unit Test: extract_due_date_from_ado converts ADO datetime to YYYY-MM-DD format.
        """
        from ado_asana_sync.sync.sync import extract_due_date_from_ado

        # Arrange: Mock ADO work item with due date
        ado_work_item = MagicMock()
        ado_work_item.fields = {"Microsoft.VSTS.Scheduling.DueDate": "2025-12-31T23:59:59.000Z"}

        # Act: Extract due date
        result = extract_due_date_from_ado(ado_work_item)

        # Assert: Should return date portion only in YYYY-MM-DD format
        self.assertEqual(result, "2025-12-31")

    def test_extract_due_date_from_ado_with_different_datetime_formats(self):
        """
        Unit Test: extract_due_date_from_ado handles various ADO datetime formats.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.sync import extract_due_date_from_ado

        test_cases = [
            ("2025-12-31T23:59:59.000Z", "2025-12-31"),  # ISO with microseconds
            ("2025-01-01T00:00:00Z", "2025-01-01"),  # ISO without microseconds
            ("2025-06-15T12:30:45.123Z", "2025-06-15"),  # Mid-year date
            ("2024-02-29T10:20:30.456Z", "2024-02-29"),  # Leap year
        ]

        for ado_datetime, expected_date in test_cases:
            with self.subTest(ado_datetime=ado_datetime):
                # Arrange
                ado_work_item = MagicMock()
                ado_work_item.fields = {"Microsoft.VSTS.Scheduling.DueDate": ado_datetime}

                # Act
                result = extract_due_date_from_ado(ado_work_item)

                # Assert
                self.assertEqual(result, expected_date)

    def test_extract_due_date_from_ado_with_missing_field(self):
        """
        Unit Test: extract_due_date_from_ado returns None when due date field is missing.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.sync import extract_due_date_from_ado

        # Arrange: Mock ADO work item without due date field
        ado_work_item = MagicMock()
        ado_work_item.fields = {
            "System.Title": "Test Task",
            "System.State": "New",
            # Note: No Microsoft.VSTS.Scheduling.DueDate field
        }

        # Act: Extract due date
        result = extract_due_date_from_ado(ado_work_item)

        # Assert: Should return None for missing field
        self.assertIsNone(result)

    def test_extract_due_date_from_ado_with_empty_field(self):
        """
        Unit Test: extract_due_date_from_ado returns None when due date field is empty.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.sync import extract_due_date_from_ado

        test_cases = [None, "", " ", "\t\n"]

        for empty_value in test_cases:
            with self.subTest(empty_value=repr(empty_value)):
                # Arrange
                ado_work_item = MagicMock()
                ado_work_item.fields = {"Microsoft.VSTS.Scheduling.DueDate": empty_value}

                # Act
                result = extract_due_date_from_ado(ado_work_item)

                # Assert: Should return None for empty/null values
                self.assertIsNone(result)

    def test_extract_due_date_from_ado_with_invalid_format(self):
        """
        Unit Test: extract_due_date_from_ado returns None and logs warning for invalid formats.

        This test will fail initially because error handling doesn't exist.
        """
        from ado_asana_sync.sync.sync import extract_due_date_from_ado

        invalid_formats = [
            "invalid-date",
            "2025-13-01T10:00:00Z",  # Invalid month
            "2025-12-32T10:00:00Z",  # Invalid day
            "not-a-date-at-all",
            "2025/12/31",  # Wrong separator
            "Dec 31, 2025",  # Different format
        ]

        with patch("ado_asana_sync.sync.sync._LOGGER") as mock_logger:
            for invalid_date in invalid_formats:
                with self.subTest(invalid_date=invalid_date):
                    # Arrange
                    ado_work_item = MagicMock()
                    ado_work_item.fields = {"Microsoft.VSTS.Scheduling.DueDate": invalid_date}

                    # Act
                    result = extract_due_date_from_ado(ado_work_item)

                    # Assert: Should return None for invalid formats
                    self.assertIsNone(result)

                    # Assert: Should log warning
                    mock_logger.warning.assert_called()

    def test_convert_ado_date_to_asana_format_valid_iso_strings(self):
        """
        Unit Test: convert_ado_date_to_asana_format converts ISO datetime to YYYY-MM-DD.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.utils import convert_ado_date_to_asana_format

        test_cases = [
            ("2025-12-31T23:59:59.000Z", "2025-12-31"),
            ("2025-01-01T00:00:00Z", "2025-01-01"),
            ("2025-06-15T12:30:45.123Z", "2025-06-15"),
            ("2024-02-29T10:20:30Z", "2024-02-29"),  # Leap year
        ]

        for iso_string, expected in test_cases:
            with self.subTest(iso_string=iso_string):
                # Act
                result = convert_ado_date_to_asana_format(iso_string)

                # Assert
                self.assertEqual(result, expected)

    def test_convert_ado_date_to_asana_format_with_invalid_input(self):
        """
        Unit Test: convert_ado_date_to_asana_format handles invalid input gracefully.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.utils import convert_ado_date_to_asana_format

        invalid_inputs = [
            None,
            "",
            "invalid-date",
            "2025-13-01T10:00:00Z",  # Invalid month
            "not-a-date",
        ]

        for invalid_input in invalid_inputs:
            with self.subTest(invalid_input=repr(invalid_input)):
                # Act & Assert: Should raise ValueError or return None
                with self.assertRaises((ValueError, TypeError)):
                    convert_ado_date_to_asana_format(invalid_input)

    def test_validate_due_date_format_valid_dates(self):
        """
        Unit Test: validate_due_date accepts valid YYYY-MM-DD format and None.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.utils import validate_due_date

        valid_dates = [
            "2025-12-31",
            "2025-01-01",
            "2024-02-29",  # Leap year
            "2025-06-15",
            None,  # None should be valid
        ]

        for valid_date in valid_dates:
            with self.subTest(due_date=valid_date):
                # Act
                result = validate_due_date(valid_date)

                # Assert
                self.assertTrue(result)

    def test_validate_due_date_format_invalid_dates(self):
        """
        Unit Test: validate_due_date rejects invalid date formats.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.utils import validate_due_date

        invalid_dates = [
            "2025-13-01",  # Invalid month
            "2025-12-32",  # Invalid day
            "2025/12/31",  # Wrong separator
            "Dec 31, 2025",  # Different format
            "2025-12-31T10:00:00Z",  # With time (should be date only)
            "invalid-date",
            "",  # Empty string
            "2025-2-29",  # Non-leap year Feb 29
        ]

        for invalid_date in invalid_dates:
            with self.subTest(due_date=invalid_date):
                # Act
                result = validate_due_date(invalid_date)

                # Assert
                self.assertFalse(result)

    def test_ado_due_date_constant_exists(self):
        """
        Unit Test: ADO_DUE_DATE constant is defined with correct value.

        This test will fail initially because the constant doesn't exist.
        """
        from ado_asana_sync.sync.sync import ADO_DUE_DATE

        # Assert: Constant should be defined with Microsoft field name
        self.assertEqual(ADO_DUE_DATE, "Microsoft.VSTS.Scheduling.DueDate")

    def test_create_asana_task_body_includes_due_on_for_initial_sync(self):
        """
        Unit Test: create_asana_task_body includes due_on field for initial sync.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.sync import create_asana_task_body
        from ado_asana_sync.sync.task_item import TaskItem

        # Arrange: TaskItem with due_date
        task = TaskItem(
            ado_id=123, title="Test Task", item_type="Task", ado_rev=1, url="http://test.com", due_date="2025-12-31"
        )

        # Act: Create task body for initial sync
        body = create_asana_task_body(task, is_initial_sync=True)

        # Assert: Should include due_on field
        self.assertIn("due_on", body["data"])
        self.assertEqual(body["data"]["due_on"], "2025-12-31")

    def test_create_asana_task_body_excludes_due_on_for_subsequent_sync(self):
        """
        Unit Test: create_asana_task_body excludes due_on field for subsequent sync.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.sync import create_asana_task_body
        from ado_asana_sync.sync.task_item import TaskItem

        # Arrange: TaskItem with due_date
        task = TaskItem(
            ado_id=123, title="Test Task", item_type="Task", ado_rev=1, url="http://test.com", due_date="2025-12-31"
        )

        # Act: Create task body for subsequent sync
        body = create_asana_task_body(task, is_initial_sync=False)

        # Assert: Should NOT include due_on field
        self.assertNotIn("due_on", body["data"])

    def test_create_asana_task_body_handles_none_due_date(self):
        """
        Unit Test: create_asana_task_body handles None due_date gracefully.

        This test will fail initially because the function doesn't exist.
        """
        from ado_asana_sync.sync.sync import create_asana_task_body
        from ado_asana_sync.sync.task_item import TaskItem

        # Arrange: TaskItem without due_date
        task = TaskItem(ado_id=123, title="Test Task", item_type="Task", ado_rev=1, url="http://test.com", due_date=None)

        # Act: Create task body for initial sync
        body = create_asana_task_body(task, is_initial_sync=True)

        # Assert: Should not include due_on field when due_date is None
        self.assertNotIn("due_on", body["data"])


if __name__ == "__main__":
    unittest.main()

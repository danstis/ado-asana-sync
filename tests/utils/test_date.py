import unittest
from datetime import datetime, timezone

import pytz

from ado_asana_sync.utils.date import iso8601_utc


class TestIso8601Utc(unittest.TestCase):
    # Tests that the function converts a datetime object to a string representation
    # in ISO 8601 format with UTC timezone correctly.
    def test_convert_to_iso8601_utc_happy_path(self):
        dt = datetime(2022, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = iso8601_utc(dt)
        self.assertEqual(result, "2022-01-01T12:00:00+00:00")

    def test_utc_conversion(self):
        timezones = pytz.all_timezones
        for tz in timezones:
            local_dt = datetime(2022, 1, 1, 12, 0, 0, tzinfo=pytz.timezone(tz))
            utc_dt_str = iso8601_utc(local_dt)

            # The time in UTC
            utc_dt_actual = local_dt.astimezone(timezone.utc)

            # Assert that the result is correctly in UTC
            self.assertEqual(utc_dt_str, utc_dt_actual.isoformat())

    # Tests that the function converts a datetime object representing a leap year date
    # to a string representation in ISO 8601 format with UTC timezone.
    def test_convert_leap_year_datetime(self):
        dt = datetime(2024, 2, 29, 12, 0, 0, tzinfo=timezone.utc)
        result = iso8601_utc(dt)
        self.assertEqual(result, "2024-02-29T12:00:00+00:00")

    # Tests that the function assumes a datetime object without a timezone is in UTC.
    def test_convert_naive_datetime(self):
        dt = datetime(2022, 1, 1, 12, 0, 0)
        result = iso8601_utc(dt)
        self.assertEqual(result, "2022-01-01T12:00:00+00:00")

    # Tests that the function raises a AttributeError if the argument is not a datetime object.
    def test_raise_type_error(self):
        with self.assertRaises(AttributeError):
            iso8601_utc("2022-01-01T12:00:00+00:00")

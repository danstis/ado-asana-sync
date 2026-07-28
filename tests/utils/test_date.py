import os
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo, available_timezones

from ado_asana_sync.utils.date import get_ado_timezone, iso8601_utc


class TestIso8601Utc(unittest.TestCase):
    # Tests that the function converts a datetime object to a string representation
    # in ISO 8601 format with UTC timezone correctly.
    def test_convert_to_iso8601_utc_happy_path(self):
        dt = datetime(2022, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = iso8601_utc(dt)
        self.assertEqual(result, "2022-01-01T12:00:00+00:00")

    def test_utc_conversion(self):
        timezones = available_timezones()
        for tz in timezones:
            local_dt = datetime(2022, 1, 1, 12, 0, 0, tzinfo=ZoneInfo(tz))
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


class TestGetAdoTimezone(unittest.TestCase):
    """Unit tests for get_ado_timezone: resolves ADO_TIMEZONE, never the host tz."""

    def test_defaults_to_utc_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIs(get_ado_timezone(), timezone.utc)

    def test_returns_zoneinfo_for_valid_iana_name(self):
        with patch.dict(os.environ, {"ADO_TIMEZONE": "Pacific/Auckland"}, clear=True):
            self.assertEqual(get_ado_timezone(), ZoneInfo("Pacific/Auckland"))

    def test_blank_value_falls_back_to_utc(self):
        with patch.dict(os.environ, {"ADO_TIMEZONE": "   "}, clear=True):
            self.assertIs(get_ado_timezone(), timezone.utc)

    def test_invalid_name_warns_and_falls_back_to_utc(self):
        with patch.dict(os.environ, {"ADO_TIMEZONE": "Mars/Olympus"}, clear=True):
            with self.assertLogs("ado_asana_sync.utils.date", level="WARNING"):
                result = get_ado_timezone()
            self.assertIs(result, timezone.utc)

    @unittest.skipIf(not hasattr(time, "tzset"), "POSIX only")
    def test_never_uses_host_local_timezone(self):
        original_tz = os.environ.get("TZ")
        try:
            os.environ["TZ"] = "Pacific/Auckland"
            time.tzset()
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ADO_TIMEZONE", None)
                self.assertIs(get_ado_timezone(), timezone.utc)
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

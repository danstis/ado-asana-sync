import logging
import os
import unittest
from unittest.mock import patch

from opentelemetry import trace

from ado_asana_sync.utils.logging_tracing import (
    SAMPLING_RATES,
    TELEMETRY_LOGGER_NAMES,
    TelemetrySamplingFilter,
    _get_sampling_rate,
    configure_telemetry_loggers,
    get_telemetry_filter,
    setup_logging_and_tracing,
)


class TestLoggingTracing(unittest.TestCase):
    def test_setup_logging_and_tracing(self):
        logger, tracer = setup_logging_and_tracing(__name__)
        self.assertIsInstance(logger, logging.Logger)
        self.assertIsInstance(tracer, trace.Tracer)

    def test_setup_logging_and_tracing_configures_telemetry_loggers(self):
        """Verify that telemetry loggers are configured after setup."""
        setup_logging_and_tracing(__name__)

        for logger_name in TELEMETRY_LOGGER_NAMES:
            logger = logging.getLogger(logger_name)
            # Check that sampling filter is applied
            filter_types = [type(f).__name__ for f in logger.filters]
            self.assertIn("TelemetrySamplingFilter", filter_types)


class TestGetSamplingRate(unittest.TestCase):
    def test_returns_default_when_env_not_set(self):
        """Returns default value when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            rate = _get_sampling_rate("NONEXISTENT_VAR", 0.5)
            self.assertEqual(rate, 0.5)

    def test_returns_env_value_when_set(self):
        """Returns environment variable value when set."""
        with patch.dict(os.environ, {"TEST_SAMPLE_RATE": "0.25"}):
            rate = _get_sampling_rate("TEST_SAMPLE_RATE", 0.5)
            self.assertEqual(rate, 0.25)

    def test_clamps_to_max_1(self):
        """Clamps values greater than 1.0 to 1.0."""
        with patch.dict(os.environ, {"TEST_SAMPLE_RATE": "1.5"}):
            rate = _get_sampling_rate("TEST_SAMPLE_RATE", 0.5)
            self.assertEqual(rate, 1.0)

    def test_clamps_to_min_0(self):
        """Clamps negative values to 0.0."""
        with patch.dict(os.environ, {"TEST_SAMPLE_RATE": "-0.5"}):
            rate = _get_sampling_rate("TEST_SAMPLE_RATE", 0.5)
            self.assertEqual(rate, 0.0)

    def test_returns_default_on_invalid_value(self):
        """Returns default value when environment variable is invalid."""
        with patch.dict(os.environ, {"TEST_SAMPLE_RATE": "not_a_number"}):
            rate = _get_sampling_rate("TEST_SAMPLE_RATE", 0.5)
            self.assertEqual(rate, 0.5)


class TestTelemetrySamplingFilter(unittest.TestCase):
    def test_always_passes_warning_at_100_percent(self):
        """WARNING logs always pass with default 100% sampling."""
        sampling_filter = TelemetrySamplingFilter(sampling_rates={logging.WARNING: 1.0})
        sampling_filter.set_random_seed(42)

        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0, msg="test", args=(), exc_info=None
        )

        # Should always pass
        for _ in range(100):
            self.assertTrue(sampling_filter.filter(record))

    def test_always_passes_error_at_100_percent(self):
        """ERROR logs always pass with default 100% sampling."""
        sampling_filter = TelemetrySamplingFilter(sampling_rates={logging.ERROR: 1.0})
        sampling_filter.set_random_seed(42)

        record = logging.LogRecord(name="test", level=logging.ERROR, pathname="", lineno=0, msg="test", args=(), exc_info=None)

        # Should always pass
        for _ in range(100):
            self.assertTrue(sampling_filter.filter(record))

    def test_always_passes_critical_at_100_percent(self):
        """CRITICAL logs always pass with default 100% sampling."""
        sampling_filter = TelemetrySamplingFilter(sampling_rates={logging.CRITICAL: 1.0})
        sampling_filter.set_random_seed(42)

        record = logging.LogRecord(
            name="test", level=logging.CRITICAL, pathname="", lineno=0, msg="test", args=(), exc_info=None
        )

        # Should always pass
        for _ in range(100):
            self.assertTrue(sampling_filter.filter(record))

    def test_never_passes_at_0_percent(self):
        """Logs never pass with 0% sampling."""
        sampling_filter = TelemetrySamplingFilter(sampling_rates={logging.INFO: 0.0})
        sampling_filter.set_random_seed(42)

        record = logging.LogRecord(name="test", level=logging.INFO, pathname="", lineno=0, msg="test", args=(), exc_info=None)

        # Should never pass
        for _ in range(100):
            self.assertFalse(sampling_filter.filter(record))

    def test_probabilistic_sampling_at_5_percent(self):
        """INFO logs are sampled at approximately 5% rate."""
        sampling_filter = TelemetrySamplingFilter(sampling_rates={logging.INFO: 0.05})
        sampling_filter.set_random_seed(42)

        record = logging.LogRecord(name="test", level=logging.INFO, pathname="", lineno=0, msg="test", args=(), exc_info=None)

        # Run many iterations to verify sampling rate is approximately 5%
        passes = sum(1 for _ in range(10000) if sampling_filter.filter(record))

        # Allow 2% tolerance (3% to 7%)
        self.assertGreater(passes, 300)
        self.assertLess(passes, 700)

    def test_deterministic_with_seed(self):
        """Same seed produces same results."""
        sampling_filter1 = TelemetrySamplingFilter(sampling_rates={logging.INFO: 0.5})
        sampling_filter2 = TelemetrySamplingFilter(sampling_rates={logging.INFO: 0.5})

        sampling_filter1.set_random_seed(12345)
        sampling_filter2.set_random_seed(12345)

        record = logging.LogRecord(name="test", level=logging.INFO, pathname="", lineno=0, msg="test", args=(), exc_info=None)

        # Same seed should produce identical results
        results1 = [sampling_filter1.filter(record) for _ in range(100)]
        results2 = [sampling_filter2.filter(record) for _ in range(100)]

        self.assertEqual(results1, results2)

    def test_uses_global_sampling_rates_by_default(self):
        """Uses global SAMPLING_RATES when no rates provided."""
        sampling_filter = TelemetrySamplingFilter()

        # Verify it has the global rates
        self.assertEqual(sampling_filter._sampling_rates, SAMPLING_RATES)

    def test_unknown_level_defaults_to_100_percent(self):
        """Unknown log levels default to 100% sampling."""
        sampling_filter = TelemetrySamplingFilter(sampling_rates={})
        sampling_filter.set_random_seed(42)

        # Create a record with an unusual level
        record = logging.LogRecord(
            name="test",
            level=25,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,  # Between INFO and WARNING
        )

        # Should always pass (defaults to 1.0)
        for _ in range(100):
            self.assertTrue(sampling_filter.filter(record))


class TestConfigureTelemetryLoggers(unittest.TestCase):
    def setUp(self):
        """Clear filters from telemetry loggers before each test."""
        for logger_name in TELEMETRY_LOGGER_NAMES:
            logger = logging.getLogger(logger_name)
            logger.filters.clear()

    def test_applies_sampling_filter_to_azure_logger(self):
        """Sampling filter is applied to azure logger."""
        configure_telemetry_loggers()

        azure_logger = logging.getLogger("azure")
        filter_types = [type(f).__name__ for f in azure_logger.filters]
        self.assertIn("TelemetrySamplingFilter", filter_types)

    def test_applies_sampling_filter_to_opentelemetry_logger(self):
        """Sampling filter is applied to opentelemetry logger."""
        configure_telemetry_loggers()

        otel_logger = logging.getLogger("opentelemetry")
        filter_types = [type(f).__name__ for f in otel_logger.filters]
        self.assertIn("TelemetrySamplingFilter", filter_types)

    def test_sets_telemetry_logger_level_to_warning_by_default(self):
        """Telemetry loggers default to WARNING level."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove APPINSIGHTS_LOGLEVEL if set
            os.environ.pop("APPINSIGHTS_LOGLEVEL", None)

            # Need to reimport to pick up env change
            import importlib

            import ado_asana_sync.utils.logging_tracing as lt

            importlib.reload(lt)
            lt.configure_telemetry_loggers()

            azure_logger = logging.getLogger("azure")
            self.assertEqual(azure_logger.level, logging.WARNING)

    def test_does_not_duplicate_filters(self):
        """Filter is not added multiple times."""
        configure_telemetry_loggers()
        configure_telemetry_loggers()
        configure_telemetry_loggers()

        azure_logger = logging.getLogger("azure")
        filter_count = sum(1 for f in azure_logger.filters if isinstance(f, TelemetrySamplingFilter))
        self.assertEqual(filter_count, 1)


class TestGetTelemetryFilter(unittest.TestCase):
    def test_returns_same_instance(self):
        """Returns the same global filter instance."""
        filter1 = get_telemetry_filter()
        filter2 = get_telemetry_filter()
        self.assertIs(filter1, filter2)

    def test_returns_telemetry_sampling_filter(self):
        """Returns a TelemetrySamplingFilter instance."""
        telemetry_filter = get_telemetry_filter()
        # Use class name check to avoid module reload identity issues from other tests
        self.assertEqual(type(telemetry_filter).__name__, "TelemetrySamplingFilter")


class TestDefaultSamplingRates(unittest.TestCase):
    def test_default_info_sampling_rate(self):
        """INFO defaults to 5% sampling."""
        self.assertEqual(SAMPLING_RATES[logging.INFO], 0.05)

    def test_default_debug_sampling_rate(self):
        """DEBUG defaults to 5% sampling."""
        self.assertEqual(SAMPLING_RATES[logging.DEBUG], 0.05)

    def test_default_warning_sampling_rate(self):
        """WARNING defaults to 100% sampling."""
        self.assertEqual(SAMPLING_RATES[logging.WARNING], 1.0)

    def test_default_error_sampling_rate(self):
        """ERROR defaults to 100% sampling."""
        self.assertEqual(SAMPLING_RATES[logging.ERROR], 1.0)

    def test_default_critical_sampling_rate(self):
        """CRITICAL defaults to 100% sampling."""
        self.assertEqual(SAMPLING_RATES[logging.CRITICAL], 1.0)


if __name__ == "__main__":
    unittest.main()

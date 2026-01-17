"""
This package provides logging and tracing functionality for the application.
It uses the OpenTelemetry library for tracing and the logging module for logging.

The `setup_logging_and_tracing` function initializes the logger and tracer for the specified module.
It takes in the module name as an argument and returns the logger and tracer objects.

Example usage:
    from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

    # This module uses the logger and tracer instances _LOGGER and _TRACER for logging and tracing, respectively.
    _LOGGER, _TRACER = setup_logging_and_tracing(__name__)

Telemetry Sampling:
    By default, telemetry loggers (azure, opentelemetry) are set to WARNING level and
    apply probabilistic sampling to reduce Application Insights ingestion volume.
    Console logging remains at INFO level with 100% output.

    Environment variables:
    - LOGLEVEL: Console log level (default: INFO)
    - APPINSIGHTS_LOGLEVEL: Telemetry logger level (default: WARNING)
    - APPINSIGHTS_SAMPLE_DEBUG: Sampling rate for DEBUG logs (default: 0.05 = 5%)
    - APPINSIGHTS_SAMPLE_INFO: Sampling rate for INFO logs (default: 0.05 = 5%)
    - APPINSIGHTS_SAMPLE_WARNING: Sampling rate for WARNING logs (default: 1.0 = 100%)
    - APPINSIGHTS_SAMPLE_ERROR: Sampling rate for ERROR logs (default: 1.0 = 100%)
    - APPINSIGHTS_SAMPLE_CRITICAL: Sampling rate for CRITICAL logs (default: 1.0 = 100%)
"""

import logging
import os
import random
from typing import Optional

from opentelemetry import trace

# Console log level (default INFO)
LOGLEVEL = os.environ.get("LOGLEVEL", "INFO").upper()

# Telemetry loggers to apply sampling filter to
TELEMETRY_LOGGER_NAMES = ["azure", "opentelemetry"]


def _get_sampling_rate(env_var: str, default: float) -> float:
    """
    Get sampling rate from environment variable with guardrails.

    Args:
        env_var: Name of the environment variable
        default: Default value if env var is not set or invalid

    Returns:
        Sampling rate clamped to [0.0, 1.0]
    """
    value = os.environ.get(env_var)
    if value is None:
        return default
    try:
        rate = float(value)
        # Clamp to valid range
        return max(0.0, min(1.0, rate))
    except ValueError:
        return default


# Sampling rates by log level (default: WARNING+ at 100%, INFO/DEBUG at 5%)
SAMPLING_RATES = {
    logging.DEBUG: _get_sampling_rate("APPINSIGHTS_SAMPLE_DEBUG", 0.05),
    logging.INFO: _get_sampling_rate("APPINSIGHTS_SAMPLE_INFO", 0.05),
    logging.WARNING: _get_sampling_rate("APPINSIGHTS_SAMPLE_WARNING", 1.0),
    logging.ERROR: _get_sampling_rate("APPINSIGHTS_SAMPLE_ERROR", 1.0),
    logging.CRITICAL: _get_sampling_rate("APPINSIGHTS_SAMPLE_CRITICAL", 1.0),
}


class TelemetrySamplingFilter(logging.Filter):
    """
    A logging filter that applies probabilistic sampling based on log level.

    This filter is designed to reduce telemetry volume to Application Insights
    while preserving 100% of WARNING, ERROR, and CRITICAL logs by default.
    INFO and DEBUG logs are sampled at a configurable rate (default 5%).

    The filter uses a random number generator that can be seeded for deterministic
    testing via the `set_random_seed` method.
    """

    def __init__(self, name: str = "", sampling_rates: Optional[dict[int, float]] = None):
        """
        Initialize the sampling filter.

        Args:
            name: Filter name (passed to parent class)
            sampling_rates: Optional dict mapping log levels to sampling rates [0.0-1.0].
                          If None, uses global SAMPLING_RATES from environment.
        """
        super().__init__(name)
        self._sampling_rates = sampling_rates if sampling_rates is not None else SAMPLING_RATES
        # Note: Using standard random for sampling, not cryptographic purposes (S311)
        self._random = random.Random()  # noqa: S311

    def set_random_seed(self, seed: int) -> None:
        """
        Set the random seed for deterministic testing.

        Args:
            seed: Random seed value
        """
        self._random.seed(seed)

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Determine if the log record should be emitted based on sampling.

        Args:
            record: The log record to filter

        Returns:
            True if the record should be emitted, False otherwise
        """
        level = record.levelno
        # Get sampling rate for this level, default to 1.0 (100%) if level not configured
        rate = self._sampling_rates.get(level, 1.0)

        # Always emit if rate is 1.0 (100%)
        if rate >= 1.0:
            return True

        # Never emit if rate is 0.0 (0%)
        if rate <= 0.0:
            return False

        # Probabilistic sampling
        return self._random.random() < rate


# Global filter instance for telemetry loggers
_telemetry_filter: Optional[TelemetrySamplingFilter] = None


def get_telemetry_filter() -> TelemetrySamplingFilter:
    """
    Get or create the global telemetry sampling filter.

    Returns:
        The global TelemetrySamplingFilter instance
    """
    global _telemetry_filter
    if _telemetry_filter is None:
        _telemetry_filter = TelemetrySamplingFilter()
    return _telemetry_filter


def configure_telemetry_loggers() -> None:
    """
    Configure telemetry loggers with sampling filter and appropriate log level.

    This applies the sampling filter and APPINSIGHTS_LOGLEVEL to all telemetry
    logger namespaces (azure, opentelemetry) to reduce Application Insights
    ingestion volume while preserving error/critical events.
    """
    appinsights_loglevel = os.environ.get("APPINSIGHTS_LOGLEVEL", "WARNING").upper()
    telemetry_level = getattr(logging, appinsights_loglevel, logging.WARNING)
    sampling_filter = get_telemetry_filter()

    for logger_name in TELEMETRY_LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        logger.setLevel(telemetry_level)
        # Add filter if not already present
        if sampling_filter not in logger.filters:
            logger.addFilter(sampling_filter)


def setup_logging_and_tracing(module_name: str):
    """
    Initializes the logger and tracer for the specified module.

    Console logging is set to LOGLEVEL (default INFO) with 100% output.
    Telemetry loggers (azure, opentelemetry) are set to APPINSIGHTS_LOGLEVEL
    (default WARNING) with probabilistic sampling to reduce Application Insights
    ingestion volume.

    Args:
        module_name (str): The name of the module to initialize the logger and tracer for.

    Returns:
        tuple: A tuple containing the logger and tracer objects.
    """
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, LOGLEVEL, logging.INFO),
    )

    logger = logging.getLogger(module_name)
    tracer = trace.get_tracer(module_name)

    # Configure telemetry loggers with sampling and appropriate level
    configure_telemetry_loggers()

    return logger, tracer

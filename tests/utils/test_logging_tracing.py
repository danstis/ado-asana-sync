import logging
import unittest

from opentelemetry import trace

from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing


class TestLoggingTracing(unittest.TestCase):
    def test_setup_logging_and_tracing(self):
        logger, tracer = setup_logging_and_tracing(__name__)
        self.assertIsInstance(logger, logging.Logger)
        self.assertIsInstance(tracer, trace.Tracer)


if __name__ == "__main__":
    unittest.main()

import logging
import unittest
import time

from opentelemetry import trace

from ado_asana_sync.utils.logging_tracing import (
    setup_logging_and_tracing,
    generate_correlation_id,
    log_with_context,
    log_performance,
    log_api_call,
    log_api_response,
)


class TestLoggingTracing(unittest.TestCase):
    def test_setup_logging_and_tracing(self):
        logger, tracer = setup_logging_and_tracing(__name__)
        self.assertIsInstance(logger, logging.Logger)
        self.assertIsInstance(tracer, trace.Tracer)

    def test_generate_correlation_id(self):
        correlation_id = generate_correlation_id()
        self.assertIsInstance(correlation_id, str)
        self.assertEqual(len(correlation_id), 8)
        
        # Test uniqueness
        correlation_id2 = generate_correlation_id()
        self.assertNotEqual(correlation_id, correlation_id2)

    def test_log_with_context(self):
        logger = logging.getLogger("test")
        # This should not raise an exception
        log_with_context(
            logger,
            logging.INFO,
            "Test message",
            correlation_id="test123",
            key1="value1",
            key2=None,  # Should be filtered out
            key3=42
        )

    def test_log_performance(self):
        logger = logging.getLogger("test")
        with log_performance(logger, "test_operation", test_param="test_value") as operation_id:
            self.assertIsInstance(operation_id, str)
            time.sleep(0.01)  # Small delay to test timing

    def test_log_api_call(self):
        logger = logging.getLogger("test")
        # This should not raise an exception
        log_api_call(
            logger,
            "TestAPI",
            "test_method",
            endpoint="test/endpoint",
            correlation_id="test123"
        )

    def test_log_api_response(self):
        logger = logging.getLogger("test")
        # Test successful response
        log_api_response(
            logger,
            "TestAPI",
            "test_method",
            success=True,
            response_time=0.5,
            correlation_id="test123"
        )
        
        # Test failed response
        log_api_response(
            logger,
            "TestAPI",
            "test_method",
            success=False,
            response_time=0.5,
            error="Test error",
            correlation_id="test123"
        )


if __name__ == "__main__":
    unittest.main()

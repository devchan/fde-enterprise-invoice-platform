from __future__ import annotations

import importlib.util
import unittest

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.main import app


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class RequestContextApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_request_id_is_generated_when_header_is_absent(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.headers["X-Request-ID"], r"^[0-9a-f-]{36}$")

    def test_request_id_header_is_preserved(self) -> None:
        response = self.client.get(
            "/health",
            headers={"X-Request-ID": "request-id-from-client"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Request-ID"], "request-id-from-client")

    def test_error_envelope_uses_generated_request_id(self) -> None:
        response = self.client.get("/api/v1/invoices")

        self.assertEqual(response.status_code, 401)
        response_request_id = response.headers["X-Request-ID"]
        error = response.json()["error"]
        self.assertEqual(error["code"], "authentication_required")
        self.assertEqual(error["request_id"], response_request_id)

    def test_validation_error_uses_consistent_error_envelope(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "a"},
            headers={"X-Request-ID": "validation-request-id"},
        )

        self.assertEqual(response.status_code, 422)
        error = response.json()["error"]
        self.assertEqual(error["code"], "request_validation_failed")
        self.assertEqual(error["request_id"], "validation-request-id")
        self.assertIn("errors", error["details"])

    def test_framework_not_found_uses_consistent_error_envelope(self) -> None:
        response = self.client.get(
            "/api/v1/not-a-real-route",
            headers={"X-Request-ID": "not-found-request-id"},
        )

        self.assertEqual(response.status_code, 404)
        error = response.json()["error"]
        self.assertEqual(error["code"], "not_found")
        self.assertEqual(error["request_id"], "not-found-request-id")

    def test_metrics_include_http_counts_duration_and_queue_depth(self) -> None:
        self.client.get("/health")

        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn("invoice_platform_http_requests_total", body)
        self.assertIn("invoice_platform_http_request_duration_seconds_sum", body)
        self.assertIn("invoice_platform_processing_queue_depth", body)
        self.assertIn("invoice_platform_processing_jobs_failed_total", body)
        self.assertIn("invoice_platform_processing_job_duration_seconds_sum", body)
        self.assertIn("invoice_platform_validation_failures_total", body)
        self.assertIn("invoice_platform_ai_estimated_cost_total", body)
        self.assertIn('path="/health"', body)
        # Latency histogram buckets enable p95/p99 via histogram_quantile.
        self.assertIn("invoice_platform_http_request_duration_seconds_bucket", body)
        self.assertIn('le="', body)


if __name__ == "__main__":
    unittest.main()

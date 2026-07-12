from __future__ import annotations

import importlib.util
import unittest

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app
    from app.middleware.rate_limit import reset_rate_limits


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class RateLimitApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        reset_rate_limits()
        self.original_enabled = settings.upload_rate_limit_enabled
        self.original_requests = settings.upload_rate_limit_requests
        self.original_window = settings.upload_rate_limit_window_seconds
        self.original_login_enabled = settings.login_rate_limit_enabled
        self.original_login_requests = settings.login_rate_limit_requests
        self.original_login_window = settings.login_rate_limit_window_seconds
        settings.upload_rate_limit_enabled = True
        settings.upload_rate_limit_requests = 2
        settings.upload_rate_limit_window_seconds = 60

    def tearDown(self) -> None:
        settings.upload_rate_limit_enabled = self.original_enabled
        settings.upload_rate_limit_requests = self.original_requests
        settings.upload_rate_limit_window_seconds = self.original_window
        settings.login_rate_limit_enabled = self.original_login_enabled
        settings.login_rate_limit_requests = self.original_login_requests
        settings.login_rate_limit_window_seconds = self.original_login_window
        reset_rate_limits()

    def test_invoice_upload_is_rate_limited_by_client(self) -> None:
        first = self.client.post("/api/v1/invoices/upload", headers={"X-Forwarded-For": "203.0.113.10"})
        second = self.client.post("/api/v1/invoices/upload", headers={"X-Forwarded-For": "203.0.113.10"})
        third = self.client.post("/api/v1/invoices/upload", headers={"X-Forwarded-For": "203.0.113.10"})

        self.assertNotEqual(first.status_code, 429)
        self.assertNotEqual(second.status_code, 429)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["error"]["code"], "rate_limit_exceeded")
        self.assertEqual(third.json()["error"]["details"]["limit"], 2)
        self.assertIn("Retry-After", third.headers)
        self.assertIn("X-Request-ID", third.headers)

    def test_non_upload_paths_are_not_rate_limited(self) -> None:
        responses = [
            self.client.get("/health", headers={"X-Forwarded-For": "203.0.113.20"})
            for _ in range(3)
        ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])

    def test_login_is_rate_limited_by_client(self) -> None:
        settings.login_rate_limit_enabled = True
        settings.login_rate_limit_requests = 2
        settings.login_rate_limit_window_seconds = 300
        credentials = {"email": "attacker@example.com", "password": "wrong-password"}

        first = self.client.post("/api/v1/auth/login", json=credentials, headers={"X-Forwarded-For": "203.0.113.40"})
        second = self.client.post("/api/v1/auth/login", json=credentials, headers={"X-Forwarded-For": "203.0.113.40"})
        third = self.client.post("/api/v1/auth/login", json=credentials, headers={"X-Forwarded-For": "203.0.113.40"})

        # Bad credentials return 401, but the third attempt is throttled before auth runs.
        self.assertNotEqual(first.status_code, 429)
        self.assertNotEqual(second.status_code, 429)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["error"]["code"], "rate_limit_exceeded")
        self.assertIn("Retry-After", third.headers)

    def test_login_rate_limit_is_independent_from_upload(self) -> None:
        settings.login_rate_limit_enabled = True
        settings.login_rate_limit_requests = 2
        settings.login_rate_limit_window_seconds = 300

        # Exhausting the upload limit must not throttle logins (separate counters).
        for _ in range(3):
            self.client.post("/api/v1/invoices/upload", headers={"X-Forwarded-For": "203.0.113.50"})
        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "x"},
            headers={"X-Forwarded-For": "203.0.113.50"},
        )

        self.assertNotEqual(login.status_code, 429)

    def test_upload_rate_limit_can_be_disabled(self) -> None:
        settings.upload_rate_limit_enabled = False

        responses = [
            self.client.post("/api/v1/invoices/upload", headers={"X-Forwarded-For": "203.0.113.30"})
            for _ in range(3)
        ]

        self.assertTrue(all(response.status_code != 429 for response in responses))


if __name__ == "__main__":
    unittest.main()

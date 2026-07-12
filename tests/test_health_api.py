from __future__ import annotations

import importlib.util
import unittest

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.main import app


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class HealthApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_liveness_returns_ok(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_reports_dependency_checks(self) -> None:
        response = self.client.get("/health/ready")

        # Runs against the live Docker stack, so dependencies are reachable.
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["checks"]["database"], "ok")
        self.assertEqual(body["checks"]["redis"], "ok")


if __name__ == "__main__":
    unittest.main()

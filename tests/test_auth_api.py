from __future__ import annotations

import importlib.util
import unittest
from uuid import uuid4

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.db.session import SessionLocal
    from app.main import app
    from app.middleware.rate_limit import reset_rate_limits
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.passwords import hash_password, verify_password


class PasswordHashTest(unittest.TestCase):
    def test_password_hash_verifies_original_password_only(self) -> None:
        if not HAS_REQUIRED_MODULES:
            self.skipTest("backend integration dependencies are not installed")

        password_hash = hash_password("correct horse battery staple")

        self.assertTrue(verify_password("correct horse battery staple", password_hash))
        self.assertFalse(verify_password("wrong horse battery staple", password_hash))
        self.assertFalse(verify_password("correct horse battery staple", None))


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class AuthApiTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_rate_limits()
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.org = Organization(name=f"Auth API Org {uuid4()}")
        self.db.add(self.org)
        self.db.flush()
        self.password = "production grade password"
        self.user = User(
            organization_id=self.org.id,
            email=f"reviewer-{uuid4()}@example.com",
            role="reviewer",
            password_hash=hash_password(self.password),
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_login_returns_access_token_and_user_context(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.user.email.upper(),
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["user_id"], str(self.user.id))
        self.assertEqual(body["organization_id"], str(self.org.id))
        self.assertEqual(body["email"], self.user.email)
        self.assertEqual(body["role"], "reviewer")
        self.assertTrue(body["access_token"])

    def test_login_token_can_access_review_queue(self) -> None:
        login_response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.user.email,
                "password": self.password,
            },
        )
        token = login_response.json()["access_token"]

        response = self.client.get(
            "/api/v1/invoices",
            params={"review_queue": "true"},
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("invoices", response.json())

    def test_login_rejects_bad_password(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.user.email,
                "password": "not the password",
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "invalid_credentials")

    def test_login_rejects_user_without_password_hash(self) -> None:
        user = User(
            organization_id=self.org.id,
            email=f"no-password-{uuid4()}@example.com",
            role="reviewer",
        )
        self.db.add(user)
        self.db.commit()

        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": user.email,
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "invalid_credentials")


if __name__ == "__main__":
    unittest.main()

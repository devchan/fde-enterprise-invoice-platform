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
    from app.services.passwords import hash_password


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class AuthSessionApiTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_rate_limits()
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.org = Organization(name=f"Session Org {uuid4()}")
        self.db.add(self.org)
        self.db.flush()
        self.password = "production grade password"
        self.user = User(
            organization_id=self.org.id,
            email=f"session-{uuid4()}@example.com",
            role="reviewer",
            password_hash=hash_password(self.password),
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def _login(self):
        return self.client.post(
            "/api/v1/auth/login",
            json={"email": self.user.email, "password": self.password},
        )

    def test_login_sets_httponly_auth_cookies(self) -> None:
        response = self._login()

        self.assertEqual(response.status_code, 200)
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn("access_token=", set_cookie)
        self.assertIn("refresh_token=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("access_token", self.client.cookies)

    def test_me_is_authenticated_via_cookie_without_bearer_header(self) -> None:
        self._login()

        response = self.client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], str(self.user.id))
        self.assertEqual(body["email"], self.user.email)
        self.assertEqual(body["role"], "reviewer")

    def test_me_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 401)

    def test_logout_revokes_access_token(self) -> None:
        access_token = self._login().json()["access_token"]

        logout = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout.status_code, 204)

        # The revoked token must be rejected even when presented as a bearer.
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def test_refresh_rotates_and_revokes_old_refresh_token(self) -> None:
        self._login()
        old_refresh = self.client.cookies.get("refresh_token")

        refreshed = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.json()["user_id"], str(self.user.id))

        # Replaying the old (rotated) refresh token must fail.
        replay = self.client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": old_refresh},
        )
        self.assertEqual(replay.status_code, 401)

    def test_access_token_cannot_be_used_as_refresh(self) -> None:
        access_token = self._login().json()["access_token"]

        response = self.client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": access_token},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()

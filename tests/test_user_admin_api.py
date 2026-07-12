from __future__ import annotations

import importlib.util
import unittest
from uuid import uuid4

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.api.auth import create_access_token
    from app.db.session import SessionLocal
    from app.main import app
    from app.models.audit import AuditLog
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.passwords import hash_password, verify_password


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class UserAdminApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.org = Organization(name=f"User Admin Org {uuid4()}")
        self.other_org = Organization(name=f"Other User Admin Org {uuid4()}")
        self.db.add_all([self.org, self.other_org])
        self.db.flush()
        self.admin = User(
            organization_id=self.org.id,
            email=f"admin-{uuid4()}@example.com",
            role="admin",
            password_hash=hash_password("admin password value"),
        )
        self.reviewer = User(
            organization_id=self.org.id,
            email=f"reviewer-{uuid4()}@example.com",
            role="reviewer",
            password_hash=hash_password("reviewer password value"),
        )
        self.other_admin = User(
            organization_id=self.other_org.id,
            email=f"other-admin-{uuid4()}@example.com",
            role="admin",
            password_hash=hash_password("other admin password"),
        )
        self.db.add_all([self.admin, self.reviewer, self.other_admin])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_admin_can_create_user_and_audit_event(self) -> None:
        email = f"new-reviewer-{uuid4()}@example.com"

        response = self.client.post(
            "/api/v1/users",
            headers=self._auth_headers(self.admin),
            json={
                "email": email.upper(),
                "role": "Reviewer",
                "password": "new reviewer password",
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["organization_id"], str(self.org.id))
        self.assertEqual(body["email"], email)
        self.assertEqual(body["role"], "reviewer")

        self.db.expire_all()
        created = self.db.get(User, body["user_id"])
        self.assertTrue(verify_password("new reviewer password", created.password_hash))
        audit = self._audit_for(entity_id=created.id, action="user.created")
        self.assertEqual(audit.actor_user_id, self.admin.id)
        self.assertEqual(audit.organization_id, self.org.id)
        self.assertEqual(audit.event_metadata["role"], "reviewer")

    def test_non_admin_cannot_create_user(self) -> None:
        response = self.client.post(
            "/api/v1/users",
            headers=self._auth_headers(self.reviewer),
            json={
                "email": f"denied-{uuid4()}@example.com",
                "role": "reviewer",
                "password": "new reviewer password",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "permission_denied")

    def test_user_list_is_limited_to_authenticated_admin_tenant(self) -> None:
        response = self.client.get("/api/v1/users", headers=self._auth_headers(self.admin))

        self.assertEqual(response.status_code, 200)
        user_ids = {item["user_id"] for item in response.json()["users"]}
        self.assertIn(str(self.admin.id), user_ids)
        self.assertIn(str(self.reviewer.id), user_ids)
        self.assertNotIn(str(self.other_admin.id), user_ids)

    def test_duplicate_email_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/users",
            headers=self._auth_headers(self.admin),
            json={
                "email": self.reviewer.email.upper(),
                "role": "reviewer",
                "password": "new reviewer password",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "user_duplicate")

    def test_admin_can_update_user_and_audit_event(self) -> None:
        new_email = f"updated-{uuid4()}@example.com"

        response = self.client.patch(
            f"/api/v1/users/{self.reviewer.id}",
            headers=self._auth_headers(self.admin),
            json={"email": new_email.upper(), "role": "uploader"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["email"], new_email)
        self.assertEqual(body["role"], "uploader")

        self.db.expire_all()
        audit = self._audit_for(entity_id=self.reviewer.id, action="user.updated")
        self.assertEqual(audit.actor_user_id, self.admin.id)
        self.assertEqual(audit.event_metadata["changed_fields"], ["email", "role"])

    def test_cross_tenant_user_update_returns_not_found(self) -> None:
        response = self.client.patch(
            f"/api/v1/users/{self.other_admin.id}",
            headers=self._auth_headers(self.admin),
            json={"role": "reviewer"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "user_not_found")

    def test_cannot_demote_last_admin(self) -> None:
        response = self.client.patch(
            f"/api/v1/users/{self.admin.id}",
            headers=self._auth_headers(self.admin),
            json={"role": "reviewer"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "last_admin_required")

    def test_admin_can_set_user_password(self) -> None:
        response = self.client.post(
            f"/api/v1/users/{self.reviewer.id}/password",
            headers=self._auth_headers(self.admin),
            json={"password": "replacement password"},
        )

        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        reviewer = self.db.get(User, self.reviewer.id)
        self.assertTrue(verify_password("replacement password", reviewer.password_hash))
        audit = self._audit_for(entity_id=self.reviewer.id, action="user.password_set")
        self.assertEqual(audit.actor_user_id, self.admin.id)

    def test_user_can_change_own_password(self) -> None:
        response = self.client.post(
            "/api/v1/users/me/password",
            headers=self._auth_headers(self.reviewer),
            json={
                "current_password": "reviewer password value",
                "new_password": "changed password value",
            },
        )

        self.assertEqual(response.status_code, 204)
        self.db.expire_all()
        reviewer = self.db.get(User, self.reviewer.id)
        self.assertTrue(verify_password("changed password value", reviewer.password_hash))
        audit = self._audit_for(entity_id=self.reviewer.id, action="user.password_changed")
        self.assertEqual(audit.actor_user_id, self.reviewer.id)

    def test_change_own_password_rejects_bad_current_password(self) -> None:
        response = self.client.post(
            "/api/v1/users/me/password",
            headers=self._auth_headers(self.reviewer),
            json={
                "current_password": "wrong password value",
                "new_password": "changed password value",
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "invalid_current_password")

    def _auth_headers(self, user: "User") -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user)}"}

    def _audit_for(self, *, entity_id, action: str) -> "AuditLog":
        return (
            self.db.query(AuditLog)
            .filter_by(entity_id=entity_id, action=action)
            .order_by(AuditLog.created_at.desc())
            .first()
        )


if __name__ == "__main__":
    unittest.main()

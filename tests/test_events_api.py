from __future__ import annotations

import importlib.util
import unittest
from uuid import uuid4

REQUIRED_MODULES = ("fastapi", "sqlalchemy", "pydantic", "sse_starlette", "redis")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.main import app
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.events import organization_channel, publish_event
    from app.services.passwords import hash_password


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies (incl. sse-starlette) are not installed")
class EventsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.org = Organization(name=f"Events API Org {uuid4()}")
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

    def test_stream_requires_authentication(self) -> None:
        # Deliberately does not open the actual stream (the dependency rejects the
        # request before the generator ever starts): a live SSE session blocks on a
        # Redis read with no clean way for TestClient to signal an ASGI disconnect,
        # which makes a "happy path" streaming test hang rather than fail.
        response = self.client.get("/api/v1/events/stream")

        self.assertEqual(response.status_code, 401)


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class PublishEventTest(unittest.TestCase):
    def test_publish_event_is_received_by_a_subscriber(self) -> None:
        import json

        from redis import Redis

        organization_id = uuid4()
        redis_client = Redis.from_url(settings.redis_url)
        pubsub = redis_client.pubsub()
        pubsub.subscribe(organization_channel(organization_id))
        # Drain the subscribe-confirmation message before publishing.
        pubsub.get_message(timeout=2)

        publish_event(organization_id, {"type": "job.completed", "invoice_id": "inv-1"})

        message = pubsub.get_message(timeout=2)
        self.assertIsNotNone(message)
        payload = json.loads(message["data"])
        self.assertEqual(payload["type"], "job.completed")
        self.assertEqual(payload["invoice_id"], "inv-1")
        self.assertIn("occurred_at", payload)

        pubsub.close()
        redis_client.close()


if __name__ == "__main__":
    unittest.main()

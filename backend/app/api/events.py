"""Realtime event stream: the frontend subscribes here instead of polling, and
invalidates its react-query cache on receipt (see app/services/events.py for
the signal-not-payload rationale)."""

import asyncio

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.api.auth import get_current_user
from app.models.user import User
from app.services.events import organization_channel

router = APIRouter(prefix="/events", tags=["events"])

_PING_SECONDS = 15


@router.get("/stream")
async def stream_events(request: Request, current_user: User = Depends(get_current_user)) -> EventSourceResponse:
    # request.app.state.redis is one shared async connection pool (opened in main.py's
    # lifespan); pubsub() checks out a dedicated connection from it for this subscription.
    pubsub = request.app.state.redis.pubsub()
    await pubsub.subscribe(organization_channel(current_user.organization_id))

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=_PING_SECONDS)
                except asyncio.CancelledError:
                    break
                if message is None:
                    continue
                data = message["data"]
                yield {"event": "message", "data": data.decode("utf-8") if isinstance(data, bytes) else data}
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return EventSourceResponse(event_generator(), ping=_PING_SECONDS)

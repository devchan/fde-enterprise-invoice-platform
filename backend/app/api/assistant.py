"""AP assistant API: agentic question answering over the caller's invoices.

The agent runs as the authenticated user, so every tool call inherits the
caller's organization scope and role — the model cannot read past the caller's
own permissions.
"""

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.errors import api_error
from app.db.session import get_db
from app.models.user import User
from app.schemas.assistant import (
    AssistantAskRequest,
    AssistantAskResponse,
    AssistantToolCallResponse,
)
from app.services.ap_assistant import AssistantError, ask_assistant

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=AssistantAskResponse)
def ask(
    payload: AssistantAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> AssistantAskResponse:
    try:
        result = ask_assistant(db, user=current_user, question=payload.question)
    except AssistantError as exc:
        raise api_error(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="assistant_request_invalid",
            message=str(exc),
            request_id=request_id,
        ) from exc

    return AssistantAskResponse(
        question=payload.question,
        answer=result.answer,
        model_name=result.model_name,
        tool_calls=[
            AssistantToolCallResponse(tool=call["tool"], arguments=call["arguments"])
            for call in result.tool_calls
        ],
    )

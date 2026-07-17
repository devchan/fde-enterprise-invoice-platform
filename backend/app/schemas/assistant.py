"""API request/response schemas for the AP assistant endpoint."""

from typing import Any

from pydantic import BaseModel, Field


class AssistantAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AssistantToolCallResponse(BaseModel):
    tool: str
    arguments: dict[str, Any]


class AssistantAskResponse(BaseModel):
    question: str
    answer: str
    model_name: str
    # The tools the agent actually called, in order — shown to the user so
    # answers are traceable to the data they came from.
    tool_calls: list[AssistantToolCallResponse]

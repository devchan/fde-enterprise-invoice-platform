"""Extraction-provider metadata: lets the UI show which providers can run and
which are disabled (no API key configured), without ever exposing the keys."""

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.models.user import User
from app.services.invoice_extraction import (
    PROVIDER_LABELS,
    default_provider,
    provider_availability,
)

router = APIRouter(tags=["extraction"])


@router.get("/extraction/providers")
def list_extraction_providers(current_user: User = Depends(get_current_user)) -> dict:
    """Report each extraction provider and whether it's usable, so the upload
    form can disable options whose API key isn't set. `available` reflects only
    key presence — never the key value itself."""
    availability = provider_availability()
    return {
        "default": default_provider(),
        "providers": [
            {"id": provider_id, "label": label, "available": availability.get(provider_id, False)}
            for provider_id, label in PROVIDER_LABELS.items()
        ],
    }

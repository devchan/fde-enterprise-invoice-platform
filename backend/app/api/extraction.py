"""Extraction-provider metadata and extraction-quality analytics: lets the UI
show which providers can run (without ever exposing keys) and how accurate
extraction has been per prompt version, measured from reviewer corrections."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.extraction_accuracy import extraction_accuracy_report
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


@router.get("/extraction/accuracy")
def get_extraction_accuracy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Per-field extraction accuracy per prompt version, derived from reviewer
    corrections (a corrected field = an extraction miss). This is the evidence
    view for judging whether a prompt/model change improved extraction."""
    report = extraction_accuracy_report(db, organization_id=current_user.organization_id)
    return {
        "prompt_versions": [
            {
                "prompt_version": entry.prompt_version,
                "model_names": entry.model_names,
                "reviewed_invoices": entry.reviewed_invoices,
                "fields": [
                    {
                        "field": field.field,
                        "reviewed_count": field.reviewed_count,
                        "corrected_count": field.corrected_count,
                        "accuracy": field.accuracy,
                    }
                    for field in entry.fields
                ],
            }
            for entry in report
        ]
    }

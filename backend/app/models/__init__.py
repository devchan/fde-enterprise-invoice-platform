# Re-export every model from one place. Importing this package registers all
# mappers with SQLAlchemy so string-based relationship references resolve and
# metadata (e.g. for migrations/create_all) is complete.
from app.models.audit import AuditLog
from app.models.invoice import (
    Invoice,
    InvoiceEmbedding,
    InvoiceExtraction,
    InvoiceFile,
    InvoiceLineItem,
    InvoiceReview,
    InvoiceValidationResult,
)
from app.models.organization import Organization
from app.models.processing import ProcessingJob
from app.models.prompt import PromptVersion
from app.models.supplier import Supplier
from app.models.user import User

__all__ = [
    "Invoice",
    "InvoiceEmbedding",
    "InvoiceExtraction",
    "InvoiceFile",
    "InvoiceLineItem",
    "InvoiceReview",
    "InvoiceValidationResult",
    "Organization",
    "Supplier",
    "User",
    "AuditLog",
    "ProcessingJob",
    "PromptVersion",
]

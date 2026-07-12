import importlib.util
import unittest
from uuid import uuid4

from backend.app.services.audit_log import (
    invoice_review_corrections_saved_event,
    invoice_review_decision_event,
    invoice_status_changed_event,
    invoice_uploaded_event,
)
from backend.app.services.invoice_workflow import InvoiceStatus

REQUIRED_MODULES = ("sqlalchemy", "psycopg")
HAS_REQUIRED_MODULES = all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)

if HAS_REQUIRED_MODULES:
    from app.db.session import SessionLocal
    from app.models.audit import AuditLog, AuditLogAppendOnlyError
    from app.models.organization import Organization
    from app.models.user import User


class AuditLogTest(unittest.TestCase):
    def test_invoice_uploaded_event_captures_required_metadata(self) -> None:
        invoice_id = uuid4()
        actor_id = uuid4()
        organization_id = uuid4()
        supplier_id = uuid4()

        event = invoice_uploaded_event(
            invoice_id=invoice_id,
            actor_id=actor_id,
            organization_id=organization_id,
            supplier_id=supplier_id,
            invoice_number="INV-100",
        )

        self.assertEqual(event.actor_id, actor_id)
        self.assertEqual(event.entity_type, "invoice")
        self.assertEqual(event.entity_id, invoice_id)
        self.assertEqual(event.action, "invoice.uploaded")
        self.assertEqual(event.metadata["organization_id"], str(organization_id))
        self.assertEqual(event.metadata["supplier_id"], str(supplier_id))
        self.assertEqual(event.metadata["invoice_number"], "INV-100")
        self.assertEqual(event.metadata["status"], InvoiceStatus.UPLOADED.value)

    def test_status_change_event_records_previous_and_next_status(self) -> None:
        event = invoice_status_changed_event(
            invoice_id=uuid4(),
            actor_id=uuid4(),
            previous_status=InvoiceStatus.PROCESSING,
            status=InvoiceStatus.REVIEW_REQUIRED,
        )

        self.assertEqual(event.action, "invoice.status_changed")
        self.assertEqual(event.metadata["previous_status"], InvoiceStatus.PROCESSING.value)
        self.assertEqual(event.metadata["status"], InvoiceStatus.REVIEW_REQUIRED.value)

    def test_review_corrections_event_records_corrected_field_names(self) -> None:
        event = invoice_review_corrections_saved_event(
            invoice_id=uuid4(),
            actor_id=uuid4(),
            corrected_fields={
                "total_amount": "120.00",
                "invoice_number": "INV-200",
            },
        )

        self.assertEqual(event.action, "invoice.review_corrections_saved")
        self.assertEqual(event.metadata["corrected_fields"], ["invoice_number", "total_amount"])

    def test_review_decision_event_records_decision_and_status(self) -> None:
        review_id = uuid4()
        event = invoice_review_decision_event(
            invoice_id=uuid4(),
            actor_id=uuid4(),
            review_id=review_id,
            decision="approve",
            previous_status=InvoiceStatus.REVIEW_REQUIRED,
            status=InvoiceStatus.APPROVED,
        )

        self.assertEqual(event.action, "invoice.review_decision")
        self.assertEqual(event.metadata["review_id"], str(review_id))
        self.assertEqual(event.metadata["decision"], "approve")
        self.assertEqual(event.metadata["previous_status"], InvoiceStatus.REVIEW_REQUIRED.value)
        self.assertEqual(event.metadata["status"], InvoiceStatus.APPROVED.value)


@unittest.skipIf(not HAS_REQUIRED_MODULES, "backend integration dependencies are not installed")
class AuditLogAppendOnlyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        self.org = Organization(name=f"Audit Append Org {uuid4()}")
        self.db.add(self.org)
        self.db.flush()
        self.user = User(
            organization_id=self.org.id,
            email=f"audit-{uuid4()}@example.com",
            role="admin",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_audit_log_insert_is_allowed(self) -> None:
        audit = self._create_audit()

        self.assertIsNotNone(audit.id)

    def test_audit_log_update_is_blocked(self) -> None:
        audit = self._create_audit()
        audit.action = "invoice.changed"

        with self.assertRaises(AuditLogAppendOnlyError):
            self.db.commit()
        self.db.rollback()

    def test_audit_log_delete_is_blocked(self) -> None:
        audit = self._create_audit()
        self.db.delete(audit)

        with self.assertRaises(AuditLogAppendOnlyError):
            self.db.commit()
        self.db.rollback()

    def _create_audit(self) -> "AuditLog":
        audit = AuditLog(
            organization_id=self.org.id,
            actor_user_id=self.user.id,
            entity_type="invoice",
            entity_id=uuid4(),
            action="invoice.uploaded",
            event_metadata={"source": "test"},
        )
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(audit)
        return audit


if __name__ == "__main__":
    unittest.main()

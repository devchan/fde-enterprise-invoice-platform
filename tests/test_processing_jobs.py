import unittest
from uuid import uuid4

from backend.app.services.processing_jobs import (
    ProcessingJobStatus,
    ProcessingJobType,
    build_invoice_extraction_job_payload,
)


class ProcessingJobsTest(unittest.TestCase):
    def test_build_invoice_extraction_job_starts_queued(self) -> None:
        invoice_id = uuid4()

        job = build_invoice_extraction_job_payload(invoice_id)

        self.assertEqual(job.invoice_id, invoice_id)
        self.assertEqual(job.job_type, ProcessingJobType.INVOICE_EXTRACTION)
        self.assertEqual(job.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(job.attempts, 0)


if __name__ == "__main__":
    unittest.main()

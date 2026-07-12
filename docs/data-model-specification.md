# Data Model Specification

This document separates implemented models from target production models.

## Implemented Models

### `organizations`

Purpose: tenant boundary.

Current fields:

- `id`
- `name`
- timestamps

### `users`

Purpose: platform users scoped to an organization.

Current fields:

- `id`
- `organization_id`
- `email`
- `role`
- timestamps

### `suppliers`

Purpose: invoice issuers scoped to an organization.

Current fields:

- `id`
- `organization_id`
- `name`
- `tax_id`
- `bank_account_hash`
- timestamps

Current constraint:

- unique supplier name per organization

### `invoices`

Purpose: primary invoice record.

Current fields:

- `id`
- `organization_id`
- `supplier_id`
- `uploaded_by`
- `invoice_number`
- `invoice_date`
- `total_amount`
- `currency`
- `status`
- `file_checksum`
- timestamps

Current constraint:

- unique invoice number per organization and supplier

### `invoice_files`

Purpose: original uploaded files and future derived files.

Current fields:

- `id`
- `invoice_id`
- `storage_key`
- `mime_type`
- `file_size`
- timestamps

### `invoice_line_items`

Purpose: extracted invoice line items.

Current fields:

- `id`
- `invoice_id`
- `description`
- `quantity`
- `unit_price`
- `line_total`
- timestamps

### `invoice_extractions`

Purpose: AI extraction payload and cost metadata.

Current fields:

- `id`
- `invoice_id`
- `prompt_version_id`
- `model_name`
- `prompt_version`
- `extracted_payload`
- `confidence_score`
- `input_tokens`
- `output_tokens`
- `estimated_cost`
- timestamps

### `invoice_validation_results`

Purpose: validation rule outputs.

Current fields:

- `id`
- `invoice_id`
- `rule_code`
- `severity`
- `message`
- `passed`
- timestamps

### `invoice_reviews`

Purpose: reviewer decisions and corrected fields.

Current fields:

- `id`
- `invoice_id`
- `reviewer_id`
- `decision`
- `notes`
- `corrected_fields`
- timestamps

### `audit_logs`

Purpose: append-only event history for compliance.

Current fields:

- `id`
- `organization_id`
- `actor_user_id`
- `entity_type`
- `entity_id`
- `action`
- `metadata`
- `request_id`
- timestamps

Current implementation note:

- SQLAlchemy reserves the attribute name `metadata`, so the model uses `event_metadata` while the database column remains `metadata`.

### `processing_jobs`

Purpose: durable tracking for background work.

Current fields:

- `id`
- `invoice_id`
- `job_type`
- `status`
- `attempts`
- `last_error`
- timestamps

Current implementation:

- upload creates a queued `invoice_extraction` job row
- upload publishes the job ID to Redis
- worker execution updates job status and invoice status
- failed jobs can be listed and manually reprocessed
- automatic retry policy is not implemented yet

### `prompt_versions`

Purpose: versioned AI extraction behavior.

Current fields:

- `id`
- `name`
- `version`
- `prompt_template`
- `json_schema`
- `is_active`
- timestamps

Rules:

- extraction rows should reference the prompt version used
- prompt changes must create a new version instead of overwriting old behavior

Current implementation:

- the worker creates or reuses prompt version `2026-07-10.v1`
- extraction rows store both `prompt_version_id` and the prompt version string for compatibility

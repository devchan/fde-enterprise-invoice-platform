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
- `category` (nullable AI-assigned expense category from a closed set: goods, services, software, travel, utilities, professional_services, marketing, other)
- timestamps

### `invoice_extractions`

Purpose: AI extraction payload and cost metadata.

Current fields:

- `id`
- `invoice_id`
- `prompt_version_id`
- `model_name`
- `prompt_version`
- `extracted_payload` (includes `field_confidences`: per-field confidence 0–1 or null for invoice_number, supplier_name, invoice_date, total_amount, currency)
- `confidence_score`
- `input_tokens`
- `output_tokens`
- `estimated_cost`
- timestamps

Current implementation note:

- when model tiering is enabled, `input_tokens`/`output_tokens`/`estimated_cost` aggregate both the tier-1 and escalated calls so spend accounting stays honest; `model_name` records the model whose payload was kept

### `invoice_validation_results`

Purpose: validation rule outputs, including post-extraction anomaly flags.

Current fields:

- `id`
- `invoice_id`
- `rule_code`
- `severity`
- `message`
- `passed`
- `explanation` (nullable plain-language reviewer guidance for failed rules)
- `suggested_fix` (nullable suggested action for failed rules)
- timestamps

Current implementation notes:

- business rules are written during extraction persistence; anomaly rules (`amount_anomaly`, `near_duplicate_similarity`) are written by a best-effort post-extraction step
- `field_confidence_low` rows flag individual extracted fields whose confidence fell below the review threshold

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
- `provider` (extraction provider chosen at upload; null lets the server decide)
- timestamps

Current implementation:

- upload creates a queued `invoice_extraction` job row
- upload publishes the job ID to Redis
- worker execution updates job status and invoice status
- failed jobs can be listed and manually reprocessed
- retryable failures are automatically requeued with exponential backoff up to `PROCESSING_JOB_MAX_ATTEMPTS`

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

- the worker creates or reuses prompt version `2026-07-17.v2` (adds per-field confidences, line-item categories, and few-shot example handling; `2026-07-10.v1` rows remain for history)
- extraction rows store both `prompt_version_id` and the prompt version string for compatibility

### `invoice_embeddings`

Purpose: semantic fingerprint of an invoice's extracted content for pgvector similarity search (similar-invoice lookup, near-duplicate triage).

Current fields:

- `id`
- `invoice_id` (unique — one current embedding per invoice)
- `model_name`
- `source_text` (the exact text embedded, kept for traceability and re-embedding)
- `embedding` (`vector(1536)`, matching OpenAI `text-embedding-3-small`)
- `input_tokens`
- `estimated_cost`
- timestamps

Rules:

- re-extraction must update the row in place, never append, so search never sees stale duplicates
- similarity queries must always be scoped to one organization

Current implementation:

- written best-effort by the worker after the extraction commit (an embedding failure never fails a completed extraction)
- queried by `GET /api/v1/invoices/{invoice_id}/similar` via pgvector cosine distance over an HNSW index
- also consumed by post-extraction anomaly detection for near-duplicate flagging
- when identical `source_text` was already embedded with the same model in the organization, the stored vector is reused instead of calling the provider (`EMBEDDING_REUSE_ENABLED`)

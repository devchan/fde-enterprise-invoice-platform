# System Design Explanation

Status: target-state system design. For the current repository state, see [Current Implementation Status](current-implementation-status.md). For the build sequence, see [Implementation Roadmap](implementation-roadmap.md).

## Problem Statement

Enterprise invoice processing is slow and error-prone when finance teams manually read supplier invoices, enter fields into systems, detect duplicates, and chase approvals.

The platform solves this by combining document upload, AI extraction, validation rules, human review, and audit logging in one controlled workflow.

## Design Goals

- Reduce manual invoice entry
- Keep humans in control for uncertain cases
- Prevent duplicate and invalid invoices
- Provide complete audit history
- Make failures visible and recoverable
- Support secure multi-tenant enterprise use
- Make the system deployable and observable

## Non-Goals for the First Version

- Full ERP replacement
- Complex payment execution
- Kubernetes-first deployment
- Multi-cloud architecture
- Fully autonomous approval for all invoices

The first version should focus on one strong workflow: invoice upload to reviewed approval.

## Main Workflow

The workflow below is the intended production workflow. It is not fully implemented yet.

1. A finance user uploads an invoice file.
2. The API validates the file and stores it in object storage.
3. The API creates an invoice record with status `uploaded`.
4. The API creates a processing job and pushes it to the queue.
5. A worker downloads the file and extracts structured data using AI.
6. The worker saves extraction output and confidence values.
7. The validation engine checks supplier, totals, tax, duplicates, and thresholds.
8. If safe, the invoice can move to approval-ready state.
9. If risky or incomplete, the invoice moves to `review_required`.
10. A reviewer corrects fields and approves or rejects the invoice.
11. Every state change and field correction is recorded in the audit log.

## Key Enterprise Decisions

### Use Background Processing

Invoice extraction can be slow, expensive, or fail due to third-party API limits. Running extraction in a background worker keeps the API responsive and makes retries safer.

### Store Original Files Separately

The database stores metadata. Object storage stores invoice files. This avoids bloating the database and allows secure file access through signed URLs.

### Keep AI Output Reviewable

AI output should not be treated as automatically correct. The platform stores extracted values, confidence scores, validation warnings, and raw response references so reviewers can inspect and correct results.

### Version Prompts

Prompt changes can alter extraction behavior. Prompt versions allow engineers to explain why older invoices were extracted differently from newer ones.

### Make Audit Logging First-Class

Enterprise systems need traceability. Every important event should produce an audit record with user, timestamp, action, entity, and changed values.

### Enforce Tenant Isolation

Every organization should see only its own suppliers, invoices, users, files, and audit logs. This must be enforced in backend queries, not only in the UI.

## Security Model

Recommended roles:

- `admin`: manages organization settings, users, suppliers, and validation rules
- `finance_user`: uploads invoices and views processing status
- `reviewer`: edits extracted fields and approves or rejects invoices
- `auditor`: read-only access to invoices and audit logs

Security controls:

- JWT authentication
- RBAC permissions
- private object storage
- signed file URLs
- no sensitive data in logs
- secrets stored outside source code
- rate limits on upload and API endpoints
- tenant-scoped database queries

## Reliability Model

The system should expect failures.

Failure cases:

- invalid file
- duplicate upload
- object storage upload failure
- AI API timeout
- AI invalid JSON response
- validation engine failure
- worker crash
- reviewer correction conflict

Reliability controls:

- idempotency keys for upload and processing
- file checksums
- retryable jobs
- dead-letter queue or failed job table
- explicit invoice failure states
- structured error messages
- manual reprocess action

## Observability Model

Every request and job should include a correlation ID.

Track:

- API request ID
- invoice ID
- organization ID
- processing job ID
- model name
- prompt version
- extraction duration
- validation duration
- token usage
- cost estimate
- error type

Dashboards should answer:

- How many invoices are stuck?
- How many failed today?
- Which validation rule fails most often?
- How long does approval take?
- How much are AI calls costing?

## Explanation for Interviews or Stakeholders

Use this short explanation:

> This platform automates invoice processing while preserving enterprise control. Users upload invoices, the system queues background processing, AI extracts structured fields, validation rules detect duplicates and mismatches, and risky invoices go to human review. Every action is audited, files are stored securely, and operations are observable through logs, metrics, and dashboards.

## What Makes It Enterprise Grade

- asynchronous processing instead of blocking API calls
- audit logs for compliance
- RBAC and tenant isolation
- object storage for files
- prompt/version tracking for AI behavior
- human review for uncertain AI output
- validation engine before approval
- retryable and observable processing jobs
- deployment and rollback documentation

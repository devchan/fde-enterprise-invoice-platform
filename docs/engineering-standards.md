# Engineering Standards

These standards define the bar for production-grade implementation.

## General Principles

- Backend owns business rules; frontend must not be trusted to enforce invoice workflow.
- All tenant-scoped data access must filter by organization.
- State transitions must be explicit and tested.
- Long-running work must run outside request-response paths.
- Every important state change must be auditable.
- AI output must be validated before it affects invoice approval.

## API Standards

- Use typed request and response schemas.
- Return stable error codes.
- Include request IDs in errors and logs.
- Do not expose internal exception text to API consumers.
- Use pagination on list endpoints.
- Use idempotency keys for upload and processing requests.

## Database Standards

- Every schema change must be represented as a migration.
- Database constraints should protect critical invariants.
- Application checks should provide friendly errors before constraint failures where practical.
- Use transactions for invoice changes plus audit writes.
- Avoid hard deletes for compliance records.

## Security Standards

- Authentication is required for all non-health endpoints.
- RBAC is enforced in backend dependencies or service layer.
- Tenant isolation is enforced in repository/query code.
- Secrets must come from environment or secret manager, never source code.
- Uploaded files are private by default.
- Signed URLs must be short-lived.
- Sensitive fields must be excluded from logs.

## AI Standards

- Use strict structured output schemas.
- Store model name, prompt version, token usage, estimated cost, confidence score, and extraction result.
- Treat invalid AI output as a controlled failure.
- Prompt changes must be versioned.
- Human corrections must be recorded.

## Testing Standards

Minimum coverage before a feature is considered complete:

- unit tests for domain rules
- API tests for request/response behavior
- persistence tests for database writes and constraints
- security tests for RBAC and tenant isolation
- failure-path tests for retries and invalid inputs

## Observability Standards

- Use structured JSON logs.
- Include request ID, organization ID, invoice ID, and job ID when available.
- Emit metrics for latency, queue depth, job duration, failures, validation outcomes, and AI cost.
- Dashboards must support operational questions without direct database access.

## Documentation Standards

- Update API docs when endpoints change.
- Update data model docs when models or migrations change.
- Update runbooks when operational behavior changes.
- Mark target-state behavior clearly until it is implemented and tested.

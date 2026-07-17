# Tests

Test critical enterprise workflows first:

- upload creates invoice and audit log
- upload validates file type, size, and checksum
- upload request rate limiting
- upload creates a queued extraction job record
- worker consumes queued jobs
- worker failures are retried up to a configured maximum
- worker persists extraction payloads and validation results
- failed jobs can be inspected and manually reprocessed
- duplicate invoice detection
- extraction result validation
- approval and rejection state transitions
- reviewer field correction audit trail
- tenant isolation
- per-field confidence validation routing and auto-approval decisions (`test_ai_optimizations.py`)
- anomaly detection (supplier amount outliers), validation explanation templates
- natural-language search fallback parsing and image preprocessing

Host-side browser smoke:

```bash
APP_URL=http://localhost:3000/ scripts/check-cockpit-smoke.sh
```

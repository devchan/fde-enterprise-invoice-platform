# Monitoring

This document describes the monitoring surface implemented in the repository today.

## Metrics Endpoint

The API exposes Prometheus text metrics at:

```text
GET /metrics
```

Metrics are produced with the official `prometheus_client` library. Current
metric families:

- `invoice_platform_http_requests_total` (counter)
- `invoice_platform_http_request_duration_seconds` (histogram; emits
  `_bucket`, `_sum`, and `_count`)
- `invoice_platform_processing_queue_depth`
- `invoice_platform_processing_jobs_failed_total`
- `invoice_platform_processing_job_duration_seconds_sum`
- `invoice_platform_processing_job_duration_seconds_count`
- `invoice_platform_validation_failures_total`
- `invoice_platform_ai_estimated_cost_total`

### Latency percentiles

The request-duration histogram exposes bucket series, so p95/p99 latency is
computed at query time and aggregates correctly across replicas:

```promql
histogram_quantile(0.95, sum by (le) (rate(invoice_platform_http_request_duration_seconds_bucket[5m])))
```

The `path` label is the matched route template (for example
`/api/v1/invoices/{invoice_id}`) rather than the raw URL, so label cardinality
stays bounded even when paths contain identifiers.

## Grafana Dashboard

An importable Grafana dashboard exists at:

```text
infra/monitoring/grafana/dashboards/invoice-platform-overview.json
```

The dashboard expects a Prometheus datasource and uses these panels:

- API request rate
- average API latency
- processing queue depth
- failed extraction jobs
- average completed processing duration
- validation failures
- estimated AI cost

## Local Scrape Target

When Docker Compose is running locally, Prometheus can scrape:

```text
http://backend:8000/metrics
```

From the host machine, the same endpoint is available at:

```text
http://localhost:8010/metrics
```

## Multi-worker Aggregation

The counter and histogram are `prometheus_client` collectors. For deployments
that run multiple worker processes in one container, set
`PROMETHEUS_MULTIPROC_DIR` to a writable (tmpfs) directory; the `/metrics`
endpoint then aggregates the per-worker shards into a single exposition. When
the variable is unset (the default single-worker container), the standard
in-process registry is used. Across separate container replicas, Prometheus
aggregates by scraping each replica and summing the bucket/counter series at
query time.

## Current Limits

Database-derived gauges (queue depth, failed jobs, validation failures,
estimated AI cost, completed-job duration) are computed at scrape time from
Postgres/Redis. Distributed tracing (OpenTelemetry) is not yet implemented.

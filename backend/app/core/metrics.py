from __future__ import annotations

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

# Exposition content type clients should serve (re-exported for the API layer).
CONTENT_TYPE = CONTENT_TYPE_LATEST

# HTTP request counter -> exposes `invoice_platform_http_requests_total`.
HTTP_REQUESTS = Counter(
    "invoice_platform_http_requests",
    "Total HTTP requests handled by the API.",
    ["method", "path", "status_code"],
)

# HTTP request latency histogram -> exposes `_bucket` (for p95/p99 via
# histogram_quantile), `_sum`, and `_count`. Prometheus aggregates the bucket
# series across replicas at query time, so percentiles are fleet-wide.
HTTP_REQUEST_DURATION = Histogram(
    "invoice_platform_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def record_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    labels = (method, path, str(status_code))
    HTTP_REQUESTS.labels(*labels).inc()
    HTTP_REQUEST_DURATION.labels(*labels).observe(duration_seconds)


def _client_exposition() -> str:
    """Render the in-process (counter/histogram) metrics. When
    PROMETHEUS_MULTIPROC_DIR is set (multi-worker deployments), aggregate the
    per-process shards so a single scrape reflects every worker."""
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry).decode("utf-8")
    return generate_latest().decode("utf-8")


def render_prometheus_metrics(
    *,
    queue_depth: int | None = None,
    database_metrics: dict[str, str] | None = None,
) -> str:
    database_metrics = database_metrics or {}
    sections = [_client_exposition().rstrip("\n")]

    # These gauges are derived from the database/Redis at scrape time rather than
    # accumulated in-process, so they are rendered as plain exposition text.
    gauges: list[str] = []
    if queue_depth is not None:
        gauges += [
            "# HELP invoice_platform_processing_queue_depth Current Redis processing queue depth.",
            "# TYPE invoice_platform_processing_queue_depth gauge",
            f"invoice_platform_processing_queue_depth {queue_depth}",
        ]
    gauges += [
        "# HELP invoice_platform_processing_jobs_failed_total Failed invoice extraction processing jobs.",
        "# TYPE invoice_platform_processing_jobs_failed_total gauge",
        "invoice_platform_processing_jobs_failed_total "
        f"{database_metrics.get('processing_jobs_failed_total', '0')}",
        "# HELP invoice_platform_processing_job_duration_seconds_sum Total completed job duration in seconds.",
        "# TYPE invoice_platform_processing_job_duration_seconds_sum gauge",
        "invoice_platform_processing_job_duration_seconds_sum "
        f"{database_metrics.get('processing_job_duration_seconds_sum', '0')}",
        "# HELP invoice_platform_processing_job_duration_seconds_count Completed job duration sample count.",
        "# TYPE invoice_platform_processing_job_duration_seconds_count gauge",
        "invoice_platform_processing_job_duration_seconds_count "
        f"{database_metrics.get('processing_job_duration_seconds_count', '0')}",
        "# HELP invoice_platform_validation_failures_total Failed invoice validation results.",
        "# TYPE invoice_platform_validation_failures_total gauge",
        "invoice_platform_validation_failures_total "
        f"{database_metrics.get('validation_failures_total', '0')}",
        "# HELP invoice_platform_ai_estimated_cost_total Total estimated AI extraction cost.",
        "# TYPE invoice_platform_ai_estimated_cost_total gauge",
        "invoice_platform_ai_estimated_cost_total "
        f"{database_metrics.get('ai_estimated_cost_total', '0')}",
    ]
    sections.append("\n".join(gauges))
    return "\n".join(sections) + "\n"

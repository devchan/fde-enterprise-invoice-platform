# syntax=docker/dockerfile:1

# ---- Builder: install dependencies into an isolated virtualenv ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

# ---- Runtime: slim image, non-root, venv copied from builder ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/backend:/app

# curl is needed for the container health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Only the backend runtime needs these; frontend/tests are bind-mounted in dev
# and irrelevant to the production image.
COPY alembic.ini /app/alembic.ini
COPY backend /app/backend
COPY infra /app/infra
COPY scripts /app/scripts

# Local object-storage scratch dir (used only when OBJECT_STORAGE_BACKEND=local);
# owned by the app user so the non-root process can write to it.
RUN mkdir -p /app/.local-storage && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/backend"]

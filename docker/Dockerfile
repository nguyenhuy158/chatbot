# syntax=docker/dockerfile:1.7
# Multi-stage build for the chatbot.
#
# Stages:
#   base    : common Python + system deps
#   builder : install Python packages into /opt/venv with uv
#   runtime : minimal final image, non-root, healthcheck
#
# Build with:
#   docker build -f docker/Dockerfile -t chatbot:latest --target runtime .
#
# Build for a specific service (app, worker, beat, ui):
#   docker build -f docker/Dockerfile -t chatbot-worker:latest --target runtime \
#     --build-arg SERVICE=worker .

ARG PYTHON_VERSION=3.12

# ────────────────────────────────────────────────────────────────────────────
# Stage 1: base — Python + system deps shared by build and runtime
# ────────────────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Ho_Chi_Minh

# Runtime system packages — kept minimal (no build-essential here)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libpq5 \
        libmagic1 \
        poppler-utils \
        tesseract-ocr \
        tini \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (UID 10001 — out of typical host UID range to avoid mount conflicts)
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home --shell /bin/bash app

WORKDIR /app

# ────────────────────────────────────────────────────────────────────────────
# Stage 2: builder — install Python deps
# ────────────────────────────────────────────────────────────────────────────
FROM base AS builder

# Build-only system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# Create venv at /opt/venv so we can copy it cleanly into runtime
ENV VIRTUAL_ENV=/opt/venv
RUN uv venv ${VIRTUAL_ENV} --python python${PYTHON_VERSION}
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# Layer cache: copy only pyproject + lock first
COPY pyproject.toml ./
COPY uv.lock* ./

# Install dependencies. --no-dev because runtime doesn't need pytest etc.
# If uv.lock missing (first build), uv will resolve from pyproject.
RUN if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev --no-install-project; \
    else \
        uv pip install -r <(uv pip compile pyproject.toml 2>/dev/null) || \
        uv pip install --requirement pyproject.toml; \
    fi

# Now copy the app code itself
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY ui ./ui
COPY evals ./evals
COPY scripts ./scripts

# Install the project (no-op for non-package, but ensures imports work)
RUN uv pip install --no-deps . 2>/dev/null || true

# Strip bytecode for smaller images (optional but saves ~20MB)
RUN find /opt/venv -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true \
    && find /opt/venv -type f -name '*.pyc' -delete

# ────────────────────────────────────────────────────────────────────────────
# Stage 3: runtime — final minimal image
# ────────────────────────────────────────────────────────────────────────────
FROM base AS runtime

ARG SERVICE=app
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown

# OCI labels for traceability
LABEL org.opencontainers.image.title="chatbot" \
      org.opencontainers.image.description="AI Chatbot service: ${SERVICE}" \
      org.opencontainers.image.source="https://github.com/your-org/chatbot" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

# Copy venv from builder
COPY --from=builder --chown=app:app /opt/venv /opt/venv

# Copy app source from builder
COPY --from=builder --chown=app:app /app /app

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app" \
    APP_ENV=prod \
    SERVICE=${SERVICE}

# Writable directories that the app needs at runtime
RUN mkdir -p /tmp/chatbot-uploads /tmp/chatbot-images /tmp/eval-reports \
    && chown -R app:app /tmp/chatbot-uploads /tmp/chatbot-images /tmp/eval-reports

USER app

# Healthcheck — different per service via entrypoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/health || exit 1

EXPOSE 8000 8501

# Use tini as PID 1 to handle signals and reap zombies properly
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/entrypoint.sh"]

# Default command — overridden by docker-compose / k8s for worker/beat/ui
CMD ["app"]

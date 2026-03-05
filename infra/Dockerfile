FROM python:3.11-slim

# Security: run as non-root
RUN groupadd -r fnews && useradd -r -g fnews -d /app fnews

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies first (layer cache)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e "."

# Application code
COPY apps/ ./apps/
COPY packages/ ./packages/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Data directories
RUN mkdir -p /data/blobs && chown -R fnews:fnews /app /data

USER fnews

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

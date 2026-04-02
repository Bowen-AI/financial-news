#!/usr/bin/env bash
# test-integration.sh – Run integration tests with a Docker-based Postgres + Redis
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " financial-news — Integration Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

COMPOSE_FILE="infra/docker-compose.test.yml"
NETWORK="fnews_test_net"

# Cleanup on exit
cleanup() {
  echo ""
  echo "→ Cleaning up test containers..."
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
  echo "  ✓ Done"
}
trap cleanup EXIT INT TERM

# ── Start test services ───────────────────────────────────────────────────────
echo "→ Starting test services (Postgres + Redis)..."
docker compose -f "$COMPOSE_FILE" up -d

echo "→ Waiting for Postgres to be ready..."
for i in $(seq 1 30); do
  if docker compose -f "$COMPOSE_FILE" exec -T test-db \
      pg_isready -U fnews -d fnews_test &>/dev/null; then
    echo "  ✓ Postgres ready"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "  ✗ Postgres did not become ready in time"
    exit 1
  fi
  sleep 1
done

# ── Install test dependencies ─────────────────────────────────────────────────
echo ""
echo "→ Ensuring test dependencies are installed..."
pip3 install --quiet \
  sqlalchemy[asyncio] asyncpg pgvector alembic pydantic-settings structlog pyyaml \
  httpx anyio fastapi uvicorn pytest pytest-asyncio pytest-mock feedparser \
  trafilatura python-dateutil 2>/dev/null
echo "  ✓ Dependencies ready"

# ── Run Alembic migrations ────────────────────────────────────────────────────
echo ""
echo "→ Running database migrations..."
DB_HOST=$(docker compose -f "$COMPOSE_FILE" port test-db 5432 | cut -d: -f1)
DB_PORT=$(docker compose -f "$COMPOSE_FILE" port test-db 5432 | cut -d: -f2)

export DATABASE_URL="postgresql+asyncpg://fnews:testpass@${DB_HOST}:${DB_PORT}/fnews_test"
export REDIS_URL="redis://localhost:6379/0"
export API_KEY="test-api-key"
export LLM_BACKEND="ollama"
export LLM_BASE_URL="http://localhost:11434"
export LLM_MODEL_NAME="llama3"
export EMBEDDING_MODEL_NAME="BAAI/bge-small-en-v1.5"
export ALERT_THRESHOLD="70"
export ALERT_MIN_SOURCES="2"
export SOURCE_CONFIG_PATH="config/sources.example.yaml"
export WATCHLIST_CONFIG_PATH="config/watchlist.example.yaml"
export BLOB_STORE_PATH="/tmp/fnews-test-blobs"
export EMAIL_SMTP_HOST="smtp.example.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_SMTP_USER="test@example.com"
export EMAIL_SMTP_PASS="testpass"
export EMAIL_FROM="test@example.com"
export EMAIL_TO="test@example.com"
export EMAIL_IMAP_HOST="imap.example.com"
export EMAIL_IMAP_PORT="993"
export EMAIL_IMAP_USER="test@example.com"
export EMAIL_IMAP_PASS="testpass"

alembic upgrade head
echo "  ✓ Migrations applied"

# ── Run integration tests ─────────────────────────────────────────────────────
echo ""
echo "→ Running integration tests..."
python -m pytest tests/integration/ -v --tb=short "$@"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Integration tests complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

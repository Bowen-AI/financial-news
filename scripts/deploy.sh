#!/usr/bin/env bash
# deploy.sh – Deploy financial-news via Docker Compose (idempotent)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " financial-news — Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Preflight checks ──────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "✗ .env not found. Run './scripts/install.sh' first."
  exit 1
fi

if [ ! -f "config/sources.yaml" ]; then
  echo "✗ config/sources.yaml not found. Run './scripts/install.sh' first."
  exit 1
fi

if [ ! -f "config/watchlist.yaml" ]; then
  echo "✗ config/watchlist.yaml not found. Run './scripts/install.sh' first."
  exit 1
fi

# Warn if API key is still default
API_KEY_VALUE=$(grep '^API_KEY=' .env | cut -d= -f2)
if [ "$API_KEY_VALUE" = "changeme-api-key-here" ]; then
  echo "⚠  WARNING: API_KEY is still the default value. Change it in .env before exposing externally."
fi

# ── Pull / build images ───────────────────────────────────────────────────────
echo "→ Building application images..."
docker compose -f infra/docker-compose.yml build --pull
echo "  ✓ Images built"

# ── Start services ────────────────────────────────────────────────────────────
echo ""
echo "→ Starting services..."
docker compose -f infra/docker-compose.yml up -d
echo "  ✓ Services started"

# ── Wait for API health ───────────────────────────────────────────────────────
echo ""
echo "→ Waiting for API to be healthy..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/health &>/dev/null; then
    echo "  ✓ API is healthy"
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "  ✗ API did not become healthy. Check logs:"
    echo "    docker compose -f infra/docker-compose.yml logs api"
    exit 1
  fi
  sleep 2
done

# ── Show status ───────────────────────────────────────────────────────────────
echo ""
echo "→ System status:"
docker compose -f infra/docker-compose.yml ps

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Deployment successful!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo " API:        http://localhost:8000"
echo " Dashboard:  http://localhost:8000/dashboard?X-API-Key=\$API_KEY"
echo " API Docs:   http://localhost:8000/docs"
echo ""
echo " To pull the LLM model:"
echo "   docker exec -it fnews-ollama ollama pull llama3"
echo ""
echo " To run first ingestion:"
echo "   KEY=\$(grep API_KEY .env | cut -d= -f2)"
echo "   curl -X POST http://localhost:8000/ingest/run -H \"X-API-Key: \$KEY\""
echo ""
echo " To view logs:"
echo "   docker compose -f infra/docker-compose.yml logs -f worker"
echo ""

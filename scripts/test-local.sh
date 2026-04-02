#!/usr/bin/env bash
# test-local.sh – Run unit tests locally (no Docker/DB required)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " financial-news — Local Unit Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check / install minimal test dependencies
echo "→ Ensuring test dependencies are installed..."
pip3 install --quiet sqlalchemy pgvector pydantic-settings structlog pyyaml \
             pytest pytest-asyncio pytest-mock httpx anyio 2>/dev/null
echo "  ✓ Dependencies ready"
echo ""

# Run unit tests
echo "→ Running unit tests..."
python -m pytest tests/unit/ -v --tb=short "$@"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Unit tests complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

#!/usr/bin/env bash
# install.sh – One-command local installation for financial-news
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " financial-news — Local Install"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Check prerequisites ────────────────────────────────────────────────────
echo ""
echo "→ Checking prerequisites..."

for cmd in docker python3 pip3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "  ✗ '$cmd' not found. Please install it first."
    exit 1
  fi
  echo "  ✓ $cmd"
done

# Check Docker Compose v2
if ! docker compose version &>/dev/null; then
  echo "  ✗ Docker Compose v2 not found. Please update Docker Desktop or install docker-compose-plugin."
  exit 1
fi
echo "  ✓ docker compose"

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; assert sys.version_info >= (3, 11), 'Need 3.11+'" 2>/dev/null; then
  echo "  ✓ Python $PYTHON_VERSION"
else
  echo "  ✗ Python 3.11+ required (found $PYTHON_VERSION)"
  exit 1
fi

# ── 2. Copy config files ──────────────────────────────────────────────────────
echo ""
echo "→ Setting up config files..."
cd "$REPO_ROOT"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  ✓ Created .env (please edit with your SMTP/IMAP credentials)"
else
  echo "  ✓ .env already exists"
fi

if [ ! -f "config/sources.yaml" ]; then
  cp config/sources.example.yaml config/sources.yaml
  echo "  ✓ Created config/sources.yaml"
else
  echo "  ✓ config/sources.yaml already exists"
fi

if [ ! -f "config/watchlist.yaml" ]; then
  cp config/watchlist.example.yaml config/watchlist.yaml
  echo "  ✓ Created config/watchlist.yaml"
else
  echo "  ✓ config/watchlist.yaml already exists"
fi

# ── 3. Install Python dev dependencies ────────────────────────────────────────
echo ""
echo "→ Installing Python development dependencies..."
pip3 install --quiet sqlalchemy pgvector pydantic-settings structlog pyyaml \
             httpx anyio fastapi uvicorn pytest pytest-asyncio pytest-mock feedparser \
             trafilatura python-dateutil
echo "  ✓ Python deps installed"

# ── 4. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Installation complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo " Next steps:"
echo ""
echo "  1. Edit your credentials:"
echo "     nano .env"
echo ""
echo "  2. Start the stack:"
echo "     cd infra && docker compose up -d"
echo ""
echo "  3. Pull the LLM model (after stack starts):"
echo "     docker exec -it fnews-ollama ollama pull llama3"
echo ""
echo "  4. Run unit tests:"
echo "     ./scripts/test-local.sh"
echo ""
echo "  5. Trigger first ingestion:"
echo "     KEY=\$(grep API_KEY .env | cut -d= -f2)"
echo "     curl -X POST http://localhost:8000/ingest/run -H \"X-API-Key: \$KEY\""
echo ""

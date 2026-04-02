# financial-news – Financial Intelligence System

A production-quality, self-hosted financial intelligence system that runs
open-weight LLMs locally, continuously ingests market-moving news, maintains
a long-term memory, sends daily email briefings, processes your reply emails
to track trades, and self-evaluates over time.

> **Disclaimer:** This system is NOT a financial advisor. All outputs are
> evidence-based summaries with citations. No "buy/sell" instructions are
> ever generated.

---

## Quickstart

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your SMTP/IMAP credentials, LLM backend, etc.

# 2. Copy sample configs
cp config/sources.example.yaml config/sources.yaml
cp config/watchlist.example.yaml config/watchlist.yaml

# 3. Start everything
cd infra
docker compose up -d

# 4. Pull your LLM model into Ollama
docker exec -it fnews-ollama ollama pull llama3

# 5. Run first ingestion
curl -X POST http://localhost:8000/ingest/run \
  -H "X-API-Key: $(grep API_KEY ../.env | cut -d= -f2)"

# 6. Send a test briefing
curl -X POST http://localhost:8000/briefing/send \
  -H "X-API-Key: $(grep API_KEY ../.env | cut -d= -f2)"
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        apps/api  (FastAPI)                  │
│  /health  /status  /ingest/run  /briefing/send  /alerts/run │
│  /portfolio  /backtest/run  /email/inbound                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ enqueue tasks
┌──────────────────────────▼──────────────────────────────────┐
│               apps/worker  (Celery + Redis)                 │
│  ingest_task  briefing_task  alert_task  imap_poll_task     │
│  eval_task                                                  │
└──┬──────────┬───────────┬──────────┬──────────┬────────────┘
   │          │           │          │          │
   ▼          ▼           ▼          ▼          ▼
packages/ packages/  packages/  packages/  packages/
ingestion  rag        alerts     emailer    portfolio
           │                    │
           ▼                    ▼
        pgvector             SMTP/IMAP

packages/backtest   packages/eval
```

Services (Docker Compose):
- **db** – PostgreSQL 15 + pgvector
- **redis** – Redis 7 (task broker + cache)
- **ollama** – Ollama LLM server (swap for vLLM/llama.cpp via LLM_BACKEND)
- **api** – FastAPI application
- **worker** – Celery worker
- **beat** – Celery beat scheduler

---

## Configuration

### Environment variables

See `.env.example` for all variables with descriptions.

Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Postgres async URL |
| `REDIS_URL` | Redis URL |
| `LLM_BACKEND` | `ollama`, `vllm`, or `llamacpp` |
| `LLM_MODEL_NAME` | Model name (e.g. `llama3`) |
| `EMBEDDING_MODEL_NAME` | HuggingFace model ID |
| `EMAIL_SMTP_*` | Outbound email settings |
| `EMAIL_IMAP_*` | Inbound email settings |
| `ALERT_THRESHOLD` | Score 0-100 to trigger alert |
| `SOURCE_CONFIG_PATH` | Path to sources YAML |

### Sources config (`config/sources.yaml`)

```yaml
sources:
  - name: Reuters Business
    type: rss
    url: https://feeds.reuters.com/reuters/businessNews
    credibility: 0.9
  - name: Custom URL
    type: http
    url: https://example.com/news
    credibility: 0.7
```

### Watchlist config (`config/watchlist.yaml`)

```yaml
watchlist:
  tickers:
    - AAPL
    - NVDA
    - TSLA
  entities:
    - "Federal Reserve"
    - "OPEC"
```

---

## Model Backend Setup

### Ollama (default)

```bash
# Ollama runs as a Docker service; pull models after starting:
docker exec -it fnews-ollama ollama pull llama3
docker exec -it fnews-ollama ollama pull nomic-embed-text
```

### vLLM

Set `LLM_BACKEND=vllm` and `LLM_BASE_URL=http://your-vllm-server:8000`.

### llama.cpp

Set `LLM_BACKEND=llamacpp` and `LLM_BASE_URL=http://your-llamacpp-server:8080`.

---

## Running Jobs Manually

```bash
API=http://localhost:8000
KEY=$(grep API_KEY .env | cut -d= -f2)

# Run ingestion
curl -X POST $API/ingest/run -H "X-API-Key: $KEY"

# Send daily briefing
curl -X POST $API/briefing/send -H "X-API-Key: $KEY"

# Run alert check
curl -X POST $API/alerts/run -H "X-API-Key: $KEY"

# Check status
curl $API/status -H "X-API-Key: $KEY"

# View portfolio
curl $API/portfolio -H "X-API-Key: $KEY"

# Add a trade manually
curl -X POST $API/portfolio/action \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"raw_text": "BUY 10 AAPL @ 180"}'

# Run backtest
curl -X POST $API/backtest/run \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"alert_id": "...", "action": "BUY", "holding_days": 5}'
```

---

## Viewing Status

```bash
# Admin dashboard (HTML)
open http://localhost:8000/dashboard

# Health check
curl http://localhost:8000/health
```

---

## Inbound Email Commands

Reply to any system email (or send to the configured inbound address) with:

```
BUY 10 AAPL @ 180.50
SELL 5 NVDA
NOTE: watching energy sector due to OPEC meeting
POSITION
HELP
```

The system will parse the command, record the action, and reply with confirmation.

---

## Backtesting

```bash
# Via CLI (inside worker container)
docker exec -it fnews-worker python -m packages.backtest.cli \
  --alert-id <uuid> \
  --action BUY \
  --holding-days 5

# Via API
curl -X POST http://localhost:8000/backtest/run \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"alert_id": "<uuid>", "action": "BUY", "holding_days": 5}'
```

---

## Troubleshooting

**No emails sent:** Check SMTP credentials and that port 587 is open from your server.

**LLM not responding:** Ensure Ollama is running and model is pulled:
```bash
docker logs fnews-ollama
docker exec -it fnews-ollama ollama list
```

**Database issues:**
```bash
docker exec -it fnews-db psql -U fnews -d fnews -c '\dt'
```

**Reset everything:**
```bash
cd infra && docker compose down -v && docker compose up -d
```

---

## Security Hardening

See `docs/security.md` for full hardening checklist including:
- Running as non-root user
- Firewall rules (ufw)
- Reverse proxy (Caddy)
- IMAP app passwords
- API key rotation
- Backup/restore procedures

---

## Backup & Restore

```bash
# Backup
docker exec fnews-db pg_dump -U fnews fnews | gzip > backup-$(date +%Y%m%d).sql.gz
tar czf blobs-$(date +%Y%m%d).tar.gz /data/blobs

# Restore
gunzip -c backup-YYYYMMDD.sql.gz | docker exec -i fnews-db psql -U fnews fnews
tar xzf blobs-YYYYMMDD.tar.gz -C /
```

---

## Multi-Server Deployment (k3s)

See `infra/k3s/` for Kubernetes manifests. Deploy with:

```bash
kubectl apply -f infra/k3s/
```

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```
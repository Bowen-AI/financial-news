# Operations Guide

## Starting the System

```bash
cd infra
docker compose up -d
```

This starts: PostgreSQL, Redis, Ollama, API, Worker, Beat scheduler.

---

## First-Time Setup

```bash
# 1. Copy and edit config
cp .env.example .env
nano .env

cp config/sources.example.yaml config/sources.yaml
cp config/watchlist.example.yaml config/watchlist.yaml

# 2. Pull LLM model (after `docker compose up -d`)
docker exec -it fnews-ollama ollama pull llama3

# 3. Verify migration ran
docker exec -it fnews-db psql -U fnews -c '\dt'

# 4. Test ingestion
curl -X POST http://localhost:8000/ingest/run \
  -H "X-API-Key: $API_KEY"

# 5. Watch logs
docker compose logs -f worker
```

---

## Monitoring

```bash
# Service status
docker compose ps

# Live logs
docker compose logs -f api worker beat

# Database
docker exec -it fnews-db psql -U fnews -d fnews

# Celery task monitor (Flower – optional)
pip install flower
celery -A apps.worker.celery_app flower --port=5555
```

---

## Updating

```bash
git pull
cd infra
docker compose build
docker compose up -d
# Migrations run automatically via the migrate service
```

---

## Scaling

For higher throughput, increase Celery concurrency:

```yaml
# in docker-compose.yml
worker:
  command: ["celery", "-A", "apps.worker.celery_app", "worker",
            "--loglevel=info", "--concurrency=8"]
```

Or run multiple worker replicas:

```bash
docker compose up -d --scale worker=3
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| LLM timeout | Increase `max_tokens` timeout in `llm_client.py` or use a smaller model |
| No articles ingested | Check `config/sources.yaml` has valid enabled sources |
| Emails not sent | Verify SMTP credentials, port 587 outbound open |
| High memory usage | Reduce `--concurrency` in worker, use smaller embedding model |
| pgvector slow | Ensure HNSW index exists: `\d chunks` |

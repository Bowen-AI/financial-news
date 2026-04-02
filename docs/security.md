# Security Hardening Guide

## Threat Model

The system is designed to be run on a private/self-hosted server with minimal internet exposure:
- Only IMAP (outbound polling, no inbound port needed)
- SMTP (outbound only)
- API exposed only on localhost (reverse proxy adds TLS if needed)
- Ollama bound to localhost only

---

## Hardening Checklist

### Container Security

- [x] Application runs as non-root user (`fnews` UID/GID)
- [x] Database port bound to `127.0.0.1` only
- [x] Redis port bound to `127.0.0.1` only
- [x] Ollama port bound to `127.0.0.1` only
- [x] API port bound to `127.0.0.1` only (use reverse proxy for external access)

### Firewall (ufw)

```bash
# Allow SSH
ufw allow ssh

# Allow SMTP outbound
ufw allow out 587/tcp
ufw allow out 465/tcp

# Allow IMAP outbound
ufw allow out 993/tcp

# Block direct database/redis/ollama access from outside
ufw deny 5432/tcp
ufw deny 6379/tcp
ufw deny 11434/tcp

# If exposing API via reverse proxy
ufw allow 443/tcp  # HTTPS

ufw enable
```

### Reverse Proxy (Caddy – recommended)

```caddy
fnews.yourdomain.com {
    reverse_proxy localhost:8000
    tls you@example.com
}
```

Or Nginx:

```nginx
server {
    listen 443 ssl;
    server_name fnews.yourdomain.com;
    ssl_certificate /etc/letsencrypt/live/fnews.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/fnews.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Credentials

- **Never commit** `.env` to git (already in `.gitignore`)
- Use **app passwords** for IMAP/SMTP (not your account password)
- Rotate `API_KEY` regularly:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  # Update API_KEY in .env and restart services
  ```
- Use a secrets manager (e.g., `docker secret`, HashiCorp Vault) for production

### Database

```bash
# Strong Postgres password
POSTGRES_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(24))")

# Only allow local connections (pg_hba.conf already restricted via Docker)
```

### Logging

- JSON logs with secret redaction (automatically redacts `password`, `secret`, `token`, etc.)
- Logs go to stdout → captured by Docker
- View logs: `docker compose logs -f api worker`

### fail2ban (optional)

If exposing the API externally, protect against brute-force on the API key:

```ini
# /etc/fail2ban/filter.d/fnews-api.conf
[Definition]
failregex = .* "GET .* HTTP.*" 403
ignoreregex =
```

---

## Backup & Restore

### Automated backup script

```bash
#!/bin/bash
set -euo pipefail
BACKUP_DIR=/var/backups/fnews
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Postgres
docker exec fnews-db pg_dump -U fnews fnews | \
  gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Blobs (content-addressed, safe to rsync)
rsync -a /data/blobs/ $BACKUP_DIR/blobs/

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +30 -delete

echo "Backup complete: $BACKUP_DIR"
```

Add to crontab: `0 2 * * * /opt/fnews/scripts/backup.sh`

### Restore

```bash
# Stop services
cd infra && docker compose down

# Restore database
gunzip -c /var/backups/fnews/db_YYYYMMDD_HHMMSS.sql.gz | \
  docker exec -i fnews-db psql -U fnews fnews

# Restore blobs
rsync -a /var/backups/fnews/blobs/ /data/blobs/

# Start services
docker compose up -d
```

---

## Audit Logs

All sensitive operations are recorded in the `audit_logs` table:

```sql
SELECT timestamp, event_type, actor, details
FROM audit_logs
ORDER BY timestamp DESC
LIMIT 100;
```

---

## TLS / HTTPS

For any internet-facing deployment:
1. Use Caddy (auto TLS) or Certbot + Nginx
2. Never expose HTTP without TLS on public networks
3. Set `SECURE_COOKIES=true` if adding a web UI with sessions

---

## Inbound Email Security

- Only process emails from `trusted_senders` (configured as `EMAIL_TO` by default)
- Use IMAP with SSL (`IMAP_PORT=993`)
- Use app-specific passwords, not primary account passwords
- Never process attachments (not implemented by design)

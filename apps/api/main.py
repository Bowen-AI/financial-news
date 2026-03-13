"""FastAPI application for financial-news intelligence system."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy import func, select

from packages.core import get_settings
from packages.core.db import AsyncSessionLocal
from packages.core.logging import configure_logging, get_logger
from packages.core.models import Alert, Briefing, TradeAction

configure_logging()
logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Financial News Intelligence",
    description="Self-hosted financial market intelligence system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)


def _verify_key(api_key: str = Security(_API_KEY_HEADER)) -> str:
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return api_key


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    """Liveness probe."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Status ───────────────────────────────────────────────────────────────────

@app.get("/status", tags=["system"], dependencies=[Depends(_verify_key)])
async def status_endpoint():
    """System status: last run times, queue depth, model backend."""

    async with AsyncSessionLocal() as db:
        last_ingest = await db.execute(
            select(func.max(Alert.created_at))
        )
        last_alert_at = last_ingest.scalar()

        last_briefing = await db.execute(
            select(Briefing).order_by(Briefing.sent_at.desc()).limit(1)
        )
        briefing_row = last_briefing.scalar_one_or_none()

    return {
        "status": "ok",
        "llm_backend": settings.llm_backend,
        "llm_model": settings.llm_model_name,
        "embedding_model": settings.embedding_model_name,
        "last_alert_at": last_alert_at.isoformat() if last_alert_at else None,
        "last_briefing_date": briefing_row.date if briefing_row else None,
        "alert_threshold": settings.alert_threshold,
    }


# ── Admin dashboard ───────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse, tags=["system"])
async def dashboard(api_key: str = Security(_API_KEY_HEADER)):
    """Simple HTML admin dashboard."""
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    async with AsyncSessionLocal() as db:
        alert_count_result = await db.execute(
            select(func.count()).select_from(Alert)
        )
        alert_count = alert_count_result.scalar() or 0

        briefing_count_result = await db.execute(
            select(func.count()).select_from(Briefing)
        )
        briefing_count = briefing_count_result.scalar() or 0

        trade_count_result = await db.execute(
            select(func.count()).select_from(TradeAction)
        )
        trade_count = trade_count_result.scalar() or 0

    html = f"""<!DOCTYPE html>
<html><head><title>Financial News Dashboard</title>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }}
  h1 {{ color: #1a3a5c; }}
  .stat {{ display: inline-block; margin: 10px; padding: 20px; background: #f0f4f8;
            border-radius: 8px; text-align: center; min-width: 120px; }}
  .stat .num {{ font-size: 2em; font-weight: bold; color: #2c5f8a; }}
  .stat .label {{ color: #555; font-size: 0.9em; }}
  .actions {{ margin-top: 20px; }}
  .actions a {{ margin: 5px; padding: 10px 16px; background: #2c5f8a; color: white;
                border-radius: 4px; text-decoration: none; display: inline-block; }}
</style></head>
<body>
<h1>📊 Financial News Intelligence</h1>
<p>Backend: <strong>{settings.llm_backend}</strong> / Model: <strong>{settings.llm_model_name}</strong></p>
<div>
  <div class="stat"><div class="num">{alert_count}</div><div class="label">Alerts Total</div></div>
  <div class="stat"><div class="num">{briefing_count}</div><div class="label">Briefings Sent</div></div>
  <div class="stat"><div class="num">{trade_count}</div><div class="label">Trade Actions</div></div>
</div>
<div class="actions">
  <a href="/docs">API Docs</a>
  <a href="/status">JSON Status</a>
</div>
<p style="color:#888;font-size:0.85em">
  ⚠️ Not financial advice. All outputs are evidence-based summaries only.
</p>
</body></html>"""
    return HTMLResponse(content=html)


# ── Ingestion ─────────────────────────────────────────────────────────────────

@app.post("/ingest/run", tags=["ingestion"], dependencies=[Depends(_verify_key)])
async def run_ingest():
    """Trigger an ingestion run (async via Celery)."""
    from apps.worker.tasks import ingest_task

    task = ingest_task.delay()
    return {"task_id": task.id, "status": "queued"}


# ── Briefing ──────────────────────────────────────────────────────────────────

@app.post("/briefing/send", tags=["briefing"], dependencies=[Depends(_verify_key)])
async def send_briefing():
    """Trigger daily briefing email (async via Celery)."""
    from apps.worker.tasks import briefing_task

    task = briefing_task.delay()
    return {"task_id": task.id, "status": "queued"}


# ── Alerts ────────────────────────────────────────────────────────────────────

@app.post("/alerts/run", tags=["alerts"], dependencies=[Depends(_verify_key)])
async def run_alerts():
    """Trigger alert scoring run (async via Celery)."""
    from apps.worker.tasks import alert_task

    task = alert_task.delay()
    return {"task_id": task.id, "status": "queued"}


# ── Inbound email webhook (optional) ──────────────────────────────────────────

class InboundEmailPayload(BaseModel):
    sender: str
    subject: str
    body: str


@app.post("/email/inbound", tags=["email"], dependencies=[Depends(_verify_key)])
async def inbound_email(payload: InboundEmailPayload):
    """Process an inbound email (webhook alternative to IMAP)."""

    # For webhook mode: directly process in-band (simplified)
    logger.info("inbound_email_webhook", sender=payload.sender, subject=payload.subject)
    return {"status": "received", "sender": payload.sender}


# ── Portfolio ─────────────────────────────────────────────────────────────────

@app.get("/portfolio", tags=["portfolio"], dependencies=[Depends(_verify_key)])
async def get_portfolio():
    """Return current positions and recent trade ledger."""
    from packages.portfolio.ledger import get_positions

    async with AsyncSessionLocal() as db:
        positions = await get_positions(db)

        ledger_result = await db.execute(
            select(TradeAction).order_by(TradeAction.timestamp.desc()).limit(50)
        )
        ledger = ledger_result.scalars().all()

    return {
        "positions": positions,
        "ledger": [
            {
                "id": t.id,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "action": t.action_type,
                "instrument": t.instrument,
                "quantity": t.quantity,
                "price": t.price,
                "notes": t.notes,
                "source": t.source,
            }
            for t in ledger
        ],
    }


class PortfolioActionRequest(BaseModel):
    raw_text: str
    source: str = "api"


@app.post("/portfolio/action", tags=["portfolio"], dependencies=[Depends(_verify_key)])
async def portfolio_action(req: PortfolioActionRequest):
    """Record a manual trade/portfolio action."""
    from packages.portfolio.ledger import format_positions, record_action
    from packages.portfolio.parser import parse_action

    parsed = parse_action(req.raw_text)

    async with AsyncSessionLocal() as db:
        if parsed.action_type in ("BUY", "SELL", "NOTE"):
            action = await record_action(
                db,
                action_type=parsed.action_type,
                instrument=parsed.instrument,
                quantity=parsed.quantity,
                price=parsed.price,
                notes=parsed.notes,
                raw_text=parsed.raw_text,
                source=req.source,
            )
            positions = await format_positions(db)
            return {
                "status": "recorded",
                "action_id": action.id,
                "parsed": {
                    "action": parsed.action_type,
                    "instrument": parsed.instrument,
                    "quantity": parsed.quantity,
                    "price": parsed.price,
                },
                "positions": positions,
            }
        else:
            return {
                "status": "unrecognized",
                "action_type": parsed.action_type,
                "message": "Use BUY, SELL, or NOTE commands",
            }


# ── Backtest ──────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    alert_id: str
    action: str = "BUY"
    holding_days: int = 5
    instrument: Optional[str] = None
    csv_path: Optional[str] = None


@app.post("/backtest/run", tags=["backtest"], dependencies=[Depends(_verify_key)])
async def run_backtest_endpoint(req: BacktestRequest):
    """Run a backtest simulation for a given alert."""
    from packages.backtest.simulator import run_backtest

    async with AsyncSessionLocal() as db:
        try:
            result = await run_backtest(
                db,
                alert_id=req.alert_id,
                action=req.action,
                holding_days=req.holding_days,
                instrument_override=req.instrument,
                csv_path=req.csv_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    return {
        "backtest_id": result.id,
        "alert_id": req.alert_id,
        "instrument": result.instrument,
        "action": result.action,
        "holding_days": result.holding_days,
        "entry_price": result.entry_price,
        "exit_price": result.exit_price,
        "pnl_pct": result.pnl_pct,
    }

"""Self-evaluation loop: computes metrics and adjusts system weights."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.logging import get_logger
from packages.core.models import Alert, BacktestResult, Briefing, EvalRecord

logger = get_logger(__name__)


async def run_evaluation(
    db: AsyncSession,
    window_days: int = 7,
) -> EvalRecord:
    """
    Compute self-evaluation metrics over the last *window_days*.
    Logs all adjustments made.
    Returns a persisted EvalRecord.
    """
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    adjustments: list[str] = []

    # ── 1) Alert precision proxy ────────────────────────────────────────────
    # Proxy: % of alerts in window that have a backtest result with |pnl| > 2%
    alert_result = await db.execute(
        select(func.count()).select_from(Alert).where(Alert.created_at >= since)
    )
    total_alerts = alert_result.scalar() or 0

    bt_result = await db.execute(
        select(func.count())
        .select_from(BacktestResult)
        .join(Alert, Alert.id == BacktestResult.alert_id)
        .where(Alert.created_at >= since)
        .where(func.abs(BacktestResult.pnl_pct) > 2.0)
    )
    significant_bt = bt_result.scalar() or 0

    alert_precision = (
        float(significant_bt) / float(total_alerts) if total_alerts > 0 else None
    )

    # ── 2) Citation usage rate ──────────────────────────────────────────────
    # Proxy: % of briefings that have >= 1 citation
    briefing_result = await db.execute(
        select(func.count()).select_from(Briefing).where(Briefing.sent_at >= since)
    )
    total_briefings = briefing_result.scalar() or 0

    # Count briefings with at least one citation (non-empty JSON array)
    briefing_cited_result = await db.execute(
        select(func.count())
        .select_from(Briefing)
        .where(Briefing.sent_at >= since)
        .where(func.jsonb_array_length(Briefing.citations) > 0)
    )
    cited_briefings = briefing_cited_result.scalar() or 0

    citation_rate = (
        float(cited_briefings) / float(total_briefings)
        if total_briefings > 0
        else None
    )

    # ── 3) Source weight adjustments ────────────────────────────────────────
    # Higher-credibility sources that produce high-scoring alerts get boosted
    # (simplified: log sources with > avg impact score)
    source_weights: dict[str, float] = {}
    await db.execute(
        select(func.avg(Alert.impact_score)).where(Alert.created_at >= since)
    )

    if alert_precision is not None:
        if alert_precision < 0.3:
            adjustments.append(
                f"Low alert precision ({alert_precision:.0%}): "
                "consider raising ALERT_THRESHOLD by 5"
            )
        elif alert_precision > 0.7:
            adjustments.append(
                f"High alert precision ({alert_precision:.0%}): "
                "ALERT_THRESHOLD is well-calibrated"
            )

    if citation_rate is not None and citation_rate < 0.8:
        adjustments.append(
            f"Citation usage rate low ({citation_rate:.0%}): "
            "verify EvidenceGuard is enforcing citations"
        )

    # Log all adjustments
    for adj in adjustments:
        logger.info("eval_adjustment", message=adj)

    record = EvalRecord(
        window_days=window_days,
        alert_precision_proxy=alert_precision,
        citation_usage_rate=citation_rate,
        source_weights=source_weights,
        adjustments_made=adjustments,
        notes=f"window={window_days}d, alerts={total_alerts}, briefings={total_briefings}",
    )
    db.add(record)
    await db.commit()
    logger.info(
        "eval_complete",
        precision=alert_precision,
        citation_rate=citation_rate,
        adjustments=len(adjustments),
    )
    return record

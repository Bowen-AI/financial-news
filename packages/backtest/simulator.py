"""
Backtesting / event study simulator.

For MVP: accepts CSV price data or fetches from Yahoo Finance (optional).
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.logging import get_logger
from packages.core.models import Alert, BacktestResult

logger = get_logger(__name__)


async def _load_price_series(
    instrument: str,
    start: datetime,
    end: datetime,
    csv_path: Optional[str] = None,
) -> dict[str, float]:
    """
    Load daily close prices.
    If csv_path provided, reads date,close columns.
    Otherwise attempts yfinance (if installed).
    Returns {date_str: close_price}.
    """
    if csv_path:
        prices: dict[str, float] = {}
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                d = row.get("date") or row.get("Date") or ""
                c = row.get("close") or row.get("Close") or ""
                if d and c:
                    prices[d[:10]] = float(c)
        return prices

    # Attempt yfinance
    try:
        import yfinance as yf  # type: ignore

        ticker = yf.Ticker(instrument)
        hist = ticker.history(start=start.date(), end=end.date())
        return {str(d.date()): float(row["Close"]) for d, row in hist.iterrows()}
    except Exception as exc:
        logger.warning(
            "yfinance_unavailable",
            instrument=instrument,
            error=str(exc),
        )
        return {}


async def run_backtest(
    db: AsyncSession,
    alert_id: str,
    action: str,               # BUY | SELL
    holding_days: int = 5,
    instrument_override: Optional[str] = None,
    csv_path: Optional[str] = None,
) -> BacktestResult:
    """
    Simulate a trade on the alert date.
    Returns a BacktestResult (also persisted to DB).
    """
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise ValueError(f"Alert {alert_id!r} not found")

    # Determine instrument from alert entities or override
    instrument = instrument_override
    if not instrument and alert.entities:
        for ent in alert.entities:
            if len(ent) <= 5 and ent.isupper():
                instrument = ent
                break
    if not instrument:
        raise ValueError("Cannot determine instrument for backtest")

    event_date = alert.created_at or datetime.now(timezone.utc)
    exit_date = event_date + timedelta(days=holding_days)

    prices = await _load_price_series(instrument, event_date, exit_date, csv_path)

    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    sim_data: dict = {"prices": prices, "event_date": event_date.isoformat()}

    if prices:
        sorted_dates = sorted(prices.keys())
        # Find closest trading day at or after event
        for d in sorted_dates:
            if d >= event_date.date().isoformat():
                entry_price = prices[d]
                break
        # Find closest trading day at or before exit
        for d in reversed(sorted_dates):
            if d <= exit_date.date().isoformat():
                exit_price = prices[d]
                break

        if entry_price and exit_price and entry_price != 0:
            if action.upper() == "BUY":
                pnl_pct = (exit_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - exit_price) / entry_price * 100

    bt = BacktestResult(
        alert_id=alert_id,
        instrument=instrument,
        action=action.upper(),
        holding_days=holding_days,
        entry_price=entry_price,
        exit_price=exit_price,
        pnl_pct=pnl_pct,
        simulation_data=sim_data,
    )
    db.add(bt)
    await db.commit()

    logger.info(
        "backtest_complete",
        alert_id=alert_id,
        instrument=instrument,
        action=action,
        pnl_pct=pnl_pct,
    )
    return bt

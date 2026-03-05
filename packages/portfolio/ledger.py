"""Portfolio ledger operations."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.logging import get_logger
from packages.core.models import TradeAction

logger = get_logger(__name__)

HELP_TEXT = """Available commands:
  BUY <qty> <ticker> [@ <price>]   Record a buy
  SELL <qty> <ticker> [@ <price>]  Record a sell
  NOTE: <text>                     Record a note
  POSITION                         View current positions
  HELP                             This message
"""


async def record_action(
    db: AsyncSession,
    action_type: str,
    instrument: Optional[str],
    quantity: Optional[float],
    price: Optional[float],
    notes: Optional[str],
    raw_text: str,
    source: str = "email",
) -> TradeAction:
    """Persist a trade action to the ledger."""
    action = TradeAction(
        action_type=action_type,
        instrument=instrument,
        quantity=quantity,
        price=price,
        notes=notes,
        raw_text=raw_text,
        source=source,
    )
    db.add(action)
    await db.commit()
    logger.info(
        "trade_recorded",
        action=action_type,
        instrument=instrument,
        qty=quantity,
        price=price,
    )
    return action


async def get_positions(db: AsyncSession) -> dict[str, dict]:
    """
    Compute current positions as {instrument: {qty, avg_cost, trades}}.
    Simple FIFO / running-average cost basis.
    """
    result = await db.execute(
        select(TradeAction)
        .where(TradeAction.action_type.in_(["BUY", "SELL"]))
        .order_by(TradeAction.timestamp)
    )
    actions = result.scalars().all()

    positions: dict[str, dict] = defaultdict(
        lambda: {"quantity": 0.0, "avg_cost": None, "trades": 0}
    )

    for action in actions:
        inst = action.instrument
        if not inst:
            continue
        pos = positions[inst]
        if action.action_type == "BUY":
            # Update avg cost if price provided
            if action.price is not None:
                old_qty = pos["quantity"]
                old_cost = pos["avg_cost"] or action.price
                new_qty = old_qty + (action.quantity or 0)
                if new_qty > 0:
                    pos["avg_cost"] = (
                        old_qty * old_cost + (action.quantity or 0) * action.price
                    ) / new_qty
            pos["quantity"] = pos["quantity"] + (action.quantity or 0)
        elif action.action_type == "SELL":
            pos["quantity"] = pos["quantity"] - (action.quantity or 0)
        pos["trades"] += 1

    return {k: dict(v) for k, v in positions.items() if v["quantity"] != 0}


async def format_positions(db: AsyncSession) -> str:
    """Return a human-readable position summary."""
    positions = await get_positions(db)
    if not positions:
        return "No open positions."
    lines = [f"{'Instrument':<12} {'Qty':>8} {'Avg Cost':>10}"]
    lines.append("-" * 34)
    for inst, pos in sorted(positions.items()):
        qty = pos["quantity"]
        cost = f"{pos['avg_cost']:.2f}" if pos["avg_cost"] else "N/A"
        lines.append(f"{inst:<12} {qty:>8.2f} {cost:>10}")
    return "\n".join(lines)

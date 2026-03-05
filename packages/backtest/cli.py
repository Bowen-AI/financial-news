"""Backtest CLI entry point."""
from __future__ import annotations

import argparse
import asyncio

from packages.core.db import AsyncSessionLocal


async def _run(args: argparse.Namespace) -> None:
    from packages.backtest.simulator import run_backtest

    async with AsyncSessionLocal() as db:
        result = await run_backtest(
            db=db,
            alert_id=args.alert_id,
            action=args.action,
            holding_days=args.holding_days,
            instrument_override=args.instrument,
            csv_path=args.csv,
        )
    print(f"Backtest result for alert {args.alert_id}")
    print(f"  Instrument : {result.instrument}")
    print(f"  Action     : {result.action}")
    print(f"  Holding    : {result.holding_days} days")
    print(f"  Entry price: {result.entry_price}")
    print(f"  Exit price : {result.exit_price}")
    pnl = f"{result.pnl_pct:.2f}%" if result.pnl_pct is not None else "N/A"
    print(f"  P&L        : {pnl}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Financial News Backtester")
    parser.add_argument("--alert-id", required=True, help="Alert UUID")
    parser.add_argument(
        "--action", required=True, choices=["BUY", "SELL"], help="Simulated action"
    )
    parser.add_argument("--holding-days", type=int, default=5)
    parser.add_argument("--instrument", default=None, help="Override ticker symbol")
    parser.add_argument("--csv", default=None, help="Path to CSV price file")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

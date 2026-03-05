"""Trade email/command parser.

Supported commands:
  BUY <qty> <instrument> [@ <price>]
  SELL <qty> <instrument> [@ <price>]
  NOTE: <free text>
  POSITION
  HELP
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedAction:
    action_type: str           # BUY | SELL | NOTE | POSITION | QUESTION | HELP
    instrument: Optional[str]
    quantity: Optional[float]
    price: Optional[float]
    notes: Optional[str]
    raw_text: str


_BUY_SELL_RE = re.compile(
    r"^(BUY|SELL)\s+"
    r"(\d+(?:\.\d+)?)\s+"
    r"([A-Z]{1,10})"
    r"(?:\s+@\s*(\d+(?:\.\d+)?))?",
    re.IGNORECASE,
)

_NOTE_RE = re.compile(r"^NOTE\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)
_POSITION_RE = re.compile(r"^POSITION\s*$", re.IGNORECASE)
_HELP_RE = re.compile(r"^HELP\s*$", re.IGNORECASE)


def parse_action(text: str) -> ParsedAction:
    """
    Parse a trade command from free-form text.
    Attempts to match the first command-like line.
    """
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        m = _BUY_SELL_RE.match(line)
        if m:
            action = m.group(1).upper()
            qty = float(m.group(2))
            instrument = m.group(3).upper()
            price = float(m.group(4)) if m.group(4) else None
            return ParsedAction(
                action_type=action,
                instrument=instrument,
                quantity=qty,
                price=price,
                notes=None,
                raw_text=text,
            )

        m = _NOTE_RE.match(line)
        if m:
            return ParsedAction(
                action_type="NOTE",
                instrument=None,
                quantity=None,
                price=None,
                notes=m.group(1).strip(),
                raw_text=text,
            )

        if _POSITION_RE.match(line):
            return ParsedAction(
                action_type="POSITION",
                instrument=None,
                quantity=None,
                price=None,
                notes=None,
                raw_text=text,
            )

        if _HELP_RE.match(line):
            return ParsedAction(
                action_type="HELP",
                instrument=None,
                quantity=None,
                price=None,
                notes=None,
                raw_text=text,
            )

    # Treat as a question for Q&A
    return ParsedAction(
        action_type="QUESTION",
        instrument=None,
        quantity=None,
        price=None,
        notes=text.strip(),
        raw_text=text,
    )

"""Entity extraction: detect tickers and named entities in text."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Commonly confused uppercase words that are NOT tickers
_NON_TICKER_WORDS = {
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER",
    "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW",
    "MAN", "NEW", "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "BOY", "DID",
    "ITS", "LET", "PUT", "SAY", "SHE", "TOO", "USE", "CEO", "CFO", "COO",
    "IPO", "GDP", "CPI", "FED", "SEC", "ETF", "ETN", "USA", "USD", "EUR",
    "GBP", "JPY", "OIL", "GAS", "API", "Q1", "Q2", "Q3", "Q4", "AI",
    "ESG", "SPX", "DJI", "NDX", "YOY", "QOQ", "MOM",
}

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")

# High-impact magnitude words that boost event scores
MAGNITUDE_WORDS = {
    "halted", "halt", "sanctions", "sanctioned", "miss", "beat",
    "guidance", "cut", "raised", "lowered", "bankruptcy", "bankrupt",
    "recall", "fraud", "investigation", "acquisition", "merger",
    "spinoff", "layoff", "layoffs", "surge", "plunge", "crash",
    "rally", "default", "downgrade", "upgrade", "lawsuit", "settlement",
    "warning", "alert", "emergency", "crisis", "collapse",
}


@dataclass
class ExtractedEntities:
    tickers: list[str]
    magnitude_words: list[str]
    watchlist_matches: list[str]


def extract_entities(
    text: str,
    watchlist_tickers: list[str] | None = None,
    watchlist_entities: list[str] | None = None,
) -> ExtractedEntities:
    """
    Extract ticker symbols and magnitude language from *text*.
    Matches against optional watchlist for relevance scoring.
    """
    tickers = list(
        {
            m
            for m in _TICKER_RE.findall(text)
            if m not in _NON_TICKER_WORDS and len(m) >= 2
        }
    )

    text_lower = text.lower()
    found_magnitude = [w for w in MAGNITUDE_WORDS if w in text_lower]

    watchlist_matches: list[str] = []
    for ticker in watchlist_tickers or []:
        if re.search(rf"\b{re.escape(ticker)}\b", text):
            watchlist_matches.append(ticker)
    for entity in watchlist_entities or []:
        if entity.lower() in text_lower:
            watchlist_matches.append(entity)

    return ExtractedEntities(
        tickers=tickers,
        magnitude_words=found_magnitude,
        watchlist_matches=list(set(watchlist_matches)),
    )

"""Source configuration loader."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SourceConfig:
    name: str
    type: str            # rss | http | playwright
    url: str
    credibility: float = 0.7
    enabled: bool = True
    headers: dict = field(default_factory=dict)


def load_sources(path: str | Path) -> list[SourceConfig]:
    """Load source definitions from a YAML file."""
    data = yaml.safe_load(Path(path).read_text())
    return [
        SourceConfig(**{k: v for k, v in src.items()})
        for src in data.get("sources", [])
        if src.get("enabled", True)
    ]


@dataclass
class WatchlistConfig:
    tickers: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


def load_watchlist(path: str | Path) -> WatchlistConfig:
    """Load watchlist from YAML."""
    data = yaml.safe_load(Path(path).read_text())
    wl = data.get("watchlist", {})
    return WatchlistConfig(
        tickers=[t.upper() for t in wl.get("tickers", [])],
        entities=wl.get("entities", []),
    )

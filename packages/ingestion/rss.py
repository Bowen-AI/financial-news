"""RSS feed reader with deduplication."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import feedparser

from packages.core.logging import get_logger
from packages.ingestion.fetcher import FetchResult, fetch_url

logger = get_logger(__name__)


async def ingest_rss(url: str, credibility: float = 0.7) -> list[FetchResult]:
    """Parse an RSS/Atom feed and fetch each entry's full page content."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            feed_text = resp.text
    except Exception as exc:
        logger.warning("rss_fetch_failed", url=url, error=str(exc))
        return []

    feed = feedparser.parse(feed_text)
    results: list[FetchResult] = []

    for entry in feed.entries[:20]:  # cap at 20 entries per feed
        link = getattr(entry, "link", None)
        if not link:
            continue
        result = await fetch_url(link)
        if result is None:
            # fall back to feed summary
            summary = getattr(entry, "summary", "") or ""
            title = getattr(entry, "title", None)
            pub_at: Optional[datetime] = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            result = FetchResult(
                url=link,
                html=b"",
                text=summary,
                title=title,
                author=None,
                published_at=pub_at,
                fetched_at=datetime.now(timezone.utc),
            )
        results.append(result)

    logger.info("rss_ingested", url=url, count=len(results))
    return results

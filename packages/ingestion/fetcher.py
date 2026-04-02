"""HTTP fetcher with robots.txt respect and trafilatura text extraction."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from packages.core.logging import get_logger

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": "FinancialNewsBot/1.0 (+https://github.com/Bowen-AI/financial-news)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_robots_cache: dict[str, RobotFileParser] = {}
_robots_lock = asyncio.Lock()


async def _get_robots(base_url: str, client: httpx.AsyncClient) -> RobotFileParser:
    """Fetch and cache robots.txt for a domain."""
    if base_url not in _robots_cache:
        async with _robots_lock:
            if base_url not in _robots_cache:
                rp = RobotFileParser()
                robots_url = urljoin(base_url, "/robots.txt")
                try:
                    resp = await client.get(robots_url, timeout=5)
                    rp.parse(resp.text.splitlines())
                except Exception:
                    rp.allow_all = True
                _robots_cache[base_url] = rp
    return _robots_cache[base_url]


def _base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


class FetchResult:
    def __init__(
        self,
        url: str,
        html: bytes,
        text: str,
        title: Optional[str],
        author: Optional[str],
        published_at: Optional[datetime],
        fetched_at: datetime,
    ) -> None:
        self.url = url
        self.html = html
        self.text = text
        self.title = title
        self.author = author
        self.published_at = published_at
        self.fetched_at = fetched_at
        self.content_hash = hashlib.sha256(
            self.text.strip().lower().encode()
        ).hexdigest()


async def fetch_url(
    url: str,
    extra_headers: dict | None = None,
    respect_robots: bool = True,
) -> FetchResult | None:
    """Fetch a URL, respect robots.txt, extract text via trafilatura."""
    async with httpx.AsyncClient(
        headers={**_HEADERS, **(extra_headers or {})},
        follow_redirects=True,
        timeout=20,
    ) as client:
        if respect_robots:
            rp = await _get_robots(_base_url(url), client)
            if not rp.can_fetch(_HEADERS["User-Agent"], url):
                logger.warning("robots_disallowed", url=url)
                return None

        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("fetch_failed", url=url, error=str(exc))
            return None

        html = resp.content
        fetched_at = datetime.now(timezone.utc)

        # Extract main text with trafilatura
        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            output_format="txt",
        )
        metadata = trafilatura.extract_metadata(html, default_url=url)
        text = extracted or ""
        title = metadata.title if metadata else None
        author = metadata.author if metadata else None

        pub_at: Optional[datetime] = None
        if metadata and metadata.date:
            try:
                from dateutil.parser import parse as dateparse
                pub_at = dateparse(metadata.date).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        return FetchResult(
            url=url,
            html=html,
            text=text,
            title=title,
            author=author,
            published_at=pub_at,
            fetched_at=fetched_at,
        )

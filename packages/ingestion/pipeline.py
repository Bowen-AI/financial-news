"""Main ingestion pipeline: fetch → dedup → store articles."""
from __future__ import annotations


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.logging import get_logger
from packages.core.models import Article
from packages.ingestion.blob_store import BlobStore
from packages.ingestion.dedup import canonical_url, content_hash, excerpt_hash
from packages.ingestion.fetcher import FetchResult, fetch_url
from packages.ingestion.rss import ingest_rss
from packages.ingestion.sources import SourceConfig, load_sources

logger = get_logger(__name__)


async def _fetch_source(src: SourceConfig) -> list[FetchResult]:
    if src.type == "rss":
        return await ingest_rss(src.url, src.credibility)
    elif src.type == "http":
        result = await fetch_url(src.url, extra_headers=src.headers)
        return [result] if result else []
    else:
        logger.warning("unsupported_source_type", type=src.type, name=src.name)
        return []


async def run_ingestion(
    db: AsyncSession,
    source_config_path: str,
    blob_store_path: str,
) -> dict:
    """Run a full ingestion cycle.  Returns summary stats."""
    sources = load_sources(source_config_path)
    blob = BlobStore(blob_store_path)

    new_articles = 0
    skipped = 0

    for src in sources:
        logger.info("ingesting_source", name=src.name, type=src.type)
        results = await _fetch_source(src)

        for result in results:
            if not result.text.strip():
                continue

            can_url = canonical_url(result.url)
            chash = content_hash(result.text)

            # Dedup check
            existing = await db.execute(
                select(Article).where(Article.canonical_url == can_url)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            # Also check by content hash
            existing_hash = await db.execute(
                select(Article).where(Article.content_hash == chash)
            )
            if existing_hash.scalar_one_or_none():
                skipped += 1
                continue

            # Store raw HTML blob
            raw_path: str | None = None
            if result.html:
                raw_path = blob.put(result.html)

            article = Article(
                url=result.url,
                canonical_url=can_url,
                content_hash=chash,
                title=result.title,
                author=result.author,
                source_name=src.name,
                source_credibility=src.credibility,
                published_at=result.published_at,
                fetched_at=result.fetched_at,
                raw_html_path=raw_path,
                extracted_text=result.text,
                excerpt_hash=excerpt_hash(result.text),
            )
            db.add(article)
            new_articles += 1

    await db.commit()
    logger.info(
        "ingestion_complete",
        new=new_articles,
        skipped=skipped,
        sources=len(sources),
    )
    return {"new_articles": new_articles, "skipped": skipped, "sources": len(sources)}

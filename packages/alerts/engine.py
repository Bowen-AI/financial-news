"""Alert engine: score recent articles, fire alerts above threshold."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.alerts.scorer import ScoredArticle, score_article
from packages.core.logging import get_logger
from packages.core.models import Alert, AlertSource, Article
from packages.ingestion.sources import WatchlistConfig
from packages.rag.embedder import EmbeddingModel
from packages.rag.evidence_guard import EvidenceGuard
from packages.rag.retriever import hybrid_search

logger = get_logger(__name__)


async def run_alert_engine(
    db: AsyncSession,
    embedder: EmbeddingModel,
    guard: EvidenceGuard,
    watchlist: WatchlistConfig,
    threshold: int = 70,
    min_sources: int = 2,
    lookback_hours: int = 4,
) -> list[Alert]:
    """
    Score articles ingested in the last *lookback_hours*, fire alerts when
    score >= threshold and the article appears confirmed by >= min_sources.

    Returns newly created Alert objects.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    result = await db.execute(
        select(Article)
        .where(Article.fetched_at >= since)
        .order_by(Article.fetched_at.desc())
    )
    articles = result.scalars().all()

    if not articles:
        logger.info("no_recent_articles_for_alert")
        return []

    scored = [
        score_article(
            a,
            watchlist_tickers=watchlist.tickers,
            watchlist_entities=watchlist.entities,
        )
        for a in articles
    ]

    # Group by approximate topic (simple title-word overlap)
    # Only fire if score >= threshold
    candidates = [s for s in scored if s.score >= threshold]

    if not candidates:
        logger.info("no_high_score_articles", threshold=threshold)
        return []

    fired: list[Alert] = []

    for scored_art in candidates:
        headline = scored_art.article.title or "Untitled event"

        # Retrieve corroborating chunks
        chunks = await hybrid_search(db, headline, embedder, top_k=10)

        # Filter chunks to sources that are not the article itself
        corroborating = [
            c for c in chunks if c.article_id != scored_art.article.id
        ]
        confirmed_source_count = len({c.article_id for c in corroborating}) + 1  # +1 for primary

        if confirmed_source_count < min_sources:
            logger.info(
                "alert_insufficient_sources",
                headline=headline,
                sources=confirmed_source_count,
                min=min_sources,
            )
            continue

        # Build alert via EvidenceGuard
        try:
            all_chunks = chunks[:10]  # use primary + corroborating
            response = await guard.alert(headline, all_chunks)
        except Exception as exc:
            logger.error("evidence_guard_failed", error=str(exc))
            continue

        alert = Alert(
            headline=headline,
            summary="\n".join(
                item
                for section in response.summary_sections
                for item in section.get("items", [])
                if isinstance(item, str)
            ),
            impact_score=scored_art.score,
            entities=scored_art.entities.watchlist_matches + scored_art.entities.tickers,
            citations=response.citations,
            source_count=confirmed_source_count,
        )
        db.add(alert)
        await db.flush()  # get alert.id

        # Link sources
        db.add(
            AlertSource(
                alert_id=alert.id,
                article_id=scored_art.article.id,
            )
        )
        for c in corroborating[:min_sources]:
            db.add(
                AlertSource(
                    alert_id=alert.id,
                    article_id=c.article_id,
                )
            )

        fired.append(alert)
        logger.info(
            "alert_created",
            alert_id=alert.id,
            score=scored_art.score,
            headline=headline,
        )

    await db.commit()
    return fired

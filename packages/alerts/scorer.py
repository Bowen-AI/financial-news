"""Event scoring engine: assigns 0-100 impact score to articles."""
from __future__ import annotations

from dataclasses import dataclass

from packages.alerts.entity_extractor import ExtractedEntities, extract_entities
from packages.core.models import Article


@dataclass
class ScoredArticle:
    article: Article
    score: int
    entities: ExtractedEntities
    reasons: list[str]


def score_article(
    article: Article,
    watchlist_tickers: list[str] | None = None,
    watchlist_entities: list[str] | None = None,
) -> ScoredArticle:
    """
    Compute impact score (0-100) for a single article.

    Factors:
    - Source credibility (0-20 pts)
    - Magnitude language (0-25 pts)
    - Watchlist relevance (0-35 pts)
    - Title signal (0-10 pts)
    - Publication recency bonus (0-10 pts, placeholder – always 5)
    """
    text = (article.extracted_text or "") + " " + (article.title or "")
    entities = extract_entities(
        text,
        watchlist_tickers=watchlist_tickers,
        watchlist_entities=watchlist_entities,
    )
    reasons: list[str] = []
    score = 0

    # 1) Source credibility
    cred_pts = int(article.source_credibility * 20)
    score += cred_pts
    reasons.append(f"credibility={article.source_credibility:.1f} (+{cred_pts})")

    # 2) Magnitude language
    mag_pts = min(len(entities.magnitude_words) * 8, 25)
    score += mag_pts
    if entities.magnitude_words:
        reasons.append(f"magnitude_words={entities.magnitude_words} (+{mag_pts})")

    # 3) Watchlist relevance
    watch_pts = min(len(entities.watchlist_matches) * 12, 35)
    score += watch_pts
    if entities.watchlist_matches:
        reasons.append(f"watchlist={entities.watchlist_matches} (+{watch_pts})")

    # 4) Title signal
    if article.title:
        title_lower = article.title.lower()
        if any(w in title_lower for w in ("breaking", "alert", "halt", "crisis")):
            score += 10
            reasons.append("title_signal (+10)")

    # 5) Recency (placeholder)
    score += 5
    reasons.append("recency (+5)")

    return ScoredArticle(
        article=article,
        score=min(score, 100),
        entities=entities,
        reasons=reasons,
    )

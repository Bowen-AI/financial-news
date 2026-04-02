"""Hybrid retrieval: pgvector cosine + PostgreSQL BM25 (tsvector)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.logging import get_logger
from packages.rag.embedder import EmbeddingModel

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    article_id: str
    article_url: str
    article_title: Optional[str]
    source_name: str
    fetched_at: str
    text: str
    score: float
    excerpt_hash: Optional[str]


async def hybrid_search(
    db: AsyncSession,
    query: str,
    embedder: EmbeddingModel,
    top_k: int = 10,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
) -> list[RetrievedChunk]:
    """
    Hybrid retrieval combining pgvector cosine similarity and tsvector BM25.

    Returns up to *top_k* chunks ranked by a weighted combination.
    """
    query_vec = embedder.embed_one(query)
    vec_str = "[" + ",".join(str(x) for x in query_vec) + "]"

    # Vector search
    vector_sql = text(
        """
        SELECT
            c.id            AS chunk_id,
            c.article_id,
            c.text,
            a.url           AS article_url,
            a.title         AS article_title,
            a.source_name,
            a.excerpt_hash,
            a.fetched_at::text,
            1 - (c.embedding <=> :vec::vector) AS vec_score
        FROM chunks c
        JOIN articles a ON a.id = c.article_id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> :vec::vector
        LIMIT :limit
        """
    )

    vec_rows = (
        await db.execute(vector_sql, {"vec": vec_str, "limit": top_k * 2})
    ).fetchall()

    # BM25 / full-text search
    bm25_sql = text(
        """
        SELECT
            c.id            AS chunk_id,
            c.article_id,
            c.text,
            a.url           AS article_url,
            a.title         AS article_title,
            a.source_name,
            a.excerpt_hash,
            a.fetched_at::text,
            ts_rank_cd(to_tsvector('english', c.text),
                       plainto_tsquery('english', :query)) AS bm25_score
        FROM chunks c
        JOIN articles a ON a.id = c.article_id
        WHERE to_tsvector('english', c.text) @@ plainto_tsquery('english', :query)
        ORDER BY bm25_score DESC
        LIMIT :limit
        """
    )

    bm25_rows = (
        await db.execute(bm25_sql, {"query": query, "limit": top_k * 2})
    ).fetchall()

    # Merge scores
    scores: dict[str, dict] = {}

    for row in vec_rows:
        cid = row.chunk_id
        scores[cid] = {
            "chunk_id": cid,
            "article_id": row.article_id,
            "article_url": row.article_url,
            "article_title": row.article_title,
            "source_name": row.source_name,
            "excerpt_hash": row.excerpt_hash,
            "fetched_at": row.fetched_at,
            "text": row.text,
            "vec_score": float(row.vec_score),
            "bm25_score": 0.0,
        }

    for row in bm25_rows:
        cid = row.chunk_id
        if cid in scores:
            scores[cid]["bm25_score"] = float(row.bm25_score)
        else:
            scores[cid] = {
                "chunk_id": cid,
                "article_id": row.article_id,
                "article_url": row.article_url,
                "article_title": row.article_title,
                "source_name": row.source_name,
                "excerpt_hash": row.excerpt_hash,
                "fetched_at": row.fetched_at,
                "text": row.text,
                "vec_score": 0.0,
                "bm25_score": float(row.bm25_score),
            }

    # Normalise BM25 scores to [0,1]
    max_bm25 = max((v["bm25_score"] for v in scores.values()), default=1.0) or 1.0
    for v in scores.values():
        v["combined"] = (
            vector_weight * v["vec_score"]
            + bm25_weight * v["bm25_score"] / max_bm25
        )

    ranked = sorted(scores.values(), key=lambda x: x["combined"], reverse=True)[:top_k]

    return [
        RetrievedChunk(
            chunk_id=r["chunk_id"],
            article_id=r["article_id"],
            article_url=r["article_url"],
            article_title=r["article_title"],
            source_name=r["source_name"],
            fetched_at=r["fetched_at"],
            text=r["text"],
            score=r["combined"],
            excerpt_hash=r["excerpt_hash"],
        )
        for r in ranked
    ]

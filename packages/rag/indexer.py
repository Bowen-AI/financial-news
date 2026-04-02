"""Indexing pipeline: chunk articles and store embeddings."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.logging import get_logger
from packages.core.models import Article, Chunk
from packages.rag.chunker import chunk_text
from packages.rag.embedder import EmbeddingModel

logger = get_logger(__name__)


async def index_unembedded_articles(
    db: AsyncSession,
    embedder: EmbeddingModel,
    chunk_size: int = 512,
    overlap: int = 64,
    batch_size: int = 50,
) -> int:
    """
    Find articles without chunks, chunk and embed them.
    Returns the number of newly indexed articles.
    """
    # Find articles with no chunks
    result = await db.execute(
        select(Article)
        .outerjoin(Chunk, Chunk.article_id == Article.id)
        .where(Chunk.id.is_(None))
        .where(Article.extracted_text.isnot(None))
        .limit(batch_size)
    )
    articles = result.scalars().all()

    if not articles:
        logger.debug("no_articles_to_index")
        return 0

    for article in articles:
        text = article.extracted_text or ""
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)

        if not chunks:
            continue

        # Embed all chunks in one batch
        embeddings = embedder.embed([c.text for c in chunks])

        for chunk_obj, vec in zip(chunks, embeddings):
            db_chunk = Chunk(
                article_id=article.id,
                chunk_index=chunk_obj.chunk_index,
                text=chunk_obj.text,
                embedding=vec,
            )
            db.add(db_chunk)

    await db.commit()
    logger.info("indexed_articles", count=len(articles))
    return len(articles)

"""SQLAlchemy ORM models for the financial-news system."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    __allow_unmapped__ = True


# ─── Articles ─────────────────────────────────────────────────────────────────

class Article(Base):
    """A deduplicated news article from any configured source."""

    __tablename__ = "articles"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    url: str = Column(Text, nullable=False)
    canonical_url: str = Column(Text, nullable=False, unique=True)
    content_hash: str = Column(String(64), nullable=False)
    title: Optional[str] = Column(Text)
    author: Optional[str] = Column(Text)
    source_name: str = Column(String(256), nullable=False)
    source_credibility: float = Column(Float, default=0.5)
    published_at: Optional[datetime] = Column(DateTime(timezone=True))
    fetched_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_html_path: Optional[str] = Column(Text)   # path in blob store
    extracted_text: Optional[str] = Column(Text)
    excerpt_hash: Optional[str] = Column(String(64))  # for citation verification

    chunks: list["Chunk"] = relationship("Chunk", back_populates="article", cascade="all, delete-orphan")
    alert_sources: list["AlertSource"] = relationship("AlertSource", back_populates="article")

    __table_args__ = (
        Index("ix_articles_fetched_at", "fetched_at"),
        Index("ix_articles_content_hash", "content_hash"),
    )


# ─── Chunks / RAG ─────────────────────────────────────────────────────────────

class Chunk(Base):
    """Text chunk derived from an article, with an embedding vector."""

    __tablename__ = "chunks"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    article_id: str = Column(
        UUID(as_uuid=False), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: int = Column(Integer, nullable=False)
    text: str = Column(Text, nullable=False)
    embedding = Column(Vector(384))  # dimension matches bge-small-en-v1.5

    article: Article = relationship("Article", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("article_id", "chunk_index", name="uq_chunk_article_index"),
        Index("ix_chunks_article_id", "article_id"),
    )


# ─── Alerts ───────────────────────────────────────────────────────────────────

class Alert(Base):
    """A fired alert with its impact score and affected entities."""

    __tablename__ = "alerts"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    headline: str = Column(Text, nullable=False)
    summary: str = Column(Text, nullable=False)
    impact_score: int = Column(Integer, nullable=False)
    entities: list = Column(JSONB, default=list)     # tickers/entities mentioned
    citations: list = Column(JSONB, default=list)    # citation dicts
    source_count: int = Column(Integer, default=1)
    sent_at: Optional[datetime] = Column(DateTime(timezone=True))
    created_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sources: list["AlertSource"] = relationship("AlertSource", back_populates="alert", cascade="all, delete-orphan")
    backtest_results: list["BacktestResult"] = relationship("BacktestResult", back_populates="alert")

    __table_args__ = (
        Index("ix_alerts_created_at", "created_at"),
        Index("ix_alerts_impact_score", "impact_score"),
    )


class AlertSource(Base):
    """Junction table linking an alert to its confirming articles."""

    __tablename__ = "alert_sources"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    alert_id: str = Column(
        UUID(as_uuid=False), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    article_id: str = Column(
        UUID(as_uuid=False), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )

    alert: Alert = relationship("Alert", back_populates="sources")
    article: Article = relationship("Article", back_populates="alert_sources")


# ─── Briefings ────────────────────────────────────────────────────────────────

class Briefing(Base):
    """A sent daily briefing email."""

    __tablename__ = "briefings"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    date: str = Column(String(10), nullable=False)   # YYYY-MM-DD
    subject: str = Column(Text, nullable=False)
    body_html: str = Column(Text, nullable=False)
    body_text: str = Column(Text, nullable=False)
    citations: list = Column(JSONB, default=list)
    sent_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_briefings_date", "date"),)


# ─── Portfolio ────────────────────────────────────────────────────────────────

class TradeAction(Base):
    """Ledger entry for a trade or portfolio note."""

    __tablename__ = "trade_actions"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    timestamp: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    action_type: str = Column(String(16), nullable=False)  # BUY | SELL | NOTE | POSITION
    instrument: Optional[str] = Column(String(32))
    quantity: Optional[float] = Column(Float)
    price: Optional[float] = Column(Float)
    notes: Optional[str] = Column(Text)
    raw_text: str = Column(Text, nullable=False)
    source: str = Column(String(32), default="email")  # email | api

    __table_args__ = (Index("ix_trade_actions_timestamp", "timestamp"),)


# ─── Backtest ─────────────────────────────────────────────────────────────────

class BacktestResult(Base):
    """Result of a simulated trade on a historical alert."""

    __tablename__ = "backtest_results"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    alert_id: str = Column(
        UUID(as_uuid=False), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    instrument: str = Column(String(32), nullable=False)
    action: str = Column(String(8), nullable=False)   # BUY | SELL
    holding_days: int = Column(Integer, nullable=False)
    entry_price: Optional[float] = Column(Float)
    exit_price: Optional[float] = Column(Float)
    pnl_pct: Optional[float] = Column(Float)
    simulation_data: dict = Column(JSONB, default=dict)
    created_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    alert: Alert = relationship("Alert", back_populates="backtest_results")


# ─── Self-evaluation ──────────────────────────────────────────────────────────

class EvalRecord(Base):
    """Recorded self-evaluation metric snapshot."""

    __tablename__ = "eval_records"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    evaluated_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    window_days: int = Column(Integer, nullable=False)
    alert_precision_proxy: Optional[float] = Column(Float)
    citation_usage_rate: Optional[float] = Column(Float)
    source_weights: dict = Column(JSONB, default=dict)
    adjustments_made: list = Column(JSONB, default=list)
    notes: Optional[str] = Column(Text)

    __table_args__ = (Index("ix_eval_records_evaluated_at", "evaluated_at"),)


# ─── Audit log ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """Immutable audit trail for sensitive operations."""

    __tablename__ = "audit_logs"

    id: str = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    timestamp: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event_type: str = Column(String(64), nullable=False)
    actor: str = Column(String(128), nullable=False, default="system")
    details: dict = Column(JSONB, default=dict)

    __table_args__ = (Index("ix_audit_logs_timestamp", "timestamp"),)

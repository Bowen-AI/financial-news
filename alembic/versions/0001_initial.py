"""Initial migration: create all tables with pgvector extension."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

VECTOR_DIM = 384


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── articles ────────────────────────────────────────────────────────────
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("canonical_url", sa.Text, nullable=False, unique=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("author", sa.Text),
        sa.Column("source_name", sa.String(256), nullable=False),
        sa.Column("source_credibility", sa.Float, default=0.5),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw_html_path", sa.Text),
        sa.Column("extracted_text", sa.Text),
        sa.Column("excerpt_hash", sa.String(64)),
    )
    op.create_index("ix_articles_fetched_at", "articles", ["fetched_at"])
    op.create_index("ix_articles_content_hash", "articles", ["content_hash"])

    # ── chunks ───────────────────────────────────────────────────────────────
    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(VECTOR_DIM)),
    )
    op.create_index("ix_chunks_article_id", "chunks", ["article_id"])
    op.create_unique_constraint("uq_chunk_article_index", "chunks", ["article_id", "chunk_index"])
    # HNSW index for fast ANN search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_embedding ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # ── alerts ───────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("impact_score", sa.Integer, nullable=False),
        sa.Column("entities", postgresql.JSONB, default=[]),
        sa.Column("citations", postgresql.JSONB, default=[]),
        sa.Column("source_count", sa.Integer, default=1),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_alerts_impact_score", "alerts", ["impact_score"])

    # ── alert_sources ────────────────────────────────────────────────────────
    op.create_table(
        "alert_sources",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("articles.id", ondelete="SET NULL")),
    )

    # ── briefings ────────────────────────────────────────────────────────────
    op.create_table(
        "briefings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body_html", sa.Text, nullable=False),
        sa.Column("body_text", sa.Text, nullable=False),
        sa.Column("citations", postgresql.JSONB, default=[]),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_briefings_date", "briefings", ["date"])

    # ── trade_actions ────────────────────────────────────────────────────────
    op.create_table(
        "trade_actions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("action_type", sa.String(16), nullable=False),
        sa.Column("instrument", sa.String(32)),
        sa.Column("quantity", sa.Float),
        sa.Column("price", sa.Float),
        sa.Column("notes", sa.Text),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("source", sa.String(32), default="email"),
    )
    op.create_index("ix_trade_actions_timestamp", "trade_actions", ["timestamp"])

    # ── backtest_results ─────────────────────────────────────────────────────
    op.create_table(
        "backtest_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instrument", sa.String(32), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("holding_days", sa.Integer, nullable=False),
        sa.Column("entry_price", sa.Float),
        sa.Column("exit_price", sa.Float),
        sa.Column("pnl_pct", sa.Float),
        sa.Column("simulation_data", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── eval_records ─────────────────────────────────────────────────────────
    op.create_table(
        "eval_records",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("window_days", sa.Integer, nullable=False),
        sa.Column("alert_precision_proxy", sa.Float),
        sa.Column("citation_usage_rate", sa.Float),
        sa.Column("source_weights", postgresql.JSONB, default={}),
        sa.Column("adjustments_made", postgresql.JSONB, default=[]),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_eval_records_evaluated_at", "eval_records", ["evaluated_at"])

    # ── audit_logs ───────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False, default="system"),
        sa.Column("details", postgresql.JSONB, default={}),
    )
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    for tbl in [
        "audit_logs",
        "eval_records",
        "backtest_results",
        "trade_actions",
        "briefings",
        "alert_sources",
        "alerts",
        "chunks",
        "articles",
    ]:
        op.drop_table(tbl)
    op.execute("DROP EXTENSION IF EXISTS vector")

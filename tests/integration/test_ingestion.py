"""
Integration tests for the ingestion pipeline.

Requires: DATABASE_URL env var pointing to a real Postgres DB with the schema applied.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    "postgresql" not in os.environ.get("DATABASE_URL", ""),
    reason="Requires Postgres DATABASE_URL for integration tests",
)


@pytest.fixture
async def db_session():
    """Create a fresh async DB session and roll back after each test."""
    from packages.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def blob_dir(tmp_path: Path) -> str:
    return str(tmp_path / "blobs")


class TestIngestionDedup:
    """Test that the ingestion pipeline correctly deduplicates articles."""

    async def test_new_article_is_stored(self, db_session, blob_dir):
        from packages.ingestion.pipeline import run_ingestion
        from packages.ingestion.sources import SourceConfig

        fake_result = MagicMock()
        fake_result.url = "https://example.com/article-integ-1"
        fake_result.html = b"<html>test</html>"
        fake_result.text = "Apple Inc reported record quarterly earnings today."
        fake_result.title = "Apple Reports Record Earnings"
        fake_result.author = "Test Author"
        fake_result.published_at = datetime.now(timezone.utc)
        fake_result.fetched_at = datetime.now(timezone.utc)

        with patch("packages.ingestion.pipeline.load_sources") as mock_sources, \
             patch("packages.ingestion.pipeline._fetch_source", new_callable=AsyncMock) as mock_fetch:

            mock_sources.return_value = [
                SourceConfig(name="Test", type="http", url="https://example.com", credibility=0.9)
            ]
            mock_fetch.return_value = [fake_result]

            result = await run_ingestion(db_session, "config/sources.example.yaml", blob_dir)

        assert result["new_articles"] == 1
        assert result["skipped"] == 0

    async def test_duplicate_url_is_skipped(self, db_session, blob_dir):
        from packages.ingestion.pipeline import run_ingestion
        from packages.ingestion.sources import SourceConfig

        fake_result = MagicMock()
        fake_result.url = "https://example.com/article-dedup-integ"
        fake_result.html = b""
        fake_result.text = "Some unique news content for dedup test."
        fake_result.title = "Dedup Test Article"
        fake_result.author = None
        fake_result.published_at = datetime.now(timezone.utc)
        fake_result.fetched_at = datetime.now(timezone.utc)

        with patch("packages.ingestion.pipeline.load_sources") as mock_sources, \
             patch("packages.ingestion.pipeline._fetch_source", new_callable=AsyncMock) as mock_fetch:

            mock_sources.return_value = [
                SourceConfig(name="Test", type="http", url="https://example.com", credibility=0.8)
            ]
            mock_fetch.return_value = [fake_result]

            result1 = await run_ingestion(db_session, "config/sources.example.yaml", blob_dir)
            result2 = await run_ingestion(db_session, "config/sources.example.yaml", blob_dir)

        assert result1["new_articles"] == 1
        assert result2["skipped"] >= 1

    async def test_empty_text_article_not_stored(self, db_session, blob_dir):
        from packages.ingestion.pipeline import run_ingestion
        from packages.ingestion.sources import SourceConfig

        fake_result = MagicMock()
        fake_result.url = "https://example.com/empty-article-integ"
        fake_result.html = b""
        fake_result.text = "   "  # whitespace only
        fake_result.title = "Empty"
        fake_result.author = None
        fake_result.published_at = None
        fake_result.fetched_at = datetime.now(timezone.utc)

        with patch("packages.ingestion.pipeline.load_sources") as mock_sources, \
             patch("packages.ingestion.pipeline._fetch_source", new_callable=AsyncMock) as mock_fetch:

            mock_sources.return_value = [
                SourceConfig(name="Test", type="http", url="https://example.com", credibility=0.8)
            ]
            mock_fetch.return_value = [fake_result]

            result = await run_ingestion(db_session, "config/sources.example.yaml", blob_dir)

        assert result["new_articles"] == 0


class TestBlobStoreIntegration:
    """Test the blob store with real filesystem I/O."""

    def test_round_trip(self, tmp_path: Path):
        from packages.ingestion.blob_store import BlobStore

        store = BlobStore(tmp_path / "blobs")
        data = b"<html><body>Test article content</body></html>"
        digest = store.put(data)
        retrieved = store.get(digest)

        assert retrieved == data
        assert store.exists(digest)

    def test_content_addressed_path_exists(self, tmp_path: Path):
        from packages.ingestion.blob_store import BlobStore

        store = BlobStore(tmp_path / "blobs")
        data = b"unique content"
        digest = store.put(data)

        path = tmp_path / "blobs" / digest[:2] / digest[2:4] / digest
        assert path.exists()


class TestPortfolioLedgerIntegration:
    """Test portfolio operations against a real DB."""

    async def test_record_and_retrieve_position(self, db_session):
        from packages.portfolio.ledger import get_positions, record_action

        await record_action(
            db_session,
            action_type="BUY",
            instrument="TSLA",
            quantity=20.0,
            price=250.0,
            notes=None,
            raw_text="BUY 20 TSLA @ 250",
            source="test",
        )

        positions = await get_positions(db_session)
        assert "TSLA" in positions
        assert positions["TSLA"]["quantity"] == 20.0
        assert positions["TSLA"]["avg_cost"] == 250.0

    async def test_buy_and_sell_reduces_position(self, db_session):
        from packages.portfolio.ledger import get_positions, record_action

        await record_action(
            db_session, "BUY", "NVDA", 10.0, 900.0, None, "BUY 10 NVDA @ 900", "test"
        )
        await record_action(
            db_session, "SELL", "NVDA", 4.0, 950.0, None, "SELL 4 NVDA @ 950", "test"
        )

        positions = await get_positions(db_session)
        assert "NVDA" in positions
        assert positions["NVDA"]["quantity"] == 6.0

    async def test_full_sell_removes_position(self, db_session):
        from packages.portfolio.ledger import get_positions, record_action

        await record_action(
            db_session, "BUY", "GLD", 5.0, 180.0, None, "BUY 5 GLD @ 180", "test"
        )
        await record_action(
            db_session, "SELL", "GLD", 5.0, 190.0, None, "SELL 5 GLD @ 190", "test"
        )

        positions = await get_positions(db_session)
        assert "GLD" not in positions

    async def test_format_positions_returns_string(self, db_session):
        from packages.portfolio.ledger import format_positions

        summary = await format_positions(db_session)
        assert isinstance(summary, str)

"""Unit tests for EvidenceGuard citation enforcement."""
from __future__ import annotations

import pytest

from packages.rag.evidence_guard import (
    _validate_citations,
)
from packages.rag.retriever import RetrievedChunk


def _make_chunk(chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        article_id="art-" + chunk_id,
        article_url=f"https://example.com/{chunk_id}",
        article_title="Test Article",
        source_name="Test Source",
        fetched_at="2024-01-01T00:00:00",
        text="Some financial news content about AAPL earnings.",
        score=0.9,
        excerpt_hash="abc123",
    )


class TestValidateCitations:
    def test_valid_citations_pass(self):
        chunks = [_make_chunk("chunk-1"), _make_chunk("chunk-2")]
        response = {
            "citations": [
                {"chunk_id": "chunk-1", "url": "https://example.com/chunk-1",
                 "title": "Test", "fetched_at": "2024-01-01", "excerpt_hash": "abc"},
            ],
            "summary_sections": [
                {
                    "section": "Top Developments",
                    "items": [{"headline": "AAPL up", "bullets": ["..."], "citation_ids": ["chunk-1"]}],
                }
            ],
        }
        # Should not raise
        _validate_citations(response, chunks)

    def test_unknown_chunk_id_raises(self):
        chunks = [_make_chunk("chunk-1")]
        response = {
            "citations": [
                {"chunk_id": "chunk-UNKNOWN", "url": "https://example.com/x",
                 "title": "Test", "fetched_at": "2024-01-01", "excerpt_hash": "abc"},
            ],
            "summary_sections": [],
        }
        with pytest.raises(ValueError, match="unknown chunk_ids"):
            _validate_citations(response, chunks)

    def test_section_references_uncited_chunk_raises(self):
        chunks = [_make_chunk("chunk-1")]
        response = {
            "citations": [
                {"chunk_id": "chunk-1", "url": "https://example.com/chunk-1",
                 "title": "T", "fetched_at": "now", "excerpt_hash": "h"},
            ],
            "summary_sections": [
                {
                    "section": "Test",
                    "items": [{"headline": "X", "bullets": [], "citation_ids": ["chunk-NOT-CITED"]}],
                }
            ],
        }
        with pytest.raises(ValueError, match="uncited chunk_id"):
            _validate_citations(response, chunks)

    def test_empty_citations_list_no_error(self):
        chunks = [_make_chunk("chunk-1")]
        response = {
            "citations": [],
            "summary_sections": [],
        }
        # No items referencing citations, so should pass
        _validate_citations(response, chunks)

    def test_no_chunk_ids_in_items_passes(self):
        chunks = [_make_chunk("chunk-1")]
        response = {
            "citations": [
                {"chunk_id": "chunk-1", "url": "https://example.com/chunk-1",
                 "title": "T", "fetched_at": "now", "excerpt_hash": "h"},
            ],
            "summary_sections": [
                {
                    "section": "What to Investigate",
                    "items": ["What is the Fed doing?", "Should I watch NVDA?"],
                }
            ],
        }
        _validate_citations(response, chunks)

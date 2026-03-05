"""Unit tests for content deduplication utilities."""
from __future__ import annotations

import pytest

from packages.ingestion.dedup import canonical_url, content_hash, excerpt_hash


class TestCanonicalUrl:
    def test_strips_fragment(self):
        assert canonical_url("https://example.com/page#section") == "https://example.com/page"

    def test_strips_utm_params(self):
        url = "https://example.com/article?utm_source=twitter&utm_campaign=xyz"
        result = canonical_url(url)
        assert "utm_source" not in result
        assert "utm_campaign" not in result

    def test_strips_trailing_slash(self):
        assert canonical_url("https://example.com/page/") == "https://example.com/page"

    def test_preserves_meaningful_params(self):
        url = "https://example.com/search?q=earnings&page=2"
        result = canonical_url(url)
        assert "q=earnings" in result
        assert "page=2" in result

    def test_strips_fbclid(self):
        url = "https://example.com/article?fbclid=IwAR123"
        result = canonical_url(url)
        assert "fbclid" not in result

    def test_same_url_produces_same_canonical(self):
        url = "https://reuters.com/business/article-123"
        assert canonical_url(url) == canonical_url(url)


class TestContentHash:
    def test_same_text_same_hash(self):
        text = "Apple reports record quarterly earnings"
        assert content_hash(text) == content_hash(text)

    def test_normalizes_whitespace(self):
        t1 = "Apple  reports  record"
        t2 = "Apple reports record"
        assert content_hash(t1) == content_hash(t2)

    def test_case_insensitive(self):
        t1 = "Apple Reports Record"
        t2 = "apple reports record"
        assert content_hash(t1) == content_hash(t2)

    def test_different_text_different_hash(self):
        t1 = "Apple reports record quarterly earnings"
        t2 = "Microsoft reports record quarterly earnings"
        assert content_hash(t1) != content_hash(t2)

    def test_returns_hex_string(self):
        h = content_hash("some text")
        assert len(h) == 64
        int(h, 16)  # should not raise


class TestExcerptHash:
    def test_returns_short_hash(self):
        h = excerpt_hash("some long text here")
        assert len(h) == 16

    def test_truncates_to_200_chars(self):
        long_text = "a" * 500
        short_text = "a" * 200
        assert excerpt_hash(long_text) == excerpt_hash(short_text)

    def test_different_start_different_hash(self):
        t1 = "Apple: record earnings"
        t2 = "Microsoft: record earnings"
        assert excerpt_hash(t1) != excerpt_hash(t2)

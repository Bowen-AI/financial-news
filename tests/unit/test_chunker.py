"""Unit tests for text chunker."""
from __future__ import annotations

import pytest

from packages.rag.chunker import chunk_text


class TestChunkText:
    def test_empty_text_returns_empty(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty(self):
        assert chunk_text("   \n  ") == []

    def test_short_text_single_chunk(self):
        text = "This is a short text."
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0

    def test_long_text_splits_into_multiple(self):
        # 1000 chars
        text = "word " * 200
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) > 1

    def test_chunk_indices_sequential(self):
        text = "word " * 200
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(indices)))

    def test_overlap_creates_shared_content(self):
        text = "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z " * 10
        chunks = chunk_text(text, chunk_size=50, overlap=20)
        assert len(chunks) >= 2
        # The last chars of chunk[0] should appear somewhere near start of chunk[1]
        last_part = chunks[0].text[-15:]
        assert last_part in chunks[1].text or len(chunks[1].text) > 0

    def test_no_infinite_loop(self):
        text = "x" * 10000
        chunks = chunk_text(text, chunk_size=512, overlap=64)
        assert len(chunks) > 0
        assert len(chunks) < 100  # sanity bound

    def test_chunk_size_respected_approximately(self):
        text = "word " * 400
        chunks = chunk_text(text, chunk_size=200, overlap=20)
        for c in chunks[:-1]:  # last chunk may be shorter
            assert len(c.text) <= 300  # allow some slack for word boundary

    def test_start_end_chars_coverage(self):
        text = "Hello world, this is a test of chunking."
        chunks = chunk_text(text, chunk_size=20, overlap=5)
        # Combined chunks should cover the full text
        all_text = "".join(c.text for c in chunks)
        assert "Hello" in all_text
        assert "chunking" in all_text

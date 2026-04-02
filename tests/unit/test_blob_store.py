"""Unit tests for blob store."""
from __future__ import annotations

from pathlib import Path

import pytest

from packages.ingestion.blob_store import BlobStore


class TestBlobStore:
    @pytest.fixture
    def store(self, tmp_path: Path) -> BlobStore:
        return BlobStore(tmp_path / "blobs")

    def test_put_returns_hash(self, store: BlobStore):
        data = b"hello world"
        digest = store.put(data)
        assert len(digest) == 64  # SHA-256 hex

    def test_get_retrieves_stored_data(self, store: BlobStore):
        data = b"some article content"
        digest = store.put(data)
        retrieved = store.get(digest)
        assert retrieved == data

    def test_get_nonexistent_returns_none(self, store: BlobStore):
        assert store.get("0" * 64) is None

    def test_exists(self, store: BlobStore):
        data = b"test data"
        digest = store.put(data)
        assert store.exists(digest) is True
        assert store.exists("0" * 64) is False

    def test_dedup_same_data(self, store: BlobStore):
        data = b"duplicate content"
        h1 = store.put(data)
        h2 = store.put(data)
        assert h1 == h2

    def test_different_data_different_hash(self, store: BlobStore):
        h1 = store.put(b"content A")
        h2 = store.put(b"content B")
        assert h1 != h2

    def test_path_structure(self, store: BlobStore):
        data = b"path test"
        digest = store.put(data)
        expected = store.base / digest[:2] / digest[2:4] / digest
        assert expected.exists()

    def test_large_data(self, store: BlobStore):
        data = b"x" * 1_000_000  # 1MB
        digest = store.put(data)
        retrieved = store.get(digest)
        assert retrieved == data
        assert len(retrieved) == 1_000_000

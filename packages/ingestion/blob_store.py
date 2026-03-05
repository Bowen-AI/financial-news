"""Blob store: content-addressed file storage with SHA-256 paths."""
from __future__ import annotations

import hashlib
from pathlib import Path


class BlobStore:
    """Store arbitrary byte blobs addressed by their SHA-256 hash."""

    def __init__(self, base_path: str | Path) -> None:
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path_for(self, sha256: str) -> Path:
        return self.base / sha256[:2] / sha256[2:4] / sha256

    def put(self, data: bytes) -> str:
        """Store data and return its SHA-256 hex digest."""
        digest = hashlib.sha256(data).hexdigest()
        path = self._path_for(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return digest

    def get(self, sha256: str) -> bytes | None:
        """Retrieve blob by SHA-256.  Returns None if not found."""
        path = self._path_for(sha256)
        if path.exists():
            return path.read_bytes()
        return None

    def exists(self, sha256: str) -> bool:
        return self._path_for(sha256).exists()

"""Content deduplication helpers."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse


def canonical_url(url: str) -> str:
    """Normalise a URL for deduplication (strip tracking params, fragments)."""
    parsed = urlparse(url)
    # drop fragment
    cleaned = parsed._replace(fragment="")
    # drop common tracking query params
    if cleaned.query:
        kept = []
        for part in cleaned.query.split("&"):
            key = part.split("=")[0].lower()
            if key not in {
                "utm_source", "utm_medium", "utm_campaign",
                "utm_content", "utm_term", "ref", "source",
                "fbclid", "gclid", "msclkid",
            }:
                kept.append(part)
        cleaned = cleaned._replace(query="&".join(kept))
    return urlunparse(cleaned).rstrip("/")


def content_hash(text: str) -> str:
    """Return SHA-256 hex digest of normalised text."""
    normalised = re.sub(r"\s+", " ", text.strip()).lower()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def excerpt_hash(text: str, max_chars: int = 200) -> str:
    """Short hash of the first *max_chars* characters (for citation verification)."""
    excerpt = text.strip()[:max_chars]
    return hashlib.sha256(excerpt.encode("utf-8")).hexdigest()[:16]

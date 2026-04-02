"""Text chunker with configurable size and overlap."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    start_char: int
    end_char: int


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[TextChunk]:
    """
    Split *text* into overlapping chunks of approximately *chunk_size* characters.

    Tries to break on whitespace boundaries to avoid cutting words.
    """
    if not text.strip():
        return []

    chunks: list[TextChunk] = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Try to extend to whitespace boundary
        if end < len(text) and not text[end].isspace():
            # look back for last space
            space = text.rfind(" ", start, end)
            if space > start:
                end = space

        chunk_text_str = text[start:end].strip()
        if chunk_text_str:
            chunks.append(
                TextChunk(
                    text=chunk_text_str,
                    chunk_index=idx,
                    start_char=start,
                    end_char=end,
                )
            )
            idx += 1

        # Move forward with overlap
        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1  # prevent infinite loop
        start = next_start

        # If we've consumed the whole text, stop
        if end >= len(text):
            break

    return chunks

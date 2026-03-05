"""EvidenceGuard: enforces citations in every LLM output."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.core.logging import get_logger
from packages.rag.llm_client import LLMClient
from packages.rag.retriever import RetrievedChunk

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are a financial market intelligence analyst.
You MUST respond with valid JSON only.
NEVER fabricate information. Only use facts from the provided context.
Every claim in summary_sections MUST be traceable to at least one citation.
If evidence is insufficient, state "Insufficient evidence" for that section.
Do NOT provide direct buy/sell advice. Provide evidence-based summaries only.
"""

_BRIEFING_PROMPT = """Based ONLY on the context below, produce a structured daily market briefing.

CONTEXT:
{context}

Respond with this exact JSON structure:
{{
  "summary_sections": [
    {{
      "section": "Top Developments",
      "items": [
        {{
          "headline": "...",
          "bullets": ["...", "..."],
          "citation_ids": ["<chunk_id>", ...]
        }}
      ]
    }},
    {{
      "section": "Watchlist Mentions",
      "items": [
        {{
          "entity": "TICKER_OR_ENTITY",
          "mentions": ["..."],
          "citation_ids": ["<chunk_id>"]
        }}
      ]
    }},
    {{
      "section": "What to Investigate",
      "items": ["question 1", "question 2"]
    }}
  ],
  "citations": [
    {{
      "chunk_id": "...",
      "url": "...",
      "title": "...",
      "fetched_at": "...",
      "excerpt_hash": "..."
    }}
  ]
}}
"""

_ALERT_PROMPT = """Based ONLY on the context below, write a concise alert summary.

EVENT HEADLINE: {headline}

CONTEXT:
{context}

Respond with this exact JSON structure:
{{
  "summary_sections": [
    {{
      "section": "What Happened",
      "items": ["..."]
    }},
    {{
      "section": "Why It Might Matter",
      "items": ["..."]
    }},
    {{
      "section": "Affected Entities",
      "items": ["TICKER1", "ENTITY2"]
    }},
    {{
      "section": "What to Monitor",
      "items": ["..."]
    }},
    {{
      "section": "Uncertainty",
      "items": ["..."]
    }}
  ],
  "citations": [
    {{
      "chunk_id": "...",
      "url": "...",
      "title": "...",
      "fetched_at": "...",
      "excerpt_hash": "..."
    }}
  ]
}}
"""

_QA_PROMPT = """Based ONLY on the context below, answer the following question.
If the answer cannot be found in the context, say "Insufficient evidence to answer."

QUESTION: {question}

CONTEXT:
{context}

Respond with this exact JSON structure:
{{
  "summary_sections": [
    {{
      "section": "Answer",
      "items": ["..."]
    }}
  ],
  "citations": [
    {{
      "chunk_id": "...",
      "url": "...",
      "title": "...",
      "fetched_at": "...",
      "excerpt_hash": "..."
    }}
  ]
}}
"""


@dataclass
class AnalystResponse:
    summary_sections: list[dict]
    citations: list[dict]
    raw: dict


def _build_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for c in chunks:
        parts.append(
            f"[chunk_id={c.chunk_id}] [source={c.source_name}] "
            f"[url={c.article_url}] [fetched={c.fetched_at}]\n{c.text}"
        )
    return "\n\n---\n\n".join(parts)


def _validate_citations(resp: dict, chunks: list[RetrievedChunk]) -> None:
    """Ensure every citation chunk_id exists in the provided context."""
    valid_ids = {c.chunk_id for c in chunks}
    bad = []
    for cit in resp.get("citations", []):
        if cit.get("chunk_id") not in valid_ids:
            bad.append(cit.get("chunk_id"))
    if bad:
        raise ValueError(
            f"EvidenceGuard: citations reference unknown chunk_ids: {bad}"
        )

    # Ensure sections reference only cited chunks
    cited_ids = {cit["chunk_id"] for cit in resp.get("citations", [])}
    for section in resp.get("summary_sections", []):
        for item in section.get("items", []):
            if isinstance(item, dict):
                for cid in item.get("citation_ids", []):
                    if cid not in cited_ids:
                        raise ValueError(
                            f"EvidenceGuard: item references uncited chunk_id: {cid}"
                        )


class EvidenceGuard:
    """Wraps LLMClient to enforce citation-backed outputs."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def briefing(self, chunks: list[RetrievedChunk]) -> AnalystResponse:
        context = _build_context(chunks)
        prompt = _BRIEFING_PROMPT.format(context=context)
        data = await self.llm.complete_json(prompt, system=_SYSTEM_PROMPT)
        _validate_citations(data, chunks)
        return AnalystResponse(
            summary_sections=data.get("summary_sections", []),
            citations=data.get("citations", []),
            raw=data,
        )

    async def alert(
        self, headline: str, chunks: list[RetrievedChunk]
    ) -> AnalystResponse:
        context = _build_context(chunks)
        prompt = _ALERT_PROMPT.format(headline=headline, context=context)
        data = await self.llm.complete_json(prompt, system=_SYSTEM_PROMPT)
        _validate_citations(data, chunks)
        return AnalystResponse(
            summary_sections=data.get("summary_sections", []),
            citations=data.get("citations", []),
            raw=data,
        )

    async def qa(
        self, question: str, chunks: list[RetrievedChunk]
    ) -> AnalystResponse:
        context = _build_context(chunks)
        prompt = _QA_PROMPT.format(question=question, context=context)
        data = await self.llm.complete_json(prompt, system=_SYSTEM_PROMPT)
        _validate_citations(data, chunks)
        return AnalystResponse(
            summary_sections=data.get("summary_sections", []),
            citations=data.get("citations", []),
            raw=data,
        )

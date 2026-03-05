"""Celery task definitions."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from apps.worker.celery_app import app
from packages.core import get_settings
from packages.core.db import AsyncSessionLocal
from packages.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


def _run(coro):
    """Run an async coroutine in a new event loop (Celery workers are sync)."""
    return asyncio.get_event_loop().run_until_complete(coro)


@app.task(name="apps.worker.tasks.ingest_task", bind=True, max_retries=3)
def ingest_task(self):
    """Pull from all configured sources and index new articles."""
    from packages.ingestion.pipeline import run_ingestion
    from packages.rag.embedder import EmbeddingModel
    from packages.rag.indexer import index_unembedded_articles

    async def _inner():
        async with AsyncSessionLocal() as db:
            stats = await run_ingestion(
                db,
                settings.source_config_path,
                settings.blob_store_path,
            )
            logger.info("ingest_task_done", **stats)

            embedder = EmbeddingModel(settings.embedding_model_name)
            indexed = await index_unembedded_articles(
                db,
                embedder,
                chunk_size=settings.chunk_size,
                overlap=settings.chunk_overlap,
            )
            logger.info("indexing_done", indexed=indexed)
            return {**stats, "indexed": indexed}

    try:
        return _run(_inner())
    except Exception as exc:
        logger.error("ingest_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@app.task(name="apps.worker.tasks.briefing_task", bind=True, max_retries=2)
def briefing_task(self):
    """Generate and send the daily briefing email."""
    from packages.core.models import Briefing
    from packages.emailer.smtp import SMTPSender
    from packages.emailer.templates import render_briefing_email
    from packages.rag.embedder import EmbeddingModel
    from packages.rag.evidence_guard import EvidenceGuard
    from packages.rag.llm_client import LLMClient
    from packages.rag.retriever import hybrid_search

    async def _inner():
        async with AsyncSessionLocal() as db:
            embedder = EmbeddingModel(settings.embedding_model_name)
            llm = LLMClient(
                settings.llm_backend, settings.llm_base_url, settings.llm_model_name
            )
            guard = EvidenceGuard(llm)

            query = "market moving news earnings economic data central bank policy"
            chunks = await hybrid_search(db, query, embedder, top_k=20)

            if not chunks:
                logger.warning("briefing_no_chunks")
                return {"status": "no_content"}

            response = await guard.briefing(chunks)
            today = datetime.now(timezone.utc).date().isoformat()
            subject, html_body, text_body = render_briefing_email(response, today)

            # Persist briefing
            briefing = Briefing(
                date=today,
                subject=subject,
                body_html=html_body,
                body_text=text_body,
                citations=response.citations,
            )
            db.add(briefing)
            await db.commit()

            # Send email
            sender = SMTPSender(
                settings.email_smtp_host,
                settings.email_smtp_port,
                settings.email_smtp_user,
                settings.email_smtp_pass,
                settings.email_from,
            )
            sender.send(settings.email_to, subject, html_body, text_body)
            logger.info("briefing_sent", date=today)
            return {"status": "sent", "date": today}

    try:
        return _run(_inner())
    except Exception as exc:
        logger.error("briefing_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=120)


@app.task(name="apps.worker.tasks.alert_task", bind=True, max_retries=2)
def alert_task(self):
    """Score recent articles and fire alerts if threshold exceeded."""
    from packages.alerts.engine import run_alert_engine
    from packages.emailer.smtp import SMTPSender
    from packages.emailer.templates import render_alert_email
    from packages.ingestion.sources import load_watchlist
    from packages.rag.embedder import EmbeddingModel
    from packages.rag.evidence_guard import EvidenceGuard
    from packages.rag.llm_client import LLMClient

    async def _inner():
        async with AsyncSessionLocal() as db:
            watchlist = load_watchlist(settings.watchlist_config_path)
            embedder = EmbeddingModel(settings.embedding_model_name)
            llm = LLMClient(
                settings.llm_backend, settings.llm_base_url, settings.llm_model_name
            )
            guard = EvidenceGuard(llm)

            alerts = await run_alert_engine(
                db,
                embedder,
                guard,
                watchlist,
                threshold=settings.alert_threshold,
                min_sources=settings.alert_min_sources,
            )

            if not alerts:
                return {"alerts_fired": 0}

            sender = SMTPSender(
                settings.email_smtp_host,
                settings.email_smtp_port,
                settings.email_smtp_user,
                settings.email_smtp_pass,
                settings.email_from,
            )

            for alert in alerts:
                from packages.rag.evidence_guard import AnalystResponse

                resp = AnalystResponse(
                    summary_sections=[
                        {"section": s, "items": [alert.summary]}
                        for s in ["Summary"]
                    ],
                    citations=alert.citations or [],
                    raw={},
                )
                subject, html_body, text_body = render_alert_email(
                    resp, alert.headline, alert.impact_score
                )
                sender.send(settings.email_to, subject, html_body, text_body)
                alert.sent_at = datetime.now(timezone.utc)

            await db.commit()
            logger.info("alerts_sent", count=len(alerts))
            return {"alerts_fired": len(alerts)}

    try:
        return _run(_inner())
    except Exception as exc:
        logger.error("alert_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=120)


@app.task(name="apps.worker.tasks.imap_poll_task", bind=True, max_retries=2)
def imap_poll_task(self):
    """Poll IMAP for inbound emails; parse trades and answer questions."""
    from packages.emailer.imap import IMAPPoller
    from packages.emailer.smtp import SMTPSender
    from packages.emailer.templates import render_confirmation_email
    from packages.portfolio.ledger import (
        HELP_TEXT,
        format_positions,
        record_action,
    )
    from packages.portfolio.parser import parse_action
    from packages.rag.embedder import EmbeddingModel
    from packages.rag.evidence_guard import EvidenceGuard
    from packages.rag.llm_client import LLMClient
    from packages.rag.retriever import hybrid_search

    async def _inner():
        poller = IMAPPoller(
            host=settings.email_imap_host,
            port=settings.email_imap_port,
            username=settings.email_imap_user,
            password=settings.email_imap_pass,
            trusted_senders=[settings.email_to],
        )
        emails = poller.poll()
        if not emails:
            return {"processed": 0}

        sender = SMTPSender(
            settings.email_smtp_host,
            settings.email_smtp_port,
            settings.email_smtp_user,
            settings.email_smtp_pass,
            settings.email_from,
        )

        async with AsyncSessionLocal() as db:
            for msg in emails:
                parsed = parse_action(msg.body)

                if parsed.action_type in ("BUY", "SELL", "NOTE"):
                    await record_action(
                        db,
                        action_type=parsed.action_type,
                        instrument=parsed.instrument,
                        quantity=parsed.quantity,
                        price=parsed.price,
                        notes=parsed.notes,
                        raw_text=parsed.raw_text,
                        source="email",
                    )
                    position_summary = await format_positions(db)
                    subj, html_b, text_b = render_confirmation_email(
                        parsed.action_type,
                        parsed.instrument,
                        parsed.quantity,
                        parsed.price,
                        parsed.notes,
                        position_summary,
                    )
                    sender.send(settings.email_to, subj, html_b, text_b)

                elif parsed.action_type == "POSITION":
                    position_summary = await format_positions(db)
                    sender.send(
                        settings.email_to,
                        "Position Summary",
                        f"<pre>{position_summary}</pre>",
                        position_summary,
                    )

                elif parsed.action_type == "HELP":
                    sender.send(
                        settings.email_to,
                        "Help",
                        f"<pre>{HELP_TEXT}</pre>",
                        HELP_TEXT,
                    )

                elif parsed.action_type == "QUESTION":
                    # Route to RAG Q&A
                    embedder = EmbeddingModel(settings.embedding_model_name)
                    llm = LLMClient(
                        settings.llm_backend,
                        settings.llm_base_url,
                        settings.llm_model_name,
                    )
                    guard = EvidenceGuard(llm)
                    question = parsed.notes or msg.body
                    chunks = await hybrid_search(db, question, embedder, top_k=10)
                    if chunks:
                        response = await guard.qa(question, chunks)
                        answer = "\n".join(
                            item
                            for s in response.summary_sections
                            for item in s.get("items", [])
                            if isinstance(item, str)
                        )
                    else:
                        answer = "Insufficient evidence to answer this question."
                    sender.send(
                        settings.email_to,
                        f"Re: {msg.subject}",
                        f"<p>{answer}</p>",
                        answer,
                    )

        logger.info("imap_task_done", processed=len(emails))
        return {"processed": len(emails)}

    try:
        return _run(_inner())
    except Exception as exc:
        logger.error("imap_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@app.task(name="apps.worker.tasks.eval_task", bind=True, max_retries=1)
def eval_task(self):
    """Run self-evaluation loop."""
    from packages.eval.evaluator import run_evaluation

    async def _inner():
        async with AsyncSessionLocal() as db:
            record = await run_evaluation(db, window_days=settings.eval_window_days)
            return {
                "precision": record.alert_precision_proxy,
                "citation_rate": record.citation_usage_rate,
                "adjustments": len(record.adjustments_made),
            }

    try:
        return _run(_inner())
    except Exception as exc:
        logger.error("eval_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)

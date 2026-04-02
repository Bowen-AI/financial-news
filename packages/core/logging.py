"""Structured JSON logging with secret redaction."""
from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|pass|secret|token|key|apikey|smtp_pass|imap_pass)=[^\s&\"']+"),
]


def _redact(event: str) -> str:
    for pat in _SECRET_PATTERNS:
        event = pat.sub(r"\1=***REDACTED***", event)
    return event


def _redact_processor(logger: Any, method: str, event_dict: dict) -> dict:
    if "event" in event_dict and isinstance(event_dict["event"], str):
        event_dict["event"] = _redact(event_dict["event"])
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog with JSON renderer and secret redaction."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)

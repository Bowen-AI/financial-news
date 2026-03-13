"""Email templates: render briefings and alerts as HTML + plain text."""
from __future__ import annotations

from datetime import date

from packages.rag.evidence_guard import AnalystResponse

_HTML_HEAD = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body { font-family: Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px; }
  h1, h2 { color: #1a3a5c; }
  h3 { color: #2c5f8a; }
  ul { margin: 4px 0; }
  .citation { font-size: 0.85em; color: #555; }
  .alert-score { background: #dc3545; color: white; padding: 2px 8px; border-radius: 4px; }
  .section { border-left: 3px solid #2c5f8a; padding-left: 12px; margin-bottom: 20px; }
  .disclaimer { background: #fff3cd; padding: 10px; border-radius: 4px; font-size: 0.9em; }
</style>
</head><body>
"""

_DISCLAIMER = (
    "<div class='disclaimer'>⚠️ <strong>Not financial advice.</strong> "
    "This is an evidence-based summary for informational purposes only. "
    "All claims are traceable to cited sources.</div>\n"
)


def _render_citations_html(citations: list[dict]) -> str:
    if not citations:
        return ""
    lines = ["<h2>📎 Sources</h2><ol class='citation'>"]
    for cit in citations:
        title = cit.get("title") or cit.get("url", "")
        url = cit.get("url", "#")
        fetched = cit.get("fetched_at", "")
        excerpt_hash = cit.get("excerpt_hash", "")
        lines.append(
            f'<li><a href="{url}">{title}</a> '
            f'<span class="citation">[fetched: {fetched}] [hash: {excerpt_hash}]</span></li>'
        )
    lines.append("</ol>")
    return "\n".join(lines)


def _render_citations_text(citations: list[dict]) -> str:
    if not citations:
        return ""
    lines = ["\nSOURCES\n" + "=" * 60]
    for i, cit in enumerate(citations, 1):
        title = cit.get("title") or cit.get("url", "")
        url = cit.get("url", "")
        fetched = cit.get("fetched_at", "")
        lines.append(f"{i}. {title}\n   {url}\n   Fetched: {fetched}")
    return "\n".join(lines)


def render_briefing_email(
    response: AnalystResponse,
    briefing_date: str | None = None,
) -> tuple[str, str, str]:
    """
    Render a daily briefing.
    Returns (subject, html_body, text_body).
    """
    today = briefing_date or date.today().isoformat()
    subject = f"Daily Market Briefing — {today}"

    html_parts = [_HTML_HEAD, f"<h1>📊 Daily Market Briefing — {today}</h1>", _DISCLAIMER]
    text_parts = [f"DAILY MARKET BRIEFING — {today}", "=" * 60]

    for section in response.summary_sections:
        name = section.get("section", "")
        items = section.get("items", [])

        html_parts.append(f"<div class='section'><h2>{name}</h2>")
        text_parts.append(f"\n{name.upper()}\n" + "-" * 40)

        for item in items:
            if isinstance(item, str):
                html_parts.append(f"<p>{item}</p>")
                text_parts.append(f"  • {item}")
            elif isinstance(item, dict):
                headline = item.get("headline") or item.get("entity", "")
                bullets = item.get("bullets") or item.get("mentions") or []
                html_parts.append(f"<h3>{headline}</h3><ul>")
                text_parts.append(f"\n  ▶ {headline}")
                for b in bullets:
                    html_parts.append(f"<li>{b}</li>")
                    text_parts.append(f"    - {b}")
                html_parts.append("</ul>")

        html_parts.append("</div>")

    html_parts.append(_render_citations_html(response.citations))
    html_parts.append("</body></html>")
    text_parts.append(_render_citations_text(response.citations))

    return subject, "\n".join(html_parts), "\n".join(text_parts)


def render_alert_email(
    response: AnalystResponse,
    headline: str,
    score: int,
) -> tuple[str, str, str]:
    """
    Render an alert email.
    Returns (subject, html_body, text_body).
    """
    subject = f"ALERT (Score {score}) — {headline}"

    html_parts = [
        _HTML_HEAD,
        f"<h1>🚨 ALERT <span class='alert-score'>Score: {score}</span></h1>",
        f"<h2>{headline}</h2>",
        _DISCLAIMER,
    ]
    text_parts = [
        f"🚨 ALERT (Score {score}) — {headline}",
        "=" * 60,
    ]

    for section in response.summary_sections:
        name = section.get("section", "")
        items = section.get("items", [])
        html_parts.append(f"<div class='section'><h2>{name}</h2><ul>")
        text_parts.append(f"\n{name.upper()}\n" + "-" * 40)
        for item in items:
            if isinstance(item, str):
                html_parts.append(f"<li>{item}</li>")
                text_parts.append(f"  • {item}")
        html_parts.append("</ul></div>")

    html_parts.append(_render_citations_html(response.citations))
    html_parts.append("</body></html>")
    text_parts.append(_render_citations_text(response.citations))

    return subject, "\n".join(html_parts), "\n".join(text_parts)


def render_confirmation_email(
    action_type: str,
    instrument: str | None,
    quantity: float | None,
    price: float | None,
    notes: str | None,
    position_summary: str,
) -> tuple[str, str, str]:
    """Render a trade confirmation email."""
    subject = f"Confirmed: {action_type} {instrument or ''}"
    lines = [
        f"Action: {action_type}",
        f"Instrument: {instrument or 'N/A'}",
        f"Quantity: {quantity or 'N/A'}",
        f"Price: {price or 'N/A'}",
        f"Notes: {notes or ''}",
        "",
        "Current Positions:",
        position_summary,
    ]
    text = "\n".join(lines)
    html = (
        _HTML_HEAD
        + f"<h2>✅ Trade Confirmed: {action_type}</h2>"
        + f"<pre>{text}</pre></body></html>"
    )
    return subject, html, text

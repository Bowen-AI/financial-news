"""IMAP inbound email poller."""
from __future__ import annotations

import email
import imaplib
from dataclasses import dataclass
from email.header import decode_header

from packages.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InboundEmail:
    uid: str
    subject: str
    sender: str
    body: str


class IMAPPoller:
    """Polls an IMAP mailbox for unread messages from trusted senders."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        trusted_senders: list[str] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self.trusted_senders = [s.lower() for s in (trusted_senders or [])]

    def _decode_header_value(self, value: str | bytes) -> str:
        parts = decode_header(value)
        result = []
        for part, enc in parts:
            if isinstance(part, bytes):
                result.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                result.append(str(part))
        return "".join(result)

    def _extract_body(self, msg: email.message.Message) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition", ""))
                if ct == "text/plain" and "attachment" not in cd:
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(
                    msg.get_content_charset() or "utf-8", errors="replace"
                )
        return ""

    def poll(self, folder: str = "INBOX") -> list[InboundEmail]:
        """Connect, fetch unseen messages, mark as seen.  Returns list of emails."""
        messages: list[InboundEmail] = []
        try:
            with imaplib.IMAP4_SSL(self.host, self.port) as imap:
                imap.login(self.username, self._password)
                imap.select(folder)
                _, data = imap.search(None, "UNSEEN")
                uids = data[0].split()

                for uid in uids:
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    if not isinstance(raw, bytes):
                        continue
                    msg = email.message_from_bytes(raw)

                    sender = self._decode_header_value(msg.get("From", ""))
                    # Security: only process from trusted senders
                    sender_addr = sender.lower()
                    if self.trusted_senders and not any(
                        t in sender_addr for t in self.trusted_senders
                    ):
                        logger.warning(
                            "imap_untrusted_sender", sender=sender_addr
                        )
                        continue

                    subject = self._decode_header_value(msg.get("Subject", ""))
                    body = self._extract_body(msg)

                    # Mark as seen
                    imap.store(uid, "+FLAGS", "\\Seen")

                    messages.append(
                        InboundEmail(
                            uid=uid.decode(),
                            subject=subject,
                            sender=sender,
                            body=body.strip(),
                        )
                    )

            logger.info("imap_polled", count=len(messages))
        except imaplib.IMAP4.error as exc:
            logger.error("imap_error", error=str(exc))
        return messages

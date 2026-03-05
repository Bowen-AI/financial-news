"""SMTP outbound email sender."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from packages.core.logging import get_logger

logger = get_logger(__name__)


class SMTPSender:
    """Sends HTML + plaintext emails via SMTP with STARTTLS."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_addr: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self.from_addr = from_addr

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        """Send an email.  Raises on failure."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = to

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self.username, self._password)
                smtp.sendmail(self.from_addr, to, msg.as_string())
            logger.info("email_sent", subject=subject, to=to)
        except smtplib.SMTPException as exc:
            logger.error("email_send_failed", subject=subject, error=str(exc))
            raise

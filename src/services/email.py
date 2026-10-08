"""Transactional email service for KitchenPilot-V1.

Supports:
- Console / In-Memory backend (development, testing, offline mode)
- SMTP backend using aiosmtplib (production transactional mailers)

Security Invariant:
- Raw tokens, passwords, SMTP credentials, and URLs containing raw tokens
  must NEVER be logged or leaked into structured logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
import logging
from typing import Any, Dict, List, Optional

from src.api.config import (
    EMAIL_BACKEND,
    EMAIL_ENABLED,
    EMAIL_FROM_ADDRESS,
    EMAIL_FROM_NAME,
    FRONTEND_URL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    SMTP_USE_TLS,
)

logger = logging.getLogger("kitchenpilot.services.email")


class EmailService:
    """Isolated asynchronous email delivery service."""

    # In-memory outbox for testing and verification
    outbox: List[Dict[str, Any]] = []

    def __init__(
        self,
        backend: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.backend = (backend or EMAIL_BACKEND).lower().strip()
        self.enabled = enabled if enabled is not None else EMAIL_ENABLED

    @classmethod
    def clear_outbox(cls) -> None:
        """Clear the in-memory outbox list."""
        cls.outbox.clear()

    @classmethod
    def get_outbox(cls) -> List[Dict[str, Any]]:
        """Retrieve sent emails from the in-memory outbox."""
        return list(cls.outbox)

    async def send_verification_email(
        self,
        recipient: str,
        raw_token: str,
        user_id: Optional[int] = None,
    ) -> bool:
        """Send an email verification message.

        Constructs verification URL and dispatches via configured backend.
        Never logs the raw token or URL.
        """
        verification_url = f"{FRONTEND_URL.rstrip('/')}/verify-email.html?token={raw_token}"
        subject = f"{EMAIL_FROM_NAME} — Verify Your Email Address"
        body = (
            f"Hello,\n\n"
            f"Thank you for registering with {EMAIL_FROM_NAME}.\n"
            f"Please verify your email address by visiting the following link:\n\n"
            f"{verification_url}\n\n"
            f"This link will expire in 24 hours. If you did not create this account, please ignore this email.\n\n"
            f"— The {EMAIL_FROM_NAME} Team\n"
        )

        return await self._dispatch(
            message_type="verification",
            recipient=recipient,
            subject=subject,
            body=body,
            raw_token=raw_token,
            user_id=user_id,
        )

    async def send_password_reset_email(
        self,
        recipient: str,
        raw_token: str,
        user_id: Optional[int] = None,
    ) -> bool:
        """Send a password recovery message.

        Constructs password reset URL and dispatches via configured backend.
        Never logs the raw token or URL.
        """
        reset_url = f"{FRONTEND_URL.rstrip('/')}/reset-password.html?token={raw_token}"
        subject = f"{EMAIL_FROM_NAME} — Password Reset Request"
        body = (
            f"Hello,\n\n"
            f"We received a request to reset the password for your {EMAIL_FROM_NAME} account.\n"
            f"You can set a new password using the following link:\n\n"
            f"{reset_url}\n\n"
            f"This link will expire in 15 minutes. If you did not request a password reset, "
            f"please ignore this email; your existing password will remain secure.\n\n"
            f"— The {EMAIL_FROM_NAME} Team\n"
        )

        return await self._dispatch(
            message_type="password_reset",
            recipient=recipient,
            subject=subject,
            body=body,
            raw_token=raw_token,
            user_id=user_id,
        )

    async def _dispatch(
        self,
        message_type: str,
        recipient: str,
        subject: str,
        body: str,
        raw_token: str,
        user_id: Optional[int] = None,
    ) -> bool:
        """Internal dispatcher routing to console or SMTP backend."""
        # Always record in outbox for observability and testing
        outbox_entry = {
            "type": message_type,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "raw_token": raw_token,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc),
        }
        self.outbox.append(outbox_entry)

        if not self.enabled and self.backend != "console":
            logger.debug(
                "Email delivery disabled (EMAIL_ENABLED=false). Message of type '%s' recorded to outbox only.",
                message_type,
            )
            return True

        if self.backend == "console":
            # Safe log message: Redact token and URL
            logger.info(
                "[EmailService:console] Dispatched '%s' message to <%s> (user_id=%s).",
                message_type,
                recipient,
                str(user_id) if user_id else "N/A",
            )
            return True

        if self.backend == "smtp":
            return await self._send_smtp(recipient, subject, body, message_type)

        logger.warning("Unrecognized EMAIL_BACKEND '%s'; message kept in outbox.", self.backend)
        return True

    async def _send_smtp(
        self,
        recipient: str,
        subject: str,
        body: str,
        message_type: str,
    ) -> bool:
        """Send message using aiosmtplib."""
        try:
            import aiosmtplib
        except ImportError:
            logger.error("aiosmtplib is required for SMTP backend but not installed.")
            return False

        message = EmailMessage()
        message["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM_ADDRESS}>"
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        try:
            await aiosmtplib.send(
                message,
                hostname=SMTP_HOST,
                port=SMTP_PORT,
                username=SMTP_USER or None,
                password=SMTP_PASSWORD or None,
                use_tls=SMTP_USE_TLS and SMTP_PORT == 465,
                start_tls=SMTP_USE_TLS and SMTP_PORT != 465,
                timeout=10.0,
            )
            logger.info("[EmailService:smtp] Sent '%s' to recipient successfully.", message_type)
            return True
        except Exception as exc:
            # Safe error logging: do not leak SMTP_PASSWORD or message body
            logger.error("[EmailService:smtp] Failed to deliver '%s': %s", message_type, type(exc).__name__)
            return False


# Global singleton instance
email_service = EmailService()

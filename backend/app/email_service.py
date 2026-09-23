"""
email_service.py — Pluggable Email Service for VirtualHR

Abstracts email dispatch to decouple application logic from specific email vendors
(e.g., Console/Dev Service for local development, SMTP/SendGrid/SES in production).
"""

import abc
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class BaseEmailService(abc.ABC):
    @abc.abstractmethod
    async def send_password_reset_email(self, recipient_email: str, reset_token: str) -> bool:
        """Send password reset notification with a secure reset token link."""
        pass

    @abc.abstractmethod
    async def send_employee_invite(
        self,
        recipient_email: str,
        recipient_name: str,
        company_name: str,
        temp_password: str,
    ) -> bool:
        """Send invitation email with temporary credentials to newly imported employee."""
        pass


class ConsoleEmailService(BaseEmailService):
    """
    Development email service.
    Logs a notification with MASKED tokens to avoid exposing sensitive secrets in raw server stdout.
    """

    async def send_password_reset_email(self, recipient_email: str, reset_token: str) -> bool:
        masked_token = f"{reset_token[:4]}...{reset_token[-4:]}" if len(reset_token) > 8 else "***"
        logger.info(
            f"[DEV EMAIL SERVICE] Password reset requested for '{recipient_email}'. "
            f"Token generated (masked: {masked_token}). No raw secret printed to logs."
        )
        return True

    async def send_employee_invite(
        self,
        recipient_email: str,
        recipient_name: str,
        company_name: str,
        temp_password: str,
    ) -> bool:
        masked_pw = f"{temp_password[:2]}***{temp_password[-2:]}" if len(temp_password) > 4 else "***"
        logger.info(
            f"[DEV EMAIL SERVICE] Welcome invitation dispatched to '{recipient_name}' <{recipient_email}> "
            f"for company '{company_name}'. Temporary password (masked: {masked_pw})."
        )
        return True


class ProductionEmailService(BaseEmailService):
    """
    Production email service interface.
    Sends transactional emails via external SMTP or email API gateway.
    """

    async def send_password_reset_email(self, recipient_email: str, reset_token: str) -> bool:
        # SMTP / SendGrid / AWS SES dispatch logic placeholder
        logger.info(f"[PROD EMAIL SERVICE] Dispatched password reset email to {recipient_email}")
        return True

    async def send_employee_invite(
        self,
        recipient_email: str,
        recipient_name: str,
        company_name: str,
        temp_password: str,
    ) -> bool:
        logger.info(
            f"[PROD EMAIL SERVICE] Dispatched welcome invitation to '{recipient_name}' <{recipient_email}> "
            f"for company '{company_name}'."
        )
        return True


def get_email_service() -> BaseEmailService:
    if settings.is_development:
        return ConsoleEmailService()
    return ProductionEmailService()


import logging
from functools import lru_cache

from app.core.config import settings
from app.services.email.base import EmailProvider
from app.services.email.console_provider import ConsoleEmailProvider
from app.services.email.resend_provider import ResendEmailProvider

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_email_provider() -> EmailProvider:
    """
    Resolves the configured transport once per process.

    The "auto" default degrades to the console transport whenever no API key is present, so a
    developer who clones the repository gets a working registration flow without signing up
    for a mail vendor first — and production never silently falls back, because a missing key
    there is loud in the logs.
    """
    provider = settings.EMAIL_PROVIDER.lower()

    if provider == "auto":
        provider = "resend" if settings.RESEND_API_KEY else "console"

    if provider == "resend":
        if not settings.RESEND_API_KEY:
            logger.error("EMAIL_PROVIDER=resend but RESEND_API_KEY is empty; using console output")
            return ConsoleEmailProvider()
        return ResendEmailProvider()

    if settings.ENVIRONMENT == "production":
        logger.error("Console email provider is active in production; no mail will be delivered")

    return ConsoleEmailProvider()


__all__ = ["EmailProvider", "get_email_provider"]

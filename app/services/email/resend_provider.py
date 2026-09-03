import logging

import httpx

from app.core.config import settings
from app.services.email.base import EmailProvider

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


class ResendEmailProvider(EmailProvider):
    """
    Production transport backed by the Resend HTTP API.

    The vendor SDK is skipped in favour of a direct httpx call: the payload is four fields,
    and avoiding the extra dependency keeps the deployment slim on a memory-constrained host.
    Failures are logged rather than raised because sending runs in a background task, where an
    exception would be invisible to the client and cannot be retried by it anyway.
    """

    async def send(self, to: str, subject: str, html: str, text: str) -> None:
        payload = {
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.EMAIL_TIMEOUT_SECONDS) as client:
                response = await client.post(RESEND_ENDPOINT, json=payload, headers=headers)
                if response.status_code >= 400:
                    # The body is logged but never surfaced to the caller: it can echo the
                    # recipient address back, which would turn a send failure into an
                    # account-existence oracle.
                    logger.error(
                        "Resend rejected the message (status=%s): %s",
                        response.status_code, response.text,
                    )
        except httpx.HTTPError as exc:
            logger.error("Failed to reach Resend: %s", exc)

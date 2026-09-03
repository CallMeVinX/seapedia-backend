import logging

from app.services.email.base import EmailProvider

logger = logging.getLogger(__name__)


class ConsoleEmailProvider(EmailProvider):
    """
    Development transport that prints messages to the application log instead of sending them.
    Keeps local and CI runs free of real deliveries and vendor quotas, while still letting a
    developer read the generated OTP straight out of the server output.
    """

    async def send(self, to: str, subject: str, html: str, text: str) -> None:
        logger.warning(
            "\n========== [DEV EMAIL] ==========\n"
            "To      : %s\n"
            "Subject : %s\n"
            "---------------------------------\n"
            "%s\n"
            "=================================",
            to, subject, text,
        )

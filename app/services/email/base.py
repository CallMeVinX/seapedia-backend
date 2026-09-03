from typing import Protocol


class EmailProvider(Protocol):
    """
    Transport-agnostic contract for outbound mail.

    Callers depend on this shape rather than on Resend, SES or SMTP directly, so swapping
    delivery vendors — the usual outcome once free-tier quotas run out — touches one module
    instead of every call site that happens to send an email.
    """

    async def send(self, to: str, subject: str, html: str, text: str) -> None:
        ...

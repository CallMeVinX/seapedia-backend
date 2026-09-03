"""
Email hygiene rules applied before a registration is ever accepted.

Three independent defences live here, ordered from cheapest to most expensive:
  1. Canonicalisation  - collapses provider-specific aliases so one mailbox maps to one account.
  2. Disposable blocklist - rejects known throwaway inbox providers (in-memory set, O(1)).
  3. MX lookup - rejects domains that cannot receive mail at all, which also catches typos.
"""

import logging
from pathlib import Path
from typing import Set

from app.core.config import settings

logger = logging.getLogger(__name__)

# Providers that treat the local part as case/dot/tag insensitive. Gmail is the
# notable one that also ignores dots, which is the alias trick most commonly used
# to farm sign-up vouchers from a single inbox.
_DOT_INSENSITIVE_DOMAINS = {"gmail.com", "googlemail.com"}
_DOMAIN_ALIASES = {"googlemail.com": "gmail.com"}

# Seed list of the highest-volume disposable providers. Extend it without touching
# code by dropping a newline-delimited file at app/core/data/disposable_domains.txt
# (for example the `disposable-email-domains` open-source list, ~50k entries).
_BUILTIN_DISPOSABLE_DOMAINS = {
    "10minutemail.com", "20minutemail.com", "33mail.com", "guerrillamail.com",
    "guerrillamail.info", "guerrillamail.net", "sharklasers.com", "grr.la",
    "mailinator.com", "mailinator.net", "maildrop.cc", "mailnesia.com",
    "tempmail.com", "temp-mail.org", "tempmailo.com", "tempr.email",
    "throwawaymail.com", "trashmail.com", "trashmail.de", "yopmail.com",
    "yopmail.fr", "fakeinbox.com", "dispostable.com", "getnada.com",
    "nada.email", "emailondeck.com", "spamgourmet.com", "mytemp.email",
    "moakt.com", "mohmal.com", "tmail.ws", "burnermail.io", "mailsac.com",
    "inboxkitten.com", "harakirimail.com", "spam4.me", "einrot.com",
    "1secmail.com", "1secmail.org", "1secmail.net", "vusra.com",
}

_DISPOSABLE_FILE = Path(__file__).parent / "data" / "disposable_domains.txt"


def _load_disposable_domains() -> Set[str]:
    """
    Builds the disposable-domain set once at import time so lookups stay O(1) per request.
    An optional external file is merged in, letting the list be refreshed operationally
    without a code change or redeploy of the module itself.
    """
    domains = set(_BUILTIN_DISPOSABLE_DOMAINS)
    if _DISPOSABLE_FILE.exists():
        try:
            for line in _DISPOSABLE_FILE.read_text(encoding="utf-8").splitlines():
                entry = line.strip().lower()
                if entry and not entry.startswith("#"):
                    domains.add(entry)
        except OSError as exc:
            logger.warning("Could not read disposable domain file: %s", exc)
    return domains


DISPOSABLE_DOMAINS = _load_disposable_domains()


def canonicalize_email(email: str) -> str:
    """
    Reduces an address to the single mailbox it actually delivers to.
    Without this, `budi+1@gmail.com`, `budi+2@gmail.com` and `b.u.d.i@gmail.com` are three
    distinct rows under a UNIQUE(email) constraint but one real inbox, which is exactly how
    a single person farms unlimited accounts and new-user vouchers.
    """
    local, _, domain = email.strip().lower().partition("@")
    if not domain:
        return email.strip().lower()

    domain = _DOMAIN_ALIASES.get(domain, domain)
    local = local.split("+", 1)[0]
    if domain in _DOT_INSENSITIVE_DOMAINS or domain in _DOMAIN_ALIASES.values():
        local = local.replace(".", "")
    return f"{local}@{domain}"


def is_disposable_email(email: str) -> bool:
    """
    Reports whether the address belongs to a known throwaway inbox provider.
    Such inboxes defeat the entire purpose of an OTP gate, since the attacker can read the
    code just as easily as a legitimate user but abandons the address seconds later.
    """
    domain = email.strip().lower().rpartition("@")[2]
    return domain in DISPOSABLE_DOMAINS


async def domain_has_mx_record(email: str) -> bool:
    """
    Confirms the address' domain publishes an MX record and can therefore receive mail.
    This rejects invented domains and — more usefully in practice — typos such as
    `gmial.com`, which otherwise cost the user a silent, never-arriving OTP.
    Deliberately fails open: a DNS outage must not take registration down with it.
    """
    domain = email.strip().lower().rpartition("@")[2]
    if not domain:
        return False

    try:
        import dns.asyncresolver
        import dns.resolver
    except ImportError:
        logger.warning("dnspython is not installed; skipping MX validation")
        return True

    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 3.0
    resolver.timeout = 3.0
    try:
        answers = await resolver.resolve(domain, "MX")
        return len(answers) > 0
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False
    except Exception as exc:  # timeouts, no nameservers, transient network failures
        logger.warning("MX lookup failed for %s, allowing through: %s", domain, exc)
        return True


async def validate_registration_email(email: str) -> tuple[bool, str]:
    """
    Runs the full acceptance policy for an address supplied at registration.
    Returns a (is_allowed, reason) pair so the caller decides the HTTP shape; the reason is
    safe to surface because it describes the submitted address, never account existence.
    """
    if is_disposable_email(email):
        return False, "Alamat email sekali pakai tidak dapat digunakan untuk mendaftar."

    if settings.SIGNUP_REQUIRE_MX_RECORD and not await domain_has_mx_record(email):
        return False, "Domain email tidak valid atau tidak dapat menerima email."

    return True, ""

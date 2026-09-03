"""
Two-phase registration: request an OTP, then redeem it.

The account row is only written once the code is redeemed. Staging the attempt means a bot
that floods /auth/register creates nothing but self-expiring rows in pending_registrations,
and can neither inflate the user base nor squat on an address it does not control.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email_rules import canonicalize_email, validate_registration_email
from app.core.security import generate_otp, get_password_hash, hash_otp, verify_otp
from app.models.user import AppRole, User, UserRole
from app.models.verification import PendingRegistration
from app.services import rate_limit_service
from app.services.email import get_email_provider, templates

logger = logging.getLogger(__name__)

# Returned for every /auth/register outcome. A caller must not be able to tell an accepted
# signup from one that hit an existing account, otherwise the endpoint becomes a free oracle
# for checking which email addresses hold a Seapedia account.
GENERIC_REGISTER_MESSAGE = (
    "Jika alamat email valid dan belum terdaftar, kode verifikasi telah dikirim."
)

# Likewise for redemption: wrong code, expired code and unknown email must be indistinguishable.
GENERIC_VERIFY_ERROR = "Kode verifikasi salah atau sudah kedaluwarsa."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_roles(raw_roles: Optional[list[str]]) -> list[str]:
    """
    Normalises the requested roles, defaulting to Buyer.
    Admin is rejected outright: self-service registration must never be able to mint an
    account that can administrate the marketplace.
    """
    if not raw_roles:
        return [AppRole.Buyer.value]

    resolved: list[str] = []
    for raw in raw_roles:
        try:
            role = AppRole(raw)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Peran tidak valid: {raw}",
            )
        if role == AppRole.Admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Peran Admin tidak dapat didaftarkan secara mandiri.",
            )
        if role.value not in resolved:
            resolved.append(role.value)
    return resolved


async def _enforce_signup_throttle(db: AsyncSession, ip: str, canonical: str) -> None:
    """
    Applies the per-IP and per-address budgets that cap bulk account creation.

    Two dimensions are needed: the IP limit stops one machine enumerating many addresses, and
    the address limit stops a distributed set of clients pounding a single mailbox. Hourly and
    daily IP windows run together so a slow drip cannot stay under the hourly bar all day.
    """
    checks = [
        (f"signup_ip_h:{ip}", settings.SIGNUP_MAX_PER_IP_PER_HOUR, 3600),
        (f"signup_ip_d:{ip}", settings.SIGNUP_MAX_PER_IP_PER_DAY, 86400),
        (f"signup_email_h:{canonical}", settings.SIGNUP_MAX_PER_EMAIL_PER_HOUR, 3600),
    ]

    for key, limit, window in checks:
        result = await rate_limit_service.hit(db, key, limit, window)
        if not result.allowed:
            await db.commit()  # persist the increment so the block cannot be reset by retrying
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Terlalu banyak percobaan pendaftaran. Silakan coba lagi nanti.",
                headers={"Retry-After": str(result.retry_after_seconds)},
            )


async def dispatch_otp_email(to_email: str, full_name: str, code: str) -> None:
    """
    Sends the OTP message. Runs as a background task after the response is returned, so a slow
    or unavailable mail vendor never adds its latency to the registration request itself.
    """
    subject, html, plain = templates.registration_otp(
        full_name=full_name, code=code, expire_minutes=settings.OTP_EXPIRE_MINUTES
    )
    await get_email_provider().send(to=to_email, subject=subject, html=html, text=plain)


async def dispatch_account_exists_email(to_email: str) -> None:
    """
    Tells an existing account holder that their address was used in a signup attempt.
    This is what keeps the uniform /auth/register response usable: the person who would
    otherwise sit waiting for an OTP that will never arrive learns why, and gets a way forward.
    """
    base = settings.FRONTEND_URL.rstrip("/")
    subject, html, plain = templates.account_already_exists(
        email=to_email,
        login_url=f"{base}/login",
        reset_url=f"{base}/forgot-password",
    )
    await get_email_provider().send(to=to_email, subject=subject, html=html, text=plain)


async def start_registration(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    roles: Optional[list[str]],
    ip: str,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Phase one: validate, throttle, stage the signup and mint an OTP.

    Returns (recipient, full_name, code). A None code means the address already belongs to an
    account and the caller should send the "account exists" notice instead — a distinction that
    stays entirely server-side and never reaches the HTTP response.
    """
    canonical = canonicalize_email(email)

    await _enforce_signup_throttle(db, ip=ip, canonical=canonical)

    is_allowed, reason = await validate_registration_email(email)
    if not is_allowed:
        await db.commit()
        # Safe to be specific here: this describes the submitted address itself and reveals
        # nothing about which accounts exist.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    resolved_roles = _resolve_roles(roles)

    existing = await db.scalar(select(User).where(User.email_canonical == canonical))
    if existing is not None:
        await db.commit()
        return existing.email, None, None

    code = generate_otp()
    staged = {
        "email": email.strip(),
        "password_hash": get_password_hash(password),
        "full_name": full_name.strip(),
        "roles": resolved_roles,
        "code_hash": hash_otp(code),
        "expires_at": _now() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
        "attempts": 0,
        "resend_count": 0,
        "request_ip": ip if ip != "unknown" else None,
        "last_sent_at": func.now(),
    }

    # A repeat attempt on the same mailbox replaces the pending row rather than adding one.
    # Re-registering before verification is legitimate (mistyped password, abandoned tab), and
    # resetting attempts/resend_count is bounded by the throttle applied above.
    stmt = (
        pg_insert(PendingRegistration)
        .values(email_canonical=canonical, **staged)
        .on_conflict_do_update(
            index_elements=[PendingRegistration.email_canonical],
            set_=staged,
        )
    )
    await db.execute(stmt)
    await db.commit()

    return email.strip(), full_name.strip(), code


async def resend_otp(
    db: AsyncSession, *, email: str, ip: str
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Issues a fresh OTP for a staged registration, subject to a cooldown and a resend ceiling.

    A brand new code is generated rather than resending the old one, so a resend cannot be used
    to extend the lifetime of a code an attacker is midway through guessing.
    """
    canonical = canonicalize_email(email)

    result = await rate_limit_service.hit(
        db, f"resend_ip_h:{ip}", settings.SIGNUP_MAX_PER_IP_PER_HOUR, 3600
    )
    if not result.allowed:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak permintaan. Silakan coba lagi nanti.",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )

    pending = await db.scalar(
        select(PendingRegistration).where(PendingRegistration.email_canonical == canonical)
    )

    # Absent or expired staging rows return quietly. Reporting "no pending registration" would
    # let an attacker probe which addresses are mid-signup.
    if pending is None or pending.expires_at <= _now():
        await db.commit()
        return None, None, None

    elapsed = (_now() - pending.last_sent_at).total_seconds()
    if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Mohon tunggu sebelum meminta kode baru.",
            headers={"Retry-After": str(int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed) + 1)},
        )

    if pending.resend_count >= settings.OTP_MAX_RESENDS:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Batas pengiriman ulang tercapai. Silakan daftar ulang beberapa saat lagi.",
        )

    code = generate_otp()
    await db.execute(
        update(PendingRegistration)
        .where(PendingRegistration.id == pending.id)
        .values(
            code_hash=hash_otp(code),
            expires_at=_now() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
            attempts=0,
            resend_count=PendingRegistration.resend_count + 1,
            last_sent_at=func.now(),
        )
    )
    await db.commit()
    return pending.email, pending.full_name, code


async def verify_registration(db: AsyncSession, *, email: str, code: str, ip: str) -> User:
    """
    Phase two: redeem the OTP and promote the staged signup into a real account.

    The attempt counter is incremented in the same UPDATE that reads the row, so parallel
    guesses each consume a slot instead of all reading the same pre-increment value — the race
    that would otherwise make the attempt ceiling meaningless against a scripted attacker.
    """
    canonical = canonicalize_email(email)

    throttle = await rate_limit_service.hit(
        db, f"verify_ip_h:{ip}", settings.VERIFY_MAX_PER_IP_PER_HOUR, 3600
    )
    if not throttle.allowed:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan verifikasi. Silakan coba lagi nanti.",
            headers={"Retry-After": str(throttle.retry_after_seconds)},
        )

    claimed = await db.execute(
        update(PendingRegistration)
        .where(
            PendingRegistration.email_canonical == canonical,
            PendingRegistration.expires_at > func.now(),
        )
        .values(attempts=PendingRegistration.attempts + 1)
        .returning(
            PendingRegistration.id,
            PendingRegistration.email,
            PendingRegistration.password_hash,
            PendingRegistration.full_name,
            PendingRegistration.roles,
            PendingRegistration.code_hash,
            PendingRegistration.attempts,
        )
    )
    row = claimed.one_or_none()

    if row is None:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_VERIFY_ERROR)

    pending_id, pending_email, password_hash, full_name, roles, code_hash, attempts = row

    if attempts > settings.OTP_MAX_ATTEMPTS:
        # Burn the staging row outright. Leaving it alive would hand an attacker unlimited
        # guesses simply by continuing to submit.
        await db.execute(delete(PendingRegistration).where(PendingRegistration.id == pending_id))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Terlalu banyak percobaan salah. Silakan daftar ulang untuk mendapatkan kode baru.",
        )

    if not verify_otp(code, code_hash):
        await db.commit()  # keep the incremented attempt count
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_VERIFY_ERROR)

    new_user = User(
        email=pending_email,
        email_canonical=canonical,
        password_hash=password_hash,
        full_name=full_name,
        email_verified_at=func.now(),
    )
    db.add(new_user)

    try:
        await db.flush()
        for role_value in (roles or [AppRole.Buyer.value]):
            db.add(UserRole(user_id=new_user.id, role=AppRole(role_value)))
        await db.execute(delete(PendingRegistration).where(PendingRegistration.id == pending_id))
        await db.commit()
    except IntegrityError:
        # The address was claimed between staging and redemption — two tabs, or a genuine race.
        # The unique index is the authority; the loser is told the code is no longer usable.
        await db.rollback()
        await db.execute(delete(PendingRegistration).where(PendingRegistration.id == pending_id))
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_VERIFY_ERROR)

    await db.refresh(new_user)
    return new_user


async def purge_expired(db: AsyncSession) -> int:
    """
    Deletes staging rows that are well past their expiry.

    Called opportunistically from the registration path rather than from a scheduler, since the
    free-tier host provides no cron and the table would otherwise accumulate every abandoned
    and every hostile attempt indefinitely.
    """
    cutoff = _now() - timedelta(hours=24)
    result = await db.execute(
        delete(PendingRegistration).where(PendingRegistration.expires_at < cutoff)
    )
    await db.commit()
    return result.rowcount or 0

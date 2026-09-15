"""
Service layer governing password recovery workflows.

Provides challenge issuance with 6-digit numeric OTPs, throttled resends,
rate-limited verification, and secure password updating.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email_rules import canonicalize_email
from app.core.security import generate_otp, get_password_hash, hash_otp, verify_otp
from app.models.user import User
from app.models.verification import PasswordResetChallenge
from app.services import rate_limit_service
from app.services.email import get_email_provider, templates


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def request_password_reset(
    db: AsyncSession,
    *,
    email: str,
    ip: str,
) -> tuple[str, str, str]:
    """
    Validates account existence, applies rate limits, and stages a reset challenge.

    Returns (recipient_email, full_name, code).
    Raises HTTPException(400) if the email address is not registered in the system.
    """
    canonical = canonicalize_email(email)

    user = await db.scalar(select(User).where(User.email_canonical == canonical))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email tidak terdaftar. Silakan periksa kembali alamat email Anda.",
        )

    ip_key = f"pwd_reset_ip_h:{ip}"
    email_key = f"pwd_reset_email_h:{canonical}"

    ip_check = await rate_limit_service.hit(db, ip_key, limit=10, window_seconds=3600)
    if not ip_check.allowed:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak permintaan reset kata sandi. Silakan coba lagi nanti.",
            headers={"Retry-After": str(ip_check.retry_after_seconds)},
        )

    email_check = await rate_limit_service.hit(db, email_key, limit=5, window_seconds=3600)
    if not email_check.allowed:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak permintaan reset kata sandi untuk email ini. Silakan coba lagi nanti.",
            headers={"Retry-After": str(email_check.retry_after_seconds)},
        )

    code = generate_otp()
    staged = {
        "email": user.email,
        "code_hash": hash_otp(code),
        "expires_at": _now() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
        "attempts": 0,
        "resend_count": 0,
        "request_ip": ip if ip != "unknown" else None,
        "last_sent_at": func.now(),
    }

    stmt = (
        pg_insert(PasswordResetChallenge)
        .values(email_canonical=canonical, **staged)
        .on_conflict_do_update(
            index_elements=[PasswordResetChallenge.email_canonical],
            set_=staged,
        )
    )
    await db.execute(stmt)
    await db.commit()

    return user.email, user.full_name, code


async def resend_password_reset_otp(
    db: AsyncSession,
    *,
    email: str,
    ip: str,
) -> tuple[str, str, str]:
    """
    Issues a replacement code for an active password recovery challenge.
    """
    canonical = canonicalize_email(email)

    user = await db.scalar(select(User).where(User.email_canonical == canonical))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email tidak terdaftar.",
        )

    challenge = await db.scalar(
        select(PasswordResetChallenge).where(PasswordResetChallenge.email_canonical == canonical)
    )
    if challenge is None or challenge.expires_at <= _now():
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada sesi reset kata sandi yang aktif. Silakan ajukan ulang permintaan.",
        )

    elapsed = (_now() - challenge.last_sent_at).total_seconds()
    if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Mohon tunggu sebelum meminta kode baru.",
            headers={"Retry-After": str(int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed) + 1)},
        )

    if challenge.resend_count >= settings.OTP_MAX_RESENDS:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Batas pengiriman ulang kode tercapai. Silakan coba beberapa saat lagi.",
        )

    code = generate_otp()
    await db.execute(
        update(PasswordResetChallenge)
        .where(PasswordResetChallenge.id == challenge.id)
        .values(
            code_hash=hash_otp(code),
            expires_at=_now() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
            attempts=0,
            resend_count=PasswordResetChallenge.resend_count + 1,
            last_sent_at=func.now(),
        )
    )
    await db.commit()
    return user.email, user.full_name, code


async def verify_and_reset_password(
    db: AsyncSession,
    *,
    email: str,
    code: str,
    new_password: str,
    ip: str,
) -> User:
    """
    Verifies the provided recovery OTP and updates the account password hash.
    """
    canonical = canonicalize_email(email)

    challenge = await db.scalar(
        select(PasswordResetChallenge).where(PasswordResetChallenge.email_canonical == canonical)
    )
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada sesi reset kata sandi aktif untuk email ini.",
        )

    if challenge.expires_at <= _now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kode verifikasi sudah kedaluwarsa. Silakan kirim ulang kode.",
        )

    if challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan kode yang salah. Silakan minta kode baru.",
        )

    await db.execute(
        update(PasswordResetChallenge)
        .where(PasswordResetChallenge.id == challenge.id)
        .values(attempts=PasswordResetChallenge.attempts + 1)
    )

    if not verify_otp(code, challenge.code_hash):
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kode verifikasi salah.",
        )

    user = await db.scalar(select(User).where(User.email_canonical == canonical))
    if user is None:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pengguna tidak ditemukan.",
        )

    user.password_hash = get_password_hash(new_password)
    await db.execute(
        delete(PasswordResetChallenge).where(PasswordResetChallenge.id == challenge.id)
    )
    await db.commit()
    return user


async def dispatch_reset_password_email(to_email: str, full_name: str, code: str) -> None:
    """
    Dispatches the password reset OTP message asynchronously in background tasks.
    """
    subject, html, plain = templates.password_reset_otp(
        full_name=full_name, code=code, expire_minutes=settings.OTP_EXPIRE_MINUTES
    )
    await get_email_provider().send(to=to_email, subject=subject, html=html, text=plain)

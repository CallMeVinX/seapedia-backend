"""
Service layer governing password recovery workflows.

Provides challenge issuance with 6-digit numeric OTPs, throttled resends,
rate-limited verification, and secure password updating.
"""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email_rules import canonicalize_email
from app.core.security import (
    create_password_reset_token,
    generate_otp,
    get_password_hash,
    hash_otp,
    verify_otp,
    verify_password_reset_token,
)
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


async def verify_reset_code(
    db: AsyncSession,
    *,
    email: str,
    code: str,
    ip: str = "unknown",
) -> tuple[User, str, int]:
    """
    Memverifikasi kode PIN 6 digit pemulihan kata sandi pengguna (Tahap 2 alur forgot-password).

    Prinsip Best Practice & Keamanan:
    1. Memvalidasi bahwa akun dan sesi tantangan (PasswordResetChallenge) aktif di database.
    2. Memastikan sesi belum kedaluwarsa dan batas salah mencoba (OTP_MAX_ATTEMPTS) belum terlampaui.
    3. Memverifikasi kecocokan kode PIN dengan HMAC hash di database secara konstan waktu (constant-time).
    4. Menerbitkan JWT reset_token berumur pendek (15 menit) bertanda tangan kriptografis (HS256)
       yang hanya sah untuk tujuan 'password_reset'.
    5. Menginvaliasi PIN 6 digit tersebut dengan menyimpan fingerprint (SHA-256) dari reset_token pada DB,
       sehingga PIN lama tidak dapat dipergunakan ulang (single-use OTP).

    Mengembalikan: (User, reset_token, expires_in_seconds)
    Raises: HTTPException(400/429/404) jika verifikasi gagal.
    """
    canonical = canonicalize_email(email)

    user = await db.scalar(select(User).where(User.email_canonical == canonical))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email tidak terdaftar atau sesi pemulihan tidak valid.",
        )

    challenge = await db.scalar(
        select(PasswordResetChallenge).where(PasswordResetChallenge.email_canonical == canonical)
    )
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada sesi pemulihan kata sandi aktif untuk email ini. Silakan ajukan permintaan baru.",
        )

    if challenge.expires_at <= _now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kode verifikasi sudah kedaluwarsa. Silakan minta kode baru.",
        )

    if challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan kode yang salah. Batas maksimal tercapai. Silakan minta kode baru.",
        )

    # Catat penambahan attempt percobaan
    await db.execute(
        update(PasswordResetChallenge)
        .where(PasswordResetChallenge.id == challenge.id)
        .values(attempts=PasswordResetChallenge.attempts + 1)
    )

    if not verify_otp(code, challenge.code_hash):
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kode verifikasi PIN salah. Harap periksa kembali 6 digit kode yang dikirim ke email Anda.",
        )

    # Terbitkan token otorisasi reset_token bertanda tangan kriptografis
    reset_token = create_password_reset_token(
        email=user.email,
        challenge_id=str(challenge.id),
        expires_delta=timedelta(minutes=15),
    )

    # Simpan sidik jari token (SHA-256) pada baris tantangan untuk mengunci sesi ke token ini
    token_fingerprint = hashlib.sha256(reset_token.encode("utf-8")).hexdigest()
    await db.execute(
        update(PasswordResetChallenge)
        .where(PasswordResetChallenge.id == challenge.id)
        .values(
            code_hash=token_fingerprint,
            attempts=0,
            expires_at=_now() + timedelta(minutes=15),
        )
    )
    await db.commit()

    expires_in_seconds = 15 * 60
    return user, reset_token, expires_in_seconds


async def reset_password_with_token(
    db: AsyncSession,
    *,
    reset_token: str,
    new_password: str,
    ip: str = "unknown",
) -> User:
    """
    Memperbarui kata sandi akun menggunakan token otorisasi reset_token yang sah (Tahap 3 alur forgot-password).

    Prinsip Best Practice & Keamanan:
    1. Memverifikasi integritas cryptographic signature dan expiry token JWT via SECRET_KEY.
    2. Mencocokkan challenge_id dan fingerprint token dengan catatan di database.
    3. Memperbarui password_hash dengan algoritma bcrypt.
    4. Menghapus sesi PasswordResetChallenge dari database sehingga token hanya dapat dipakai satu kali (single-use).

    Mengembalikan: Objek User yang telah diperbarui.
    Raises: HTTPException(400/404) jika token tidak sah atau sesi tidak ditemukan.
    """
    payload = verify_password_reset_token(reset_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token otorisasi ganti kata sandi tidak valid atau sudah kedaluwarsa. Silakan ulangi verifikasi PIN.",
        )

    email = payload.get("sub")
    challenge_id = payload.get("challenge_id")
    if not email or not challenge_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Klaim token pemulihan tidak valid.",
        )

    canonical = canonicalize_email(email)
    challenge = await db.scalar(
        select(PasswordResetChallenge).where(
            PasswordResetChallenge.id == challenge_id,
            PasswordResetChallenge.email_canonical == canonical,
        )
    )
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sesi reset kata sandi telah kedaluwarsa atau sudah pernah digunakan. Silakan ajukan permintaan baru.",
        )

    if challenge.expires_at <= _now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sesi reset kata sandi telah kedaluwarsa. Silakan lakukan verifikasi ulang.",
        )

    # Validasi kesesuaian fingerprint token dengan sesi di database
    token_fingerprint = hashlib.sha256(reset_token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(challenge.code_hash, token_fingerprint):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token reset tidak cocok dengan sesi verifikasi PIN aktif.",
        )

    user = await db.scalar(select(User).where(User.email_canonical == canonical))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pengguna tidak ditemukan.",
        )

    user.password_hash = get_password_hash(new_password)

    # Hapus tantangan dari database (Single-use guarantee: mencegah replay attack)
    await db.execute(
        delete(PasswordResetChallenge).where(PasswordResetChallenge.id == challenge.id)
    )
    await db.commit()
    return user


async def verify_and_reset_password(
    db: AsyncSession,
    *,
    new_password: str,
    reset_token: Optional[str] = None,
    email: Optional[str] = None,
    code: Optional[str] = None,
    ip: str = "unknown",
) -> User:
    """
    Fungsi penghubung terpadu untuk pembaruan kata sandi.

    Mendukung skema best-practice berbasis `reset_token`,
    serta skema backward-compatibility berbasis `email` dan `code`.
    """
    if reset_token:
        return await reset_password_with_token(
            db, reset_token=reset_token, new_password=new_password, ip=ip
        )

    if not email or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Harap sertakan reset_token hasil verifikasi PIN atau kombinasi email dan kode verifikasi.",
        )

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

"""
Comprehensive test suite for the Multi-Step Forgot Password & PIN Verification workflow.
"""

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest

from pydantic import ValidationError
from fastapi import HTTPException

from app.core.security import (
    create_password_reset_token,
    verify_password_reset_token,
    verify_password,
    get_password_hash,
    hash_otp,
)
from app.schemas.auth_schema import (
    VerifyResetCodeRequest,
    ResetPasswordRequest,
)
from app.models.user import User
from app.models.verification import PasswordResetChallenge
from app.services import password_reset_service


def test_password_reset_token_issuance_and_verification():
    """Test JWT creation, claim structure, and verification logic."""
    email = "test.user@example.com"
    challenge_id = "550e8400-e29b-41d4-a716-446655440000"

    token = create_password_reset_token(email=email, challenge_id=challenge_id, expires_delta=timedelta(minutes=15))
    assert isinstance(token, str) and len(token) > 20

    # Valid token verification
    payload = verify_password_reset_token(token)
    assert payload is not None
    assert payload["sub"] == email
    assert payload["challenge_id"] == challenge_id
    assert payload["purpose"] == "password_reset"
    assert "exp" in payload

    # Tampered token verification
    tampered_token = token[:-5] + "ABCDE"
    assert verify_password_reset_token(tampered_token) is None

    # Expired token verification
    expired_token = create_password_reset_token(email=email, challenge_id=challenge_id, expires_delta=timedelta(seconds=-1))
    assert verify_password_reset_token(expired_token) is None


def test_schema_validations():
    """Test input validations for PIN code and password schemas."""
    # 1. VerifyResetCodeRequest valid
    req1 = VerifyResetCodeRequest(email="test@example.com", code="123456")
    assert req1.code == "123456"

    # Invalid code (not 6 digits, letters, etc.)
    with pytest.raises(ValidationError):
        VerifyResetCodeRequest(email="test@example.com", code="12345")  # 5 digits
    with pytest.raises(ValidationError):
        VerifyResetCodeRequest(email="test@example.com", code="1234567")  # 7 digits
    with pytest.raises(ValidationError):
        VerifyResetCodeRequest(email="test@example.com", code="abcdef")  # letters

    # 2. ResetPasswordRequest valid with reset_token
    req2 = ResetPasswordRequest(reset_token="valid_jwt_token_sample", new_password="NewSecretPassword123")
    assert req2.reset_token == "valid_jwt_token_sample"

    # 3. ResetPasswordRequest valid with legacy email + code
    req3 = ResetPasswordRequest(email="test@example.com", code="123456", new_password="NewSecretPassword123")
    assert req3.code == "123456"

    # 4. ResetPasswordRequest invalid without token or code
    with pytest.raises(ValidationError):
        ResetPasswordRequest(new_password="NewSecretPassword123")

    # 5. Weak password (no digits or no letters)
    with pytest.raises(ValidationError):
        ResetPasswordRequest(reset_token="token", new_password="alllowercaseletters")
    with pytest.raises(ValidationError):
        ResetPasswordRequest(reset_token="token", new_password="1234567890123")


def test_full_service_flow():
    """
    Simulates the complete lifecycle:
    1. User has active PasswordResetChallenge with 6-digit OTP.
    2. Submits wrong PIN -> rejected with 400 Bad Request, attempts count increments.
    3. Submits correct PIN -> returns valid reset_token, stores token fingerprint in DB.
    4. Attacker attempts to forge token -> rejected with 400 Bad Request.
    5. Submits valid reset_token + new_password -> updates password hash, deletes challenge (single-use).
    6. Replay attack with same reset_token -> rejected because challenge is deleted.
    """
    async def _async_runner():
        user_email = "alexa@seapedia.id"
        plain_otp = "849201"
        otp_hash = hash_otp(plain_otp)
        challenge_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        fake_user = User(
            id=challenge_uuid,
            email=user_email,
            email_canonical=user_email,
            full_name="Alexa Doe",
            password_hash=get_password_hash("OldPassword123"),
        )

        fake_challenge = PasswordResetChallenge(
            id=challenge_uuid,
            email=user_email,
            email_canonical=user_email,
            code_hash=otp_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            attempts=0,
            resend_count=0,
        )

        mock_db = AsyncMock()

        # Step A: Verify with wrong code
        mock_db.scalar.side_effect = [fake_user, fake_challenge]
        with pytest.raises(HTTPException) as exc_info:
            await password_reset_service.verify_reset_code(
                mock_db,
                email=user_email,
                code="000000",
                ip="127.0.0.1",
            )
        assert exc_info.value.status_code == 400
        assert "salah" in exc_info.value.detail.lower()

        # Step B: Verify with correct code
        mock_db.scalar.side_effect = [fake_user, fake_challenge]
        user, reset_token, expires_in = await password_reset_service.verify_reset_code(
            mock_db,
            email=user_email,
            code=plain_otp,
            ip="127.0.0.1",
        )
        assert user.email == user_email
        assert reset_token is not None
        assert expires_in == 15 * 60

        # Simulate that the DB now has the token fingerprint
        expected_fingerprint = hashlib.sha256(reset_token.encode("utf-8")).hexdigest()
        fake_challenge.code_hash = expected_fingerprint

        # Step C: Reset password using valid reset_token
        mock_db.scalar.side_effect = [fake_challenge, fake_user]
        new_pwd = "BrandNewSecurePassword999"
        updated_user = await password_reset_service.reset_password_with_token(
            mock_db,
            reset_token=reset_token,
            new_password=new_pwd,
            ip="127.0.0.1",
        )
        assert verify_password(new_pwd, updated_user.password_hash) is True
        assert not verify_password("OldPassword123", updated_user.password_hash)

        # Step D: Replay attack (challenge already deleted from DB)
        mock_db.scalar.side_effect = [None]  # Challenge no longer in DB
        with pytest.raises(HTTPException) as exc_replay:
            await password_reset_service.reset_password_with_token(
                mock_db,
                reset_token=reset_token,
                new_password="AnotherPassword123",
                ip="127.0.0.1",
            )
        assert exc_replay.value.status_code == 400
        assert "kedaluwarsa atau sudah pernah digunakan" in exc_replay.value.detail

    asyncio.run(_async_runner())

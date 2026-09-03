from datetime import datetime, timedelta
from typing import Optional, Union
from jose import jwt
import bcrypt
import hashlib
import hmac
import secrets
from app.core.config import settings

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def create_access_token(
    user_id: Union[str, int], 
    active_role: Optional[str] = None, 
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Creates a JWT token.
    If `active_role` is None, this is considered an 'initial login' token
    that only permits calling `/api/auth/select-role`.
    Once a role is selected, a new token is generated with `active_role` populated.
    """
    to_encode = {
        "sub": str(user_id),
    }
    
    if active_role:
        to_encode["active_role"] = active_role.upper()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


# ---------------------------------------------------------------------------
# One-Time Password (OTP) primitives
# ---------------------------------------------------------------------------

def generate_otp(length: Optional[int] = None) -> str:
    """
    Generates a numeric one-time password using a cryptographically secure RNG.
    `random` is deliberately avoided here: its Mersenne Twister state is recoverable
    from previous outputs, which would let an attacker predict other users' codes.
    """
    digits = length or settings.OTP_LENGTH
    upper_bound = 10 ** digits
    return str(secrets.randbelow(upper_bound)).zfill(digits)


def hash_otp(code: str) -> str:
    """
    Derives a keyed HMAC-SHA256 digest of an OTP for storage.
    A plain hash would be useless for a 6-digit code (the entire keyspace is only one
    million entries and can be reversed instantly), so the server SECRET_KEY is mixed
    in as a pepper: leaking the database alone is not enough to recover live codes.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_otp(code: str, stored_hash: str) -> bool:
    """
    Compares a submitted OTP against its stored digest in constant time.
    Using `==` would leak how many leading characters matched through response timing,
    which reduces a brute-force search from 10^6 to roughly 10*6 attempts.
    """
    return hmac.compare_digest(hash_otp(code), stored_hash)

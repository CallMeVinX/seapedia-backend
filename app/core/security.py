from datetime import datetime, timedelta
from typing import Optional, Union
from jose import jwt
import bcrypt
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

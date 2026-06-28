from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.core.config import settings
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_token_payload(request: Request) -> dict:
    """
    Extracts and decodes the JWT from either HTTP cookies or the Authorization header.
    Essential for stateless authentication, allowing the backend to securely identify users across distributed requests without session storage.
    """
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ")[1]
            
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user_id(payload: dict = Depends(get_token_payload)) -> str:
    """
    Retrieves the raw user ID directly from the validated token payload.
    Optimizes performance by avoiding database lookups when only the user's UUID is needed for relational queries (e.g., fetching their wallet).
    """
    return payload.get("sub")

async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Fetches the full User model instance from the database using the authenticated ID.
    Used exclusively in scenarios where deep user profile data is required beyond the basic fields embedded in the JWT.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

class RequireActiveRole:
    """
    Validates that the user's explicitly selected 'active_role' matches the endpoint's required roles.
    Enforces role segregation in a multi-role system, preventing users with multiple roles (e.g., Buyer and Seller) from performing unauthorized actions under the wrong context.
    """
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, payload: dict = Depends(get_token_payload)) -> dict:
        active_role = payload.get("active_role")
        
        if not active_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active role selected. Please call /auth/select-role first."
            )
            
        if active_role.upper() not in [r.upper() for r in self.allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Active role '{active_role}' is not authorized to perform this action."
            )
            
        return payload

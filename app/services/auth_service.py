from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import UserRole, AppRole

async def verify_user_owns_role(db: AsyncSession, user_id: str, role: str) -> bool:
    # Ensure role is a valid AppRole string
    try:
        enum_role = AppRole(role)
    except ValueError:
        return False

    stmt = select(UserRole).where(
        UserRole.user_id == user_id,
        UserRole.role == enum_role
    )
    result = await db.execute(stmt)
    user_role = result.scalar_one_or_none()
    return user_role is not None

async def get_user_roles(db: AsyncSession, user_id: str) -> list[str]:
    stmt = select(UserRole.role).where(UserRole.user_id == user_id)
    result = await db.execute(stmt)
    roles = result.scalars().all()
    return [
        (r.value.upper() if hasattr(r, "value") else str(r).upper())
        for r in roles
    ]

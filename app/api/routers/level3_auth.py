from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.schemas.auth_schema import SelectRoleRequest, TokenResponse, LoginRequest, RegisterRequest, LoginResponse, AddRoleRequest
from app.api.dependencies import get_current_user_id, get_token_payload
from app.services.auth_service import verify_user_owns_role, get_user_roles
from app.core.security import create_access_token, verify_password, get_password_hash
from datetime import timedelta
from app.core.config import settings
from app.models.user import User, UserRole, AppRole

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=dict)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Handles new user registration by validating email uniqueness and assigning initial roles.
    This ensures that each user has at least one role (defaulting to Buyer) to interact with the system.
    """
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        
    new_user = User(
        email=request.email,
        password_hash=get_password_hash(request.password),
        full_name=request.full_name
    )
    db.add(new_user)
    await db.flush() 
    
    assigned_roles = []
    if request.roles:
        for r_str in request.roles:
            role_enum = AppRole(r_str)
            if not role_enum:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Invalid role: {r_str}"
                )
            assigned_roles.append(role_enum)
    else:
        assigned_roles = [AppRole.Buyer]
        
    for role in assigned_roles:
        user_role = UserRole(user_id=new_user.id, role=role)
        db.add(user_role)
        
    await db.commit()
    return {"message": "User registered successfully"}


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Authenticates user credentials and issues a base JWT.
    The initial token intentionally omits the 'active_role' claim to force the client to explicitly select a role before accessing protected resources.
    """
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    expire_minutes = 60 * 24 * 30 if request.remember_me else 60 * 24 * 1 
    access_token_expires = timedelta(minutes=expire_minutes)
    access_token = create_access_token(
        user_id=str(user.id),
        expires_delta=access_token_expires
    )
    
    is_prod = settings.ENVIRONMENT == "production"
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=expire_minutes * 60,
        samesite="none" if is_prod else "lax",
        secure=is_prod
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/select-role", response_model=TokenResponse)
async def select_role(
    request: SelectRoleRequest,
    response: Response,
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """
    Allows users to select an active role for their session.
    This issues a new JWT explicitly including the 'active_role', which is required by the authorization middleware.
    """
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
        
    owns_role = await verify_user_owns_role(db, user_id=user_id, role=request.chosen_role)
    if not owns_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not own the role: {request.chosen_role}"
        )

    access_token_expires = timedelta(minutes=60 * 24 * 30)
    active_role_token = create_access_token(
        user_id=user_id,
        active_role=request.chosen_role,
        expires_delta=access_token_expires
    )
    
    is_prod = settings.ENVIRONMENT == "production"
    
    response.set_cookie(
        key="access_token",
        value=active_role_token,
        httponly=True,
        max_age=60 * 24 * 30 * 60,
        samesite="none" if is_prod else "lax",
        secure=is_prod
    )
    
    return {"access_token": active_role_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(response: Response):
    """
    Terminates the current session by clearing the access token cookie (HttpOnly).
    """
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        key="access_token",
        samesite="none" if is_prod else "lax",
        secure=is_prod
    )
    return {"message": "Logged out successfully"}

@router.get("/roles", response_model=list[str])
async def get_available_roles():
    """
    Retrieves all available roles in the system.
    This endpoint is used by the client to dynamically render role selection options.
    """
    return [role.value for role in AppRole]

@router.post("/add-role")
async def add_role(
    request: AddRoleRequest,
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """
    Grants an additional role to the authenticated user.
    This allows a seamless transition between personas (e.g., Buyer becoming a Seller) without requiring multiple accounts.
    """
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
        
    role_enum = AppRole(request.role.upper())
    if not role_enum:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")

    owns_role = await verify_user_owns_role(db, user_id=user_id, role=request.role)
    if owns_role:
        return {"message": f"User already has the role: {request.role}"}

    user_role = UserRole(user_id=user_id, role=role_enum)
    db.add(user_role)
    await db.commit()
    
    return {"message": f"Successfully added role: {request.role}"}

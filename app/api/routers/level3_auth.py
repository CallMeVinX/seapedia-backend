from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.schemas.auth_schema import (
    SelectRoleRequest, TokenResponse, LoginRequest, RegisterRequest, LoginResponse,
    AddRoleRequest, VerifyRegistrationRequest, ResendOtpRequest, RegistrationChallengeResponse,
)
from app.api.dependencies import get_current_user_id, get_token_payload
from app.services.auth_service import verify_user_owns_role, get_user_roles
from app.core.security import create_access_token, verify_password, get_password_hash
from datetime import timedelta
from app.core.config import settings
from app.models.user import User, UserRole, AppRole
from app.services import registration_service
from app.services.rate_limit_service import client_ip
from app.core.email_rules import canonicalize_email

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=RegistrationChallengeResponse)
async def register(
    request: RegisterRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Opens a registration by staging the details and emailing a one-time code.

    No row is written to the users table here. Requiring proof of mailbox ownership before the
    account exists is what stops automated sign-ups from populating the marketplace with
    disposable accounts, claiming other people's addresses, or harvesting new-user vouchers.
    The response is identical in every case, including when the address is already registered,
    so the endpoint cannot be used to discover which emails hold an account.
    """
    ip = client_ip(http_request)

    recipient, full_name, code = await registration_service.start_registration(
        db,
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        roles=request.roles,
        ip=ip,
    )

    if code is not None:
        background_tasks.add_task(registration_service.dispatch_otp_email, recipient, full_name, code)
    else:
        # The address already has an account. The owner is told so out-of-band, which keeps the
        # HTTP response uniform while still explaining to a real user why no code arrived.
        background_tasks.add_task(registration_service.dispatch_account_exists_email, recipient)

    return RegistrationChallengeResponse(
        message=registration_service.GENERIC_REGISTER_MESSAGE,
        expires_in_seconds=settings.OTP_EXPIRE_MINUTES * 60,
        resend_available_in_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
    )


@router.post("/register/verify", response_model=dict)
async def verify_registration(
    request: VerifyRegistrationRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Completes a registration by redeeming the one-time code, creating the account only now.

    No session is issued on success. Anyone able to read the mailbox could otherwise walk away
    with a live session, so the client is sent to the normal login flow where the password is
    still required.
    """
    user = await registration_service.verify_registration(
        db,
        email=request.email,
        code=request.code,
        ip=client_ip(http_request),
    )

    return {
        "message": "Verifikasi berhasil. Akun Anda telah aktif, silakan masuk.",
        "user_id": str(user.id),
        "email": user.email,
    }


@router.post("/register/resend", response_model=RegistrationChallengeResponse)
async def resend_registration_otp(
    request: ResendOtpRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Issues a replacement code for a registration still awaiting verification.

    Guarded by a per-request cooldown and a hard resend ceiling, because an uncapped resend
    button is itself an abuse vector: it turns the mail provider into a free relay for flooding
    an arbitrary inbox.
    """
    recipient, full_name, code = await registration_service.resend_otp(
        db, email=request.email, ip=client_ip(http_request)
    )

    if code is not None:
        background_tasks.add_task(registration_service.dispatch_otp_email, recipient, full_name, code)

    return RegistrationChallengeResponse(
        message=registration_service.GENERIC_REGISTER_MESSAGE,
        expires_in_seconds=settings.OTP_EXPIRE_MINUTES * 60,
        resend_available_in_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Authenticates user credentials and issues a base JWT.
    The initial token intentionally omits the 'active_role' claim to force the client to explicitly select a role before accessing protected resources.
    """
    canonical = canonicalize_email(request.email)
    result = await db.execute(select(User).where(User.email_canonical == canonical))
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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.schemas.auth_schema import (
    ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordRequest, ResetPasswordResponse,
    VerifyResetCodeRequest, VerifyResetCodeResponse,
    SelectRoleRequest, TokenResponse, LoginRequest, RegisterRequest, LoginResponse,
    AddRoleRequest, VerifyRegistrationRequest, ResendOtpRequest, RegistrationChallengeResponse,
)
from app.api.dependencies import get_current_user_id, get_token_payload
from app.services.auth_service import verify_user_owns_role, get_user_roles
from app.core.security import create_access_token, verify_password, get_password_hash
from datetime import timedelta
from app.core.config import settings
from app.models.user import User, UserRole, AppRole
from app.services import registration_service, password_reset_service
from app.services.rate_limit_service import client_ip, hit as rate_limit_hit
from app.core.email_rules import canonicalize_email

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Roles a user may grant themselves. Admin is intentionally excluded so it can only be
# assigned out-of-band by a trusted process, never through a self-service request.
SELF_ASSIGNABLE_ROLES = frozenset({AppRole.Buyer, AppRole.Seller, AppRole.Driver})

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
    account exists stops automated sign-ups and disposable accounts.
    If the email is already registered, an immediate 400 Bad Request is returned to notify
    the user and prevent unwanted email dispatch to existing accounts.
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

    background_tasks.add_task(registration_service.dispatch_otp_email, recipient, full_name, code)

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
async def login(
    request: LoginRequest,
    response: Response,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate credentials and issue a base JWT (no active_role claim yet).

    The attempt is rate limited per source IP and per targeted account before any password
    check runs, so the endpoint cannot be used for unbounded credential stuffing or password
    brute forcing. Limits are enforced on both dimensions so neither one machine against many
    accounts nor many machines against one account slips through.
    """
    canonical = canonicalize_email(request.email)
    ip = client_ip(http_request)

    ip_limit = await rate_limit_hit(
        db, f"login_ip:{ip}", settings.LOGIN_MAX_PER_IP_PER_15MIN, 900
    )
    account_limit = await rate_limit_hit(
        db, f"login_acct:{canonical}", settings.LOGIN_MAX_PER_ACCOUNT_PER_15MIN, 900
    )
    await db.commit()  # persist the counters so a rejected attempt still consumes its slot
    if not ip_limit.allowed or not account_limit.allowed:
        retry_after = max(ip_limit.retry_after_seconds, account_limit.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan masuk. Silakan coba lagi nanti.",
            headers={"Retry-After": str(retry_after)},
        )

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
    """Grant an additional self-service role to the authenticated user.

    Only Buyer, Seller, and Driver may be self-assigned. Admin is never grantable through
    this endpoint: without that restriction any authenticated user could escalate to full
    administrative access, since the endpoint otherwise trusts the requested role verbatim.
    """
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        role_enum = AppRole(request.role.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")

    if role_enum not in SELF_ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role_enum.value}' cannot be self-assigned.",
        )

    owns_role = await verify_user_owns_role(db, user_id=user_id, role=role_enum.value)
    if owns_role:
        return {"message": f"User already has the role: {request.role}"}

    user_role = UserRole(user_id=user_id, role=role_enum)
    db.add(user_role)
    await db.commit()
    
    return {"message": f"Successfully added role: {request.role}"}


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    request: ForgotPasswordRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiates account password recovery.

    Verifies account presence and dispatches a single-use 6-digit OTP to the registered mailbox.
    Returns 400 Bad Request if the account is not found.
    """
    ip = client_ip(http_request)
    recipient, full_name, code = await password_reset_service.request_password_reset(
        db, email=request.email, ip=ip
    )

    background_tasks.add_task(
        password_reset_service.dispatch_reset_password_email, recipient, full_name, code
    )

    return ForgotPasswordResponse(
        message="Kode verifikasi pemulihan kata sandi telah dikirim ke email Anda.",
        expires_in_seconds=settings.OTP_EXPIRE_MINUTES * 60,
        resend_available_in_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
    )


@router.post(
    "/reset-password/verify",
    response_model=VerifyResetCodeResponse,
    summary="Verifikasi Kode PIN Reset Password",
    description="Tahap 2: Pengguna wajib memasukkan kode PIN 6 digit yang dikirim ke email. "
                "Jika kode valid, server mengembalikan `reset_token` kriptografis yang digunakan "
                "oleh antarmuka pengguna untuk membuka dan menampilkan form ganti kata sandi baru.",
)
@router.post(
    "/verify-reset-code",
    response_model=VerifyResetCodeResponse,
    include_in_schema=False,
)
async def verify_reset_password_code(
    request: VerifyResetCodeRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Memverifikasi keabsahan kode PIN 6 digit pemulihan kata sandi.

    - **email**: Alamat email akun terdaftar.
    - **code**: Kode PIN 6 digit yang diterima pengguna.

    Mengembalikan `reset_token` berumur pendek (15 menit) yang digunakan sebagai
    bukti otorisasi untuk menampilkan form ganti kata sandi dan mengeksekusi reset kata sandi.
    """
    ip = client_ip(http_request)
    _, reset_token, expires_in_seconds = await password_reset_service.verify_reset_code(
        db,
        email=request.email,
        code=request.code,
        ip=ip,
    )

    return VerifyResetCodeResponse(
        message="Kode verifikasi berhasil divalidasi. Silakan lanjutkan pengisian kata sandi baru.",
        reset_token=reset_token,
        expires_in_seconds=expires_in_seconds,
    )


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    summary="Setel Kata Sandi Baru",
    description="Tahap 3: Form ganti password baru mengirimkan `reset_token` yang didapatkan dari tahap 2 "
                "bersama dengan kata sandi baru. Setelah berhasil diubah, sesi dan token langsung dianulir (single-use).",
)
async def reset_password(
    request: ResetPasswordRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Memvalidasi otorisasi pemulihan kata sandi dan memperbarui kata sandi pengguna.

    - **reset_token**: Token otorisasi yang diperoleh dari `/reset-password/verify` (Direkomendasikan).
    - **email**: Alamat email akun (opsional jika menggunakan `reset_token`).
    - **code**: Kode PIN 6 digit (opsional jika menggunakan `reset_token`).
    - **new_password**: Kata sandi baru (minimal 8 karakter, wajib mengandung huruf dan angka).
    """
    ip = client_ip(http_request)
    await password_reset_service.verify_and_reset_password(
        db,
        new_password=request.new_password,
        reset_token=request.reset_token,
        email=request.email,
        code=request.code,
        ip=ip,
    )

    return ResetPasswordResponse(
        message="Kata sandi berhasil diperbarui. Silakan masuk menggunakan kata sandi baru Anda."
    )



@router.post("/reset-password/resend", response_model=ForgotPasswordResponse)
async def resend_reset_password_otp(
    request: ForgotPasswordRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Issues a replacement OTP for an ongoing password recovery session.
    """
    ip = client_ip(http_request)
    recipient, full_name, code = await password_reset_service.resend_password_reset_otp(
        db, email=request.email, ip=ip
    )

    background_tasks.add_task(
        password_reset_service.dispatch_reset_password_email, recipient, full_name, code
    )

    return ForgotPasswordResponse(
        message="Kode verifikasi baru telah dikirim ke email Anda.",
        expires_in_seconds=settings.OTP_EXPIRE_MINUTES * 60,
        resend_available_in_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
    )

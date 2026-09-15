from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import List, Optional

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False

class RegisterRequest(BaseModel):
    """
    Payload that opens a registration. Nothing is persisted to the users table from this
    request; it only stages an attempt and triggers an OTP.
    """
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)
    roles: Optional[List[str]] = None

    @field_validator("password")
    @classmethod
    def password_must_be_mixed(cls, value: str) -> str:
        """
        Rejects trivially weak passwords at the edge of the system.
        Length alone is a poor filter: enforcing at least one letter and one digit here means
        the service layer never has to re-validate what the schema already guarantees.
        """
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Kata sandi harus mengandung huruf dan angka.")
        return value

    @field_validator("full_name")
    @classmethod
    def full_name_not_blank(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Nama lengkap tidak valid.")
        return cleaned


class VerifyRegistrationRequest(BaseModel):
    """
    Redeems a staged registration. The email is carried alongside the code because no session
    exists yet at this point in the flow.
    """
    email: EmailStr
    code: str = Field(min_length=4, max_length=10, pattern=r"^\d+$")


class ResendOtpRequest(BaseModel):
    email: EmailStr


class RegistrationChallengeResponse(BaseModel):
    """
    Deliberately uniform response for every registration outcome.

    The timings tell the client how to render the OTP screen without disclosing whether an
    account was actually staged, so the endpoint cannot be used to test address existence.
    """
    message: str
    expires_in_seconds: int
    resend_available_in_seconds: int

class SelectRoleRequest(BaseModel):
    chosen_role: str

class AddRoleRequest(BaseModel):
    role: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    owned_roles: List[str]
    active_role: Optional[str] = None

class LoginResponse(TokenResponse):
    pass

class FinancialsResponse(BaseModel):
    walletBalance: float = 0.0
    sellerIncome: float = 0.0
    driverEarnings: float = 0.0

class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    roles: List[str]
    active_role: Optional[str] = None
    financials: FinancialsResponse

class UserProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    """
    Payload to initiate password recovery for an account.
    """
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """
    Response providing client-side challenge timing metrics.
    """
    message: str
    expires_in_seconds: int
    resend_available_in_seconds: int


class VerifyResetCodeRequest(BaseModel):
    """
    Payload untuk memverifikasi kode PIN 6 digit sebelum pengguna membuka form ganti kata sandi baru.
    """
    email: EmailStr = Field(..., description="Alamat email akun yang meminta pemulihan kata sandi.")
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="Kode PIN verifikasi 6 digit angka.")


class VerifyResetCodeResponse(BaseModel):
    """
    Respons setelah kode PIN 6 digit berhasil divalidasi.
    Menyediakan reset_token yang wajib dikirimkan saat mengisi form kata sandi baru.
    """
    message: str = Field(..., description="Pesan konfirmasi keberhasilan verifikasi kode PIN.")
    reset_token: str = Field(..., description="Token otorisasi pemulihan sementara bertanda tangan kriptografis.")
    expires_in_seconds: int = Field(..., description="Masa berlaku reset_token dalam detik.")


class ResetPasswordRequest(BaseModel):
    """
    Payload untuk mengatur kata sandi baru.
    Mendukung skema best-practice menggunakan `reset_token` (setelah PIN lolos verifikasi),
    maupun skema backward-compatibility dengan menyertakan `email` dan `code`.
    """
    reset_token: Optional[str] = Field(default=None, description="Token otorisasi yang didapat dari /reset-password/verify.")
    email: Optional[EmailStr] = Field(default=None, description="Alamat email akun (opsional jika menggunakan reset_token).")
    code: Optional[str] = Field(default=None, min_length=6, max_length=6, pattern=r"^\d{6}$", description="Kode OTP 6 digit (opsional jika menggunakan reset_token).")
    new_password: str = Field(min_length=8, max_length=128, description="Kata sandi baru pengguna.")

    @field_validator("new_password")
    @classmethod
    def password_must_be_mixed(cls, value: str) -> str:
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Kata sandi baru harus mengandung huruf dan angka.")
        return value

    @model_validator(mode="after")
    def check_token_or_code_present(self) -> "ResetPasswordRequest":
        if not self.reset_token and not (self.email and self.code):
            raise ValueError("Wajib menyertakan 'reset_token' dari tahap verifikasi PIN, atau kombinasi 'email' dan 'code'.")
        return self


class ResetPasswordResponse(BaseModel):
    """
    Konfirmasi keberhasilan pembaruan kata sandi akun.
    """
    message: str = Field(..., description="Pesan konfirmasi berhasil memperbarui kata sandi.")


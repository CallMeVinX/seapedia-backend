from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Seapedia Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"

    # Public base URL of the SPA, used to build links inside outbound email.
    FRONTEND_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/seapedia"

    # JWT Auth
    SECRET_KEY: str = "supersecretkey" # Override in .env
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 days

    # Supabase (for storage)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # ---- Email delivery -------------------------------------------------
    # EMAIL_PROVIDER: "auto" resolves to "resend" when RESEND_API_KEY is set,
    # otherwise falls back to "console" so local development never sends real mail.
    EMAIL_PROVIDER: str = "auto"
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "Seapedia <onboarding@resend.dev>"
    EMAIL_TIMEOUT_SECONDS: float = 10.0

    # ---- Registration OTP -----------------------------------------------
    OTP_LENGTH: int = 6
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5           # wrong-code submissions before the pending row is burned
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    OTP_MAX_RESENDS: int = 5            # resends allowed per pending registration

    # ---- Signup abuse throttling ----------------------------------------
    SIGNUP_MAX_PER_EMAIL_PER_HOUR: int = 5
    SIGNUP_MAX_PER_IP_PER_HOUR: int = 10
    SIGNUP_MAX_PER_IP_PER_DAY: int = 20
    VERIFY_MAX_PER_IP_PER_HOUR: int = 30

    # Reject addresses whose domain publishes no MX record (catches typos and
    # throwaway domains). Fails open when DNS itself is unreachable.
    SIGNUP_REQUIRE_MX_RECORD: bool = True

    class Config:
        env_file = ".env"

settings = Settings()

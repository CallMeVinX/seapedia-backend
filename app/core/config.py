from pydantic_settings import BaseSettings
from pydantic import model_validator

# Placeholder secret shipped for local development. It must never reach production, where a
# known signing key means anyone can forge a valid JWT for any user and role.
_INSECURE_DEFAULT_SECRET = "supersecretkey"


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

    # Login brute-force throttle. Counted per IP and per targeted account so neither a single
    # source hammering many accounts nor many sources hammering one account goes unbounded.
    LOGIN_MAX_PER_IP_PER_15MIN: int = 20
    LOGIN_MAX_PER_ACCOUNT_PER_15MIN: int = 10

    # Reject addresses whose domain publishes no MX record (catches typos and
    # throwaway domains). Fails open when DNS itself is unreachable.
    SIGNUP_REQUIRE_MX_RECORD: bool = True

    @model_validator(mode="after")
    def _forbid_insecure_secret_in_production(self):
        """Refuse to boot in production with the development signing key still in place."""
        if self.ENVIRONMENT == "production" and self.SECRET_KEY == _INSECURE_DEFAULT_SECRET:
            raise ValueError(
                "SECRET_KEY is set to the insecure development default in a production "
                "environment. Set a strong, unique SECRET_KEY before deploying."
            )
        return self

    class Config:
        env_file = ".env"

settings = Settings()

from sqlalchemy import Column, String, Integer, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from app.db.session import Base


class PendingRegistration(Base):
    """
    Holds a signup that has been requested but not yet proven by OTP.

    Registrations are staged here instead of being written straight into `users` so that an
    unverified attempt never becomes an account. A bot hammering /auth/register therefore
    produces rows in a disposable table that expire on their own, and can never inflate the
    real user base, occupy a victim's email address, or collect a new-user voucher.
    """
    __tablename__ = "pending_registrations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # `email` is kept verbatim for delivery; `email_canonical` is the alias-collapsed form
    # and carries the uniqueness constraint, so one mailbox can only hold one pending signup.
    email = Column(String(255), nullable=False)
    email_canonical = Column(String(255), nullable=False, unique=True, index=True)

    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    roles = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    # Only the HMAC digest is persisted; the plaintext OTP exists solely inside the email.
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, server_default=text("0"))
    resend_count = Column(Integer, nullable=False, server_default=text("0"))

    request_ip = Column(INET, nullable=True)
    last_sent_at = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"), nullable=False)


class RateLimitCounter(Base):
    """
    Generic fixed-window counter used to throttle abuse-prone endpoints.

    Postgres is used rather than Redis because the traffic volume does not justify another
    managed service on a free-tier deployment, and because the counter must survive the
    instance restarts that a cold-starting host performs routinely. Increments are applied
    through a single atomic UPSERT so concurrent requests cannot race past the limit.
    """
    __tablename__ = "rate_limit_counters"

    key = Column(String(200), primary_key=True)
    count = Column(Integer, nullable=False, server_default=text("0"))
    window_start = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

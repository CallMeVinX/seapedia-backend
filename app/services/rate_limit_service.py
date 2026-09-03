"""
Fixed-window rate limiting backed by Postgres.

A dedicated store (Redis, or an API gateway) is the usual answer, but neither is available on
the current free-tier deployment and both would add an operational dependency for a handful of
counters. Correctness under concurrency is preserved by doing the whole check-and-increment in
one atomic UPSERT rather than a read followed by a write.
"""

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    retry_after_seconds: int


_UPSERT = text("""
    INSERT INTO rate_limit_counters (key, count, window_start)
    VALUES (:key, 1, NOW())
    ON CONFLICT (key) DO UPDATE SET
        count = CASE
            WHEN rate_limit_counters.window_start < NOW() - make_interval(secs => :window_seconds)
            THEN 1
            ELSE rate_limit_counters.count + 1
        END,
        window_start = CASE
            WHEN rate_limit_counters.window_start < NOW() - make_interval(secs => :window_seconds)
            THEN NOW()
            ELSE rate_limit_counters.window_start
        END
    RETURNING count, EXTRACT(EPOCH FROM (window_start + make_interval(secs => :window_seconds) - NOW()))::int AS retry_after
""")


async def hit(db: AsyncSession, key: str, limit: int, window_seconds: int) -> RateLimitResult:
    """
    Records one use of `key` and reports whether the caller is still within `limit`.

    The CASE expressions roll the window over in the same statement that increments it, so two
    simultaneous requests can never both observe a stale window and each reset the counter —
    the failure mode that lets a burst slip past a naive read-then-write limiter.
    """
    result = await db.execute(
        _UPSERT, {"key": key, "window_seconds": window_seconds}
    )
    row = result.one()
    count, retry_after = int(row[0]), max(int(row[1] or 0), 1)
    return RateLimitResult(allowed=count <= limit, count=count, retry_after_seconds=retry_after)


def client_ip(request: Request) -> str:
    """
    Extracts the originating IP, honouring the proxy header set by the hosting platform.

    Behind a reverse proxy `request.client.host` is always the proxy itself, which would
    collapse every visitor into a single bucket and rate-limit the entire user base as one.
    Only the first hop is trusted; note that this header is forgeable if the app is ever
    exposed without a proxy in front of it, so it must not be treated as an identity.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "detail": exc.detail
        },
        # Headers carried on the exception must survive. Throttled endpoints answer with
        # Retry-After, and dropping it leaves the client with no idea how long to wait.
        headers=getattr(exc, "headers", None),
    )

def _serializable_errors(errors: list) -> list:
    """
    Strips values that json.dumps cannot encode out of Pydantic's error list.

    A custom field_validator reports failure by raising ValueError, and Pydantic v2 attaches
    that exception object under ctx["error"]. Serialising it raises TypeError inside the
    handler itself, which turns a clean 422 into an opaque 500 — so the exception is reduced
    to its message and any other exotic context value is stringified.
    """
    cleaned = []
    for err in errors:
        item = {k: v for k, v in err.items() if k != "ctx"}
        item["loc"] = [str(part) for part in err.get("loc", ())]
        ctx = err.get("ctx")
        if ctx:
            item["ctx"] = {
                key: (str(value) if isinstance(value, Exception) else value)
                for key, value in ctx.items()
            }
        # `input` echoes whatever the client sent and may hold a raw password, so it is
        # never reflected back in the response body.
        item.pop("input", None)
        item.pop("url", None)
        cleaned.append(item)
    return cleaned


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = _serializable_errors(exc.errors())
    # Build a readable message from errors
    msg = "; ".join([f"{'.'.join(err['loc'])}: {err['msg']}" for err in errors])
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": "Validation error occurred",
            "detail": msg,
            "errors": errors
        }
    )

async def generic_exception_handler(request: Request, exc: Exception):
    """
    Last-resort handler for anything that escaped the routers.

    The exception text is written to the log and deliberately withheld from the response in
    production. An unhandled error here is usually a database or driver failure, and those
    messages carry table names, column names, connection strings and fragments of the failing
    query — handing them to an anonymous caller maps out the schema for free. Development keeps
    the detail inline, where fast feedback matters more than disclosure.

    Both paths share a short error id so a user-reported failure can be matched to its log
    entry without the response having to describe what actually broke.
    """
    error_id = uuid.uuid4().hex[:8]
    logger.error(
        "Unhandled exception [%s] on %s %s: %s",
        error_id, request.method, request.url.path, exc,
        exc_info=True,
    )

    is_production = settings.ENVIRONMENT == "production"
    detail = (
        f"Terjadi kesalahan pada server. Sertakan kode {error_id} bila menghubungi dukungan."
        if is_production
        else f"[{error_id}] {type(exc).__name__}: {exc}"
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Internal server error occurred",
            "detail": detail,
            "error_id": error_id,
        }
    )

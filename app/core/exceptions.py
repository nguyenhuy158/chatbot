"""Custom exceptions and handlers."""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    """Base application exception."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, message: str, **extra):
        self.message = message
        self.extra = extra
        super().__init__(message)


class AuthError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "auth_error"


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class QuotaExceededError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "quota_exceeded"


class ModerationBlockError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "moderation_blocked"


class LLMError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "llm_error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "app_exception",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
            **exc.extra,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_code, "message": exc.message, **exc.extra},
        )

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "Internal server error"},
        )

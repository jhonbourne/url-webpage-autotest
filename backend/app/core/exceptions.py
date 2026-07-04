import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, user-reportable failures."""

    status_code = 500
    error_code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, error_code: str | None = None):
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code


class FetchError(AppError):
    status_code = 502
    error_code = "FETCH_FAILED"


class FetchTimeoutError(FetchError):
    error_code = "FETCH_TIMEOUT"


class BlockedUrlError(FetchError):
    """URL rejected by the SSRF guard (non-http scheme, private address, ...)."""

    status_code = 400
    error_code = "URL_BLOCKED"


class EmptyPageError(FetchError):
    error_code = "EMPTY_RESPONSE"


class PlanningError(AppError):
    status_code = 422
    error_code = "PLANNING_FAILED"


class ExtractionError(AppError):
    status_code = 422
    error_code = "EXTRACTION_FAILED"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("request failed: %s %s", exc.error_code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"status": "error", "error": {"code": exc.error_code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
            },
        )

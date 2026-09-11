"""Global exception handlers producing one consistent error envelope."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def _envelope(status_code: int, error_code: str, message, path: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {"code": error_code, "message": message},
            "path": path,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return _envelope(exc.status_code, exc.error_code, exc.detail, request.url.path)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return _envelope(exc.status_code, "http_error", exc.detail, request.url.path)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(str(p) for p in err["loc"][1:]) or "body",
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return _envelope(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            errors,
            request.url.path,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        logger.warning("Integrity error at %s: %s", request.url.path, exc)
        return _envelope(
            status.HTTP_409_CONFLICT,
            "integrity_error",
            "That operation conflicts with existing data.",
            request.url.path,
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        logger.exception("Database error at %s", request.url.path)
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "database_error",
            "A database error occurred.",
            request.url.path,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error at %s", request.url.path)
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred.",
            request.url.path,
        )

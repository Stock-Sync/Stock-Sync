import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import APIError

logger = logging.getLogger(__name__)


def error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def serialize_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert validation errors to JSON-serializable format."""
    serialized = []
    for error in errors:
        serialized_error = dict(error)
        # Convert any non-serializable values in ctx
        if "ctx" in serialized_error and serialized_error["ctx"]:
            serialized_ctx = {}
            for k, v in serialized_error["ctx"].items():
                if isinstance(v, (str, int, float, bool, type(None))):
                    serialized_ctx[k] = v
                else:
                    serialized_ctx[k] = str(v)
            serialized_error["ctx"] = serialized_ctx
        serialized.append(serialized_error)
    return serialized


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload("validation_error", "Request validation failed", serialize_errors(exc.errors())),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_payload("conflict", "Resource already exists or violates a constraint"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload("http_error", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_payload("internal_error", "Internal server error"),
        )
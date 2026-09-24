"""Stable, sanitized JSON errors for the HTTP API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def install_error_handlers(app: FastAPI) -> None:
    """Map expected and unexpected failures to the documented error envelope."""

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        code, message = _http_error_details(error.status_code)
        return _response(error.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def request_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return _response(422, "invalid_request", "Request input is invalid")

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, __: Exception) -> JSONResponse:
        return _response(500, "internal_error", "An unexpected error occurred")


def _http_error_details(status_code: int) -> tuple[str, str]:
    known = {
        401: ("unauthorized", "Invalid or missing API key"),
        404: ("not_found", "Resource not found"),
        413: ("file_too_large", "File exceeds the allowed size"),
        415: ("unsupported_media_type", "File type is not supported"),
        422: ("invalid_request", "Request input is invalid"),
        503: ("service_unavailable", "Service is not configured"),
    }
    return known.get(status_code, ("request_failed", "Request could not be completed"))


def _response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )

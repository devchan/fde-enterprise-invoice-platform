from http import HTTPStatus
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id


def error_body(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id or get_request_id(),
        }
    }


def api_error(
    *,
    http_status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail=error_body(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        ),
    )


def conflict_error(code: str, message: str, *, request_id: str | None = None) -> HTTPException:
    return api_error(
        http_status=status.HTTP_409_CONFLICT,
        code=code,
        message=message,
        request_id=request_id,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_body_from_http_exception(request, exc),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_body(
            code="request_validation_failed",
            message="Request validation failed.",
            details={"errors": jsonable_encoder(exc.errors())},
            request_id=_request_id(request),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body(
            code="internal_server_error",
            message="An unexpected server error occurred.",
            request_id=_request_id(request),
        ),
    )


def _body_from_http_exception(request: Request, exc: StarletteHTTPException) -> dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
        body = {"error": dict(detail["error"])}
        body["error"]["details"] = body["error"].get("details") or {}
        body["error"]["request_id"] = body["error"].get("request_id") or _request_id(request)
        return body

    message = detail if isinstance(detail, str) and detail else _status_phrase(exc.status_code)
    return error_body(
        code=_http_error_code(exc.status_code),
        message=message,
        details={} if isinstance(detail, str) else {"detail": jsonable_encoder(detail)},
        request_id=_request_id(request),
    )


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or get_request_id())


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP error"


def _http_error_code(status_code: int) -> str:
    if status_code == status.HTTP_404_NOT_FOUND:
        return "not_found"
    if status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        return "method_not_allowed"
    return "http_error"

"""One error shape for every failure:

    {"error": {"code": "INSUFFICIENT_STOCK", "message": "...", "field": null,
               "details": {...}, "request_id": "..."}}

validation (malformed / wrong types)  -> 422 VALIDATION_ERROR, logged at INFO
domain rule / not found / conflict    -> 422 / 404 / 409 with a specific code, logged at WARNING
database unreachable                  -> 503 DATABASE_UNAVAILABLE, logged at ERROR
anything else                         -> 500 INTERNAL_ERROR, logged at ERROR with the stack trace
                                         (the client never sees the trace)
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import DomainError
from app.logging_setup import request_id_var

log = logging.getLogger("app.errors")


def error_response(
    status: int,
    code: str,
    message: str,
    *,
    field: str | None = None,
    details: Any = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "field": field,
                "details": details if details is not None else {},
                "request_id": request_id_var.get(),
            }
        },
    )


def _field_name(loc: tuple) -> str:
    # ("body", "IN", "unit_cost") -> "unit_cost"; ("query", "limit") -> "limit"
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    parts = [p for p in parts if p not in ("IN", "OUT", "TRANSFER", "ADJUSTMENT")]
    return ".".join(parts) or "body"


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    problems = [
        {"field": _field_name(tuple(e.get("loc", ()))), "message": e.get("msg", "invalid")}
        for e in exc.errors()
    ]
    log.info(
        "request validation failed",
        extra={"ctx": {"path": request.url.path, "fields": [p["field"] for p in problems]}},
    )
    first = problems[0] if problems else {"field": None, "message": "invalid request"}
    return error_response(
        422,
        "VALIDATION_ERROR",
        f"{first['field']}: {first['message']}" if first["field"] else first["message"],
        field=first["field"],
        details={"errors": problems},
    )


async def _domain_handler(request: Request, exc: DomainError) -> JSONResponse:
    log.warning(
        "business rule rejected request",
        extra={"ctx": {"path": request.url.path, "code": exc.code, **exc.details}},
    )
    return error_response(
        exc.http_status, exc.code, exc.message, field=exc.field, details=exc.details
    )


async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    return error_response(
        exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail)
    )


async def _integrity_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # Reached only if a DB constraint catches something the domain layer did not.
    log.warning("database constraint rejected write", extra={"ctx": {"path": request.url.path}})
    return error_response(
        409, "CONSTRAINT_VIOLATION", "the change conflicts with current data; nothing was saved"
    )


async def _operational_handler(request: Request, exc: OperationalError) -> JSONResponse:
    log.error("database unavailable", exc_info=exc, extra={"ctx": {"path": request.url.path}})
    return error_response(503, "DATABASE_UNAVAILABLE", "database is unavailable, try again shortly")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(DomainError, _domain_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(IntegrityError, _integrity_handler)
    app.add_exception_handler(OperationalError, _operational_handler)

"""Application entry point: `uvicorn app.main:app`.

Request flow: middleware (request id, timing, last-resort 500) -> router (app/api) ->
service (app/services: transaction + lock) -> domain rules (app/domain) -> repositories (app/db).
"""

import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text

from app.api import routes_catalog, routes_movements, routes_reports
from app.api.errors import error_response, register_error_handlers
from app.config import Settings, load_settings
from app.db.session import build_engine, build_session_factory
from app.logging_setup import configure_logging, request_id_var

log = logging.getLogger("app.request")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    engine = engine or build_engine(settings.database_url)

    app = FastAPI(
        title="Warehouse Stock Ledger API",
        version="1.0.0",
        description=(
            "Immutable stock movements with derived balances, weighted average cost and "
            "reconciliation. Errors always use the shape "
            '`{"error": {"code", "message", "field", "details", "request_id"}}`.'
        ),
    )
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)

    register_error_handlers(app)
    for router in (routes_catalog.router, routes_movements.router, routes_reports.router):
        app.include_router(router, prefix="/api/v1")

    @app.get("/health", tags=["meta"])
    def health():
        """Liveness + database connectivity. 503 when the database cannot be reached."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            log.exception("health check failed")
            return JSONResponse(status_code=503, content={"status": "degraded", "database": "down"})
        return {"status": "ok", "database": "ok"}

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "unhandled error",
                extra={"ctx": {"method": request.method, "path": request.url.path}},
            )
            response = error_response(
                500, "INTERNAL_ERROR", "unexpected server error; quote the request_id if reporting"
            )
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request completed",
            extra={
                "ctx": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        request_id_var.reset(token)
        return response

    # Added last so it wraps everything, including error responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    return app


app = create_app()

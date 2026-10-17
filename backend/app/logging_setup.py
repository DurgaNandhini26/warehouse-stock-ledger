"""Structured JSON logging with a per-request correlation id.

Every line is one JSON object: ts (UTC), level, logger, msg, request_id, plus any domain
identifiers passed as `extra={"ctx": {...}}`. Request bodies are never logged.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVED = {"ts", "level", "logger", "msg", "request_id"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            payload.update({k: v for k, v in ctx.items() if k not in _RESERVED})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Our middleware logs every request once with its id; uvicorn's access log would duplicate it.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True

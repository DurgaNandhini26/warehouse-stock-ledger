"""Runtime configuration, read once from environment variables (see .env.example)."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Load backend/.env into os.environ for local runs; real env vars always win."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def normalise_database_url(url: str) -> str:
    """Hosted providers hand out postgres:// URLs; SQLAlchemy needs the psycopg3 driver name."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: list[str] = field(default_factory=list)
    log_level: str = "INFO"


def load_settings() -> Settings:
    _load_dotenv()
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        database_url=normalise_database_url(
            os.environ.get("DATABASE_URL", "sqlite:///./stock_ledger.db")
        ),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )

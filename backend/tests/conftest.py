"""Shared fixtures.

By default every test gets its own SQLite file, copied from a template that was migrated once
per run (fast and fully isolated). Set TEST_DATABASE_URL to a PostgreSQL URL to run the same
suite against Postgres; tables are then truncated between tests (CI does this).
"""

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.cli import migrate
from app.config import normalise_database_url
from app.db.session import build_engine, build_session_factory

PG_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def _sqlite_template(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("template") / "template.db"
    migrate(f"sqlite:///{path.as_posix()}")
    return path


@pytest.fixture(scope="session")
def _pg_engine() -> Iterator[Engine | None]:
    if not PG_URL:
        yield None
        return
    url = normalise_database_url(PG_URL)
    migrate(url)
    engine = build_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def database_url(request, tmp_path) -> str:
    if PG_URL:
        return normalise_database_url(PG_URL)
    template = request.getfixturevalue("_sqlite_template")
    path = tmp_path / "test.db"
    shutil.copy(template, path)
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def engine(database_url, _pg_engine) -> Iterator[Engine]:
    if _pg_engine is not None:
        with _pg_engine.begin() as conn:
            # TRUNCATE is not blocked by the row-level immutability trigger.
            conn.execute(
                text(
                    "TRUNCATE stock_balances, movements, locations, products"
                    " RESTART IDENTITY CASCADE"
                )
            )
        yield _pg_engine
        return
    eng = build_engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker[Session]:
    return build_session_factory(engine)


@pytest.fixture
def session(session_factory) -> Iterator[Session]:
    with session_factory() as s:
        yield s

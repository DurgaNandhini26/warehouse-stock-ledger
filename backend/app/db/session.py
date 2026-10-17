"""Engine and session factory.

Concurrency strategy (see README, rule 3):
- PostgreSQL: every stock-changing transaction locks the product row with SELECT ... FOR UPDATE,
  so movements for the same product are serialised while other products proceed in parallel.
- SQLite: every transaction starts with BEGIN IMMEDIATE, which takes the database write lock up
  front. Two racing OUTs therefore run one after the other and the second sees the first's result.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection, _record) -> None:
            # Hand transaction control to SQLAlchemy so we can emit BEGIN IMMEDIATE ourselves.
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        @event.listens_for(engine, "begin")
        def _on_begin(connection) -> None:
            connection.exec_driver_sql("BEGIN IMMEDIATE")

        return engine

    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(session: Session) -> Iterator[Session]:
    """Commit on success, roll back on any exception, so a failure never leaves partial writes."""
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise

"""Operational commands: migrate/seed/reset, and the reviewer aid that corrupts the cache."""

from decimal import Decimal

import pytest

from app import cli
from app.db import repositories as repo
from app.db.session import build_engine, build_session_factory
from app.services import reports
from app.services.reconciliation import reconcile


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def _session(url):
    engine = build_engine(url)
    return engine, build_session_factory(engine)()


def test_seed_is_consistent_idempotent_and_has_a_reversal(db_url, capsys):
    assert cli.main(["seed"]) == 0
    assert cli.main(["seed"]) == 0
    assert "seed skipped" in capsys.readouterr().out

    engine, session = _session(db_url)
    try:
        assert reconcile(session, repair=False).consistent
        products, _ = repo.list_products(session, None, 50, 0)
        assert len(products) == 8
        rows, total = repo.list_movements(session, repo.MovementFilters(), 200, 0)
        assert total == 29
        assert any(r.movement.reverses_movement_id for r in rows)
        assert reports.low_stock(session)  # sample data includes low-stock products
    finally:
        session.close()
        engine.dispose()


def test_corrupt_cache_then_reconcile_finds_it_and_reset_restores(db_url):
    cli.main(["seed"])
    cli.main(["corrupt-cache", "--sku", "rice-snm-25", "--location", "a-01", "--quantity", "40"])
    engine, session = _session(db_url)
    try:
        report = reconcile(session, repair=False)
        assert [(d.sku, d.location_code, d.cached) for d in report.balance_drift] == [
            ("RICE-SNM-25", "A-01", Decimal(40))
        ]
    finally:
        session.close()
        engine.dispose()

    cli.main(["corrupt-cache", "--sku", "TEA-DUST-250", "--location", "QC-HOLD", "--quantity", "3"])
    with pytest.raises(SystemExit):
        cli.main(["corrupt-cache", "--sku", "NOPE", "--location", "A-01", "--quantity", "1"])

    assert cli.main(["reset"]) == 0
    engine, session = _session(db_url)
    try:
        assert reconcile(session, repair=False).consistent
    finally:
        session.close()
        engine.dispose()


def test_migrate_command(db_url):
    assert cli.main(["migrate"]) == 0

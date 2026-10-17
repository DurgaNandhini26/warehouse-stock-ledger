"""Operational commands: `python -m app.cli <command>`.

migrate         apply all Alembic migrations
seed            load sample data (skipped if the database already has products)
reset           drop everything, migrate, seed (local / review use only)
corrupt-cache   deliberately damage one cached balance, to demo the reconcile endpoint
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import load_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = database_url
    return cfg


def migrate(database_url: str) -> None:
    command.upgrade(_alembic_config(database_url), "head")


def downgrade_all(database_url: str) -> None:
    command.downgrade(_alembic_config(database_url), "base")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("seed")
    sub.add_parser("reset")
    corrupt = sub.add_parser("corrupt-cache")
    corrupt.add_argument("--sku", required=True)
    corrupt.add_argument("--location", required=True, help="bin code")
    corrupt.add_argument("--quantity", required=True, type=Decimal)
    args = parser.parse_args(argv)

    url = load_settings().database_url
    # Imported lazily so `migrate` works even before the app modules are importable.
    from app.seed import corrupt_cached_balance, seed_if_empty

    if args.command == "migrate":
        migrate(url)
    elif args.command == "seed":
        migrate(url)
        print("seeded" if seed_if_empty(url) else "database already has data; seed skipped")
    elif args.command == "reset":
        downgrade_all(url)
        migrate(url)
        seed_if_empty(url)
        print("database reset and seeded")
    elif args.command == "corrupt-cache":
        corrupt_cached_balance(url, args.sku, args.location, args.quantity)
        print(f"cached balance for {args.sku} @ {args.location} set to {args.quantity}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

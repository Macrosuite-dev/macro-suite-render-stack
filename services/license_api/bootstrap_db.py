from __future__ import annotations

import logging
import subprocess
import sys

from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.database import normalize_database_url


EXPECTED_TABLES = {"licenses", "activations", "audit_logs"}


def run_alembic(*args: str) -> None:
    command = ["alembic", *args]
    logging.info("running %s", " ".join(command))
    subprocess.run(command, check=True)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    engine = create_engine(normalize_database_url(settings.database_url), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
    finally:
        engine.dispose()

    has_alembic_version = "alembic_version" in tables
    existing_expected = EXPECTED_TABLES & tables

    if has_alembic_version:
        logging.info("alembic version table detected; applying migrations")
        run_alembic("upgrade", "head")
        return 0

    if EXPECTED_TABLES.issubset(tables):
        logging.warning("legacy schema detected without alembic version; stamping current revision")
        run_alembic("stamp", "head")
        return 0

    if existing_expected:
        missing = ", ".join(sorted(EXPECTED_TABLES - tables))
        logging.error("partial legacy schema detected without alembic version; missing tables: %s", missing)
        return 1

    logging.info("no existing schema detected; applying migrations")
    run_alembic("upgrade", "head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

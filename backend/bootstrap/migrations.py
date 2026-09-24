"""Alembic migration runner."""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from common.logger import logger


class MigrationConfigError(RuntimeError):
    """Raised when migration configuration is missing."""


def _table_exists(db_url: str, schema: str, table_name: str) -> bool:
    engine = sa.create_engine(db_url)
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                sa.text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = :schema
                          AND table_name = :table_name
                    )
                    """
                ),
                {"schema": schema, "table_name": table_name},
            ).scalar()
            logger.info(
                f"Migration verify: table existence check schema={schema} table={table_name} exists={bool(exists)}"
            )
            return bool(exists)
    finally:
        engine.dispose()


def run_alembic(config_path: str | None, db_url: str | None) -> None:
    """Run Alembic migrations using provided ini path and DB URL."""
    if not config_path or not db_url:
        raise MigrationConfigError(
            "Missing Alembic configuration path or migration database URL in bootstrap configuration"
        )

    alembic_cfg = Config(config_path)
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    schema = (os.environ.get("POSTGRES_APP_SCHEMA", "public") or "public").strip()
    logger.info(
        f"Running Alembic migrations config={config_path} schema={schema} db_url_set={bool(db_url)}"
    )
    command.upgrade(alembic_cfg, "heads")

    # Safety net: if version table state is inconsistent, force one repair cycle.
    if not _table_exists(db_url, schema, "organizations"):
        logger.warning(
            "Alembic head applied but organizations table missing; attempting one repair cycle "
            "(stamp base -> upgrade heads)."
        )
        command.stamp(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "heads")
        if not _table_exists(db_url, schema, "organizations"):
            raise RuntimeError(
                f"Alembic migration verification failed: '{schema}.organizations' still missing after repair cycle."
            )

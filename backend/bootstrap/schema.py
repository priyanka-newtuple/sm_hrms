"""Schema bootstrap helpers."""

from __future__ import annotations

from sqlalchemy import text

from common.logger import logger


def ensure_schema(engine, schema: str) -> None:
    """Ensure the target schema exists."""
    if not schema:
        schema = "public"
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.commit()
    logger.info("Schema ensured", extra={"schema": schema})


def ensure_core_tables(engine, schema: str) -> None:
    """No-op: tables are managed entirely by Alembic migrations."""
    logger.info("Core tables ensured", extra={"schema": schema})

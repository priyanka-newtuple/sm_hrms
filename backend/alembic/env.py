import os
import sys
from logging.config import fileConfig
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

from alembic import context  # type: ignore[attr-defined]

# Add the backend directory to sys.path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import shared metadata and URL resolver only.
from common.configuration import get_database_url
from database.manager import Base as ModularBase

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url from environment
config.set_main_option(
    "sqlalchemy.url",
    get_database_url(),
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Backend-only metadata; no dependency on deprecated app module.
target_metadata = ModularBase.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

    # Ensure schema exists in a separate committed transaction so that the
    # autobegin state on the alembic connection is clean.  If we execute DDL
    # on the same connection before context.begin_transaction(), SQLAlchemy 2.x
    # autobegin fires an implicit transaction; alembic then detects an active
    # transaction and uses a SAVEPOINT instead of a real commit, causing the
    # whole migration to roll back on connection close.
    with connectable.begin() as setup_conn:
        setup_conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=schema,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

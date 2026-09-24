"""SQLAlchemy engine + SessionLocal for the modular backend.

This is a lightweight replacement for `app.db.session` so modular modules can
create DB sessions without importing from `app/`.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from common.configuration import get_configuration


def _build_database_url() -> URL | str:
    _pg = get_configuration().postgresql_configuration
    schema = _pg.app_schema
    host = _pg.host
    port = _pg.port
    username = _pg.username
    password = _pg.password
    database = _pg.db

    if host and port and username and password and database:
        # Return the URL object directly — never str(URL) as SQLAlchemy masks
        # the password as "***" in __str__, which would be passed literally.
        return URL.create(
            drivername="postgresql",
            username=username,
            password=password,
            host=host,
            port=port,
            database=database,
            query={"options": f"-csearch_path={schema},public"},
        )

    # Fall back to legacy environment variables if present.
    for key in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URL", "SQLALCHEMY_DATABASE_MIGRATION_URL"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value

    raise RuntimeError(
        "Database configuration missing. Set POSTGRES_HOST/PORT/USERNAME/PASSWORD/DATABASE "
        "(recommended) or DATABASE_URL."
    )


DATABASE_URL = _build_database_url()

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
    expire_on_commit=False,
)

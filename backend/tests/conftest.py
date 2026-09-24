from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

MODULE_ROOT = Path(__file__).resolve().parents[1]
module_root_str = str(MODULE_ROOT)
if module_root_str not in sys.path:
    sys.path.insert(0, module_root_str)


# Test organization IDs used by the entities-suite fixtures. Pre-seeded into
# `${schema}.organizations` so cross-schema FKs from entity_types/entities can
# resolve. Tests reference these directly via x-org-id headers.
ENTITIES_TEST_ORG_IDS: tuple[str, ...] = ("test-org-1", "test-org-2")


@pytest.fixture(scope="session")
def entities_db_service_manager():
    """Session-scoped database_service_manager bound to the dev Postgres.

    Connects with `search_path=<app_schema>,public` like the production engine,
    seeds two test organizations, and yields a stub manager exposing the
    `postgres_db_service()` interface that `EntitiesModelService` expects.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql://statemachine:statemachine@modular-db:5432/statemachine"
    )
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={app_schema},public"},
    )

    with engine.begin() as conn:
        for org_id in ENTITIES_TEST_ORG_IDS:
            conn.execute(
                text(
                    f"""
                    INSERT INTO "{app_schema}".organizations (id, name, slug, settings, status)
                    VALUES (:id, :name, :slug, '{{}}', 'active')
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": org_id, "name": f"Test Org {org_id}", "slug": f"slug-{org_id}"},
            )

    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    class _DbService:
        def __init__(self) -> None:
            self.engine = engine

        def get_db_session(self):
            return SessionLocal()

    class _DbServiceManager:
        def __init__(self) -> None:
            self._svc = _DbService()

        def postgres_db_service(self):
            return self._svc

    yield _DbServiceManager()
    engine.dispose()


@pytest.fixture
def clean_entities_tables(entities_db_service_manager):
    """Truncate test-org rows from runtime.entities + definitions.entity_types
    around the requesting test. Explicitly requested by entities-suite tests
    only — NOT autouse, so unrelated tests (e.g. test_startup.py running
    against a fresh DB before migrations) don't trip on missing tables."""
    from sqlalchemy import text

    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
    runtime_schema = f"{app_schema}_runtime"
    definitions_schema = f"{app_schema}_definitions"
    audit_schema = f"{app_schema}_audit"
    engine = entities_db_service_manager.postgres_db_service().engine

    def _cleanup() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'DELETE FROM "{audit_schema}".entity_events '
                    f"WHERE organization_id = ANY(:ids)"
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(
                    f'DELETE FROM "{audit_schema}".transition_attempts '
                    f"WHERE organization_id = ANY(:ids)"
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(
                    f'DELETE FROM "{runtime_schema}".entity_state '
                    f"WHERE organization_id = ANY(:ids)"
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(
                    f'DELETE FROM "{runtime_schema}".entities '
                    f"WHERE organization_id = ANY(:ids)"
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(
                    f'DELETE FROM "{definitions_schema}".entity_type_relations '
                    f"WHERE organization_id = ANY(:ids)"
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )
            conn.execute(
                text(
                    f'DELETE FROM "{definitions_schema}".entity_types '
                    f"WHERE organization_id = ANY(:ids)"
                ),
                {"ids": list(ENTITIES_TEST_ORG_IDS)},
            )

    _cleanup()
    yield
    _cleanup()

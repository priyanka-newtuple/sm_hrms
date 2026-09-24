"""Bootstrap runner for modular backend."""

from __future__ import annotations

from bootstrap.migrations import run_alembic
from bootstrap.schema import ensure_core_tables, ensure_schema
from bootstrap.seed import (
    backfill_user_roles,
    seed_bootstrap_admin,
    seed_default_file_types_for_active_organizations,
    seed_minimum_data,
    seed_permissions_catalog,
)
from common.configuration import Configuration, get_configuration
from common.logger import logger


def run_bootstrap(database_service_manager, config: Configuration) -> None:
    """Run schema ensure, migrations, and seed in order."""
    engine = database_service_manager.postgres_db_service().engine
    _ = config
    bootstrap_config = get_configuration().bootstrap_configuration
    schema = bootstrap_config.app_schema.strip() or "public"
    logger.info(
        "Bootstrap start: "
        f"schema={schema} "
        f"alembic_config_path={bootstrap_config.alembic_config_path} "
        f"migration_url_set={bool(bootstrap_config.migration_url)}"
    )

    ensure_schema(engine, schema)
    ensure_core_tables(engine, schema)
    # Idempotent safety: ensure migrations are definitely applied in app process before seed.
    run_alembic(bootstrap_config.alembic_config_path, bootstrap_config.migration_url)

    seed_minimum_data(
        engine,
        schema,
        bootstrap_config.seed_org_id,
        bootstrap_config.seed_org_name,
        bootstrap_config.seed_org_slug,
    )
    seed_bootstrap_admin(database_service_manager, config)
    seed_default_file_types_for_active_organizations(database_service_manager)
    seed_permissions_catalog(database_service_manager)
    backfill_user_roles(database_service_manager)

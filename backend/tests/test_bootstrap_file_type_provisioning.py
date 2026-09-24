from types import SimpleNamespace
from unittest.mock import MagicMock, call

from bootstrap import runner, seed


def test_bootstrap_provisions_file_types_for_all_active_organizations(
    monkeypatch,
) -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        ("org-1",),
        ("org-2",),
    ]
    postgres = MagicMock()
    postgres.get_db_session.return_value = db
    database = MagicMock()
    database.postgres_db_service.return_value = postgres

    file_types = MagicMock()
    file_types.seed_default_file_types.side_effect = [3, 3]
    file_type_factory = MagicMock(return_value=file_types)
    monkeypatch.setattr(seed, "FilehandlerModelService", file_type_factory)

    seed.seed_default_file_types_for_active_organizations(database)

    file_type_factory.assert_called_once_with(database)
    assert file_types.seed_default_file_types.call_args_list == [
        call("org-1"),
        call("org-2"),
    ]
    db.close.assert_called_once()


def test_bootstrap_provisions_file_types_after_organizations_are_seeded(
    monkeypatch,
) -> None:
    calls: list[str] = []
    bootstrap_configuration = SimpleNamespace(
        app_schema="modular_backend",
        alembic_config_path="alembic.ini",
        migration_url="postgresql://test",
        seed_org_id="org-1",
        seed_org_name="Test",
        seed_org_slug="test",
    )
    monkeypatch.setattr(
        runner,
        "get_configuration",
        lambda: SimpleNamespace(bootstrap_configuration=bootstrap_configuration),
    )
    monkeypatch.setattr(runner, "ensure_schema", lambda *_: calls.append("schema"))
    monkeypatch.setattr(runner, "ensure_core_tables", lambda *_: calls.append("tables"))
    monkeypatch.setattr(runner, "run_alembic", lambda *_: calls.append("migrations"))
    monkeypatch.setattr(runner, "seed_minimum_data", lambda *_: calls.append("minimum"))
    monkeypatch.setattr(runner, "seed_bootstrap_admin", lambda *_: calls.append("admin"))
    monkeypatch.setattr(
        runner,
        "seed_default_file_types_for_active_organizations",
        lambda *_: calls.append("file-types"),
    )
    monkeypatch.setattr(
        runner,
        "seed_permissions_catalog",
        lambda *_: calls.append("permissions"),
    )
    monkeypatch.setattr(runner, "backfill_user_roles", lambda *_: calls.append("roles"))

    database = MagicMock()
    config = MagicMock()
    runner.run_bootstrap(database, config)

    assert calls == [
        "schema",
        "tables",
        "migrations",
        "minimum",
        "admin",
        "file-types",
        "permissions",
        "roles",
    ]

from __future__ import annotations

from types import SimpleNamespace

import backend.modular_backend.bootstrap.runner as runner


class _StubEngine:
    def connect(self):
        raise AssertionError("Should not connect in this test")


class _StubPostgresService:
    def __init__(self):
        self.engine = _StubEngine()


class _StubDBManager:
    def postgres_db_service(self):
        return _StubPostgresService()


class _StubConfig:
    def configuration(self):
        return SimpleNamespace(
            bootstrap_configuration=SimpleNamespace(
                app_schema="modular_backend",
                alembic_config_path=None,
                migration_url=None,
                seed_org_id=None,
                seed_org_name=None,
                seed_org_slug=None,
            )
        )


def test_run_bootstrap_skips_alembic_when_missing_config(monkeypatch) -> None:
    calls: list[str] = []

    def _ensure_schema(engine, schema):
        calls.append(f"schema:{schema}")

    def _ensure_core_tables(engine, schema):
        calls.append(f"tables:{schema}")

    def _seed_minimum_data(engine, schema, org_id, org_name, org_slug):
        calls.append(f"seed:{schema}:{org_id}:{org_name}:{org_slug}")

    monkeypatch.setattr(runner, "ensure_schema", _ensure_schema)
    monkeypatch.setattr(runner, "ensure_core_tables", _ensure_core_tables)
    monkeypatch.setattr(runner, "seed_minimum_data", _seed_minimum_data)

    runner.run_bootstrap(_StubDBManager(), _StubConfig())

    assert calls == [
        "schema:modular_backend",
        "tables:modular_backend",
        "seed:modular_backend:None:None:None",
    ]

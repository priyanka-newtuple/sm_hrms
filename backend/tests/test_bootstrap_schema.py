from __future__ import annotations

from backend.modular_backend.bootstrap.schema import ensure_core_tables, ensure_schema


class _StubConnection:
    def __init__(self, statements: list[str]):
        self._statements = statements

    def execute(self, stmt):  # noqa: ANN001
        self._statements.append(str(stmt))

    def commit(self):
        self._statements.append("COMMIT")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _StubEngine:
    def __init__(self):
        self.statements: list[str] = []

    def connect(self):
        return _StubConnection(self.statements)


def test_ensure_schema_emits_create_schema() -> None:
    engine = _StubEngine()
    ensure_schema(engine, "modular_backend")
    assert any("CREATE SCHEMA IF NOT EXISTS \"modular_backend\"" in stmt for stmt in engine.statements)
    assert "COMMIT" in engine.statements


def test_ensure_core_tables_emits_bootstrap_managed_tables_only() -> None:
    engine = _StubEngine()
    ensure_core_tables(engine, "modular_backend")
    assert any("CREATE TABLE IF NOT EXISTS \"modular_backend\".organizations" in stmt for stmt in engine.statements)
    assert not any("CREATE TABLE IF NOT EXISTS \"modular_backend\".tasks" in stmt for stmt in engine.statements)
    assert "COMMIT" in engine.statements

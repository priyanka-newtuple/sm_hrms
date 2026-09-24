from __future__ import annotations

from backend.modular_backend.bootstrap.seed import seed_minimum_data


class _StubConnection:
    def __init__(self, statements: list[str]):
        self._statements = statements

    def execute(self, stmt, params=None):  # noqa: ANN001
        self._statements.append((str(stmt), params))

    def commit(self):
        self._statements.append(("COMMIT", None))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _StubEngine:
    def __init__(self):
        self.statements: list[tuple[str, object]] = []

    def connect(self):
        return _StubConnection(self.statements)


def test_seed_skips_without_config() -> None:
    engine = _StubEngine()

    seed_minimum_data(engine, "modular_backend", None, None, None)
    assert engine.statements == []


def test_seed_inserts_with_config() -> None:
    engine = _StubEngine()

    seed_minimum_data(engine, "modular_backend", "org1", "Org One", "org1")

    assert any("INSERT INTO \"modular_backend\".organizations" in stmt for stmt, _ in engine.statements)
    assert ("COMMIT", None) in engine.statements

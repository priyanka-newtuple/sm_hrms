"""Startup smoke tests.

Verify that the application boots, migrations run, and core endpoints respond.
Requires a running PostgreSQL instance (use `make db` to start one).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _dotenv_loaded() -> bool:
    """Return True if the backend .env has been loaded into the environment."""
    return bool(os.environ.get("BOOTSTRAP_ADMIN_EMAIL"))


@pytest.fixture(scope="module", autouse=True)
def _load_env():
    """Ensure backend .env is loaded before any test in this module."""
    if not _dotenv_loaded():
        from dotenv import load_dotenv

        load_dotenv(BACKEND_ROOT / "etc" / ".env")


def _pg_is_ready() -> bool:
    """Check if PostgreSQL is reachable."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5455")
    result = subprocess.run(
        ["pg_isready", "-h", host, "-p", port, "-q"],
        capture_output=True,
    )
    return result.returncode == 0


requires_db = pytest.mark.skipif(
    not _pg_is_ready(),
    reason="PostgreSQL not available (start with `make db`)",
)


# -- Test 1: app module imports without error ----------------------------------

def test_app_module_imports():
    """main:app should be importable without crashing."""
    from main import app  # noqa: F401
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)


# -- Test 2: health endpoint responds -----------------------------------------

@requires_db
def test_health_endpoint():
    """GET /health should return 200 with status ok."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# -- Test 3: alembic migrations are consistent --------------------------------

@requires_db
def test_alembic_heads_single():
    """There should be exactly one alembic head (no divergent branches)."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "heads"],
        capture_output=True,
        text=True,
        cwd=BACKEND_ROOT,
    )
    assert result.returncode == 0, f"alembic heads failed: {result.stderr}"
    heads = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(heads) == 1, f"Expected 1 head, got {len(heads)}: {heads}"


@requires_db
def test_alembic_current_at_head():
    """Database should be at the latest migration head."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "current"],
        capture_output=True,
        text=True,
        cwd=BACKEND_ROOT,
    )
    assert result.returncode == 0, f"alembic current failed: {result.stderr}"
    assert "(head)" in result.stdout, f"DB not at head: {result.stdout}"


# -- Test 5: JWT_SECRET_KEY is required, no insecure fallback ------------------

def _ensure_configuration_module_importable(monkeypatch):
    """Import common.configuration under a guaranteed-valid dummy secret first.

    The module constructs a Configuration() singleton as an import-time side
    effect. If this is the first import in the test session, that side effect
    runs under whatever JWT_SECRET_KEY happens to already be in the ambient
    environment (e.g. a developer's real, un-rotated .env) — which could
    itself be missing/short/a placeholder and blow up the import before the
    test's own scenario ever runs. Force a safe value first so the import
    always succeeds; each test then overrides JWT_SECRET_KEY again and
    constructs its own fresh Configuration() to exercise the real scenario.
    """
    monkeypatch.setenv("JWT_SECRET_KEY", "a-safe-dummy-secret-for-import-bootstrap-only")
    from common.configuration import Configuration

    return Configuration


def test_missing_jwt_secret_key_fails_startup(monkeypatch):
    """Configuration() must raise if JWT_SECRET_KEY is unset, not fall back silently."""
    Configuration = _ensure_configuration_module_importable(monkeypatch)

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="is not set"):
        Configuration()


def test_short_jwt_secret_key_fails_startup(monkeypatch):
    """Configuration() must reject a JWT_SECRET_KEY that's too short to be a real secret."""
    Configuration = _ensure_configuration_module_importable(monkeypatch)

    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
    with pytest.raises(ValueError, match="must be at least"):
        Configuration()


def test_valid_jwt_secret_key_is_used_as_is(monkeypatch):
    """A properly configured JWT_SECRET_KEY should resolve unchanged, no substitution."""
    Configuration = _ensure_configuration_module_importable(monkeypatch)

    strong_secret = "a-sufficiently-long-secret-value-for-testing-purposes"
    monkeypatch.setenv("JWT_SECRET_KEY", strong_secret)
    config = Configuration()
    assert config._configuration.security_configuration.jwt_secret_key == strong_secret


@pytest.mark.parametrize(
    "placeholder",
    [
        "your-secret-key-here-change-in-production",
        "change-this-to-a-strong-secret-in-production",
        "YOUR-SECRET-KEY-HERE-CHANGE-IN-PRODUCTION",  # case-insensitive match
    ],
)
def test_template_placeholder_jwt_secret_key_fails_startup(monkeypatch, placeholder):
    """Configuration() must reject known env.example placeholders even though they pass the length check."""
    Configuration = _ensure_configuration_module_importable(monkeypatch)

    monkeypatch.setenv("JWT_SECRET_KEY", placeholder)
    with pytest.raises(ValueError, match="placeholder"):
        Configuration()


# -- Test 4: search_path is set correctly on the DB engine ---------------------

@requires_db
def test_db_search_path():
    """PostgresDBService engine should set search_path to the configured schema."""
    from common.configuration import Configuration
    from database.manager import PostgresDBService

    config = Configuration()
    expected_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    db_service = PostgresDBService(config)
    session = db_service.get_db_session()
    try:
        import sqlalchemy
        result = session.execute(sqlalchemy.text("SHOW search_path")).scalar()
        assert expected_schema in result, f"Expected '{expected_schema}' in search_path, got '{result}'"
    finally:
        session.close()

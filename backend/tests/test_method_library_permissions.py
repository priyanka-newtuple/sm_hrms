"""Method library permission scope: the catalog entries, the backfill, the gate.

The method library used to ride on workflow:read / workflow:write and now has its
own keys. Two things have to hold at once: the new keys are genuinely separate
from the workflow ones at the endpoint, and no existing role lost access when the
switch happened. The backfill migration is what buys the second, so it is
exercised here directly rather than trusted.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from common.auth import register_membership_db_service, register_roles_db_service
from common.deps import get_db
from common.security import create_access_token
from method_library.controller import MethodLibraryRestController
from method_library.db_models import MethodLibraryModelService
from method_library.manager import MethodLibraryServiceManager
from permissions.models.interface import DEFAULT_PERMISSION_DEFINITIONS

ORG_A = "test-org-1"
READ_KEY = "method_library:read"
WRITE_KEY = "method_library:write"

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "2026_08_22_0001_backfill_method_library_permissions.py"
)


def _load_migration():
    """Import the migration module by path.

    alembic/versions is not a package, so it cannot be imported normally. Loading
    it this way means the tests run the migration's own SQL rather than a copy of
    it that could drift.
    """
    spec = importlib.util.spec_from_file_location("_backfill_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_migration()


@pytest.fixture
def session(entities_db_service_manager):
    db = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def role_ids(session):
    """Two throwaway roles, removed along with their permissions afterwards."""
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    for index, role_id in enumerate(ids):
        name = f"perm-test-{index}-{role_id[:8]}"
        session.execute(
            text(
                "INSERT INTO roles "
                "(id, organization_id, name, display_name, is_system, priority) "
                "VALUES (:id, :org, :name, :name, false, 0)"
            ),
            {"id": role_id, "org": ORG_A, "name": name},
        )
    session.commit()
    yield ids
    session.execute(
        text("DELETE FROM role_permissions WHERE role_id IN :ids"), {"ids": tuple(ids)}
    )
    session.execute(text("DELETE FROM roles WHERE id IN :ids"), {"ids": tuple(ids)})
    session.commit()


def _grant(session, role_id: str, permission_key: str, allowed: bool = True) -> None:
    session.execute(
        text(
            "INSERT INTO role_permissions (id, role_id, permission_key, allowed) "
            "VALUES (:id, :role_id, :key, :allowed)"
        ),
        {
            "id": str(uuid.uuid4()),
            "role_id": role_id,
            "key": permission_key,
            "allowed": allowed,
        },
    )
    session.commit()


def _keys_for(session, role_id: str) -> list[str]:
    rows = session.execute(
        text("SELECT permission_key FROM role_permissions WHERE role_id = :role_id"),
        {"role_id": role_id},
    ).fetchall()
    return sorted(row[0] for row in rows)


# ── The catalog ───────────────────────────────────────────────────────────────


def test_the_catalog_defines_both_method_library_keys() -> None:
    by_key = {entry["key"]: entry for entry in DEFAULT_PERMISSION_DEFINITIONS}
    assert by_key[READ_KEY]["resource"] == "method_library"
    assert by_key[READ_KEY]["action"] == "read"
    assert by_key[WRITE_KEY]["resource"] == "method_library"
    assert by_key[WRITE_KEY]["action"] == "write"


def test_seeding_puts_both_keys_in_the_permissions_table(
    entities_db_service_manager, session
) -> None:
    """The catalog seeds itself on boot, so the rows should already be there."""
    from permissions.db_models import PermissionsModelService

    PermissionsModelService(entities_db_service_manager).ensure_default_permissions(session)
    rows = session.execute(
        text("SELECT key FROM permissions WHERE key IN (:read_key, :write_key)"),
        {"read_key": READ_KEY, "write_key": WRITE_KEY},
    ).fetchall()
    assert sorted(row[0] for row in rows) == [READ_KEY, WRITE_KEY]


# ── The backfill ──────────────────────────────────────────────────────────────


def test_a_role_with_workflow_read_gains_method_library_read(
    migration, session, role_ids
) -> None:
    role_id = role_ids[0]
    _grant(session, role_id, "workflow:read")

    migration.backfill_method_library_permissions(session.connection())
    session.commit()

    assert _keys_for(session, role_id) == [READ_KEY, "workflow:read"]


def test_a_role_with_workflow_write_gains_method_library_write(
    migration, session, role_ids
) -> None:
    role_id = role_ids[0]
    _grant(session, role_id, "workflow:write")

    migration.backfill_method_library_permissions(session.connection())
    session.commit()

    assert _keys_for(session, role_id) == [WRITE_KEY, "workflow:write"]


def test_the_backfill_carries_a_denial_across_rather_than_granting_access(
    migration, session, role_ids
) -> None:
    """A role explicitly denied workflow:read must not be granted the new key."""
    role_id = role_ids[0]
    _grant(session, role_id, "workflow:read", allowed=False)

    migration.backfill_method_library_permissions(session.connection())
    session.commit()

    allowed = session.execute(
        text(
            "SELECT allowed FROM role_permissions "
            "WHERE role_id = :role_id AND permission_key = :key"
        ),
        {"role_id": role_id, "key": READ_KEY},
    ).scalar()
    assert allowed is False


def test_a_role_without_workflow_access_is_left_alone(migration, session, role_ids) -> None:
    with_workflow, without_workflow = role_ids
    _grant(session, with_workflow, "workflow:read")

    migration.backfill_method_library_permissions(session.connection())
    session.commit()

    assert _keys_for(session, without_workflow) == []


def test_running_the_backfill_twice_inserts_nothing_the_second_time(
    migration, session, role_ids
) -> None:
    """No unique constraint guards (role_id, permission_key), so this must."""
    role_id = role_ids[0]
    # Backfill whatever else the database is carrying first, so the counts below
    # are about this role alone rather than about the state it was left in.
    migration.backfill_method_library_permissions(session.connection())
    session.commit()
    _grant(session, role_id, "workflow:read")
    _grant(session, role_id, "workflow:write")

    first = migration.backfill_method_library_permissions(session.connection())
    session.commit()
    second = migration.backfill_method_library_permissions(session.connection())
    session.commit()

    assert first == 2
    assert second == 0, "a re-run must not duplicate rows"
    assert _keys_for(session, role_id) == [
        READ_KEY,
        WRITE_KEY,
        "workflow:read",
        "workflow:write",
    ]


def test_the_downgrade_removes_only_the_new_keys(migration, session, role_ids) -> None:
    role_id = role_ids[0]
    _grant(session, role_id, "workflow:read")
    migration.backfill_method_library_permissions(session.connection())
    session.commit()

    session.connection().execute(
        text(migration._DELETE_GRANTS.format(schema=migration._schema))
    )
    session.commit()

    assert _keys_for(session, role_id) == ["workflow:read"]


# ── The endpoint gate ─────────────────────────────────────────────────────────


class _RolesGate:
    """Permission-check double, registered through the real auth hook.

    Grants exactly the keys it is given, so a caller holding workflow:write and
    nothing else is a caller the method library must now refuse.
    """

    def __init__(self, granted: set[str]) -> None:
        self.granted = granted
        self.checked: list[str] = []

    def check_permission(self, db, user_id, organization_id, permission_key):
        _ = db, user_id, organization_id
        self.checked.append(permission_key)
        return SimpleNamespace(
            allowed=permission_key in self.granted, reason="not granted"
        )


class _AlwaysActiveMembership:
    """Membership seam for require_permission — reports every membership active so
    these tests exercise the permission gate, not per-org suspension."""

    def is_membership_active(self, db, user_id, org_id) -> bool:
        _ = db, user_id, org_id
        return True


def _client(gate: _RolesGate, db_service_manager) -> TestClient:
    register_roles_db_service(gate)
    register_membership_db_service(_AlwaysActiveMembership())
    manager = MethodLibraryServiceManager(MethodLibraryModelService(db_service_manager))
    manager.start()
    router = APIRouter()
    MethodLibraryRestController(manager).prepare(router)
    app = FastAPI()
    app.include_router(router)

    def _real_db():
        db = db_service_manager.postgres_db_service().get_db_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _real_db
    return TestClient(app)


def _headers() -> dict[str, str]:
    """A real, signature-verified token: the only identity the auth layer trusts."""
    token = create_access_token(subject="user-a", organization_id=ORG_A)
    return {"Authorization": f"Bearer {token}"}


def test_workflow_write_alone_no_longer_opens_the_method_library(
    entities_db_service_manager,
) -> None:
    """The whole point of the new scope: the two are independent now."""
    gate = _RolesGate({"workflow:read", "workflow:write"})
    try:
        response = _client(gate, entities_db_service_manager).post(
            "/method-library/methods",
            json={"name": "Should Not Land", "fields": []},
            headers=_headers(),
        )
        assert response.status_code == 403
        assert gate.checked == [WRITE_KEY], "the route must check its own key"
    finally:
        register_roles_db_service(None)
        register_membership_db_service(None)


def test_workflow_read_alone_no_longer_opens_the_method_library(
    entities_db_service_manager,
) -> None:
    gate = _RolesGate({"workflow:read"})
    try:
        response = _client(gate, entities_db_service_manager).get(
            "/method-library/methods", headers=_headers()
        )
        assert response.status_code == 403
        assert gate.checked == [READ_KEY]
    finally:
        register_roles_db_service(None)
        register_membership_db_service(None)


def test_the_new_keys_do_open_the_method_library(entities_db_service_manager) -> None:
    gate = _RolesGate({READ_KEY, WRITE_KEY})
    try:
        response = _client(gate, entities_db_service_manager).get(
            "/method-library/methods", headers=_headers()
        )
        assert response.status_code == 200
    finally:
        register_roles_db_service(None)
        register_membership_db_service(None)


def test_the_category_routes_use_the_same_scope(entities_db_service_manager) -> None:
    gate = _RolesGate({"workflow:write"})
    try:
        response = _client(gate, entities_db_service_manager).post(
            "/method-library/categories", json={"name": "Blocked"}, headers=_headers()
        )
        assert response.status_code == 403
        assert gate.checked == [WRITE_KEY]
    finally:
        register_roles_db_service(None)
        register_membership_db_service(None)

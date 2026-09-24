from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.deps import get_db
from database.manager import Base
from exceptions import ServiceError
from permissions.controller import PermissionsRestController
from permissions.db_models import Permission, PermissionsModelService
from permissions.models.interface import DEFAULT_PERMISSION_DEFINITIONS
from permissions.models.response import PermissionRead


class _StubPermissionsManager:
    def list_permissions(self, db):  # noqa: ANN001
        _ = db
        return [
            PermissionRead(id="perm-1", key="role:read",  resource="role", action="read",  description="View roles and permissions", is_system=True),
            PermissionRead(id="perm-2", key="role:write", resource="role", action="write", description="Create and update roles",      is_system=True),
        ]


class _StubPermissionsManagerError:
    def list_permissions(self, db):  # noqa: ANN001
        raise ServiceError("db down")


def _build_client(manager=None) -> TestClient:  # noqa: ANN001
    manager = manager or _StubPermissionsManager()
    router = APIRouter()
    PermissionsRestController(manager).prepare(router)
    app = FastAPI()
    app.include_router(router)

    def _stub_db():  # noqa: ANN001
        yield None

    app.dependency_overrides[get_db] = _stub_db
    return TestClient(app)


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Permission.__table__])
    session_local = sessionmaker(bind=engine)
    return session_local(), engine


def test_default_permissions_seed_is_idempotent() -> None:
    db, engine = _db_session()
    try:
        service = PermissionsModelService()

        first = service.ensure_default_permissions(db)
        second = service.ensure_default_permissions(db)

        assert len(first) == len(DEFAULT_PERMISSION_DEFINITIONS)
        assert len(second) == len(DEFAULT_PERMISSION_DEFINITIONS)
        assert db.query(Permission).count() == len(DEFAULT_PERMISSION_DEFINITIONS)
        assert {p.key for p in second} >= {"role:read", "role:write", "user:read", "user:write"}
    finally:
        db.close()
        engine.dispose()


def test_list_permissions_returns_seeded_catalog_ordered() -> None:
    db, engine = _db_session()
    try:
        svc = PermissionsModelService()
        svc.ensure_default_permissions(db)
        permissions = svc.list_permissions(db)

        assert permissions
        assert permissions == sorted(permissions, key=lambda p: (p.resource, p.action, p.key))
        assert all(p.is_system for p in permissions)
    finally:
        db.close()
        engine.dispose()


def test_list_permissions_returns_catalog() -> None:
    client = _build_client()
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "viewer"}

    resp = client.get("/permissions", headers=headers)

    assert resp.status_code == 200
    keys = [item["key"] for item in resp.json()]
    assert keys == ["role:read", "role:write"]
    assert resp.json()[0]["is_system"] is True


def test_list_permissions_requires_auth() -> None:
    client = _build_client()

    resp = client.get("/permissions")

    assert resp.status_code == 401


def test_list_permissions_service_error_maps_to_500() -> None:
    client = _build_client(_StubPermissionsManagerError())
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    resp = client.get("/permissions", headers=headers)

    assert resp.status_code == 500

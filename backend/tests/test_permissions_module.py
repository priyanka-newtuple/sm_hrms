from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Request
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
    def list_permissions(self, db, organization_id=None):  # noqa: ANN001
        _ = db
        return [
            PermissionRead(id="perm-1", key="role:read",  resource="role", action="read",  description="View roles and permissions", is_system=True),
            PermissionRead(id="perm-2", key="role:write", resource="role", action="write", description="Create and update roles",      is_system=True),
        ]


class _StubPermissionsManagerError:
    def list_permissions(self, db, organization_id=None):  # noqa: ANN001
        raise ServiceError("db down")


def _build_client(manager=None) -> TestClient:  # noqa: ANN001
    manager = manager or _StubPermissionsManager()
    router = APIRouter()
    PermissionsRestController(manager).prepare(router)
    app = FastAPI()
    app.include_router(router)

    def _stub_db():  # noqa: ANN001
        yield None

    # Isolate controller contracts from the application's auth composition root.
    from permissions.controller import PermissionReadActor, PermissionWriteActor
    def read_actor(request: Request):
        if not request.headers.get('x-user-id'):
            raise HTTPException(401)
        return {'user_id': request.headers['x-user-id'], 'organization_id': request.headers['x-org-id']}
    def write_actor(request: Request):
        actor = read_actor(request)
        if request.headers.get('x-user-roles') != 'admin':
            raise HTTPException(403)
        return actor
    app.dependency_overrides[PermissionReadActor.__metadata__[0].dependency] = read_actor
    app.dependency_overrides[PermissionWriteActor.__metadata__[0].dependency] = write_actor
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


def test_tenant_permission_registration_is_idempotent_and_isolated():
    from permissions.models.request import PermissionRegistration
    db, engine = _db_session()
    try:
        svc = PermissionsModelService()
        svc.ensure_default_permissions(db)
        payload = PermissionRegistration(namespace='example', resource='project', action='approve', description='Approve a project')
        first = svc.register(db, 'org-a', payload)
        first_id = first.id
        again = svc.register(db, 'org-a', payload)
        other = svc.register(db, 'org-b', payload)
        assert first_id == again.id and other.id != first_id
        assert first.key == 'tenant.org-a.example.project:approve'
        assert not first.is_system
        assert svc.get_by_key(db, first.key, 'org-a') is not None
        assert svc.get_by_key(db, first.key, 'org-b') is None
        assert svc.get_by_key(db, first.key) is None
        assert first.key not in {p.key for p in svc.list_permissions(db, 'org-b')}
        assert {p.key for p in svc.list_permissions(db, 'org-a')} >= {first.key, 'role:read'}
    finally:
        db.close()
        engine.dispose()


def test_roles_cannot_grant_another_tenants_permission():
    from types import SimpleNamespace
    import pytest
    from exceptions import ValidationError
    from permissions.models.request import PermissionRegistration
    from roles.manager import RolesServiceManager
    db, engine = _db_session()
    try:
        svc = PermissionsModelService()
        registered = svc.register(db, 'org-a', PermissionRegistration(namespace='example', resource='project', action='approve', description='Approve'))
        manager = RolesServiceManager.__new__(RolesServiceManager)
        manager.db_model_service = SimpleNamespace(_permissions_svc=svc)
        manager._validate_permission_keys(db, [registered.key], 'org-a')
        with pytest.raises(ValidationError, match='Unknown permission'):
            manager._validate_permission_keys(db, [registered.key], 'org-b')
    finally:
        db.close()
        engine.dispose()


def test_system_roles_do_not_implicitly_receive_application_permissions():
    from types import SimpleNamespace
    from roles.db_models import RolesModelService
    role = SimpleNamespace(is_system=True, permissions=[])
    svc = RolesModelService.__new__(RolesModelService)
    assert svc._role_grants_permission(role, 'user:write')
    assert not svc._role_grants_permission(role, 'tenant.org.example.project:approve')
    role.permissions = [SimpleNamespace(allowed=True, permission_key='tenant.org.example.project:approve')]
    assert svc._role_grants_permission(role, 'tenant.org.example.project:approve')


def test_permission_registration_is_authenticated_and_uses_actor_tenant():
    class Manager(_StubPermissionsManager):
        def register(self, db, organization_id, payload):
            assert organization_id == 'org1'
            return PermissionRead(id='p', key='tenant.org1.example.project:approve', resource='example.project',
                                  action='approve', description=payload.description, is_system=False, organization_id=organization_id)
    client = _build_client(Manager())
    payload = dict(namespace='example', resource='project', action='approve', description='Approve')
    assert client.post('/permissions', json=payload).status_code == 401
    headers = {'x-user-id': 'u1', 'x-org-id': 'org1', 'x-user-roles': 'admin'}
    assert client.post('/permissions', headers=headers, json=payload).status_code == 200
    assert client.post('/permissions', headers=headers, json={**payload, 'organization_id':'org2'}).status_code == 422

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from common.deps import get_db
from exceptions import NotFoundError, ServiceError, ValidationError
from roles.controller import RolesRestController
from roles.db_models import RolesModelService
from roles.manager import RolesServiceManager
from roles.models.request import (
    RoleCreateRequest,
    RoleDuplicateRequest,
    RoleUpdateRequest,
    TransitionPermissionCreate,
    UserRoleSetRequest,
    WorkflowPermissionCreate,
)
from roles.models.response import (
    PermissionsSummary,
    RoleListItem,
    RoleRead,
    RolePermissionRead,
    UserRoleRead,
)


class _StubRolesManager:
    def __init__(self):
        self.deleted: list[str] = []
        self.removed_assignments: list[tuple[str, str]] = []

    def list_roles(self, db, organization_id: str):  # noqa: ANN001
        _ = db, organization_id
        return [
            RoleListItem(
                id="role-1",
                name="admin",
                display_name="Admin",
                description=None,
                is_system=True,
                priority=100,
                color="#DC2626",
                user_count=1,
                created_at=datetime.now(timezone.utc),
            )
        ]

    def get_role(self, db, role_id: str, organization_id: str, actor_roles=None):  # noqa: ANN001
        _ = db, organization_id
        if role_id == "missing":
            raise NotFoundError("Role not found")
        return RoleRead(
            id=role_id,
            organization_id="org1",
            name="viewer",
            display_name="Viewer",
            description=None,
            is_system=True,
            priority=10,
            color="#6B7280",
            permissions=[RolePermissionRead(permission_key="role:read")],
            field_permissions=[],
            user_count=0,
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )

    def create_role(self, db, organization_id: str, payload: RoleCreateRequest):  # noqa: ANN001
        _ = db, organization_id
        if payload.name == "bad":
            raise ValidationError("bad role")
        return self.get_role(db, "role-new", organization_id)

    def update_role(self, db, role_id: str, organization_id: str, payload: RoleUpdateRequest):  # noqa: ANN001
        _ = payload
        if role_id == "bad-update":
            raise ValidationError("bad update")
        return self.get_role(db, role_id, organization_id)

    def delete_role(self, db, role_id: str, organization_id: str):  # noqa: ANN001
        _ = db, organization_id
        if role_id == "bad-delete":
            raise ValidationError("bad delete")
        if role_id == "missing":
            raise NotFoundError("Role not found")
        self.deleted.append(role_id)

    def duplicate_role(self, db, role_id: str, organization_id: str, payload: RoleDuplicateRequest):  # noqa: ANN001
        if payload.name == "bad":
            raise ValidationError("bad duplicate")
        return self.get_role(db, f"{role_id}-copy", organization_id)

    def get_user_roles(self, db, user_id: str, organization_id: str):  # noqa: ANN001
        _ = db, user_id, organization_id
        return []

    def set_user_role(self, db, user_id: str, organization_id: str, payload: UserRoleSetRequest, *, assigned_by: str):  # noqa: ANN001
        _ = db, organization_id, assigned_by
        return UserRoleRead(
            id="ur1",
            user_id=user_id,
            organization_id="org1",
            role_id=payload.role_id,
            role_name="viewer",
            role_display_name="Viewer",
            role_color=None,
            role_is_system=True,
            assigned_at=datetime.now(timezone.utc),
            assigned_by=assigned_by,
        )

    def remove_user_role(self, db, user_id: str, organization_id: str, role_id: str):  # noqa: ANN001
        _ = db, organization_id
        if role_id == "missing":
            raise NotFoundError("Role assignment not found")
        self.removed_assignments.append((user_id, role_id))

    def get_permissions_summary(self, db, user_id: str, organization_id: str):  # noqa: ANN001
        _ = db, user_id, organization_id
        return PermissionsSummary(roles=[], entity_permissions=[], field_permissions=[])

    def get_effective_permissions(self, db, user_id: str, organization_id: str, actor_user_id: str, actor_org_id: str, actor_roles=None):  # noqa: ANN001
        _ = db, organization_id, actor_user_id, actor_org_id, actor_roles
        return PermissionsSummary(roles=[], entity_permissions=[], field_permissions=[])


def _build_client(manager: _StubRolesManager | None = None) -> tuple[TestClient, _StubRolesManager]:
    """Description:
        Build a FastAPI TestClient with a stubbed roles controller + dependencies.

    Args:
        manager: Optional stub manager to inject into the controller.

    Returns:
        Tuple of (TestClient, manager) for assertions.

    Raises:
        None
    """
    manager = manager or _StubRolesManager()
    controller = RolesRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)

    def _stub_db():  # noqa: ANN001
        yield None

    app.dependency_overrides[get_db] = _stub_db
    return TestClient(app), manager


def test_roles_crud_and_permissions_endpoints() -> None:
    """Description:
        Validate happy-path CRUD and permissions endpoints return expected status codes and payload shapes.

    Args:
        None

    Returns:
        None

    Raises:
        AssertionError: If response codes/payloads are unexpected.
    """
    client, manager = _build_client()
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    resp = client.get("/roles", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "admin"

    created = client.post(
        "/roles",
        headers=headers,
        json={
            "name": "custom",
            "display_name": "Custom",
            "permissions": [{"permission_key": "role:read"}],
            "field_permissions": [],
        },
    )
    assert created.status_code == 201

    updated = client.put(
        "/roles/role-1",
        headers=headers,
        json={"display_name": "New", "permissions": [{"permission_key": "role:read"}]},
    )
    assert updated.status_code == 200

    deleted = client.delete("/roles/role-1", headers=headers)
    assert deleted.status_code == 204
    assert manager.deleted == ["role-1"]

    perms = client.get("/roles/my-permissions", headers=headers)
    assert perms.status_code == 200
    assert perms.json()["roles"] == []

    duplicated = client.post(
        "/roles/role-1/duplicate",
        headers=headers,
        json={"name": "custom-copy", "display_name": "Custom Copy"},
    )
    assert duplicated.status_code == 201

    user_roles = client.get("/roles/users/u2/roles", headers=headers)
    assert user_roles.status_code == 200
    assert user_roles.json() == []

    set_role = client.put("/roles/users/u2/role", headers=headers, json={"role_id": "role-1"})
    assert set_role.status_code == 200
    assert set_role.json()["user_id"] == "u2"

    removed = client.delete("/roles/users/u2/roles/role-1", headers=headers)
    assert removed.status_code == 204
    assert manager.removed_assignments == [("u2", "role-1")]


def test_roles_create_validation_maps_to_400() -> None:
    """Description:
        Ensure ValidationError from manager maps to HTTP 400 for role creation.

    Args:
        None

    Returns:
        None

    Raises:
        AssertionError: If response code is not 400.
    """
    client, _ = _build_client()
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    created = client.post(
        "/roles",
        headers=headers,
        json={
            "name": "bad",
            "display_name": "Bad",
            "permissions": [{"permission_key": "role:read"}],
            "field_permissions": [],
        },
    )
    assert created.status_code == 400


def test_roles_get_missing_maps_to_404() -> None:
    """Description:
        Ensure NotFoundError from manager maps to HTTP 404 for role reads.

    Args:
        None

    Returns:
        None

    Raises:
        AssertionError: If response code is not 404.
    """
    client, _ = _build_client()
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    resp = client.get("/roles/missing", headers=headers)
    assert resp.status_code == 404


def test_roles_list_service_error_maps_to_500() -> None:
    """Description:
        Ensure ServiceError from manager maps to HTTP 500 for list roles.

    Args:
        None

    Returns:
        None

    Raises:
        AssertionError: If response code is not 500.
    """
    class _FailingManager(_StubRolesManager):
        def list_roles(self, db, organization_id: str):  # noqa: ANN001
            """Description:
                Simulate a service-layer failure for list_roles.

            Args:
                db: DB session stub.
                organization_id: Organization id.

            Returns:
                Never returns (always raises).

            Raises:
                ServiceError: Always raised to simulate failure.
            """
            _ = db, organization_id
            raise ServiceError("boom")

    client, _ = _build_client(_FailingManager())
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    resp = client.get("/roles", headers=headers)
    assert resp.status_code == 500


def test_roles_get_not_found_maps_to_404() -> None:
    client, _ = _build_client()
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    resp = client.get("/roles/missing", headers=headers)
    assert resp.status_code == 404


def test_roles_delete_validation_and_not_found_mappings() -> None:
    client, _ = _build_client()
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    resp = client.delete("/roles/bad-delete", headers=headers)
    assert resp.status_code == 400

    resp = client.delete("/roles/missing", headers=headers)
    assert resp.status_code == 404


def test_roles_user_role_remove_not_found_maps_to_404() -> None:
    client, _ = _build_client()
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    resp = client.delete("/roles/users/u2/roles/missing", headers=headers)
    assert resp.status_code == 404


def test_roles_duplicate_validation_maps_to_400() -> None:
    client, _ = _build_client()
    headers = {"x-user-id": "u1", "x-org-id": "org1", "x-user-roles": "admin"}

    resp = client.post("/roles/role-1/duplicate", headers=headers, json={"name": "bad", "display_name": "Bad"})
    assert resp.status_code == 400


def test_workflow_access_scope_is_backward_compatible_and_union_based(monkeypatch) -> None:
    service = RolesModelService()
    workflow_read = [SimpleNamespace(allowed=True, permission_key="workflow:read")]
    selected = SimpleNamespace(
        is_system=False,
        permissions=workflow_read,
        workflow_permissions=[SimpleNamespace(machine_name="hiring")],
    )
    other = SimpleNamespace(
        is_system=False,
        permissions=workflow_read,
        workflow_permissions=[SimpleNamespace(machine_name="onboarding")],
    )
    monkeypatch.setattr(service, "_get_user_roles_for_org", lambda *_: [selected, other])
    assert service.get_workflow_access_scope(None, "u1", "org1") == {"hiring", "onboarding"}

    unrestricted = SimpleNamespace(
        is_system=False,
        permissions=workflow_read,
        workflow_permissions=[],
    )
    monkeypatch.setattr(service, "_get_user_roles_for_org", lambda *_: [selected, unrestricted])
    assert service.get_workflow_access_scope(None, "u1", "org1") is None


def test_narrowing_workflow_scope_prunes_stale_transition_grants() -> None:
    role = SimpleNamespace(
        is_system=False,
        workflow_permissions=[],
        transition_permissions=[],
    )
    persistence = SimpleNamespace(
        get_role=lambda *_args: role,
        update_role=lambda _db, _role, payload: payload,
        _permissions_svc=None,
    )
    manager = RolesServiceManager(persistence)
    manager._to_role_read = lambda _db, payload: payload

    updated = manager.update_role(
        None,
        "role-1",
        "org-1",
        RoleUpdateRequest(
            workflow_permissions=[WorkflowPermissionCreate(machine_name="hiring")],
            transition_permissions=[
                TransitionPermissionCreate(machine_name="hiring", transition_key="screen"),
                TransitionPermissionCreate(machine_name="onboarding", transition_key="start"),
            ],
        ),
    )

    assert [(item.machine_name, item.transition_key) for item in updated.transition_permissions] == [
        ("hiring", "screen")
    ]

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from auth.db_models import PLATFORM_ORG_ID
from common.auth import register_membership_db_service, register_roles_db_service
from common.deps import get_db
from common.security import create_access_token
from organizations.controller import OrganizationsRestController
from roles.models.interface import PermissionCheckResult

NON_PLATFORM_ORG_ID = "tenant-org-1"
TARGET_ORG_ID = "tenant-org-2"


class _StubOrganizationsManager:
    """Minimal stand-in for OrganizationsServiceManager — records calls, returns fixed reads."""

    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def _org_read(self, org_id: str = TARGET_ORG_ID) -> dict:
        return {
            "id": org_id,
            "name": "Some Org",
            "slug": "some-org",
            "logo_url": None,
            "domain": None,
            "settings": None,
            "status": "active",
            "requested_by_user_id": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": None,
        }

    def _record(self, method_name, *args, **kwargs):
        self.calls.append((method_name, args, kwargs))

    def create_organization(self, db, **kwargs):
        self._record("create_organization", db, **kwargs)
        return self._org_read()

    def list_organizations(self, db, **kwargs):
        self._record("list_organizations", db, **kwargs)
        return {"items": [self._org_read()], "total": 1}

    def list_pending(self, db, **kwargs):
        self._record("list_pending", db, **kwargs)
        return {"items": [], "total": 0}

    def get_current(self, db, org_id):
        self._record("get_current", db, org_id)
        return self._org_read(org_id)

    def get_organization(self, db, org_id):
        self._record("get_organization", db, org_id)
        return self._org_read(org_id)

    def update_organization(self, db, org_id, **kwargs):
        self._record("update_organization", db, org_id, **kwargs)
        return self._org_read(org_id)

    def rename_current_org(self, db, org_id, name):
        self._record("rename_current_org", db, org_id, name)
        return self._org_read(org_id)

    def approve_organization(self, db, org_id):
        self._record("approve_organization", db, org_id)
        return self._org_read(org_id)

    def reject_organization(self, db, org_id):
        self._record("reject_organization", db, org_id)
        return self._org_read(org_id)

    def delete_organization(self, db, org_id, **kwargs):
        self._record("delete_organization", db, org_id, **kwargs)

    def provision_tenant(self, db, **kwargs):
        self._record("provision_tenant", db, **kwargs)
        return {"organization_id": kwargs.get("org_id"), "success": True}

    def get_provision_status(self, db, **kwargs):
        self._record("get_provision_status", db, **kwargs)
        return {
            "organization_id": kwargs.get("org_id"),
            "fully_provisioned": False,
            "has_entity_types": False,
            "has_picklists": False,
            "has_form_schemas": False,
            "has_document_types": False,
            "has_funnels": False,
        }

    def list_org_users(self, db, **kwargs):
        self._record("list_org_users", db, **kwargs)
        return {"items": [], "total": 0}

    def create_org_user(self, db, **kwargs):
        self._record("create_org_user", db, **kwargs)
        return {
            "id": "user-1",
            "email": "new@tenant.com",
            "full_name": "New User",
            "role": "viewer",
            "status": "active",
            "auth_type": "local",
            "is_active": True,
            "organization_id": kwargs.get("org_id"),
            "created_at": datetime.now(timezone.utc),
        }

    def delete_org_user(self, db, **kwargs):
        self._record("delete_org_user", db, **kwargs)


class _StubRolesDbService:
    """Stand-in for the roles module's DB service — the seam require_permission and
    require_platform_permission (common/auth.py) actually call. No real DB involved;
    each test controls exactly which permissions/roles are granted."""

    def __init__(self):
        self.platform_roles: list[str] = []
        self.platform_permissions: set[str] = set()
        self.org_permissions: dict[str, set[str]] = {}

    def get_user_roles_with_permissions(self, db, user_id, org_id):
        _ = db, user_id
        if org_id == PLATFORM_ORG_ID:
            return [SimpleNamespace(name=name) for name in self.platform_roles]
        return []

    def check_permission(self, db, user_id, org_id, permission_key):
        _ = db, user_id
        granted = permission_key in (
            self.platform_permissions if org_id == PLATFORM_ORG_ID else self.org_permissions.get(org_id, set())
        )
        if granted:
            return PermissionCheckResult.allow(permission_key)
        return PermissionCheckResult.deny(permission_key, "not granted")


class _StubMembershipChecker:
    """Membership seam for require_permission/require_platform_permission — reports
    every membership active so tests exercise the role/permission paths, not
    suspension (per-org suspension has its own dedicated tests)."""

    def is_membership_active(self, db, user_id, org_id) -> bool:
        _ = db, user_id, org_id
        return True


@pytest.fixture
def roles_stub():
    """Registers a fresh stub roles service for the test, and always de-registers it
    afterward — _roles_db_service is a module-level global in common/auth.py. Also
    wires an always-active membership checker, the other seam the permission
    dependencies call."""
    stub = _StubRolesDbService()
    register_roles_db_service(stub)
    register_membership_db_service(_StubMembershipChecker())
    yield stub
    register_roles_db_service(None)
    register_membership_db_service(None)


def _build_client() -> tuple[TestClient, _StubOrganizationsManager]:
    """Build a FastAPI TestClient wired to the real OrganizationsRestController + a stub manager."""
    manager = _StubOrganizationsManager()
    controller = OrganizationsRestController(manager)
    router = APIRouter()
    controller.prepare(router)

    app = FastAPI()
    app.include_router(router)

    def _stub_db():
        # require_permission/require_platform_permission treat a None session as
        # "roles service unavailable" and fail closed (503) — yield a dummy object
        # instead. Neither the manager stub nor _StubRolesDbService touch it.
        yield object()

    app.dependency_overrides[get_db] = _stub_db
    return TestClient(app), manager


def _bearer(user_id: str, organization_id: str) -> dict[str, str]:
    """A real, signature-verified access token — the only identity source build_actor_context
    trusts outside of the explicit dev-only BYPASS_AUTH mode."""
    token = create_access_token(subject=user_id, organization_id=organization_id)
    return {"Authorization": f"Bearer {token}"}


# Platform-wide organization management endpoints: (label, method, path, body, success_status, permission_key).
PLATFORM_ENDPOINTS = [
    ("create_organization", "POST", "/organizations", {"name": "New Org"}, 201, "platform_organization:create"),
    ("list_organizations", "GET", "/organizations", None, 200, "platform_organization:read"),
    ("list_pending_organizations", "GET", "/organizations/pending", None, 200, "platform_organization:read"),
    ("get_organization", "GET", f"/organizations/{TARGET_ORG_ID}", None, 200, "platform_organization:read"),
    ("update_organization", "PUT", f"/organizations/{TARGET_ORG_ID}", {"name": "Renamed"}, 200, "platform_organization:write"),
    ("approve_organization", "POST", f"/organizations/{TARGET_ORG_ID}/approve", None, 200, "platform_organization:approve"),
    ("reject_organization", "POST", f"/organizations/{TARGET_ORG_ID}/reject", None, 200, "platform_organization:reject"),
    ("delete_organization", "DELETE", f"/organizations/{TARGET_ORG_ID}", None, 204, "platform_organization:delete"),
    ("provision_organization", "POST", f"/organizations/{TARGET_ORG_ID}/provision", None, 200, "platform_organization:provision"),
    ("get_provision_status", "GET", f"/organizations/{TARGET_ORG_ID}/provision-status", None, 200, "platform_organization:read"),
    ("list_organization_users", "GET", f"/organizations/{TARGET_ORG_ID}/users", None, 200, "platform_user:read"),
    (
        "create_organization_user",
        "POST",
        f"/organizations/{TARGET_ORG_ID}/users",
        {"email": "new@tenant.com", "full_name": "New User"},
        201,
        "platform_user:write",
    ),
    ("delete_organization_user", "DELETE", f"/organizations/{TARGET_ORG_ID}/users/user-9", None, 204, "platform_user:write"),
]

ENDPOINT_IDS = [e[0] for e in PLATFORM_ENDPOINTS]


@pytest.mark.parametrize("label,method,path,body,expected_status,permission_key", PLATFORM_ENDPOINTS, ids=ENDPOINT_IDS)
def test_platform_endpoint_rejects_caller_without_platform_superadmin_role(
    label, method, path, body, expected_status, permission_key, roles_stub
) -> None:
    """A real, verified JWT with no platform-org superadmin role assignment must be
    rejected, even if the org-scoped permission would otherwise be granted."""
    client, manager = _build_client()
    roles_stub.platform_permissions.add(permission_key)  # permission alone is not enough
    headers = _bearer("caller-1", NON_PLATFORM_ORG_ID)

    resp = client.request(method, path, json=body, headers=headers)

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Requires the platform superadmin role"
    assert manager.calls == []


@pytest.mark.parametrize("label,method,path,body,expected_status,permission_key", PLATFORM_ENDPOINTS, ids=ENDPOINT_IDS)
def test_platform_endpoint_rejects_platform_superadmin_role_without_specific_permission(
    label, method, path, body, expected_status, permission_key, roles_stub
) -> None:
    """Holding the platform superadmin role is necessary but not sufficient — the
    specific permission for this action must also be granted."""
    client, manager = _build_client()
    roles_stub.platform_roles.append("superadmin")  # role present, permission is not
    headers = _bearer("caller-1", NON_PLATFORM_ORG_ID)

    resp = client.request(method, path, json=body, headers=headers)

    assert resp.status_code == 403
    assert manager.calls == []


@pytest.mark.parametrize("label,method,path,body,expected_status,permission_key", PLATFORM_ENDPOINTS, ids=ENDPOINT_IDS)
def test_platform_endpoint_allows_verified_platform_superadmin_with_permission(
    label, method, path, body, expected_status, permission_key, roles_stub
) -> None:
    """No regression: a real, verified JWT for a user holding the platform superadmin
    role AND the specific permission still succeeds. The token's own organization_id
    is a normal tenant here on purpose — require_platform_permission checks the
    platform org's role/permission tables directly, it never trusts the token's org."""
    client, manager = _build_client()
    roles_stub.platform_roles.append("superadmin")
    roles_stub.platform_permissions.add(permission_key)
    headers = _bearer("caller-1", NON_PLATFORM_ORG_ID)

    resp = client.request(method, path, json=body, headers=headers)

    assert resp.status_code == expected_status
    assert manager.calls, f"{label} did not reach the manager"


@pytest.mark.parametrize("label,method,path,body,expected_status,permission_key", PLATFORM_ENDPOINTS, ids=ENDPOINT_IDS)
def test_platform_endpoint_rejects_unsigned_headers_with_no_bearer_token(
    label, method, path, body, expected_status, permission_key, roles_stub
) -> None:
    """SEC-006 closed: plain x-user-id/x-org-id/x-user-roles headers claiming the
    platform org and superadmin role, with no Authorization bearer token at all,
    are rejected outright — build_actor_context no longer trusts them."""
    client, manager = _build_client()
    roles_stub.platform_roles.append("superadmin")
    roles_stub.platform_permissions.add(permission_key)
    headers = {"x-user-id": "attacker", "x-org-id": PLATFORM_ORG_ID, "x-user-roles": "superadmin"}

    resp = client.request(method, path, json=body, headers=headers)

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing or invalid access token"
    assert manager.calls == []


def test_get_current_organization_works_with_a_verified_jwt_and_no_permission_check() -> None:
    """/organizations/current only needs a verified identity, no platform permission —
    it resolves the org from the actor's own token, never a path parameter."""
    client, manager = _build_client()
    headers = _bearer("u1", NON_PLATFORM_ORG_ID)

    resp = client.get("/organizations/current", headers=headers)

    assert resp.status_code == 200
    assert manager.calls[-1][0] == "get_current"
    assert manager.calls[-1][1][-1] == NON_PLATFORM_ORG_ID


def test_update_branding_requires_permission_scoped_to_callers_own_org(roles_stub) -> None:
    """Tenant-scoped action: granted only when the caller's own org has the permission,
    never via the platform-org tables."""
    client, manager = _build_client()
    roles_stub.org_permissions[NON_PLATFORM_ORG_ID] = {"organization:branding"}
    headers = _bearer("u1", NON_PLATFORM_ORG_ID)

    resp = client.put("/organizations/current/branding", json={"logo_url": "https://x/y.png"}, headers=headers)

    assert resp.status_code == 200
    assert manager.calls[-1][0] == "update_organization"
    assert manager.calls[-1][1][-1] == NON_PLATFORM_ORG_ID


def test_update_branding_rejected_without_org_scoped_permission(roles_stub) -> None:
    """No branding permission granted for the caller's org: rejected, and never
    reaches the manager."""
    client, manager = _build_client()
    headers = _bearer("u1", NON_PLATFORM_ORG_ID)

    resp = client.put("/organizations/current/branding", json={"logo_url": "https://x/y.png"}, headers=headers)

    assert resp.status_code == 403
    assert manager.calls == []

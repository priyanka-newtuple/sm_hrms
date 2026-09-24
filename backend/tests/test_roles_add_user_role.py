"""Additive role grants: `POST /roles/users/{user_id}/roles`.

Unlike `PUT /roles/users/{user_id}/role` (replace-all-with-one), this grants one
more role while keeping the ones the user already holds, so a person can be an
executor at several client sites at once. Fakes follow `test_roles_module.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from common.deps import get_db
from exceptions import NotFoundError, PersistenceError, ValidationError
from roles import controller as roles_controller
from roles.controller import RolesRestController
from roles.manager import RolesServiceManager
from roles.models.request import UserRoleSetRequest
from roles.models.response import UserRoleRead

ACTOR = {"user_id": "admin-1", "organization_id": "org-1", "roles": ["admin"]}
NOW = datetime.now(timezone.utc)


def _assignment(role_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"assignment-{role_id}",
        user_id="user-1",
        organization_id="org-1",
        role_id=role_id,
        assigned_at=NOW,
        assigned_by="admin-1",
    )


def _role(role_id: str, priority: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=role_id,
        name=f"{role_id}-name",
        display_name=f"{role_id} display",
        color=None,
        is_system=False,
        priority=priority,
    )


class _FakeRolesDb:
    """Records which persistence call each manager method makes."""

    def __init__(
        self,
        *,
        user_exists: bool = True,
        roles: dict[str, SimpleNamespace] | None = None,
        already_held: list[str] | None = None,
    ) -> None:
        self.user_exists = user_exists
        self.roles = roles if roles is not None else {"role-1": _role("role-1"), "role-2": _role("role-2")}
        self.assigned: list[str] = []
        self.replaced: list[str] = []
        self.held: list[str] = list(already_held or [])
        self.membership_role: str | None = None

    def get_user(self, db, user_id: str):  # noqa: ANN001
        _ = db, user_id
        return SimpleNamespace(id="user-1") if self.user_exists else None

    def get_role(self, db, role_id: str, organization_id: str):  # noqa: ANN001
        _ = db, organization_id
        return self.roles.get(role_id)

    def assign_role_to_user(self, db, user_id: str, org_id: str, role_id: str, assigned_by=None):  # noqa: ANN001
        _ = db, user_id, org_id, assigned_by
        self.assigned.append(role_id)
        if role_id not in self.held:
            self.held.append(role_id)
        return _assignment(role_id)

    def get_user_roles_with_permissions(self, db, user_id: str, org_id: str):  # noqa: ANN001
        _ = db, user_id, org_id
        return [self.roles[role_id] for role_id in self.held]

    def set_user_role(self, db, *, user_id: str, organization_id: str, payload, assigned_by: str):  # noqa: ANN001
        _ = db, user_id, organization_id, assigned_by
        self.replaced.append(payload.role_id)
        return _assignment(payload.role_id)

    def update_user_org_role(self, db, user_id: str, organization_id: str, role_name: str) -> None:  # noqa: ANN001
        _ = db, user_id, organization_id
        self.membership_role = role_name


# --------------------------------------------------------------- manager


def test_add_user_role_grants_without_replacing_existing_roles() -> None:
    db = _FakeRolesDb()
    manager = RolesServiceManager(db)

    first = manager.add_user_role(None, "user-1", "org-1", UserRoleSetRequest(role_id="role-1"), assigned_by="admin-1")
    second = manager.add_user_role(None, "user-1", "org-1", UserRoleSetRequest(role_id="role-2"), assigned_by="admin-1")

    assert db.assigned == ["role-1", "role-2"]
    assert db.replaced == [], "additive grant must never go through the replace-all path"
    assert (first.role_id, first.role_name) == ("role-1", "role-1-name")
    assert (second.role_id, second.role_name) == ("role-2", "role-2-name")
    assert db.held == ["role-1", "role-2"]


def test_add_user_role_keeps_the_higher_priority_role_as_membership_label() -> None:
    """An admin picking up a priority-0 site role must not be demoted in the legacy mirror."""
    roles = {"admin": _role("admin", priority=100), "site-exec": _role("site-exec", priority=0)}
    db = _FakeRolesDb(roles=roles, already_held=["admin"])
    manager = RolesServiceManager(db)

    manager.add_user_role(None, "user-1", "org-1", UserRoleSetRequest(role_id="site-exec"), assigned_by="admin-1")

    assert db.held == ["admin", "site-exec"]
    assert db.membership_role == "admin-name"


def test_add_user_role_promotes_the_membership_label_when_the_new_role_outranks() -> None:
    roles = {"viewer": _role("viewer", priority=10), "admin": _role("admin", priority=100)}
    db = _FakeRolesDb(roles=roles, already_held=["viewer"])
    manager = RolesServiceManager(db)

    manager.add_user_role(None, "user-1", "org-1", UserRoleSetRequest(role_id="admin"), assigned_by="admin-1")

    assert db.membership_role == "admin-name"


def test_add_user_role_rejects_unknown_user() -> None:
    manager = RolesServiceManager(_FakeRolesDb(user_exists=False))

    with pytest.raises(NotFoundError, match="User not found"):
        manager.add_user_role(None, "ghost", "org-1", UserRoleSetRequest(role_id="role-1"), assigned_by="admin-1")


def test_add_user_role_rejects_role_missing_from_this_organization() -> None:
    db = _FakeRolesDb(roles={})
    manager = RolesServiceManager(db)

    with pytest.raises(NotFoundError, match="Role not found in this organization"):
        manager.add_user_role(None, "user-1", "org-1", UserRoleSetRequest(role_id="role-1"), assigned_by="admin-1")
    assert db.assigned == []


def test_set_user_role_still_replaces_via_the_original_persistence_path() -> None:
    """Regression guard for the shared helpers: PUT semantics are unchanged."""
    db = _FakeRolesDb()
    manager = RolesServiceManager(db)

    result = manager.set_user_role(None, "user-1", "org-1", UserRoleSetRequest(role_id="role-2"), assigned_by="admin-1")

    assert db.replaced == ["role-2"]
    assert db.assigned == []
    assert isinstance(result, UserRoleRead)
    assert (result.role_id, result.role_display_name, result.assigned_by) == ("role-2", "role-2 display", "admin-1")


# ------------------------------------------------------------ controller


class _StubManager:
    def __init__(self, outcome: Exception | None = None) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, str, str, str]] = []

    def add_user_role(self, db, user_id: str, organization_id: str, payload: UserRoleSetRequest, *, assigned_by: str):  # noqa: ANN001
        _ = db
        self.calls.append((user_id, organization_id, payload.role_id, assigned_by))
        if self.outcome is not None:
            raise self.outcome
        return UserRoleRead(
            id="assignment-1",
            user_id=user_id,
            organization_id=organization_id,
            role_id=payload.role_id,
            role_name="pfizer.mumbai.executor",
            role_display_name="Pfizer · Mumbai · Executor",
            role_color=None,
            role_is_system=False,
            assigned_at=NOW,
            assigned_by=assigned_by,
        )


def _client(manager: _StubManager) -> TestClient:
    """Same actor-override shape `test_workflow_module.py` uses for permission-gated routes."""
    controller = RolesRestController(manager)
    router = APIRouter()
    controller.prepare(router)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[roles_controller.UserWriteActor.__metadata__[0].dependency] = lambda: ACTOR
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_post_user_roles_returns_201_with_the_new_assignment() -> None:
    manager = _StubManager()
    response = _client(manager).post("/roles/users/user-1/roles", json={"role_id": "role-1"})

    assert response.status_code == 201
    body = response.json()
    assert (body["user_id"], body["role_id"], body["role_name"]) == ("user-1", "role-1", "pfizer.mumbai.executor")
    assert manager.calls == [("user-1", "org-1", "role-1", "admin-1")]


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        (NotFoundError("Role not found in this organization"), 404),
        (ValidationError("bad role"), 400),
        (PersistenceError("db down"), 500),
    ],
)
def test_post_user_roles_maps_manager_errors_to_http_status(outcome: Exception, expected_status: int) -> None:
    response = _client(_StubManager(outcome)).post(
        "/roles/users/user-1/roles", json={"role_id": "role-1"}
    )

    assert response.status_code == expected_status
    assert str(outcome) in response.json()["detail"]


def test_post_user_roles_requires_a_role_id() -> None:
    manager = _StubManager()
    response = _client(manager).post("/roles/users/user-1/roles", json={})

    assert response.status_code == 422
    assert manager.calls == []

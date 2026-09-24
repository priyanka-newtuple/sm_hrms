"""Multi-org membership sync tests.

Covers the org-membership fixes: membership rows created with users, org user
lists including all members (membership join + primary-org fallback), org
switching (previous-org backfill + RBAC self-heal), org-scoped role updates,
and membership/RBAC cleanup on removal.

Runs the real services against an in-memory SQLite database — no stubs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth.db_models import AuthService, _add_membership_row
from common.security import decode_token
from database.manager import Base
from exceptions import AuthorizationError, NotFoundError, PersistenceError, ValidationError
from organizations.db_models import (
    Organization,
    OrganizationsModelService,
    UserOrganization,
    org_members_query,
)
from organizations.manager import OrganizationsServiceManager
from organizations.models.request import PlatformUserCreate
from roles.db_models import (
    FieldPermission,
    Role,
    RolePermission,
    RolesModelService,
    TransitionPermission,
    UserRoleAssignment,
)
from roles.manager import RolesServiceManager
from user.db_models import RefreshToken, User, UserModelService
from user.manager import UserServiceManager


# ── Fixtures / helpers ─────────────────────────────────────────────────────────


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Organization.__table__,
            UserOrganization.__table__,
            Role.__table__,
            RolePermission.__table__,
            FieldPermission.__table__,
            TransitionPermission.__table__,
            UserRoleAssignment.__table__,
            RefreshToken.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _org(db, name: str) -> Organization:
    org = Organization(id=str(uuid.uuid4()), name=name, slug=name.lower().replace(" ", "-"), settings={})
    db.add(org)
    db.commit()
    return org


def _user(db, email: str, org_id: str, role: str = "admin") -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        full_name=email.split("@")[0],
        role=role,
        status="active",
        auth_type="local",
        organization_id=org_id,
    )
    db.add(user)
    db.commit()
    return user


def _user_with_status(db, email: str, org_id: str, status: str, role: str = "viewer") -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        full_name=email.split("@")[0],
        role=role,
        status=status,
        auth_type="local",
        organization_id=org_id,
    )
    db.add(user)
    db.commit()
    return user


def _membership(db, user_id: str, org_id: str, role: str = "admin", status: str = "active") -> UserOrganization:
    row = UserOrganization(user_id=user_id, organization_id=org_id, role=role, status=status)
    db.add(row)
    db.commit()
    return row


def _memberships(db, user_id: str) -> dict[str, UserOrganization]:
    rows = db.query(UserOrganization).filter(UserOrganization.user_id == user_id).all()
    return {str(r.organization_id): r for r in rows}


def _rbac_role_names(db, user_id: str, org_id: str) -> set[str]:
    rows = (
        db.query(Role.name)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
        .filter(UserRoleAssignment.user_id == user_id, UserRoleAssignment.organization_id == org_id)
        .all()
    )
    return {name for (name,) in rows}


def _user_svc() -> UserModelService:
    return UserModelService(None)


def _org_svc() -> OrganizationsModelService:
    return OrganizationsModelService(None, user_model_service=_user_svc())


def _org_manager() -> OrganizationsServiceManager:
    roles_manager = RolesServiceManager(RolesModelService())
    return OrganizationsServiceManager(_org_svc(), None, None, roles_service_manager=roles_manager)


def _user_manager() -> UserServiceManager:
    return UserServiceManager(_user_svc(), roles_db_service=RolesModelService())


# ── auth helper ────────────────────────────────────────────────────────────────


def test_add_membership_row_helper(db) -> None:
    org = _org(db, "Org A")
    user = _user(db, "a@x.com", org.id)

    _add_membership_row(db, user.id, org.id, "admin")
    db.commit()

    rows = _memberships(db, user.id)
    assert org.id in rows
    assert rows[org.id].role == "admin"
    assert rows[org.id].status == "active"


# ── list queries (outerjoin + primary-org fallback) ────────────────────────────


def test_org_members_query_includes_members_and_legacy_primary(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    legacy = _user(db, "legacy@x.com", org_a.id)  # primary org A, no membership row
    member = _user(db, "member@x.com", org_a.id)
    _membership(db, member.id, org_a.id)
    _membership(db, member.id, org_b.id)  # also member of B

    in_a = {u.email for u in org_members_query(db, User, org_a.id).all()}
    in_b = {u.email for u in org_members_query(db, User, org_b.id).all()}

    assert in_a == {"legacy@x.com", "member@x.com"}
    assert in_b == {"member@x.com"}  # legacy user must NOT leak into org B


def test_list_users_shows_multi_org_member_in_both_orgs(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    user = _user(db, "multi@x.com", org_a.id)
    _membership(db, user.id, org_a.id)
    _membership(db, user.id, org_b.id)

    svc = _org_svc()
    users_a, total_a = svc.list_users(db, org_id=org_a.id)
    users_b, total_b = svc.list_users(db, org_id=org_b.id)

    assert {u.email for u in users_a} == {"multi@x.com"} and total_a == 1
    assert {u.email for u in users_b} == {"multi@x.com"} and total_b == 1


def test_user_list_all_scopes_by_membership_with_role_override(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    user = _user(db, "multi@x.com", org_a.id, role="admin")
    _membership(db, user.id, org_a.id, role="admin")
    _membership(db, user.id, org_b.id, role="viewer")

    manager = _user_manager()
    in_b = manager.list_users(db, organization_id=org_b.id)

    assert [u.email for u in in_b] == ["multi@x.com"]
    # display role must be the org-B membership role, not the primary-org mirror
    assert in_b[0].role == "viewer"


def test_search_users_finds_multi_org_member_by_membership_row(db) -> None:
    """search_users must scope by org_members_query (the membership join), the
    same helper list_all uses — not the narrow users.organization_id "current
    org" column. A user whose current org is A but who holds an active
    membership row in B must still be found/taggable when searching within B."""
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    member = _user(db, "tagalice@x.com", org_a.id)  # current org = A
    _membership(db, member.id, org_b.id)  # active membership row for B
    outsider = _user(db, "bobsmith@x.com", org_a.id)  # never joined org B

    results = _user_svc().search_users(db, query="tagalice", organization_id=org_b.id)

    emails = {u.email for u in results}
    assert member.email in emails
    assert outsider.email not in emails


# ── membership role helpers ────────────────────────────────────────────────────


def test_get_memberships_map_and_set_membership_role(db) -> None:
    org = _org(db, "Org A")
    u1 = _user(db, "u1@x.com", org.id)
    u2 = _user(db, "u2@x.com", org.id)
    _membership(db, u1.id, org.id, role="admin")
    _membership(db, u2.id, org.id, role="viewer")

    svc = _user_svc()
    memberships = svc.get_memberships_map(db, org.id, [u1.id, u2.id, "unknown-id"])
    assert set(memberships) == {u1.id, u2.id}
    assert memberships[u1.id].role == "admin"
    assert memberships[u2.id].role == "viewer"
    assert svc.get_memberships_map(db, org.id, []) == {}

    svc.set_membership_role(db, u2.id, org.id, "admin")
    assert _memberships(db, u2.id)[org.id].role == "admin"

    # no-op (must not raise) when there is no membership row
    svc.set_membership_role(db, u1.id, "missing-org", "viewer")


# ── org switching ──────────────────────────────────────────────────────────────


def test_switch_organization_backfills_membership_for_previous_org(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    user = _user(db, "kartikeya@x.com", org_a.id, role="admin")
    _membership(db, user.id, org_b.id)  # member of B; NO row for primary org A (legacy state)

    svc = _user_svc()
    svc.switch_organization(db, user, org_b.id)

    assert user.organization_id == org_b.id
    rows = _memberships(db, user.id)
    # the org being left was backfilled, so the user can switch back
    assert org_a.id in rows and rows[org_a.id].status == "active" and rows[org_a.id].role == "admin"

    svc.switch_organization(db, user, org_a.id)  # and switching back actually works
    assert user.organization_id == org_a.id


def test_switch_organization_rejects_non_member_and_inactive_membership(db) -> None:
    org_a, org_b, org_c = _org(db, "Org A"), _org(db, "Org B"), _org(db, "Org C")
    user = _user(db, "u@x.com", org_a.id)
    _membership(db, user.id, org_b.id, status="pending")

    svc = _user_svc()
    with pytest.raises(AuthorizationError):
        svc.switch_organization(db, user, org_c.id)
    with pytest.raises(AuthorizationError):
        svc.switch_organization(db, user, org_b.id)
    assert user.organization_id == org_a.id


def test_manager_switch_self_heals_missing_rbac_role(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    RolesModelService().ensure_default_roles(db, org_b.id)
    user = _user(db, "u@x.com", org_a.id, role="admin")
    _membership(db, user.id, org_a.id)
    _membership(db, user.id, org_b.id, role="admin")
    assert _rbac_role_names(db, user.id, org_b.id) == set()  # the 403 precondition

    org_name, access_token = _user_manager().switch_organization(db, user, org_b.id)

    assert org_name == "Org B"
    assert access_token
    # the missing RBAC assignment was self-healed, so the token carries roles
    assert _rbac_role_names(db, user.id, org_b.id) == {"admin"}


# ── create_org_user ────────────────────────────────────────────────────────────


def test_create_org_user_new_user_gets_membership_and_rbac_role(db) -> None:
    org = _org(db, "Org A")
    manager = _org_manager()

    created = manager.create_org_user(
        db, org_id=org.id, payload=PlatformUserCreate(email="new@x.com", full_name="New User", role="admin")
    )

    assert created.email == "new@x.com"
    rows = _memberships(db, created.id)
    assert org.id in rows and rows[org.id].role == "admin"
    assert _rbac_role_names(db, created.id, org.id) == {"admin"}


def test_create_org_user_existing_user_added_to_second_org(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    user = _user(db, "multi@x.com", org_a.id)
    _membership(db, user.id, org_a.id)
    manager = _org_manager()

    result = manager.create_org_user(
        db, org_id=org_b.id, payload=PlatformUserCreate(email="multi@x.com", full_name="Multi", role="viewer")
    )

    assert result.id == user.id  # existing account reused, not duplicated
    assert db.query(User).filter(User.email == "multi@x.com").count() == 1
    rows = _memberships(db, user.id)
    assert rows[org_b.id].role == "viewer"
    assert _rbac_role_names(db, user.id, org_b.id) == {"viewer"}


def test_create_org_user_duplicate_membership_rejected(db) -> None:
    org = _org(db, "Org A")
    user = _user(db, "dup@x.com", org.id)
    _membership(db, user.id, org.id)

    with pytest.raises(ValidationError):
        _org_manager().create_org_user(
            db, org_id=org.id, payload=PlatformUserCreate(email="dup@x.com", full_name="Dup", role="admin")
        )


# ── delete_org_user ────────────────────────────────────────────────────────────


def test_delete_org_user_removes_membership_and_rbac_roles(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    manager = _org_manager()
    user_resp = manager.create_org_user(
        db, org_id=org_b.id, payload=PlatformUserCreate(email="u@x.com", full_name="U", role="admin")
    )
    # make org A the primary so removing from org B is a pure membership removal
    db.query(User).filter(User.id == user_resp.id).update({"organization_id": org_a.id})
    db.commit()
    assert _rbac_role_names(db, user_resp.id, org_b.id) == {"admin"}

    manager.delete_org_user(db, org_id=org_b.id, user_id=user_resp.id)

    assert org_b.id not in _memberships(db, user_resp.id)
    assert _rbac_role_names(db, user_resp.id, org_b.id) == set()  # no stale permissions on re-add
    assert db.query(User).filter(User.id == user_resp.id).count() == 1  # account kept


# ── update_role (org-scoped) ───────────────────────────────────────────────────


def test_update_role_only_affects_acting_org(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    roles_svc = RolesModelService()
    roles_svc.ensure_default_roles(db, org_a.id)
    roles_svc.ensure_default_roles(db, org_b.id)
    user = _user(db, "u@x.com", org_a.id, role="admin")
    _membership(db, user.id, org_a.id, role="admin")
    _membership(db, user.id, org_b.id, role="admin")
    manager = _user_manager()
    manager._sync_rbac_role(db, user.id, org_a.id, "admin")
    manager._sync_rbac_role(db, user.id, org_b.id, "admin")

    result = manager.update_role(db, user.id, "viewer", organization_id=org_b.id)

    assert result.role == "viewer"
    rows = _memberships(db, user.id)
    assert rows[org_b.id].role == "viewer"
    assert _rbac_role_names(db, user.id, org_b.id) == {"viewer"}
    # org A must be completely untouched
    assert rows[org_a.id].role == "admin"
    assert _rbac_role_names(db, user.id, org_a.id) == {"admin"}
    # users.role mirrors the PRIMARY org only — org B change must not leak into it
    db.refresh(user)
    assert user.role == "admin"


def test_update_role_in_primary_org_updates_legacy_mirror(db) -> None:
    org_a = _org(db, "Org A")
    RolesModelService().ensure_default_roles(db, org_a.id)
    user = _user(db, "u@x.com", org_a.id, role="admin")
    _membership(db, user.id, org_a.id, role="admin")

    _user_manager().update_role(db, user.id, "viewer", organization_id=org_a.id)

    db.refresh(user)
    assert user.role == "viewer"
    assert _memberships(db, user.id)[org_a.id].role == "viewer"
    assert _rbac_role_names(db, user.id, org_a.id) == {"viewer"}


# ── SEC-005 — cross-tenant target scoping & self-escalation guard ─────────────


def test_get_user_rejects_cross_org_target(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    target = _user(db, "victim@x.com", org_a.id)

    with pytest.raises(NotFoundError):
        _user_manager().get_user(db, target.id, organization_id=org_b.id)

    # same-org lookup still works
    assert _user_manager().get_user(db, target.id, organization_id=org_a.id).email == "victim@x.com"


def test_approve_user_rejects_cross_org_target(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    target = _user_with_status(db, "pending@x.com", org_a.id, status="pending")

    with pytest.raises(NotFoundError):
        _user_manager().approve_user(db, target.id, organization_id=org_b.id)

    result = _user_manager().approve_user(db, target.id, organization_id=org_a.id)
    assert result.status == "active"


def test_reject_user_rejects_cross_org_target(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    target = _user_with_status(db, "pending@x.com", org_a.id, status="pending")

    with pytest.raises(NotFoundError):
        _user_manager().reject_user(db, target.id, organization_id=org_b.id)

    result = _user_manager().reject_user(db, target.id, organization_id=org_a.id)
    assert result.status == "rejected"


def test_suspend_and_reactivate_user_reject_cross_org_target(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    caller = _user(db, "caller@x.com", org_b.id)
    target = _user(db, "victim@x.com", org_a.id)  # status="active" via _user()
    _membership(db, target.id, org_a.id, status="active")  # per-org suspension acts on this row

    with pytest.raises(NotFoundError):
        _user_manager().suspend_user(db, target.id, caller.id, organization_id=org_b.id)

    result = _user_manager().suspend_user(db, target.id, caller.id, organization_id=org_a.id)
    assert result.status == "suspended"

    with pytest.raises(NotFoundError):
        _user_manager().reactivate_user(db, target.id, organization_id=org_b.id)

    result = _user_manager().reactivate_user(db, target.id, organization_id=org_a.id)
    assert result.status == "active"


def test_update_role_rejects_cross_org_target(db) -> None:
    org_a, org_b = _org(db, "Org A"), _org(db, "Org B")
    RolesModelService().ensure_default_roles(db, org_b.id)
    target = _user(db, "victim@x.com", org_a.id)  # not a member of org B at all

    with pytest.raises(NotFoundError):
        _user_manager().update_role(db, target.id, "viewer", organization_id=org_b.id)


def test_update_role_rejects_unknown_role_name(db) -> None:
    org = _org(db, "Org A")
    RolesModelService().ensure_default_roles(db, org.id)
    target = _user(db, "u@x.com", org.id)
    _membership(db, target.id, org.id)

    with pytest.raises(ValidationError):
        _user_manager().update_role(db, target.id, "not-a-real-role", organization_id=org.id)


def test_update_role_blocks_self_escalation_to_own_rank_or_above(db) -> None:
    org = _org(db, "Attacker Corp")
    RolesModelService().ensure_default_roles(db, org.id)
    admin = _user(db, "admin@x.com", org.id, role="admin")
    _membership(db, admin.id, org.id, role="admin")
    _user_manager()._sync_rbac_role(db, admin.id, org.id, "admin")

    with pytest.raises(AuthorizationError):
        _user_manager().update_role(
            db, admin.id, "superadmin", organization_id=org.id, caller_user_id=admin.id
        )

    # legacy column must be untouched by the rejected attempt
    db.refresh(admin)
    assert admin.role == "admin"


def test_update_role_allows_self_downgrade_below_own_rank(db) -> None:
    org = _org(db, "Org A")
    RolesModelService().ensure_default_roles(db, org.id)
    admin = _user(db, "admin@x.com", org.id, role="admin")
    _membership(db, admin.id, org.id, role="admin")
    _user_manager()._sync_rbac_role(db, admin.id, org.id, "admin")

    result = _user_manager().update_role(
        db, admin.id, "viewer", organization_id=org.id, caller_user_id=admin.id
    )

    assert result.role == "viewer"


def test_update_role_allows_admin_promoting_a_teammate(db) -> None:
    """Sanity check: promoting SOMEONE ELSE within your own org is unaffected —
    the self-escalation guard only applies when the target is the caller."""
    org = _org(db, "Org A")
    RolesModelService().ensure_default_roles(db, org.id)
    admin = _user(db, "admin@x.com", org.id, role="admin")
    _membership(db, admin.id, org.id, role="admin")
    _user_manager()._sync_rbac_role(db, admin.id, org.id, "admin")
    teammate = _user(db, "teammate@x.com", org.id, role="viewer")
    _membership(db, teammate.id, org.id, role="viewer")

    result = _user_manager().update_role(
        db, teammate.id, "admin", organization_id=org.id, caller_user_id=admin.id
    )

    assert result.role == "admin"
    assert _rbac_role_names(db, teammate.id, org.id) == {"admin"}


# ── create_tokens fallback (SEC-006) ───────────────────────────────────────────
# Membership fallback must apply the same active-membership + active-org check
# switch_organization already uses — never mint a token scoped to a suspended
# membership or an inactive organization, and be deterministic when more than
# one active membership qualifies.


def _token_org_id(access_token: str) -> str | None:
    payload = decode_token(access_token)
    assert payload is not None
    return payload.get("organization_id")


def test_list_users_shows_pending_account_over_active_membership(db) -> None:
    """A pending self-signup has an active membership row but a pending account;
    the org user list must show 'pending' so admins can still approve it."""
    org = _org(db, "Org A")
    RolesModelService().ensure_default_roles(db, org.id)
    user = _user_with_status(db, "pending@x.com", org.id, status="pending")
    _membership(db, user.id, org.id, role="viewer", status="active")

    row = next(u for u in _user_manager().list_users(db, organization_id=org.id) if u.id == user.id)
    assert row.status == "pending"


def test_list_users_shows_suspended_membership_when_account_active(db) -> None:
    """An approved (active) account suspended in this org must show 'suspended'."""
    org = _org(db, "Org A")
    RolesModelService().ensure_default_roles(db, org.id)
    user = _user(db, "member@x.com", org.id)
    _membership(db, user.id, org.id, role="viewer", status="suspended")

    row = next(u for u in _user_manager().list_users(db, organization_id=org.id) if u.id == user.id)
    assert row.status == "suspended"


@pytest.mark.parametrize(
    ("membership_status", "expect_fallback"),
    [
        ("active", True),
        ("suspended", False),
        ("pending", False),
    ],
)
def test_create_tokens_fallback_requires_active_membership(db, membership_status, expect_fallback) -> None:
    org = _org(db, "Org A")
    user = _user(db, "u@x.com", org.id)
    user.organization_id = None  # legacy/drifted primary org
    db.commit()
    _membership(db, user.id, org.id, role="admin", status=membership_status)

    if expect_fallback:
        access_token, _ = AuthService(db).create_tokens(user)
        assert _token_org_id(access_token) == org.id
    else:
        # No active membership anywhere -> login is blocked, not given a no-org token.
        with pytest.raises(ValidationError):
            AuthService(db).create_tokens(user)


def test_create_tokens_fallback_ignores_membership_in_inactive_org(db) -> None:
    org = _org(db, "Org A")
    org.status = "suspended"
    db.commit()
    user = _user(db, "u@x.com", org.id)
    user.organization_id = None
    db.commit()
    _membership(db, user.id, org.id, role="admin", status="active")

    # The only membership is in a non-active org -> no landing org -> login blocked.
    with pytest.raises(ValidationError):
        AuthService(db).create_tokens(user)


def test_create_tokens_fallback_is_deterministic_across_multiple_active_memberships(db) -> None:
    org_older, org_newer = _org(db, "Org Older"), _org(db, "Org Newer")
    user = _user(db, "u@x.com", org_older.id)
    user.organization_id = None
    db.commit()
    now = datetime.now(UTC)
    db.add(
        UserOrganization(
            user_id=user.id, organization_id=org_older.id, role="admin", status="active",
            updated_at=now - timedelta(days=1),
        )
    )
    db.add(
        UserOrganization(
            user_id=user.id, organization_id=org_newer.id, role="admin", status="active",
            updated_at=now,
        )
    )
    db.commit()

    access_token, _ = AuthService(db).create_tokens(user)

    assert _token_org_id(access_token) == org_newer.id


def test_create_tokens_fallback_is_deterministic_when_updated_at_is_null(db) -> None:
    """updated_at is nullable with no DB default on the live schema — most real
    rows have it NULL, and Postgres sorts NULL first on DESC, so the fallback
    must not silently regress to nondeterministic once updated_at can't help."""
    org_older, org_newer = _org(db, "Org Older"), _org(db, "Org Newer")
    user = _user(db, "u@x.com", org_older.id)
    user.organization_id = None
    db.commit()
    _membership(db, user.id, org_older.id, role="admin", status="active")
    _membership(db, user.id, org_newer.id, role="admin", status="active")
    # Force updated_at back to NULL and control created_at explicitly: the
    # SQLite test schema (built from the current model, server_default=func.now())
    # auto-populates updated_at on insert regardless of the Python-level value
    # passed, and SQLite's CURRENT_TIMESTAMP is only second-precision, so two
    # inserts in the same test can tie on created_at too. Neither matches real
    # production, where updated_at has no DB default at all.
    now = datetime.now(UTC)
    db.query(UserOrganization).filter(
        UserOrganization.user_id == user.id, UserOrganization.organization_id == org_older.id
    ).update({"updated_at": None, "created_at": now - timedelta(days=1)})
    db.query(UserOrganization).filter(
        UserOrganization.user_id == user.id, UserOrganization.organization_id == org_newer.id
    ).update({"updated_at": None, "created_at": now})
    db.commit()
    rows = _memberships(db, user.id)
    assert rows[org_older.id].updated_at is None and rows[org_newer.id].updated_at is None

    access_token, _ = AuthService(db).create_tokens(user)

    assert _token_org_id(access_token) == org_newer.id


# ── _require_active_membership fail-closed contract (common/auth) ────────────────


class _StubMembershipChecker:
    """Minimal MembershipStatusChecker stub returning a fixed active/inactive verdict."""

    def __init__(self, active: bool) -> None:
        self._active = active

    def is_membership_active(self, db, user_id, org_id) -> bool:
        return self._active


def test_require_active_membership_fails_closed_when_service_unregistered(monkeypatch) -> None:
    """503, not allow-through, when the membership checker was never wired."""
    import common.auth as auth_mod

    monkeypatch.setattr(auth_mod, "_auth_bypass_enabled", lambda: False)
    monkeypatch.setattr(auth_mod, "_membership_db_service", None, raising=False)

    with pytest.raises(auth_mod.HTTPException) as exc_info:
        auth_mod._require_active_membership("role:write", "u1", "org1", object())
    assert exc_info.value.status_code == 503


def test_require_active_membership_fails_closed_when_db_missing(monkeypatch) -> None:
    """503 when there is no DB session to evaluate the check against."""
    import common.auth as auth_mod

    monkeypatch.setattr(auth_mod, "_auth_bypass_enabled", lambda: False)
    monkeypatch.setattr(
        auth_mod, "_membership_db_service", _StubMembershipChecker(active=True), raising=False
    )

    with pytest.raises(auth_mod.HTTPException) as exc_info:
        auth_mod._require_active_membership("role:write", "u1", "org1", None)
    assert exc_info.value.status_code == 503


def test_require_active_membership_denies_suspended(monkeypatch) -> None:
    """403 when the checker reports the membership is not active."""
    import common.auth as auth_mod

    monkeypatch.setattr(auth_mod, "_auth_bypass_enabled", lambda: False)
    monkeypatch.setattr(
        auth_mod, "_membership_db_service", _StubMembershipChecker(active=False), raising=False
    )

    with pytest.raises(auth_mod.HTTPException) as exc_info:
        auth_mod._require_active_membership("role:write", "u1", "org1", object())
    assert exc_info.value.status_code == 403


def test_require_active_membership_allows_active(monkeypatch) -> None:
    """No raise when the membership is active."""
    import common.auth as auth_mod

    monkeypatch.setattr(auth_mod, "_auth_bypass_enabled", lambda: False)
    monkeypatch.setattr(
        auth_mod, "_membership_db_service", _StubMembershipChecker(active=True), raising=False
    )

    auth_mod._require_active_membership("role:write", "u1", "org1", object())


def test_require_active_membership_skips_check_in_bypass_mode(monkeypatch) -> None:
    """Under BYPASS_AUTH the synthetic dev actor is exempt — no raise even with
    no checker wired (dev-only, env-gated path)."""
    import common.auth as auth_mod

    monkeypatch.setattr(auth_mod, "_auth_bypass_enabled", lambda: True)
    monkeypatch.setattr(auth_mod, "_membership_db_service", None, raising=False)

    auth_mod._require_active_membership("role:write", "modular-dev-user", "org1", None)


# ── is_membership_active legacy primary-org fallback (no membership row) ─────────


def test_is_membership_active_legacy_primary_org_fallback(db) -> None:
    """No membership row: the user's primary org counts as active (legacy path)."""
    org = _org(db, "Legacy Org")
    user = _user(db, "legacy@x.com", org.id)  # _user creates no membership row
    assert _user_svc().is_membership_active(db, user.id, org.id) is True


def test_is_membership_active_false_when_no_row_and_not_primary(db) -> None:
    """No membership row and the org is not the user's primary -> not active."""
    primary = _org(db, "Primary Org")
    other = _org(db, "Other Org")
    user = _user(db, "u2@x.com", primary.id)
    assert _user_svc().is_membership_active(db, user.id, other.id) is False


def test_is_membership_active_membership_row_overrides_primary_fallback(db) -> None:
    """A suspended membership row wins over the primary-org fallback -> not active."""
    org = _org(db, "Org With Suspended Membership")
    user = _user(db, "u3@x.com", org.id)
    _membership(db, user.id, org.id, status="suspended")
    assert _user_svc().is_membership_active(db, user.id, org.id) is False

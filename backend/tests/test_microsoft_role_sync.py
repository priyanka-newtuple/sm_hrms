"""Unit tests for Microsoft Entra role sync, the legacy-role mirror, and the
PKCE helpers on the auth manager.

These exercise the pure orchestration logic in isolation using lightweight
fakes for the roles service / db / user / org — no Postgres or network needed.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from types import SimpleNamespace

import pytest

from auth.manager import AuthServiceManager, MicrosoftOAuthService
from exceptions import MicrosoftOAuthError, NotFoundError

SYNC = AuthServiceManager.MICROSOFT_SYNC_ASSIGNED_BY


# ── Fakes ────────────────────────────────────────────────────────────────────

class FakeRole:
    def __init__(self, id: str, name: str, priority: int = 0, is_system: bool = False):
        self.id = id
        self.name = name
        self.priority = priority
        self.is_system = is_system


class FakeAssignment:
    def __init__(self, role_id: str, user_id: str, org_id: str, assigned_by: str | None):
        self.role_id = role_id
        self.user_id = user_id
        self.org_id = org_id
        self.assigned_by = assigned_by


class FakeUser:
    def __init__(self, id: str = "u1", role: str = "viewer"):
        self.id = id
        self.role = role


class FakeOrg:
    def __init__(self, id: str = "org1"):
        self.id = id


class FakeDB:
    """Stand-in Session — the mirror calls commit()/refresh()."""

    def commit(self) -> None:  # noqa: D401
        pass

    def refresh(self, _obj) -> None:
        pass


class FakeRolesService:
    """Minimal stand-in for RolesModelService covering the methods the
    reconcile/mirror logic calls."""

    def __init__(self):
        self.roles: dict[tuple[str, str], FakeRole] = {}
        self.assignments: list[FakeAssignment] = []
        self.created_payloads: list = []
        self._seq = 0

    def seed_role(self, org_id, name, priority=0, is_system=False) -> FakeRole:
        self._seq += 1
        role = FakeRole(f"r{self._seq}", name, priority, is_system)
        self.roles[(org_id, name)] = role
        return role

    def seed_assignment(self, role_id, user_id, org_id, assigned_by) -> None:
        self.assignments.append(FakeAssignment(role_id, user_id, org_id, assigned_by))

    # --- methods used by the manager ---
    def get_role_by_name(self, db, org_id, name):
        return self.roles.get((org_id, name))

    def create_role(self, db, org_id, payload):
        self.created_payloads.append(payload)
        role = self.seed_role(org_id, payload.name, int(payload.priority or 0), is_system=False)
        return role

    def get_user_roles(self, db, user_id, org_id):
        return [a for a in self.assignments if a.user_id == user_id and a.org_id == org_id]

    def assign_role_to_user(self, db, user_id, org_id, role_id, assigned_by=None):
        for a in self.assignments:
            if a.user_id == user_id and a.org_id == org_id and a.role_id == role_id:
                return a
        a = FakeAssignment(role_id, user_id, org_id, assigned_by)
        self.assignments.append(a)
        return a

    def remove_user_role(self, db, user_id, org_id, role_id):
        for a in list(self.assignments):
            if a.user_id == user_id and a.org_id == org_id and a.role_id == role_id:
                self.assignments.remove(a)
                return
        raise NotFoundError("Role assignment not found")

    def get_user_roles_with_permissions(self, db, user_id, org_id):
        ids = {a.role_id for a in self.get_user_roles(db, user_id, org_id)}
        return [r for r in self.roles.values() if r.id in ids]


def _make_manager(fake: FakeRolesService) -> AuthServiceManager:
    return AuthServiceManager(roles_db_service=fake)


def _assigned_names(fake: FakeRolesService, user_id="u1", org_id="org1") -> set[str]:
    by_id = {r.id: r.name for r in fake.roles.values()}
    return {by_id[a.role_id] for a in fake.get_user_roles(None, user_id, org_id)}


# ── Reconcile: create + grant ────────────────────────────────────────────────

def test_reconcile_autocreates_readonly_role_and_grants_it():
    fake = FakeRolesService()
    mgr = _make_manager(fake)
    user, org, db = FakeUser(), FakeOrg(), FakeDB()

    matched = mgr._reconcile_microsoft_roles(db, user, org, ["StoreAppL1Resolver"])

    assert matched is True
    role = fake.get_role_by_name(None, org.id, "StoreAppL1Resolver")
    assert role is not None
    assert role.is_system is False  # auto-created roles must never be system

    # created with exactly the read-only baseline
    payload = fake.created_payloads[0]
    assert {p.permission_key for p in payload.permissions} == set(
        AuthServiceManager.READ_ONLY_BASELINE_PERMISSIONS
    )

    # assigned to the user, marked as sync-managed
    assignments = fake.get_user_roles(None, user.id, org.id)
    assert len(assignments) == 1
    assert assignments[0].role_id == role.id
    assert assignments[0].assigned_by == SYNC


def test_reconcile_reuses_existing_role():
    fake = FakeRolesService()
    existing = fake.seed_role("org1", "StoreAppL1Resolver", priority=0)
    mgr = _make_manager(fake)

    mgr._reconcile_microsoft_roles(FakeDB(), FakeUser(), FakeOrg(), ["StoreAppL1Resolver"])

    assert fake.created_payloads == []  # nothing created — existing reused
    assert _assigned_names(fake) == {"StoreAppL1Resolver"}
    assert fake.get_user_roles(None, "u1", "org1")[0].role_id == existing.id


# ── Reconcile: idempotency ───────────────────────────────────────────────────

def test_reconcile_is_idempotent():
    fake = FakeRolesService()
    mgr = _make_manager(fake)
    user, org, db = FakeUser(), FakeOrg(), FakeDB()

    mgr._reconcile_microsoft_roles(db, user, org, ["StoreAppL1Resolver"])
    mgr._reconcile_microsoft_roles(db, user, org, ["StoreAppL1Resolver"])

    assert len(fake.created_payloads) == 1                      # created once
    assert len(fake.get_user_roles(None, user.id, org.id)) == 1  # assigned once


# ── Reconcile: revoke on directory change ────────────────────────────────────

def test_reconcile_revokes_role_dropped_from_claim():
    fake = FakeRolesService()
    mgr = _make_manager(fake)
    user, org, db = FakeUser(), FakeOrg(), FakeDB()

    mgr._reconcile_microsoft_roles(db, user, org, ["StoreAppL1Resolver"])
    mgr._reconcile_microsoft_roles(db, user, org, ["StoreAppL2Resolver"])

    # L1 revoked, L2 granted
    assert _assigned_names(fake) == {"StoreAppL2Resolver"}


# ── Reconcile: sentinel protects manual / non-sync roles ─────────────────────

def test_reconcile_preserves_manually_assigned_roles():
    fake = FakeRolesService()
    admin = fake.seed_role("org1", "admin", priority=100, is_system=True)
    fake.seed_assignment(admin.id, "u1", "org1", assigned_by=None)  # manual / bootstrap
    mgr = _make_manager(fake)

    # empty claim → nothing matched, but the manual admin must survive
    matched = mgr._reconcile_microsoft_roles(FakeDB(), FakeUser(), FakeOrg(), [])

    assert matched is False
    assert "admin" in _assigned_names(fake)


def test_reconcile_ignores_blank_role_values():
    fake = FakeRolesService()
    mgr = _make_manager(fake)

    matched = mgr._reconcile_microsoft_roles(FakeDB(), FakeUser(), FakeOrg(), ["", "  ", None])

    assert matched is False
    assert fake.created_payloads == []


def test_reconcile_noops_without_org():
    fake = FakeRolesService()
    mgr = _make_manager(fake)
    # org with no id
    matched = mgr._reconcile_microsoft_roles(FakeDB(), FakeUser(), SimpleNamespace(id=None), ["X"])
    assert matched is False


# ── Legacy-role mirror ───────────────────────────────────────────────────────

def test_mirror_uses_synced_role_when_it_is_the_only_role():
    fake = FakeRolesService()
    mgr = _make_manager(fake)
    user, org, db = FakeUser(role="viewer"), FakeOrg(), FakeDB()

    mgr._reconcile_microsoft_roles(db, user, org, ["StoreAppL2Resolver"])

    # reconcile mirrors the highest-priority role into the legacy column
    assert user.role == "StoreAppL2Resolver"


def test_mirror_never_downgrades_a_higher_priority_role():
    fake = FakeRolesService()
    admin = fake.seed_role("org1", "admin", priority=100, is_system=True)
    fake.seed_assignment(admin.id, "u1", "org1", assigned_by=None)
    mgr = _make_manager(fake)
    user = FakeUser(role="admin")

    # user also gets a read-only synced role, but admin (priority 100) must win
    mgr._reconcile_microsoft_roles(FakeDB(), user, FakeOrg(), ["StoreAppL1Resolver"])

    assert user.role == "admin"


def test_mirror_is_noop_when_user_has_no_roles():
    fake = FakeRolesService()
    mgr = _make_manager(fake)
    user = FakeUser(role="viewer")

    mgr._mirror_primary_role_to_legacy(FakeDB(), user, "org1")

    assert user.role == "viewer"  # unchanged


# ── PKCE helpers ─────────────────────────────────────────────────────────────

def _configure_ms(secret: str) -> None:
    oauth = SimpleNamespace(
        enabled=True,
        client_id="client-123",
        tenant_id="tenant-abc",
        client_secret=secret,
        redirect_uri="http://localhost:3000/auth/microsoft/callback",
        state_secret="state-secret",
        state_ttl_seconds=600,
    )
    cfg = SimpleNamespace(_configuration=SimpleNamespace(microsoft_oauth_configuration=oauth))
    MicrosoftOAuthService.configure(cfg)


@pytest.fixture(autouse=True)
def _restore_ms_config():
    original = MicrosoftOAuthService._configuration
    yield
    MicrosoftOAuthService._configuration = original


def test_generate_pkce_pair_is_valid_s256():
    verifier, challenge = MicrosoftOAuthService.generate_pkce_pair()
    assert 43 <= len(verifier) <= 128  # RFC 7636 bounds
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    assert challenge == expected
    assert "=" not in challenge  # base64url, no padding


def test_use_pkce_true_when_no_secret():
    _configure_ms("")
    assert MicrosoftOAuthService.has_client_secret() is False
    assert MicrosoftOAuthService.use_pkce() is True


def test_use_pkce_false_when_real_secret_set():
    _configure_ms("a-real-secret-value")
    assert MicrosoftOAuthService.has_client_secret() is True
    assert MicrosoftOAuthService.use_pkce() is False


def test_authorization_url_includes_pkce_challenge_when_provided():
    _configure_ms("")
    url = MicrosoftOAuthService.build_authorization_url(
        state="st", redirect_uri="http://localhost:3000/auth/microsoft/callback",
        code_challenge="CHALLENGE123",
    )
    assert "code_challenge=CHALLENGE123" in url
    assert "code_challenge_method=S256" in url


def test_authorization_url_omits_challenge_when_absent():
    _configure_ms("a-real-secret-value")
    url = MicrosoftOAuthService.build_authorization_url(
        state="st", redirect_uri="http://localhost:3000/auth/microsoft/callback",
    )
    assert "code_challenge" not in url


def test_exchange_requires_secret_or_verifier():
    # No verifier (PKCE) and no real secret → must refuse before any network call.
    _configure_ms("")
    with pytest.raises(MicrosoftOAuthError):
        asyncio.run(
            MicrosoftOAuthService.exchange_code_for_tokens(
                code="auth-code",
                redirect_uri="http://localhost:3000/auth/microsoft/callback",
                code_verifier=None,
            )
        )

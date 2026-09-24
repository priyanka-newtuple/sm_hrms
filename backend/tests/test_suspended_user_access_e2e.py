"""Black-box E2E — per-org suspension (regression test for the suspended-user bug).

Every step is a real HTTP call against the live, fully-wired application
(the `modular-backend` container). A member belongs to two active orgs; an admin
suspends them in org A only. Asserts the FIXED behaviour:

  - Before suspension: the member can act (permissioned read) in org A.
  - After suspension in org A: the member is denied in org A (403, membership
    suspended) — their existing token no longer grants access there.
  - The member can still switch to org B and act there.
  - The account stays authenticatable: users.status='active', is_active=True
    (derived), while user_organizations.status for org A is 'suspended'.

Requires the per-org-suspension fix to be deployed (migrations applied + new code
running). Skips automatically if the live server is unreachable.

Run (inside the container):
    docker exec -w /app/backend -e STORY_TEST_BASE_URL=http://localhost:8000 \
        <backend-container> python -m pytest tests/test_suspended_user_access_e2e.py -v -s
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
import requests
from sqlalchemy import create_engine, text

BASE_URL = os.environ.get("STORY_TEST_BASE_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/v1/api"
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://statemachine:statemachine@localhost:5455/statemachine"
)
SCHEMA = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")
PASSWORD = "SuspendTest123!"


def _reachable() -> bool:
    for _ in range(3):
        try:
            if requests.get(f"{BASE_URL}/health", timeout=8).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


requires_live = pytest.mark.skipif(
    not _reachable(), reason=f"Live server not reachable at {BASE_URL}"
)


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DB_URL, connect_args={"options": f"-csearch_path={SCHEMA},public"})
    yield e
    e.dispose()


def _seed_org(conn, name_prefix: str) -> str:
    org_id = str(uuid.uuid4())
    conn.execute(
        text(
            f'INSERT INTO "{SCHEMA}".organizations (id, name, slug, settings, status) '
            f"VALUES (:id, :n, :s, '{{}}', 'active')"
        ),
        {"id": org_id, "n": f"{name_prefix} Org", "s": f"{name_prefix.lower()}-{org_id[:8]}"},
    )
    return org_id


def _seed_user(conn, org_id: str, label: str, pw_hash: str) -> tuple[str, str]:
    user_id = str(uuid.uuid4())
    email = f"{label}-{user_id[:8]}@suspendtest.io"
    conn.execute(
        text(
            f'INSERT INTO "{SCHEMA}".users '
            f"(id, email, full_name, hashed_password, organization_id, role, status, auth_type) "
            f"VALUES (:id, :em, :fn, :pw, :org, 'admin', 'active', 'local')"
        ),
        {"id": user_id, "em": email, "fn": label, "pw": pw_hash, "org": org_id},
    )
    return user_id, email


def _add_membership(conn, user_id: str, org_id: str) -> None:
    conn.execute(
        text(
            f'INSERT INTO "{SCHEMA}".user_organizations (id, user_id, organization_id, role, status) '
            f"VALUES (:id, :uid, :org, 'admin', 'active')"
        ),
        {"id": str(uuid.uuid4()), "uid": user_id, "org": org_id},
    )


def _grant_admin_role(engine, org_id: str, *user_ids: str) -> None:
    from sqlalchemy.orm import sessionmaker

    import organizations.db_models  # noqa: F401
    import user.db_models  # noqa: F401
    from roles.db_models import RolesModelService

    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        svc = RolesModelService()
        roles = svc.ensure_default_roles(s, org_id)
        admin_role = next(r for r in roles if r.name == "admin")
        for uid in user_ids:
            svc.assign_role_to_user(s, uid, org_id, admin_role.id)
    finally:
        s.close()


@pytest.fixture(scope="module")
def fixtures(engine):
    from common.security import hash_password

    pw_hash = hash_password(PASSWORD)
    with engine.begin() as conn:
        org_a = _seed_org(conn, "SuspendA")
        org_b = _seed_org(conn, "SuspendB")
        admin_id, admin_email = _seed_user(conn, org_a, "admin", pw_hash)
        member_id, member_email = _seed_user(conn, org_a, "member", pw_hash)
        _add_membership(conn, admin_id, org_a)
        _add_membership(conn, member_id, org_a)
        _add_membership(conn, member_id, org_b)

    _grant_admin_role(engine, org_a, admin_id, member_id)
    _grant_admin_role(engine, org_b, member_id)

    yield {
        "org_a": org_a,
        "org_b": org_b,
        "admin_id": admin_id,
        "admin_email": admin_email,
        "member_id": member_id,
        "member_email": member_email,
    }

    with engine.begin() as conn:
        conn.execute(
            text(f'DELETE FROM "{SCHEMA}".users WHERE id IN (:a, :m)'),
            {"a": admin_id, "m": member_id},
        )
        conn.execute(
            text(f'DELETE FROM "{SCHEMA}".organizations WHERE id IN (:a, :b)'),
            {"a": org_a, "b": org_b},
        )


def _login(email: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}, timeout=10)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


def _get_users(access_token: str):
    """Permissioned read used as the per-org access probe."""
    return requests.get(
        f"{API}/users", headers={"Authorization": f"Bearer {access_token}"}, timeout=10
    )


def _membership_status(conn, user_id: str, org_id: str) -> str | None:
    return conn.execute(
        text(
            f'SELECT status FROM "{SCHEMA}".user_organizations '
            f"WHERE user_id = :u AND organization_id = :o"
        ),
        {"u": user_id, "o": org_id},
    ).scalar()


def _account_and_membership_states(engine, member_id: str, org_a: str, org_b: str) -> tuple:
    """Return (account_status, is_active, org_a_status, org_b_status) read from the DB."""
    with engine.connect() as conn:
        acct = conn.execute(
            text(f'SELECT status, is_active FROM "{SCHEMA}".users WHERE id = :id'),
            {"id": member_id},
        ).fetchone()
        return (
            acct[0], acct[1],
            _membership_status(conn, member_id, org_a),
            _membership_status(conn, member_id, org_b),
        )


@requires_live
def test_per_org_suspension_isolates_to_one_org(engine, fixtures):
    member_tok = _login(fixtures["member_email"])["access_token"]

    # Member lands in primary org A and can act there (permissioned read).
    before = _get_users(member_tok)
    assert before.status_code == 200, f"member should read in org A before suspend: {before.text}"

    # Admin suspends the member in org A.
    admin_h = {"Authorization": f"Bearer {_login(fixtures['admin_email'])['access_token']}"}
    susp = requests.post(f"{API}/users/{fixtures['member_id']}/suspend", headers=admin_h, timeout=10)
    assert susp.status_code == 200, f"suspend failed: {susp.status_code} {susp.text}"
    assert susp.json().get("status") == "suspended", "suspend response should reflect membership status"

    # Same token, org A — now denied (membership suspended).
    after_a = _get_users(member_tok)
    assert after_a.status_code == 403, f"suspended member should be denied in org A, got {after_a.status_code}"
    assert "suspend" in after_a.json().get("detail", "").lower()

    # Member can still switch to org B and act there.
    switch = requests.post(
        f"{API}/users/me/organizations/switch",
        headers={"Authorization": f"Bearer {member_tok}"},
        json={"organization_id": fixtures["org_b"]}, timeout=10,
    )
    assert switch.status_code == 200, f"member should still switch to org B: {switch.text}"
    in_b = _get_users(switch.json()["access_token"])
    assert in_b.status_code == 200, f"member should act in org B: {in_b.text}"

    # Account stays authenticatable; suspension lives only on the org-A membership.
    acct_status, is_active, mem_a, mem_b = _account_and_membership_states(
        engine, fixtures["member_id"], fixtures["org_a"], fixtures["org_b"]
    )
    assert acct_status == "active" and is_active is True, "account must stay active/authenticatable"
    assert mem_a == "suspended", "org-A membership must be suspended"
    assert mem_b == "active", "org-B membership must stay active"
    print("\n==> per-org suspension confirmed: denied in org A, active in org B, account intact.")


@requires_live
def test_derived_is_active_cannot_be_written_directly(engine):
    """is_active is a generated column — a direct write must be rejected by the DB."""
    from sqlalchemy.exc import ProgrammingError

    uid = str(uuid.uuid4())
    with engine.begin() as conn:
        org_id = _seed_org(conn, "DerivedCol")
        conn.execute(
            text(
                f'INSERT INTO "{SCHEMA}".users '
                f"(id, email, full_name, organization_id, role, status, auth_type) "
                f"VALUES (:id, :em, 'Derived', :org, 'viewer', 'active', 'local')"
            ),
            {"id": uid, "em": f"derived-{uid[:8]}@suspendtest.io", "org": org_id},
        )
    try:
        with engine.connect() as conn:
            active = conn.execute(
                text(f'SELECT is_active FROM "{SCHEMA}".users WHERE id = :id'), {"id": uid}
            ).scalar()
            assert active is True, "active account -> is_active derived True"
        with pytest.raises(ProgrammingError), engine.begin() as conn:
            conn.execute(
                text(f'UPDATE "{SCHEMA}".users SET is_active = false WHERE id = :id'),
                {"id": uid},
            )
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DELETE FROM "{SCHEMA}".users WHERE id = :id'), {"id": uid})
            conn.execute(text(f'DELETE FROM "{SCHEMA}".organizations WHERE id = :id'), {"id": org_id})

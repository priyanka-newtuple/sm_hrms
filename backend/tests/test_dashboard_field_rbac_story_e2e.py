"""End-to-end, API-only validation of the Dashboard Field RBAC story
(design_docs/tony_dashboard_field_rbac_fix.md).

Every assertion is a real HTTP call against the live, fully-wired application
(the `modular-backend` docker container) — no manager/db_models shortcuts, no
fakes, no stubs. Follows the exact same harness convention as
`test_entity_field_permission_filter_story_e2e.py` (the prior fix's own E2E
story test): fresh org + human user rows provisioned directly in Postgres
(explicitly out-of-scope subsystem — real registration/approval is unrelated
to this feature), a real DB-backed role assigned via `PUT /roles/users/{id}/role`
(the same documented substitution for the invitation flow used by the prior
story test — no separate "assign role" endpoint exists beyond this one).

Two additional runtime rows are also seeded directly rather than through the
API, both explicitly out of scope for this feature and each documented at its
seed site below:
- `entity_state` (workflow enrollment) — a separate subsystem (workflow
  definitions + enrollment), unrelated to field-level RBAC itself.
- `projection_rows` (denormalized dashboard read model) — built by an async
  projection pipeline outside this test's control; per the design doc's own
  "One open question" note, the story's projection-backed assertions
  (`query-preview`, `query-sources`) seed a row directly rather than depend on
  that pipeline's timing.

Requires:
- The `modular-backend` container running and reachable at BASE_URL
  (defaults to http://localhost:8001 per docker-compose.local.yml; override
  via STORY_TEST_BASE_URL).
- Postgres reachable via DATABASE_URL/POSTGRES_APP_SCHEMA (the same DB the
  container itself uses) for the non-API setup/cleanup steps above.

Run directly (skipped automatically if the live server isn't reachable, so
it's safe inside a normal `pytest tests/` sweep too):
    pytest tests/test_dashboard_field_rbac_story_e2e.py -v -s
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from sqlalchemy import create_engine, text

BASE_URL = os.environ.get("STORY_TEST_BASE_URL", "http://localhost:8001").rstrip("/")
API_URL = f"{BASE_URL}/v1/api"
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://statemachine:statemachine@localhost:5455/statemachine"
)
APP_SCHEMA = os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")


def _server_reachable() -> bool:
    try:
        return requests.get(f"{BASE_URL}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


requires_live_server = pytest.mark.skipif(
    not _server_reachable(),
    reason=f"Live server not reachable at {BASE_URL} — start the modular-backend container",
)


# ── Setup (non-API: organization + human user accounts) ────────────────────────


@pytest.fixture(scope="module")
def db_engine():
    # search_path matches the live container's own engine (see
    # tests/conftest.py::entities_db_service_manager) — needed for
    # `_bootstrap_admin_role`'s unqualified ORM queries (`roles`, `role_permissions`);
    # the raw inserts elsewhere in this file are already fully schema-qualified
    # and unaffected either way.
    engine = create_engine(
        DB_URL, connect_args={"options": f"-csearch_path={APP_SCHEMA},public"}
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def story_org(db_engine):
    org_id = str(uuid.uuid4())
    with db_engine.begin() as conn:
        conn.execute(
            text(
                f'INSERT INTO "{APP_SCHEMA}".organizations (id, name, slug, settings, status) '
                f"VALUES (:id, :name, :slug, '{{}}', 'active')"
            ),
            {"id": org_id, "name": "Dashboard RBAC Story Org", "slug": f"dash-story-{org_id[:8]}"},
        )
    yield org_id
    with db_engine.begin() as conn:
        conn.execute(text(f'DELETE FROM "{APP_SCHEMA}".organizations WHERE id = :id'), {"id": org_id})


def _make_user(db_engine, org_id: str, label: str) -> str:
    user_id = str(uuid.uuid4())
    email = f"{label}-{user_id[:8]}@dash-story.test"
    with db_engine.begin() as conn:
        conn.execute(
            text(
                f'INSERT INTO "{APP_SCHEMA}".users '
                f"(id, email, full_name, organization_id, role, status, auth_type) "
                f"VALUES (:id, :email, :full_name, :org_id, 'viewer', 'active', 'local')"
            ),
            {"id": user_id, "email": email, "full_name": label.capitalize(), "org_id": org_id},
        )
    return user_id


@pytest.fixture(scope="module")
def story_users(db_engine, story_org):
    return {
        "admin": _make_user(db_engine, story_org, "admin"),
        "recruiter": _make_user(db_engine, story_org, "recruiter"),
    }


def _bearer_headers(user_id: str, org_id: str) -> dict[str, str]:
    """A real, signed access token — `common/auth.py` no longer trusts plain
    `x-user-id`/`x-org-id`/`x-user-roles` headers at all (the header-trust
    removal from `design_docs/tony_header_auth_bypass_fix.md` landed on `main`
    2026-07-15, after this fix was originally built against header auth —
    corrected here). `roles` is deliberately omitted: every permission this
    story exercises (`require_permission`, entities/dashboard's own RBAC) is
    re-evaluated live against the DB on every request, never read from the
    token's claims.
    """
    from common.security import create_access_token

    token = create_access_token(subject=user_id, organization_id=org_id)
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_admin_role(db_engine, org_id: str, admin_user_id: str) -> None:
    """Seed the org's default RBAC roles and assign `admin` to the story's admin
    user — real org creation does this via `organizations/manager.py::create_organization`
    / `approve_organization`, an unrelated self-serve-signup subsystem this test
    doesn't exercise (the org here is seeded directly, not registered through
    that flow). Calls the exact same `RolesModelService` methods that subsystem
    calls, just directly rather than through its own separate API surface —
    the one non-API setup step in this story, matching the precedent story
    test's own carve-out for out-of-scope subsystems."""
    from sqlalchemy.orm import sessionmaker

    import organizations.db_models  # noqa: F401 — registers `organizations` on Base.metadata
    import user.db_models  # noqa: F401 — registers `users` on Base.metadata (roles FK target)
    from roles.db_models import RolesModelService

    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        service = RolesModelService()
        roles = service.ensure_default_roles(session, org_id)
        admin_role = next(r for r in roles if r.name == "admin")
        service.assign_role_to_user(session, admin_user_id, org_id, admin_role.id)
    finally:
        session.close()


# ── The story, step by step, entirely over HTTP ─────────────────────────────────


@requires_live_server
def test_dashboard_field_rbac_story(db_engine, story_org, story_users) -> None:
    _bootstrap_admin_role(db_engine, story_org, story_users["admin"])
    admin_headers = _bearer_headers(story_users["admin"], story_org)

    # ── Step 1 — Admin creates the `candidate` entity type ──────────────────
    resp = requests.post(
        f"{API_URL}/entity-types",
        headers=admin_headers,
        json={
            "name": "candidate",
            "schema_definition": {
                "fields": [
                    {"id": "name", "name": "Name", "type": "text"},
                    {"id": "email", "name": "Email", "type": "text"},
                    {"id": "phone", "name": "Phone", "type": "text"},
                ]
            },
        },
    )
    assert resp.status_code == 201, resp.text
    entity_type = resp.json()
    entity_type_id = entity_type["entity_type_id"]

    # ── Step 2 — Admin creates one real candidate record ────────────────────
    resp = requests.post(
        f"{API_URL}/entity-records",
        headers=admin_headers,
        json={
            "entity_type_id": entity_type_id,
            "data": {
                "identifier": "CAND-1",
                "name": "Ada Lovelace",
                "email": "ada@example.com",
                "phone": "555-1234",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    candidate = resp.json()
    candidate_id = candidate["entity_id"]

    # Non-API setup: enroll the candidate into a workflow so it shows up in
    # `instances.list` (`EntityStateRuntimeModel`) — enrollment mechanics are a
    # separate, unrelated subsystem (workflow definitions + enroll), out of
    # scope for a field-level-RBAC feature test.
    workflow_id = str(uuid.uuid4())
    with db_engine.begin() as conn:
        conn.execute(
            text(
                f'INSERT INTO "{APP_SCHEMA}_runtime".entity_state '
                f"(state_id, organization_id, entity_id, workflow_id, current_state, state_version) "
                f"VALUES (:state_id, :org_id, :entity_id, :workflow_id, 'APPLIED', 0)"
            ),
            {
                "state_id": str(uuid.uuid4()),
                "org_id": story_org,
                "entity_id": candidate_id,
                "workflow_id": workflow_id,
            },
        )

    # Non-API setup: one projection row for the `application_pipeline` source,
    # so the `query-preview`/`query-sources` assertions below have something to
    # resolve — built by an async projection pipeline in production, seeded
    # directly here per the design doc's own "one open question" note.
    projection_view_name = "application_pipeline"
    with db_engine.begin() as conn:
        conn.execute(
            text(
                f'INSERT INTO "{APP_SCHEMA}".projection_rows '
                f"(view_name, entity_id, organization_id, entity_type, current_state, data, created_at, updated_at) "
                f"VALUES (:view_name, :entity_id, :org_id, 'application', 'APPLIED', "
                f"CAST(:data AS JSON), :now, :now)"
            ),
            {
                "view_name": projection_view_name,
                "entity_id": candidate_id,
                "org_id": story_org,
                "data": (
                    '{"candidate_name": "Ada Lovelace", "candidate_email": "ada@example.com"}'
                ),
                "now": datetime.now(timezone.utc),
            },
        )

    # ── Step 3 — Admin creates the `limited_recruiter` role, no field
    #     permissions configured yet ──────────────────────────────────────────
    resp = requests.post(
        f"{API_URL}/roles",
        headers=admin_headers,
        json={
            "name": "limited_recruiter",
            "display_name": "Limited Recruiter",
            # Custom roles need explicit catalog permissions to pass the
            # controller-level `require_permission` gate — `dashboard:read` is
            # this module's own gate; entity_record:read/write is needed to
            # create/view the candidate record via the API at all.
            "permissions": [
                {"permission_key": "dashboard:read"},
                {"permission_key": "entity_record:read"},
                {"permission_key": "entity_record:write"},
            ],
            "entity_permissions": [
                {"entity_type": "candidate", "action": "view", "allowed": True},
                {"entity_type": "candidate", "action": "edit", "allowed": True},
            ],
            "field_permissions": [
                {"entity_type": "candidate", "field_name": "name", "can_view": True, "can_edit": True, "mask_value": False},
                {"entity_type": "candidate", "field_name": "phone", "can_view": True, "can_edit": False, "mask_value": True},
                # `email` deliberately absent — not visible at all.
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    role = resp.json()
    role_id = role["id"]

    # ── Step 4 — Admin assigns the role to the recruiter ────────────────────
    resp = requests.put(
        f"{API_URL}/roles/users/{story_users['recruiter']}/role",
        headers=admin_headers,
        json={"role_id": role_id},
    )
    assert resp.status_code == 200, resp.text

    recruiter_headers = _bearer_headers(story_users["recruiter"], story_org)

    # ── Step 5 — As admin: dashboard endpoints unaffected (is_system bypass) ─
    resp = requests.post(
        f"{API_URL}/dashboards/data",
        headers=admin_headers,
        json={
            "items": [
                {
                    "widget_id": "w1",
                    "metric": "instances.list",
                    "filters": {"fields": ["current_state", "data.name", "data.email", "data.phone"]},
                }
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    admin_row = next(r for r in resp.json()["results"]["w1"]["rows"] if r["entity_id"] == candidate_id)
    assert admin_row["data.email"] == "ada@example.com"
    assert admin_row["data.phone"] == "555-1234"

    # ── Step 6 — As recruiter, no explicit fields: name real, phone masked,
    #     email silently absent (INV-5) ─────────────────────────────────────
    resp = requests.post(
        f"{API_URL}/dashboards/data",
        headers=recruiter_headers,
        json={"items": [{"widget_id": "w1", "metric": "instances.list", "filters": {}}]},
    )
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json()["results"]["w1"]["rows"] if r["entity_id"] == candidate_id)
    assert row["data.name"] == "Ada Lovelace"
    assert row["data.phone"] == "***"
    assert "data.email" not in row

    # ── Step 7 — As recruiter, explicit `data.email` on a dashboard widget:
    #     silently dropped, not an error — a saved widget may have been built
    #     by someone with broader access than the current viewer, so one
    #     inaccessible field must not blank the whole widget/dashboard. ─────
    resp = requests.post(
        f"{API_URL}/dashboards/data",
        headers=recruiter_headers,
        json={
            "items": [
                {"widget_id": "w1", "metric": "instances.list", "filters": {"fields": ["data.email"]}}
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["results"]["w1"]["rows"]
    row = next(r for r in rows if r["entity_id"] == candidate_id)
    assert "data.email" not in row

    # ── Step 8 — As recruiter: catalogs never list `data.email` (INV-3) ─────
    resp = requests.get(f"{API_URL}/dashboards/metrics", headers=recruiter_headers)
    assert resp.status_code == 200, resp.text
    instances_metric = next(m for m in resp.json()["metrics"] if m["key"] == "instances.list")
    assert "data.email" not in {f["key"] for f in instances_metric["fields"]}

    resp = requests.get(f"{API_URL}/dashboards/filter-options", headers=recruiter_headers)
    assert resp.status_code == 200, resp.text
    assert "data.email" not in {o["value"] for o in resp.json()["entity_fields"]}

    # ── Step 9 — As recruiter: query-preview on the projection-backed source —
    #     forbidden field dropped, preview still returns 200 with what's left ─
    resp = requests.post(
        f"{API_URL}/dashboards/query-preview",
        headers=recruiter_headers,
        json={
            "query": {
                "source": projection_view_name,
                "select": [{"field": "candidate_name"}, {"field": "candidate_email"}],
            }
        },
    )
    assert resp.status_code == 200, resp.text
    preview_row = resp.json()["rows"][0]
    assert preview_row["candidate_name"] == "Ada Lovelace"
    assert "candidate_email" not in preview_row

    resp = requests.get(f"{API_URL}/dashboards/query-sources", headers=recruiter_headers)
    assert resp.status_code == 200, resp.text
    pipeline_source = next(s for s in resp.json()["sources"] if s["id"] == projection_view_name)
    assert "candidate_email" not in {f["key"] for f in pipeline_source["fields"]}

    # ── Step 10 — Admin grants email visibility, removes phone masking ──────
    resp = requests.put(
        f"{API_URL}/roles/{role_id}",
        headers=admin_headers,
        json={
            "field_permissions": [
                {"entity_type": "candidate", "field_name": "name", "can_view": True, "can_edit": True, "mask_value": False},
                {"entity_type": "candidate", "field_name": "phone", "can_view": True, "can_edit": True, "mask_value": False},
                {"entity_type": "candidate", "field_name": "email", "can_view": True, "can_edit": False, "mask_value": False},
            ]
        },
    )
    assert resp.status_code == 200, resp.text

    # ── Step 11 — Same recruiter, same headers, no new login: live re-check ──
    # This is the step that actually proves the check reads live DB state on
    # every request — not something decided once and cached.
    resp = requests.post(
        f"{API_URL}/dashboards/data",
        headers=recruiter_headers,
        json={"items": [{"widget_id": "w1", "metric": "instances.list", "filters": {}}]},
    )
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json()["results"]["w1"]["rows"] if r["entity_id"] == candidate_id)
    assert row["data.email"] == "ada@example.com"
    assert row["data.phone"] == "555-1234"

    # Cleanup: entity_state / projection_rows aren't cascaded by the org delete
    # fixture's FK (they key off entity_id, not directly off organization_id
    # with ON DELETE CASCADE for every column) — deleted explicitly here rather
    # than relying on it, mirroring the org-delete cleanup already run by the
    # `story_org` fixture on teardown.
    with db_engine.begin() as conn:
        conn.execute(
            text(f'DELETE FROM "{APP_SCHEMA}_runtime".entity_state WHERE entity_id = :id'),
            {"id": candidate_id},
        )
        conn.execute(
            text(f'DELETE FROM "{APP_SCHEMA}".projection_rows WHERE entity_id = :id'),
            {"id": candidate_id},
        )

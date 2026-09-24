"""End-to-end, API-only validation of the Entity Field Permission Filter story.

Every one of the 17 story steps is exercised as a real HTTP call against the
live, fully-wired application (the `modular-backend` docker container) —
no manager/db_models shortcuts, no fakes, no stubs. The only non-API setup is
provisioning the organization row and the four human user accounts (Admin,
Priya, Karan, Superadmin) directly in Postgres — explicitly agreed as
acceptable, since real user registration/approval is a separate, unrelated
workflow. Every other action in the story (entity type creation, role
creation/update, role assignment, entity record creation, listing, viewing,
editing) goes through the real REST API exactly as a real client would call
it.

Requires:
- The `modular-backend` container running and reachable at BASE_URL
  (defaults to http://localhost:8001 per docker-compose.local.yml; override
  via STORY_TEST_BASE_URL).
- Postgres reachable via DATABASE_URL/POSTGRES_APP_SCHEMA (the same DB the
  container itself uses) for the one-time user/org setup and cleanup.

Run directly (skipped automatically if the live server isn't reachable, so
it's safe inside a normal `pytest tests/` sweep too):
    pytest tests/test_entity_field_permission_filter_story_e2e.py -v -s

Known, accepted API gap exercised in Step 15: `PUT /roles/users/{id}/role`
replaces a user's role assignments rather than adding to them (confirmed in
`roles/db_models.py::set_user_role`) — there is no additive "assign another
role" endpoint today. The permission *check* itself already correctly
supports a user holding multiple simultaneous roles (proven directly against
the DB layer in `test_entity_field_permission_filter.py::
test_evaluate_entity_access_most_permissive_role_wins`); this file documents
the assignment-endpoint gap in place rather than working around it with a
non-API shortcut.
"""

from __future__ import annotations

import os
import uuid

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


# ── Setup (the one non-API part: organization + human user accounts) ───────────


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def story_org(db_engine):
    """A fresh, already-active organization — org bootstrap/approval is a
    separate, unrelated workflow, so it's seeded directly rather than routed
    through the real registration flow."""
    org_id = str(uuid.uuid4())
    with db_engine.begin() as conn:
        conn.execute(
            text(
                f'INSERT INTO "{APP_SCHEMA}".organizations (id, name, slug, settings, status) '
                f"VALUES (:id, :name, :slug, '{{}}', 'active')"
            ),
            {"id": org_id, "name": "Story Org", "slug": f"story-org-{org_id[:8]}"},
        )
    yield org_id
    with db_engine.begin() as conn:
        conn.execute(text(f'DELETE FROM "{APP_SCHEMA}".organizations WHERE id = :id'), {"id": org_id})


def _make_user(db_engine, org_id: str, label: str) -> str:
    """Provision one real `users` row directly — the one setup step
    explicitly carved out as non-API; everything downstream of this uses it
    only as an id/header value, never touched again outside the API."""
    user_id = str(uuid.uuid4())
    email = f"{label}-{user_id[:8]}@story.test"
    with db_engine.begin() as conn:
        conn.execute(
            text(
                f'INSERT INTO "{APP_SCHEMA}".users '
                f"(id, email, full_name, organization_id, role, status, auth_type, is_active) "
                f"VALUES (:id, :email, :full_name, :org_id, 'viewer', 'active', 'local', true)"
            ),
            {"id": user_id, "email": email, "full_name": label.capitalize(), "org_id": org_id},
        )
    return user_id


@pytest.fixture(scope="module")
def story_users(db_engine, story_org):
    return {
        "admin": _make_user(db_engine, story_org, "admin"),
        "priya": _make_user(db_engine, story_org, "priya"),
        "karan": _make_user(db_engine, story_org, "karan"),
        "superadmin": _make_user(db_engine, story_org, "superadmin"),
    }


def _headers(user_id: str, org_id: str, roles: str = "") -> dict[str, str]:
    return {"x-user-id": user_id, "x-org-id": org_id, "x-user-roles": roles}


# ── The story, step by step, entirely over HTTP ─────────────────────────────────


@requires_live_server
def test_entity_field_permission_filter_story(story_org, story_users) -> None:
    # Admin uses the header-trust "superadmin" shortcut purely to configure
    # the org (real per-request behavior of this system today, documented in
    # design_docs/jarvis_map.md) — Priya/Karan/Superadmin below carry no such
    # shortcut, so every read/write they perform is gated by their real,
    # DB-backed role assignment.
    admin_headers = _headers(story_users["admin"], story_org, roles="superadmin")
    priya_headers = _headers(story_users["priya"], story_org)
    karan_headers = _headers(story_users["karan"], story_org)

    # ── Step 1 — Admin creates the entity type ──────────────────────────────
    resp = requests.post(
        f"{API_URL}/entity-types",
        headers=admin_headers,
        json={
            "name": "Incident",
            "schema_definition": {
                "fields": [
                    {"id": "store_id", "name": "Store ID", "type": "text"},
                    {"id": "description", "name": "Description", "type": "text"},
                ]
            },
        },
    )
    assert resp.status_code == 201, resp.text
    entity_type = resp.json()
    entity_type_id = entity_type["entity_type_id"]
    assert entity_type["name"] == "Incident"

    # The condition feature's field list comes from the entity type's *forms*
    # (`entity_type_schema.fields_json`, forms module — an entity type can have
    # multiple forms, each contributing fields), not `entity_types.schema` —
    # corrected 2026-07-16. A form must exist with `store_id`/`description`
    # for the save-time field validation (Step 17) and the condition itself
    # (Step 3) to resolve against real fields.
    resp = requests.post(
        f"{API_URL}/forms/config",
        headers=admin_headers,
        json={
            "schema_key": "incident__incident_form",
            "name": "Incident Form",
            "entity_type": "Incident",
            "fields": [
                {"field": "store_id", "type": "string", "description": "Store ID"},
                {"field": "description", "type": "string", "description": "Description"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text

    # A custom (non-system) role with zero configured field_permissions gets
    # `visible=[]` from `get_visible_fields` — "deny all fields", pre-existing
    # behavior unrelated to this feature — so every role below needs explicit
    # field_permissions to see any field content at all.
    def _incident_field_permissions() -> list[dict[str, object]]:
        return [
            {
                "entity_type": "Incident",
                "field_name": field_name,
                "can_view": True,
                "can_edit": True,
                "mask_value": False,
            }
            for field_name in ("store_id", "description", "identifier")
        ]

    # ── Step 2 — Admin creates the Resolver role: full access, no condition ─
    resp = requests.post(
        f"{API_URL}/roles",
        headers=admin_headers,
        json={
            "name": "resolver",
            "display_name": "Resolver",
            "permissions": [
                {"permission_key": "entity_record:write"},
                {"permission_key": "entity_record:read"},
            ],
            "entity_permissions": [
                {"entity_type": "Incident", "action": "view", "allowed": True},
                {"entity_type": "Incident", "action": "edit", "allowed": True},
            ],
            "field_permissions": _incident_field_permissions(),
        },
    )
    assert resp.status_code == 201, resp.text
    resolver_role = resp.json()
    resolver_role_id = resolver_role["id"]
    assert all(ep["entity_field"] is None for ep in resolver_role["entity_permissions"])

    # Give the admin persona a real, DB-backed `is_system` role now that
    # default roles exist for this org (seeded by the `POST /roles` call
    # above). The `x-user-roles: superadmin` header only bypasses the
    # coarse `require_permission` controller gate — entities/manager.py's
    # own entity-type-scoped RBAC check (`guard_write`/`evaluate_entity_access`)
    # is fully DB-driven and ignores the header entirely, so admin needs a
    # genuine role to create/manage entity records below (setup only —
    # not one of the story's numbered steps).
    resp = requests.get(f"{API_URL}/roles", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    admin_system_role = next(r for r in resp.json() if r["name"] == "admin")
    resp = requests.put(
        f"{API_URL}/roles/users/{story_users['admin']}/role",
        headers=admin_headers,
        json={"role_id": admin_system_role["id"]},
    )
    assert resp.status_code == 200, resp.text

    # ── Step 3 — Admin creates the Store Associate role: conditioned view ───
    resp = requests.post(
        f"{API_URL}/roles",
        headers=admin_headers,
        json={
            "name": "store_associate",
            "display_name": "Store Associate",
            "permissions": [
                {"permission_key": "entity_record:write"},
                {"permission_key": "entity_record:read"},
            ],
            "entity_permissions": [
                {
                    "entity_type": "Incident",
                    "action": "view",
                    "allowed": True,
                    "entity_field": "store_id",
                    "operator": "==",
                    "value_source": "LITERAL",
                    "condition_value": "store-A",
                },
                {"entity_type": "Incident", "action": "edit", "allowed": True},
            ],
            "field_permissions": _incident_field_permissions(),
        },
    )
    assert resp.status_code == 201, resp.text
    store_associate_role = resp.json()
    store_associate_role_id = store_associate_role["id"]
    view_ep = next(ep for ep in store_associate_role["entity_permissions"] if ep["action"] == "view")
    assert view_ep["entity_field"] == "store_id"
    assert view_ep["operator"] == "=="
    assert view_ep["condition_value"] == "store-A"

    # ── Step 4 — Admin assigns the roles ────────────────────────────────────
    resp = requests.put(
        f"{API_URL}/roles/users/{story_users['priya']}/role",
        headers=admin_headers,
        json={"role_id": store_associate_role_id},
    )
    assert resp.status_code == 200, resp.text

    resp = requests.put(
        f"{API_URL}/roles/users/{story_users['karan']}/role",
        headers=admin_headers,
        json={"role_id": resolver_role_id},
    )
    assert resp.status_code == 200, resp.text

    # ── Step 5 — Three incidents get created ────────────────────────────────
    def _create_incident(identifier: str, store_id: str | None) -> str:
        data = {"identifier": identifier, "description": f"Incident {identifier}"}
        if store_id is not None:
            data["store_id"] = store_id
        resp = requests.post(
            f"{API_URL}/entity-records",
            headers=admin_headers,
            json={"entity_type_id": entity_type_id, "data": data},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["entity_id"]

    incident_1 = _create_incident("INC-1", "store-A")  # Store A
    incident_2 = _create_incident("INC-2", "store-B")  # Store B
    incident_3 = _create_incident("INC-3", None)  # Store ID empty

    def _list_incidents(headers: dict[str, str]) -> set[str]:
        resp = requests.get(
            f"{API_URL}/entity-records", headers=headers, params={"entity_type_name": "Incident"}
        )
        assert resp.status_code == 200, resp.text
        return {item["entity_id"] for item in resp.json()["items"]}

    # ── Step 6 — Priya lists incidents: only Incident 1, no error/hint ──────
    assert _list_incidents(priya_headers) == {incident_1}

    # ── Step 7 — Priya opens Incident 2 (Store B) directly: blocked, generic ─
    resp = requests.get(f"{API_URL}/entity-records/{incident_2}", headers=priya_headers)
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"].lower()
    assert "store" not in detail
    assert "field" not in detail

    # ── Step 8 — Priya opens Incident 1 (Store A) directly: works normally ──
    resp = requests.get(f"{API_URL}/entity-records/{incident_1}", headers=priya_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["store_id"] == "store-A"

    # ── Step 9 — Priya opens Incident 3 (empty Store ID) directly: blocked ──
    resp = requests.get(f"{API_URL}/entity-records/{incident_3}", headers=priya_headers)
    assert resp.status_code == 403, resp.text

    # ── Step 10 — Karan (Resolver, no condition) lists incidents: sees all ──
    assert _list_incidents(karan_headers) == {incident_1, incident_2, incident_3}

    # ── Step 11 — Karan opens Incident 2 directly: works fine ───────────────
    resp = requests.get(f"{API_URL}/entity-records/{incident_2}", headers=karan_headers)
    assert resp.status_code == 200, resp.text

    # ── Step 12 — Priya edits Incident 2's description despite no read access ─
    resp = requests.put(
        f"{API_URL}/entity-records/{incident_2}",
        headers=priya_headers,
        json={"data": {"description": "Edited by Priya despite no read access"}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["description"] == "Edited by Priya despite no read access"

    # ── Step 13 — Admin changes the condition Store A -> Store B ───────────
    def _set_store_associate_condition(condition_value: str | None) -> None:
        view_permission = {"entity_type": "Incident", "action": "view", "allowed": True}
        if condition_value is not None:
            view_permission |= {
                "entity_field": "store_id",
                "operator": "==",
                "value_source": "LITERAL",
                "condition_value": condition_value,
            }
        resp = requests.put(
            f"{API_URL}/roles/{store_associate_role_id}",
            headers=admin_headers,
            json={
                "entity_permissions": [
                    view_permission,
                    {"entity_type": "Incident", "action": "edit", "allowed": True},
                ]
            },
        )
        assert resp.status_code == 200, resp.text

    _set_store_associate_condition("store-B")
    assert _list_incidents(priya_headers) == {incident_2}

    # ── Step 14 — Admin clears the condition entirely: full access returns ──
    _set_store_associate_condition(None)
    assert _list_incidents(priya_headers) == {incident_1, incident_2, incident_3}

    # ── Step 15 — Priya also gets Resolver (documented API gap — see module
    # docstring). Re-apply a restrictive condition to Store Associate first
    # so replacing her assignment with Resolver is a meaningful check, not a
    # no-op: if she were still limited to Store Associate she'd only see
    # Incident 1 again; holding Resolver instead means she sees everything.
    _set_store_associate_condition("store-A")
    assert _list_incidents(priya_headers) == {incident_1}  # sanity re-check

    resp = requests.put(
        f"{API_URL}/roles/users/{story_users['priya']}/role",
        headers=admin_headers,
        json={"role_id": resolver_role_id},
    )
    assert resp.status_code == 200, resp.text
    assert _list_incidents(priya_headers) == {incident_1, incident_2, incident_3}

    # ── Step 16 — Superadmin bypasses any condition (real is_system role,
    # not the header-trust shortcut — Store Associate's Store-A condition
    # from Step 15 is still active, so there's an actual condition to bypass) ─
    resp = requests.get(f"{API_URL}/roles", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    system_superadmin_role = next(r for r in resp.json() if r["name"] == "superadmin")
    assert system_superadmin_role["is_system"] is True

    resp = requests.put(
        f"{API_URL}/roles/users/{story_users['superadmin']}/role",
        headers=admin_headers,
        json={"role_id": system_superadmin_role["id"]},
    )
    assert resp.status_code == 200, resp.text

    superadmin_headers = _headers(story_users["superadmin"], story_org)  # no role-string shortcut
    assert _list_incidents(superadmin_headers) == {incident_1, incident_2, incident_3}

    resp = requests.get(f"{API_URL}/entity-records/{incident_2}", headers=superadmin_headers)
    assert resp.status_code == 200, resp.text

    # ── Step 17 — Negative save-time checks ─────────────────────────────────
    resp = requests.post(
        f"{API_URL}/roles",
        headers=admin_headers,
        json={
            "name": f"bad-field-{uuid.uuid4().hex[:6]}",
            "display_name": "Bad Field Role",
            "entity_permissions": [
                {
                    "entity_type": "Incident",
                    "action": "view",
                    "allowed": True,
                    "entity_field": "Store_ID_Typo",
                    "operator": "==",
                    "value_source": "LITERAL",
                    "condition_value": "store-A",
                }
            ],
        },
    )
    assert resp.status_code == 400, resp.text
    assert "Store_ID_Typo" in resp.json()["detail"]

    resp = requests.post(
        f"{API_URL}/roles",
        headers=admin_headers,
        json={
            "name": f"bad-operator-{uuid.uuid4().hex[:6]}",
            "display_name": "Bad Operator Role",
            "entity_permissions": [
                {
                    "entity_type": "Incident",
                    "action": "view",
                    "allowed": True,
                    "entity_field": "store_id",
                    "operator": ">",
                    "value_source": "LITERAL",
                    "condition_value": "store-A",
                }
            ],
        },
    )
    assert resp.status_code == 400, resp.text
    assert ">" in resp.json()["detail"]

    resp = requests.post(
        f"{API_URL}/roles",
        headers=admin_headers,
        json={
            "name": f"bad-entity-type-{uuid.uuid4().hex[:6]}",
            "display_name": "Bad Entity Type Role",
            "entity_permissions": [{"entity_type": "GhostType", "action": "view", "allowed": True}],
        },
    )
    assert resp.status_code == 400, resp.text

    # ── Additional coverage (from PR review) ────────────────────────────────

    # Reassign Priya back to the conditioned Store Associate role — Step 15
    # left her on Resolver (unconditioned). Sanity re-check the condition
    # ("store-A") is still active before relying on it below.
    resp = requests.put(
        f"{API_URL}/roles/users/{story_users['priya']}/role",
        headers=admin_headers,
        json={"role_id": store_associate_role_id},
    )
    assert resp.status_code == 200, resp.text
    assert _list_incidents(priya_headers) == {incident_1}

    # Audit event reads must respect the same condition as a direct entity
    # read — `_check_entity_scope` (audit module) previously only checked the
    # coarse entity-type permission, never the record-specific condition, so
    # a record a role can't view directly could still have its audit
    # trail/changed_fields read by id. Same generic denial as a direct read.
    resp = requests.get(f"{API_URL}/audit-events", headers=priya_headers, params={"entity_id": incident_1})
    assert resp.status_code == 200, resp.text

    resp = requests.get(f"{API_URL}/audit-events", headers=priya_headers, params={"entity_id": incident_2})
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"].lower()
    assert "store" not in detail
    assert "field" not in detail

    # A `limit` must not hide a visible record behind non-matching ones — the
    # DB-level limit used to apply before the per-record condition filter, so
    # enough non-matching records sorting first could silently drop a page's
    # only visible record. Pick a condition value only the last-created record
    # matches, so every earlier row is a non-matching "decoy" ahead of it.
    _set_store_associate_condition("store-LATE")
    for i in range(5):
        _create_incident(f"PAGINATION-DECOY-{i}", "store-other")
    late_match_id = _create_incident("PAGINATION-MATCH", "store-LATE")

    resp = requests.get(
        f"{API_URL}/entity-records",
        headers=priya_headers,
        params={"entity_type_name": "Incident", "limit": 2},
    )
    assert resp.status_code == 200, resp.text
    assert late_match_id in {item["entity_id"] for item in resp.json()["items"]}

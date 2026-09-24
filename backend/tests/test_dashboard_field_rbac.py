"""Tests for dashboard field-level RBAC (design_docs/tony_dashboard_field_rbac_fix.md).

Covers:
- `DashboardServiceManager._field_entity_type_map` — field -> owning entity type
  resolution for the SOURCE_CATALOG fallback, the heatmap source, and real
  `ViewDefinition` rows (source_fields + denormalized_fields layered on top of the
  always-checked base map).
- `DashboardServiceManager._resolve_field_visibility` — system bypass, unwired roles
  service (fail closed), is_system role bypass, custom-role sets, DB failure wrapping.
- `DashboardServiceManager._resolve_source_field_policy` — per-entity-type denial/mask
  resolution across a multi-entity-type source.
- `DashboardServiceManager._explicit_query_fields` — field-name extraction.
- `DashboardServiceManager._entity_field_policy_resolver` — the `instances.list` binder.
- `DashboardServiceManager._visible_org_data_field_names` — org-wide catalog filter.
- `preview_query_for_actor` / `list_query_sources_for_actor` / `get_data_for_actor` /
  `list_metrics` / `get_filter_options_for_actor` — end-to-end manager behavior against
  a faked `db_models` layer and a scripted roles manager (per test_standards.md: unit
  tests for manager methods mock the db_models layer).
- `dashboard/db_models.py::preview_projection_query` and `dashboard/metrics.py::_instances_list`
  — integration tests against a real Postgres connection (per test_standards.md:
  integration tests for db_models methods use a real DB, not mocks).
"""

from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import pytest

from dashboard.db_models import DashboardModelService
from dashboard.manager import FALLBACK_FIELD_ENTITY_TYPES, DashboardServiceManager
from dashboard.models.request import (
    DashboardQueryDefinitionRequest,
    DashboardQueryFilter,
    DashboardQuerySelect,
)
from entities.db_models import EntitiesModelService, EntityStateRuntimeModel
from entities.manager import EntitiesServiceManager
from entities.models.request import EntityRecordCreateRequest, EntityTypeCreateRequest
from exceptions import AuthorizationError, ServiceUnavailableError
from projections.db_models import ProjectionRow

ORG_ID = "test-org-1"


def _db_is_reachable() -> bool:
    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql://statemachine:statemachine@modular-db:5432/statemachine"
    )
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        socket.getaddrinfo(host, port)
    except OSError:
        return False
    return True


DB_REACHABLE = pytest.mark.skipif(not _db_is_reachable(), reason="database host is not reachable")


class _AlwaysAllowAuth:
    class _Decision:
        allowed = True
        reason = ""

    def check_access(self, _payload: dict[str, object]):
        return self._Decision()


def _entities_manager(database_service_manager) -> EntitiesServiceManager:
    return EntitiesServiceManager(
        EntitiesModelService(database_service_manager=database_service_manager),
        database_service_manager=database_service_manager,
        config=None,
        auth_service_manager=_AlwaysAllowAuth(),
    )


# ── Fakes shared by the manager-level unit tests ────────────────────────────────


class _FakeView:
    """Minimal stand-in for `projections.db_models.ViewDefinition`."""

    def __init__(
        self,
        name: str,
        source_entity_type: str,
        source_fields: list[dict] | None = None,
        denormalized_fields: list[dict] | None = None,
    ) -> None:
        self.name = name
        self.display_name = None
        self.description = None
        self.source_entity_type = source_entity_type
        self.source_fields = source_fields or []
        self.denormalized_fields = denormalized_fields or []


class _ScriptedRolesManager:
    """Scriptable `RolesServiceProtocol` stub for field-visibility checks.

    `visible_by_type[et] is None` means unrestricted (an is_system role) for that
    entity type; a missing key defaults to `[]` (deny-all, matching
    `get_visible_fields`'s own documented default for zero configured permissions).
    """

    def __init__(
        self,
        visible_by_type: dict[str, list[str] | None] | None = None,
        masked_by_type: dict[str, list[str]] | None = None,
        raise_for_types: set[str] | None = None,
        workflow_access_scope: set[str] | None = None,
    ) -> None:
        self.visible_by_type = visible_by_type or {}
        self.masked_by_type = masked_by_type or {}
        self.raise_for_types = raise_for_types or set()
        # `None` = unrestricted — matches `RolesServiceManager.get_workflow_access_scope`'s
        # own contract, consulted by `DashboardServiceManager._deny_restricted_workflow_actor`
        # (an unrelated, already-merged workflow-access-scope feature) before any of this
        # feature's own field-visibility logic runs.
        self.workflow_access_scope = workflow_access_scope

    def get_visible_fields(self, db, user_id, org_id, entity_type):  # noqa: ANN001
        if entity_type in self.raise_for_types:
            raise RuntimeError("roles DB exploded")
        return self.visible_by_type.get(entity_type, [])

    def get_masked_fields(self, db, user_id, org_id, entity_type):  # noqa: ANN001
        if entity_type in self.raise_for_types:
            raise RuntimeError("roles DB exploded")
        return self.masked_by_type.get(entity_type, [])

    def get_editable_fields(self, db, user_id, org_id, entity_type):  # noqa: ANN001
        return None

    def check_entity_permission(self, db, user_id, org_id, entity_type, action):  # noqa: ANN001
        return True

    def evaluate_entity_access(self, db, user_id, org_id, entity_type, action):  # noqa: ANN001
        raise NotImplementedError("not exercised by this feature")

    def get_workflow_access_scope(self, actor):  # noqa: ANN001
        return self.workflow_access_scope


class _FakeEntityTypeRecord:
    def __init__(self, entity_type_id: str, name: str) -> None:
        self.entity_type_id = entity_type_id
        self.name = name


class _FakeEntitiesServiceManager:
    """`EntitiesServiceManager` stand-in for dashboard's cross-module
    entity-type name resolution (never via a direct `entities.db_models` import)."""

    def __init__(self, entity_types: list[tuple[str, str]] | None = None, raises: bool = False) -> None:
        self._entity_types = entity_types or []
        self._raises = raises

    def list_entity_type_records(self, *, organization_id):  # noqa: ANN001
        if self._raises:
            raise RuntimeError("entities service exploded")
        return [_FakeEntityTypeRecord(eid, name) for eid, name in self._entity_types]


class _FakeDashboardDb:
    """`DashboardModelService` stand-in — records the policy sets it was called
    with (an observable contract, not an internal call count) and returns
    canned/empty payloads."""

    def __init__(
        self,
        *,
        view: _FakeView | None = None,
        data_fields: list[tuple[str, str]] | None = None,
        filter_options_payload: dict | None = None,
        view_definitions: list[_FakeView] | None = None,
    ) -> None:
        self._view = view
        self._data_fields = data_fields or []
        self._filter_options_payload = filter_options_payload or {
            "workflows": [],
            "entity_types": [],
            "states": [],
            "event_types": [],
            "entity_fields": [],
        }
        self._view_definitions = view_definitions if view_definitions is not None else (
            [view] if view else []
        )
        self.last_preview_kwargs: dict | None = None
        self.last_run_query_widget_kwargs: dict | None = None
        self.last_run_metric_kwargs: dict | None = None

    def get_active_view_definition(self, organization_id, view_name):  # noqa: ANN001
        return self._view

    def list_active_view_definitions(self, organization_id):  # noqa: ANN001
        return list(self._view_definitions)

    def resolve_field_visibility(self, roles_manager, organization_id, user_id, entity_type):  # noqa: ANN001
        visible = roles_manager.get_visible_fields(None, user_id, organization_id, entity_type)
        masked = roles_manager.get_masked_fields(None, user_id, organization_id, entity_type)
        return visible, masked

    def entity_data_fields(self, organization_id, entity_type=None):  # noqa: ANN001
        return list(self._data_fields)

    def filter_options(self, organization_id, workflow_id=None):  # noqa: ANN001
        return self._filter_options_payload

    def resolve_workflow_entity_type(self, organization_id, workflow_id):  # noqa: ANN001
        return None

    def preview_projection_query(self, organization_id, view_name, query_def, **kwargs):  # noqa: ANN001
        self.last_preview_kwargs = kwargs
        return {
            "source": f"projection::{view_name}",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "suggested_visuals": [],
        }

    def preview_heatmap_query(self, organization_id, query_def, **kwargs):  # noqa: ANN001
        self.last_preview_kwargs = kwargs
        return {
            "source": "heatmap",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "suggested_visuals": [],
        }

    def run_query_widget(self, organization_id, query_def, filters, **kwargs):  # noqa: ANN001
        self.last_run_query_widget_kwargs = kwargs
        return {"kind": "rows", "columns": [], "rows": []}

    def run_metric(self, organization_id, metric_key, filters=None, **kwargs):  # noqa: ANN001
        self.last_run_metric_kwargs = kwargs
        return {"kind": "rows", "columns": [], "rows": []}


def _manager(
    db: _FakeDashboardDb, roles_manager, entities_service_manager: Any = None
) -> DashboardServiceManager:
    return DashboardServiceManager(
        db,
        database_service_manager=None,
        config=None,
        roles_manager=roles_manager,
        entities_service_manager=entities_service_manager,
    )


CUSTOM_ACTOR = {"user_id": "recruiter-1", "organization_id": ORG_ID, "actor_type": "human"}
SYSTEM_ACTOR = {"user_id": None, "organization_id": ORG_ID, "actor_type": "system"}


# ── Interaction with the (separately merged) workflow-access-scope guard ────────
# `_deny_restricted_workflow_actor` runs before any of this feature's own field
# checks in every one of these methods — confirms the two features compose,
# not that workflow-scope restriction itself is correct (that's owned elsewhere).


def test_preview_query_for_actor_workflow_restricted_actor_denied_before_field_checks() -> None:
    roles = _ScriptedRolesManager(workflow_access_scope={"workflow-1"})
    manager = _manager(_FakeDashboardDb(view=None), roles)
    query_def = DashboardQueryDefinitionRequest(source="application_pipeline")
    with pytest.raises(AuthorizationError):
        manager.preview_query_for_actor(CUSTOM_ACTOR, query_def)


def test_list_metrics_workflow_restricted_actor_denied() -> None:
    roles = _ScriptedRolesManager(workflow_access_scope={"workflow-1"})
    manager = _manager(_FakeDashboardDb(), roles)
    with pytest.raises(AuthorizationError):
        manager.list_metrics(CUSTOM_ACTOR)


# ── _field_entity_type_map ───────────────────────────────────────────────────────


def test_field_entity_type_map_heatmap_source_maps_job_id_to_job() -> None:
    manager = _manager(_FakeDashboardDb(), _ScriptedRolesManager())
    assert manager._field_entity_type_map(ORG_ID, "heatmap") == {"job_id": ("job", "id")}


def test_field_entity_type_map_no_view_returns_fallback_map_only() -> None:
    manager = _manager(_FakeDashboardDb(view=None), _ScriptedRolesManager())
    result = manager._field_entity_type_map(ORG_ID, "application_pipeline")
    assert result == FALLBACK_FIELD_ENTITY_TYPES


def test_field_entity_type_map_real_view_layers_declared_fields_over_fallback() -> None:
    view = _FakeView(
        name="candidate_pipeline",
        source_entity_type="job",
        source_fields=[{"name": "hiring_manager_notes"}],
        denormalized_fields=[{"name": "candidate_location", "relation_type": "candidate_of"}],
    )
    manager = _manager(_FakeDashboardDb(view=view), _ScriptedRolesManager())
    result = manager._field_entity_type_map(ORG_ID, "projection::candidate_pipeline")

    # The always-checked base map is still present (Finding 1 — base_field_map
    # resolves these regardless of the view's own declared fields), checked
    # against the entity's real field-permission name (email/title), not the
    # denormalized alias.
    assert result["candidate_email"] == ("candidate", "email")
    assert result["job_title"] == ("job", "title")
    # Plus the view's own declared fields — real view fields have no alias, so
    # the field-permission name is the field name itself.
    assert result["hiring_manager_notes"] == ("job", "hiring_manager_notes")
    assert result["candidate_location"] == ("job", "candidate_location")


def test_field_entity_type_map_strips_projection_prefix_before_lookup() -> None:
    view = _FakeView(name="candidate_pipeline", source_entity_type="candidate")
    db = _FakeDashboardDb(view=view)
    manager = _manager(db, _ScriptedRolesManager())
    result = manager._field_entity_type_map(ORG_ID, "projection::candidate_pipeline")
    # No declared fields on this view — result is exactly the base fallback map.
    assert result == FALLBACK_FIELD_ENTITY_TYPES


# ── _resolve_field_visibility ────────────────────────────────────────────────────


def test_resolve_field_visibility_system_actor_bypasses_without_calling_roles_manager() -> None:
    manager = _manager(_FakeDashboardDb(), _ScriptedRolesManager(raise_for_types={"candidate"}))
    visible, masked = manager._resolve_field_visibility(SYSTEM_ACTOR, ORG_ID, "candidate")
    assert visible is None
    assert masked == set()


def test_resolve_field_visibility_roles_manager_unwired_raises_service_unavailable() -> None:
    manager = _manager(_FakeDashboardDb(), None)
    with pytest.raises(ServiceUnavailableError):
        manager._resolve_field_visibility(CUSTOM_ACTOR, ORG_ID, "candidate")


def test_resolve_field_visibility_is_system_role_returns_unrestricted() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": None})
    manager = _manager(_FakeDashboardDb(), roles)
    visible, masked = manager._resolve_field_visibility(CUSTOM_ACTOR, ORG_ID, "candidate")
    assert visible is None
    assert masked == set()


def test_resolve_field_visibility_custom_role_returns_configured_sets() -> None:
    roles = _ScriptedRolesManager(
        visible_by_type={"candidate": ["candidate_name"]},
        masked_by_type={"candidate": []},
    )
    manager = _manager(_FakeDashboardDb(), roles)
    visible, masked = manager._resolve_field_visibility(CUSTOM_ACTOR, ORG_ID, "candidate")
    assert visible == {"candidate_name"}
    assert masked == set()


def test_resolve_field_visibility_roles_db_failure_wraps_service_unavailable() -> None:
    roles = _ScriptedRolesManager(raise_for_types={"candidate"})
    manager = _manager(_FakeDashboardDb(), roles)
    with pytest.raises(ServiceUnavailableError):
        manager._resolve_field_visibility(CUSTOM_ACTOR, ORG_ID, "candidate")


# ── _resolve_source_field_policy ─────────────────────────────────────────────────


def test_resolve_source_field_policy_denies_field_not_in_visible_set() -> None:
    # Visible sets use the entity's real field-permission names (id/name/title/
    # department), not the denormalized query aliases (candidate_id/job_title).
    roles = _ScriptedRolesManager(
        visible_by_type={"candidate": ["id", "name"], "job": ["id", "title", "department"]},
    )
    manager = _manager(_FakeDashboardDb(view=None), roles)
    denied, masked = manager._resolve_source_field_policy(CUSTOM_ACTOR, ORG_ID, "application_pipeline")
    assert "candidate_email" in denied
    assert "candidate_id" not in denied
    assert "job_id" not in denied
    assert masked == set()


def test_resolve_source_field_policy_marks_masked_field_visible_but_masked() -> None:
    roles = _ScriptedRolesManager(
        visible_by_type={
            "candidate": [raw for owner, raw in FALLBACK_FIELD_ENTITY_TYPES.values() if owner == "candidate"],
            "job": ["id", "title", "department"],
        },
        masked_by_type={"job": ["title"]},
    )
    manager = _manager(_FakeDashboardDb(view=None), roles)
    denied, masked = manager._resolve_source_field_policy(CUSTOM_ACTOR, ORG_ID, "application_pipeline")
    assert "job_title" in masked
    assert "job_title" not in denied


def test_resolve_source_field_policy_denies_unrecognized_field_by_default() -> None:
    """A field that's neither a fixed column nor in the known ownership map
    (a stale/undeclared projection key) must not pass through unchecked."""
    roles = _ScriptedRolesManager(visible_by_type={"candidate": [], "job": []})
    manager = _manager(_FakeDashboardDb(view=None), roles)
    denied, _ = manager._resolve_source_field_policy(
        CUSTOM_ACTOR, ORG_ID, "application_pipeline", explicit_fields={"totally_unmapped_field"}
    )
    assert "totally_unmapped_field" in denied


def test_resolve_source_field_policy_allows_unrecognized_field_for_system_actor() -> None:
    manager = _manager(_FakeDashboardDb(view=None), _ScriptedRolesManager())
    denied, _ = manager._resolve_source_field_policy(
        SYSTEM_ACTOR, ORG_ID, "application_pipeline", explicit_fields={"totally_unmapped_field"}
    )
    assert denied == set()


def test_resolve_source_field_policy_ignores_unrecognized_field_when_not_requested() -> None:
    """Only fields actually named in the query are checked as "unrecognized" —
    an unmapped key never surfaces just because the source could produce it."""
    roles = _ScriptedRolesManager(visible_by_type={"candidate": [], "job": []})
    manager = _manager(_FakeDashboardDb(view=None), roles)
    denied, _ = manager._resolve_source_field_policy(CUSTOM_ACTOR, ORG_ID, "application_pipeline")
    assert "totally_unmapped_field" not in denied


def test_resolve_source_field_policy_heatmap_denies_job_id_when_job_not_visible() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"job": []})
    manager = _manager(_FakeDashboardDb(), roles)
    denied, masked = manager._resolve_source_field_policy(CUSTOM_ACTOR, ORG_ID, "heatmap")
    assert denied == {"job_id"}
    assert masked == set()


def test_resolve_source_field_policy_heatmap_masks_job_id_when_job_masked() -> None:
    roles = _ScriptedRolesManager(
        visible_by_type={"job": ["id"]}, masked_by_type={"job": ["id"]}
    )
    manager = _manager(_FakeDashboardDb(), roles)
    denied, masked = manager._resolve_source_field_policy(CUSTOM_ACTOR, ORG_ID, "heatmap")
    assert denied == set()
    assert masked == {"job_id"}


# ── _explicit_query_fields ───────────────────────────────────────────────────────


def test_explicit_query_fields_unions_select_group_by_filters_sort_and_aggregations() -> None:
    query_def = DashboardQueryDefinitionRequest(
        source="application_pipeline",
        select=[DashboardQuerySelect(field="candidate_email")],
        group_by=["job_id"],
        filters=[DashboardQueryFilter(field="job_title", op="eq", value="Engineer")],
    )
    fields = DashboardServiceManager._explicit_query_fields(query_def)
    assert fields == {"candidate_email", "job_id", "job_title"}


def test_explicit_query_fields_empty_query_returns_empty_set() -> None:
    query_def = DashboardQueryDefinitionRequest(source="application_pipeline")
    assert DashboardServiceManager._explicit_query_fields(query_def) == set()


# ── _entity_field_policy_resolver ────────────────────────────────────────────────


def test_entity_field_policy_resolver_unknown_entity_type_denies_all() -> None:
    manager = _manager(_FakeDashboardDb(), _ScriptedRolesManager(), _FakeEntitiesServiceManager([]))
    resolve = manager._entity_field_policy_resolver(CUSTOM_ACTOR, ORG_ID)
    visible, masked = resolve("missing-type-id")
    assert visible == []
    assert masked == []


def test_entity_field_policy_resolver_known_type_delegates_to_roles_manager() -> None:
    roles = _ScriptedRolesManager(
        visible_by_type={"candidate": ["candidate_name"]},
        masked_by_type={"candidate": ["candidate_phone"]},
    )
    entities = _FakeEntitiesServiceManager([("type-1", "candidate")])
    manager = _manager(_FakeDashboardDb(), roles, entities)
    resolve = manager._entity_field_policy_resolver(CUSTOM_ACTOR, ORG_ID)
    visible, masked = resolve("type-1")
    assert visible == ["candidate_name"]
    assert masked == ["candidate_phone"]


def test_entity_field_policy_resolver_repeated_calls_return_consistent_results() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": None})
    entities = _FakeEntitiesServiceManager([("type-1", "candidate")])
    manager = _manager(_FakeDashboardDb(), roles, entities)
    resolve = manager._entity_field_policy_resolver(CUSTOM_ACTOR, ORG_ID)
    first = resolve("type-1")
    second = resolve("type-1")
    assert first == second == (None, [])


# ── _visible_org_data_field_names ────────────────────────────────────────────────


def test_visible_org_data_field_names_system_actor_returns_none() -> None:
    manager = _manager(_FakeDashboardDb(), _ScriptedRolesManager())
    assert manager._visible_org_data_field_names(SYSTEM_ACTOR, ORG_ID) is None


def test_visible_org_data_field_names_no_entity_types_returns_empty_set() -> None:
    manager = _manager(_FakeDashboardDb(), _ScriptedRolesManager(), _FakeEntitiesServiceManager([]))
    assert manager._visible_org_data_field_names(CUSTOM_ACTOR, ORG_ID) == set()


def test_visible_org_data_field_names_unrestricted_type_short_circuits_to_none() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["email"], "job": None})
    entities = _FakeEntitiesServiceManager([("id-1", "candidate"), ("id-2", "job")])
    manager = _manager(_FakeDashboardDb(), roles, entities)
    assert manager._visible_org_data_field_names(CUSTOM_ACTOR, ORG_ID) is None


def test_visible_org_data_field_names_unions_visible_fields_across_types() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["email"], "job": ["title"]})
    entities = _FakeEntitiesServiceManager([("id-1", "candidate"), ("id-2", "job")])
    manager = _manager(_FakeDashboardDb(), roles, entities)
    assert manager._visible_org_data_field_names(CUSTOM_ACTOR, ORG_ID) == {"email", "title"}


def test_visible_org_data_field_names_unevaluable_check_raises_service_unavailable() -> None:
    roles = _ScriptedRolesManager(raise_for_types={"candidate"})
    entities = _FakeEntitiesServiceManager([("id-1", "candidate")])
    manager = _manager(_FakeDashboardDb(), roles, entities)
    with pytest.raises(ServiceUnavailableError):
        manager._visible_org_data_field_names(CUSTOM_ACTOR, ORG_ID)


def test_visible_org_data_field_names_entities_service_unwired_raises_service_unavailable() -> None:
    manager = _manager(_FakeDashboardDb(), _ScriptedRolesManager())
    with pytest.raises(ServiceUnavailableError):
        manager._visible_org_data_field_names(CUSTOM_ACTOR, ORG_ID)


# ── preview_query_for_actor ──────────────────────────────────────────────────────


def test_preview_query_for_actor_drops_forbidden_field_keeps_the_rest() -> None:
    """A forbidden field among several selected is dropped, not a whole-preview
    rejection — query-preview degrades the same way a rendered widget does."""
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["name"]})
    db = _FakeDashboardDb(view=None)
    manager = _manager(db, roles)
    query_def = DashboardQueryDefinitionRequest(
        source="application_pipeline",
        select=[DashboardQuerySelect(field="candidate_name"), DashboardQuerySelect(field="candidate_email")],
    )
    manager.preview_query_for_actor(CUSTOM_ACTOR, query_def)  # must not raise
    assert "candidate_email" in db.last_preview_kwargs["denied_fields"]


def test_preview_query_for_actor_passes_masked_fields_down_to_db_layer() -> None:
    roles = _ScriptedRolesManager(
        visible_by_type={"job": ["title"]},
        masked_by_type={"job": ["title"]},
    )
    db = _FakeDashboardDb(view=None)
    manager = _manager(db, roles)
    query_def = DashboardQueryDefinitionRequest(
        source="application_pipeline",
        select=[DashboardQuerySelect(field="job_title")],
    )
    manager.preview_query_for_actor(CUSTOM_ACTOR, query_def)
    assert "job_title" in db.last_preview_kwargs["masked_fields"]
    assert "job_title" not in db.last_preview_kwargs["denied_fields"]


def test_preview_query_for_actor_heatmap_source_redacts_job_id_when_denied() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"job": []})
    db = _FakeDashboardDb()
    manager = _manager(db, roles)
    query_def = DashboardQueryDefinitionRequest(source="heatmap")
    manager.preview_query_for_actor(CUSTOM_ACTOR, query_def)  # must not raise
    assert "job_id" in db.last_preview_kwargs["denied_fields"]


def test_preview_query_for_actor_heatmap_source_allows_when_job_id_visible() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"job": ["id"]})
    db = _FakeDashboardDb()
    manager = _manager(db, roles)
    query_def = DashboardQueryDefinitionRequest(source="heatmap")
    manager.preview_query_for_actor(CUSTOM_ACTOR, query_def)
    assert db.last_preview_kwargs["denied_fields"] == set()


def test_preview_query_for_actor_service_unavailable_propagates_uncaught() -> None:
    roles = _ScriptedRolesManager(raise_for_types={"candidate"})
    manager = _manager(_FakeDashboardDb(view=None), roles)
    query_def = DashboardQueryDefinitionRequest(
        source="application_pipeline",
        select=[DashboardQuerySelect(field="candidate_email")],
    )
    with pytest.raises(ServiceUnavailableError):
        manager.preview_query_for_actor(CUSTOM_ACTOR, query_def)


def test_preview_query_for_actor_system_actor_never_denied() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": []})  # would deny a human
    db = _FakeDashboardDb(view=None)
    manager = _manager(db, roles)
    query_def = DashboardQueryDefinitionRequest(
        source="application_pipeline",
        select=[DashboardQuerySelect(field="candidate_email")],
    )
    manager.preview_query_for_actor(SYSTEM_ACTOR, query_def)  # must not raise
    assert db.last_preview_kwargs["denied_fields"] == set()


def test_preview_query_for_actor_drops_unrecognized_field_by_default() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": [], "job": []})
    db = _FakeDashboardDb(view=None)
    manager = _manager(db, roles)
    query_def = DashboardQueryDefinitionRequest(
        source="application_pipeline",
        select=[DashboardQuerySelect(field="some_stale_projection_key")],
    )
    manager.preview_query_for_actor(CUSTOM_ACTOR, query_def)  # must not raise
    assert "some_stale_projection_key" in db.last_preview_kwargs["denied_fields"]


# ── list_query_sources_for_actor ─────────────────────────────────────────────────


def test_list_query_sources_for_actor_removes_invisible_fields_from_catalog() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["name"], "job": None})
    db = _FakeDashboardDb(view=None, view_definitions=[])
    manager = _manager(db, roles)
    response = manager.list_query_sources_for_actor(CUSTOM_ACTOR)
    pipeline = next(s for s in response.sources if s.id == "application_pipeline")
    keys = {f.key for f in pipeline.fields}
    assert "candidate_email" not in keys
    assert "candidate_name" in keys
    assert "job_title" in keys  # unrestricted (is_system) role for "job"


# ── get_data_for_actor ───────────────────────────────────────────────────────────


def test_get_data_for_actor_forbidden_explicit_query_field_is_dropped_not_rejected() -> None:
    """A dashboard widget replays a saved config — a field this viewer can't see
    is silently dropped from that widget, not an error that blanks the page."""
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["name"]})
    db = _FakeDashboardDb(view=None)
    manager = _manager(db, roles)
    item = SimpleNamespace(
        widget_id="w1",
        metric=None,
        query=DashboardQueryDefinitionRequest(
            source="application_pipeline",
            select=[DashboardQuerySelect(field="candidate_email")],
        ),
        filters={},
    )
    response = manager.get_data_for_actor(CUSTOM_ACTOR, [item])
    assert response.results["w1"] == {"kind": "rows", "columns": [], "rows": []}
    assert "candidate_email" in db.last_run_query_widget_kwargs["denied_fields"]


def test_get_data_for_actor_service_unavailable_fails_whole_batch_not_per_widget() -> None:
    roles = _ScriptedRolesManager(raise_for_types={"candidate"})
    manager = _manager(_FakeDashboardDb(view=None), roles)
    item = SimpleNamespace(
        widget_id="w1",
        metric=None,
        query=DashboardQueryDefinitionRequest(
            source="application_pipeline",
            select=[DashboardQuerySelect(field="candidate_email")],
        ),
        filters={},
    )
    with pytest.raises(ServiceUnavailableError):
        manager.get_data_for_actor(CUSTOM_ACTOR, [item])


def test_get_data_for_actor_instances_list_metric_wires_field_policy_resolver() -> None:
    db = _FakeDashboardDb()
    manager = _manager(db, _ScriptedRolesManager())
    item = SimpleNamespace(widget_id="w1", metric="instances.list", query=None, filters={})
    response = manager.get_data_for_actor(CUSTOM_ACTOR, [item])
    assert response.results["w1"] == {"kind": "rows", "columns": [], "rows": []}
    assert "field_policy_resolver" in db.last_run_metric_kwargs


def test_get_data_for_actor_entities_by_field_returns_error_when_field_not_visible_anywhere() -> None:
    """A single-field grouping metric has no partial result to fall back to —
    an invisible field is an explicit per-widget error, isolated to that widget
    (the batch itself still succeeds)."""
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["name"]})
    entities = _FakeEntitiesServiceManager([("id-1", "candidate")])
    db = _FakeDashboardDb()
    manager = _manager(db, roles, entities)
    item = SimpleNamespace(widget_id="w1", metric="entities.by_field", query=None, filters={"field": "data.salary"})
    response = manager.get_data_for_actor(CUSTOM_ACTOR, [item])
    assert response.results["w1"]["kind"] == "error"
    assert "salary" in response.results["w1"]["error"]


def test_get_data_for_actor_entities_by_field_returns_error_when_masked() -> None:
    roles = _ScriptedRolesManager(
        visible_by_type={"candidate": ["salary"]}, masked_by_type={"candidate": ["salary"]}
    )
    entities = _FakeEntitiesServiceManager([("id-1", "candidate")])
    manager = _manager(_FakeDashboardDb(), roles, entities)
    item = SimpleNamespace(widget_id="w1", metric="entities.by_field", query=None, filters={"field": "data.salary"})
    response = manager.get_data_for_actor(CUSTOM_ACTOR, [item])
    assert response.results["w1"]["kind"] == "error"


def test_get_data_for_actor_entities_by_field_allows_visible_unmasked_field() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["name"]})
    entities = _FakeEntitiesServiceManager([("id-1", "candidate")])
    db = _FakeDashboardDb()
    manager = _manager(db, roles, entities)
    item = SimpleNamespace(widget_id="w1", metric="entities.by_field", query=None, filters={"field": "data.name"})
    response = manager.get_data_for_actor(CUSTOM_ACTOR, [item])
    assert response.results["w1"]["kind"] == "rows"


def test_get_data_for_actor_entities_by_field_system_actor_never_denied() -> None:
    db = _FakeDashboardDb()
    manager = _manager(db, _ScriptedRolesManager())
    item = SimpleNamespace(widget_id="w1", metric="entities.by_field", query=None, filters={"field": "data.salary"})
    response = manager.get_data_for_actor(SYSTEM_ACTOR, [item])
    assert response.results["w1"]["kind"] == "rows"


def test_get_data_for_actor_unrelated_widget_failure_still_isolated_per_widget() -> None:
    db = _FakeDashboardDb()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("widget exploded")

    db.run_metric = _boom  # type: ignore[method-assign]
    manager = _manager(db, _ScriptedRolesManager())
    item = SimpleNamespace(widget_id="w1", metric="entities.count", query=None, filters={})
    response = manager.get_data_for_actor(CUSTOM_ACTOR, [item])
    assert response.results["w1"]["kind"] == "error"


# ── list_metrics ─────────────────────────────────────────────────────────────────


def _data_field_keys(metric) -> set[str]:
    """The dynamic `data.*` portion of a metric's fields — excludes the metric's own
    static column catalog (e.g. `instances.list`'s entity_id/current_state/etc.)."""
    return {f.key for f in metric.fields if f.key.startswith("data.")}


def test_list_metrics_skips_rbac_evaluation_when_no_data_fields_discovered() -> None:
    roles = _ScriptedRolesManager(raise_for_types={"candidate"})  # would raise if ever consulted
    db = _FakeDashboardDb(data_fields=[])
    manager = _manager(db, roles)
    response = manager.list_metrics(CUSTOM_ACTOR)
    instances_metric = next(m for m in response.metrics if m.key == "instances.list")
    assert _data_field_keys(instances_metric) == set()


def test_list_metrics_filters_invisible_data_fields_from_instances_list() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["email"]})
    db = _FakeDashboardDb(data_fields=[("data.email", "Email"), ("data.salary", "Salary")])
    entities = _FakeEntitiesServiceManager([("id-1", "candidate")])
    manager = _manager(db, roles, entities)
    response = manager.list_metrics(CUSTOM_ACTOR)
    instances_metric = next(m for m in response.metrics if m.key == "instances.list")
    assert _data_field_keys(instances_metric) == {"data.email"}


def test_list_metrics_system_actor_keeps_every_data_field() -> None:
    db = _FakeDashboardDb(data_fields=[("data.salary", "Salary")])
    manager = _manager(db, _ScriptedRolesManager())
    response = manager.list_metrics(SYSTEM_ACTOR)
    instances_metric = next(m for m in response.metrics if m.key == "instances.list")
    assert _data_field_keys(instances_metric) == {"data.salary"}


# ── get_filter_options_for_actor ─────────────────────────────────────────────────


def test_get_filter_options_for_actor_filters_entity_fields_to_visible_names() -> None:
    roles = _ScriptedRolesManager(visible_by_type={"candidate": ["email"]})
    db = _FakeDashboardDb(
        filter_options_payload={
            "workflows": [],
            "entity_types": [],
            "states": [],
            "event_types": [],
            "entity_fields": [
                {"value": "data.email", "label": "Email"},
                {"value": "data.salary", "label": "Salary"},
            ],
        },
    )
    entities = _FakeEntitiesServiceManager([("id-1", "candidate")])
    manager = _manager(db, roles, entities)
    response = manager.get_filter_options_for_actor(CUSTOM_ACTOR)
    values = {o.value for o in response.entity_fields}
    assert values == {"data.email"}


def test_get_filter_options_for_actor_service_unavailable_propagates_uncaught() -> None:
    roles = _ScriptedRolesManager(raise_for_types={"candidate"})
    entities = _FakeEntitiesServiceManager([("id-1", "candidate")])
    manager = _manager(_FakeDashboardDb(), roles, entities)
    with pytest.raises(ServiceUnavailableError):
        manager.get_filter_options_for_actor(CUSTOM_ACTOR)


# ── Integration: dashboard/db_models.py::preview_projection_query ───────────────


@DB_REACHABLE
def test_preview_projection_query_denied_field_dropped_from_select(
    entities_db_service_manager,
) -> None:
    view_name = f"rbac-view-{uuid.uuid4().hex[:8]}"
    dashboard_db = DashboardModelService(entities_db_service_manager)
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        session.add(
            ProjectionRow(
                view_name=view_name,
                entity_id=str(uuid.uuid4()),
                organization_id=ORG_ID,
                entity_type="application",
                current_state="APPLIED",
                data={"candidate_email": "secret@example.com"},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        query_def = DashboardQueryDefinitionRequest(
            source=view_name,
            select=[DashboardQuerySelect(field="candidate_email")],
        )
        payload = dashboard_db.preview_projection_query(
            ORG_ID, view_name, query_def, denied_fields={"candidate_email"}
        )
        # Only forbidden field was selected — falls back to the entity_id-only
        # default, same as "nothing selected" (see the `not selected_exprs` branch).
        assert "candidate_email" not in payload["rows"][0]
    finally:
        session.query(ProjectionRow).filter_by(view_name=view_name).delete()
        session.commit()
        session.close()


@DB_REACHABLE
def test_preview_projection_query_masked_field_redacts_value_not_removes_column(
    entities_db_service_manager,
) -> None:
    view_name = f"rbac-view-{uuid.uuid4().hex[:8]}"
    dashboard_db = DashboardModelService(entities_db_service_manager)
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        session.add(
            ProjectionRow(
                view_name=view_name,
                entity_id=str(uuid.uuid4()),
                organization_id=ORG_ID,
                entity_type="application",
                current_state="APPLIED",
                data={"candidate_email": "secret@example.com"},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        query_def = DashboardQueryDefinitionRequest(
            source=view_name,
            select=[DashboardQuerySelect(field="candidate_email")],
        )
        payload = dashboard_db.preview_projection_query(
            ORG_ID, view_name, query_def, masked_fields={"candidate_email"}
        )
        assert payload["rows"][0]["candidate_email"] == "***"
    finally:
        session.query(ProjectionRow).filter_by(view_name=view_name).delete()
        session.commit()
        session.close()


@DB_REACHABLE
def test_preview_projection_query_no_policy_behaves_exactly_as_before(
    entities_db_service_manager,
) -> None:
    view_name = f"rbac-view-{uuid.uuid4().hex[:8]}"
    dashboard_db = DashboardModelService(entities_db_service_manager)
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        session.add(
            ProjectionRow(
                view_name=view_name,
                entity_id=str(uuid.uuid4()),
                organization_id=ORG_ID,
                entity_type="application",
                current_state="APPLIED",
                data={"candidate_email": "secret@example.com"},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        query_def = DashboardQueryDefinitionRequest(
            source=view_name,
            select=[DashboardQuerySelect(field="candidate_email")],
        )
        payload = dashboard_db.preview_projection_query(ORG_ID, view_name, query_def)
        assert payload["rows"][0]["candidate_email"] == "secret@example.com"
    finally:
        session.query(ProjectionRow).filter_by(view_name=view_name).delete()
        session.commit()
        session.close()


@DB_REACHABLE
def test_preview_projection_query_drops_only_the_denied_field_keeps_the_rest(
    entities_db_service_manager,
) -> None:
    """One denied field among several selected is dropped — the rest of the
    query still returns normally, whether it's a live preview or a widget."""
    view_name = f"rbac-view-{uuid.uuid4().hex[:8]}"
    dashboard_db = DashboardModelService(entities_db_service_manager)
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        session.add(
            ProjectionRow(
                view_name=view_name,
                entity_id=str(uuid.uuid4()),
                organization_id=ORG_ID,
                entity_type="application",
                current_state="APPLIED",
                data={"candidate_email": "secret@example.com", "candidate_name": "Ada"},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        query_def = DashboardQueryDefinitionRequest(
            source=view_name,
            select=[
                DashboardQuerySelect(field="candidate_name"),
                DashboardQuerySelect(field="candidate_email"),
            ],
        )
        payload = dashboard_db.preview_projection_query(
            ORG_ID, view_name, query_def, denied_fields={"candidate_email"}
        )
        assert payload["rows"][0]["candidate_name"] == "Ada"
        assert "candidate_email" not in payload["rows"][0]
    finally:
        session.query(ProjectionRow).filter_by(view_name=view_name).delete()
        session.commit()
        session.close()


# ── Integration: dashboard/metrics.py::_instances_list ──────────────────────────


def _enroll_state_row(session, *, entity_id: str, organization_id: str) -> None:
    session.add(
        EntityStateRuntimeModel(
            state_id=str(uuid.uuid4()),
            organization_id=organization_id,
            entity_id=entity_id,
            workflow_id=str(uuid.uuid4()),
            current_state="APPLIED",
            state_version=0,
        )
    )
    session.commit()


@DB_REACHABLE
def test_instances_list_explicit_forbidden_data_field_is_dropped_not_rejected(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    """A saved widget's explicit `fields` list may include a field this viewer
    can't see — dropped silently, the rest of the widget still renders."""
    from dashboard.metrics import _instances_list

    entities = _entities_manager(entities_db_service_manager)
    entity_type = entities.create_entity_type(
        EntityTypeCreateRequest(organization_id=ORG_ID, name="rbac_candidate")
    )
    record = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=ORG_ID,
            entity_type_id=entity_type.entity_type_id,
            data={"email": "secret@example.com"},
        )
    )
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        _enroll_state_row(session, entity_id=record.entity_id, organization_id=ORG_ID)

        def resolver(entity_type_id):
            return (["name"], [])  # "email" not visible

        result = _instances_list(
            session,
            ORG_ID,
            {"fields": ["current_state", "data.email"]},
            field_policy_resolver=resolver,
        )
        row = next(r for r in result["rows"] if r["entity_id"] == record.entity_id)
        assert "data.email" not in row
    finally:
        session.close()


@DB_REACHABLE
def test_instances_list_no_selection_silently_narrows_and_masks(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    from dashboard.metrics import _instances_list

    entities = _entities_manager(entities_db_service_manager)
    entity_type = entities.create_entity_type(
        EntityTypeCreateRequest(organization_id=ORG_ID, name="rbac_candidate")
    )
    record = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=ORG_ID,
            entity_type_id=entity_type.entity_type_id,
            data={"name": "Ada", "email": "secret@example.com", "phone": "555-1234"},
        )
    )
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        _enroll_state_row(session, entity_id=record.entity_id, organization_id=ORG_ID)

        def resolver(entity_type_id):
            return (["name", "phone"], ["phone"])  # email hidden entirely; phone masked

        result = _instances_list(session, ORG_ID, {}, field_policy_resolver=resolver)
        row = next(r for r in result["rows"] if r["entity_id"] == record.entity_id)
        assert "data.email" not in row
        assert row["data.name"] == "Ada"
        assert row["data.phone"] == "***"
    finally:
        session.close()


@DB_REACHABLE
def test_instances_list_without_resolver_preserves_legacy_unrestricted_behavior(
    entities_db_service_manager,
    clean_entities_tables,
) -> None:
    from dashboard.metrics import _instances_list

    entities = _entities_manager(entities_db_service_manager)
    entity_type = entities.create_entity_type(
        EntityTypeCreateRequest(organization_id=ORG_ID, name="rbac_candidate")
    )
    record = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id=ORG_ID,
            entity_type_id=entity_type.entity_type_id,
            data={"email": "secret@example.com"},
        )
    )
    session = entities_db_service_manager.postgres_db_service().get_db_session()
    try:
        _enroll_state_row(session, entity_id=record.entity_id, organization_id=ORG_ID)

        result = _instances_list(
            session, ORG_ID, {"fields": ["current_state", "data.email"]}, field_policy_resolver=None
        )
        row = next(r for r in result["rows"] if r["entity_id"] == record.entity_id)
        assert row["data.email"] == "secret@example.com"
    finally:
        session.close()

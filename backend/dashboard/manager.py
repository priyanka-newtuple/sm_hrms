"""Business logic manager for dashboard definitions and query previews."""

from __future__ import annotations

from typing import Any, Callable

from audit.db_models import AuditEventsModelService
from audit.manager import AuditServiceManager
from common.enums import ModuleStatus
from common.logger import logger
from dashboard.db_models import DashboardModelService
from dashboard.global_filters import GLOBAL_ENTITY_IDS_FILTER, global_entity_ids
from dashboard.metrics import ACTIVITY_FIELDS, METRIC_REGISTRY, _filter_int, _range_since, _range_until
from dashboard.models.interface import (
    FALLBACK_FIELD_ENTITY_TYPES,
    HEATMAP_FIXED_COLUMNS,
    PROJECTION_FIXED_COLUMNS,
    SOURCE_CATALOG,
    WIDGET_RESULT_KIND_ERROR,
    QueryFieldSpec,
)
from dashboard.models.request import DashboardQueryDefinitionRequest
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from dashboard.models.response import (
    DashboardDataResponse,
    DashboardFilterOption,
    DashboardFilterOptionsResponse,
    DashboardMetricFieldRead,
    DashboardMetricParamRead,
    DashboardMetricRead,
    DashboardMetricsResponse,
    DashboardQueryFieldRead,
    DashboardQueryPreviewResponse,
    DashboardQuerySourceRead,
    DashboardQuerySourcesResponse,
    DashboardRead,
    DashboardStatusResponse,
)
from exceptions import AuthorizationError, ServiceError, ServiceUnavailableError
from projections.db_models import ViewDefinition

# Not a real entity type — used only to ask "is this actor globally
# unrestricted" via `get_visible_fields`'s is_system bypass, which is checked
# before any entity-type-specific lookup and so doesn't depend on this value.
_UNRECOGNIZED_ENTITY_TYPE = "__unrecognized__"


def _field_to_read(spec: QueryFieldSpec) -> DashboardQueryFieldRead:
    return DashboardQueryFieldRead(
        key=spec.key,
        label=spec.label,
        type=spec.field_type,  # type: ignore[arg-type]
        groupable=spec.groupable,
        filterable=spec.filterable,
        aggregatable=spec.aggregatable,
    )


class DashboardQueryService:
    """Provides dashboard query metadata and safe preview execution."""

    def list_sources(self, view_definitions: list[ViewDefinition]) -> DashboardQuerySourcesResponse:
        sources: list[DashboardQuerySourceRead] = [
            self._projection_view_to_source(view) for view in view_definitions
        ]
        if not sources:
            # Fallback for orgs that still rely on legacy dashboard sources.
            sources = [
                DashboardQuerySourceRead(
                    id=source.id,
                    label=source.label,
                    description=source.description,
                    fields=[_field_to_read(field) for field in source.fields],
                    joins=[],
                )
                for source in SOURCE_CATALOG.values()
            ]
        return DashboardQuerySourcesResponse(sources=sources)

    def _projection_view_to_source(self, view: ViewDefinition) -> DashboardQuerySourceRead:
        fields: list[DashboardQueryFieldRead] = [
            DashboardQueryFieldRead(key="entity_id", label="Entity ID", type="string"),
            DashboardQueryFieldRead(key="current_state", label="Current State", type="string"),
            DashboardQueryFieldRead(key="sla_risk", label="SLA Risk", type="string"),
            DashboardQueryFieldRead(key="machine_name", label="Machine Name", type="string"),
            DashboardQueryFieldRead(key="machine_version", label="Machine Version", type="number", aggregatable=True),
            DashboardQueryFieldRead(key="state_entered_at", label="State Entered At", type="date"),
            DashboardQueryFieldRead(key="sla_due_at", label="SLA Due At", type="date"),
            DashboardQueryFieldRead(key="created_at", label="Created At", type="date"),
            DashboardQueryFieldRead(key="updated_at", label="Updated At", type="date"),
        ]

        for field_cfg in (view.source_fields or []):
            field_name = str(field_cfg.get("name", "")).strip()
            if field_name:
                fields.append(DashboardQueryFieldRead(key=field_name, label=field_name.replace("_", " ").title(), type="string"))
        for field_cfg in (view.denormalized_fields or []):
            field_name = str(field_cfg.get("name", "")).strip()
            if field_name:
                fields.append(DashboardQueryFieldRead(key=field_name, label=field_name.replace("_", " ").title(), type="string"))

        dedup: dict[str, DashboardQueryFieldRead] = {}
        for field in fields:
            dedup[field.key] = field
        return DashboardQuerySourceRead(
            id=f"projection::{view.name}",
            label=view.display_name or view.name.replace("_", " ").title(),
            description=view.description,
            fields=list(dedup.values()),
            joins=[],
        )


class DashboardServiceManager:
    """Orchestrates dashboard config persistence and query preview behavior."""

    def __init__(
        self,
        dashboard_db_model_service: DashboardModelService,
        database_service_manager: Any = None,
        config: Any = None,
        roles_manager: Any = None,
        entities_service_manager: Any = None,
    ) -> None:
        self.db = dashboard_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.roles_manager = roles_manager
        # Bound post-init in main.py, same pattern as filehandler_service_manager's.
        self.entities_service_manager = entities_service_manager
        self.module_name = "dashboard"
        self._started = False
        self.query_service = DashboardQueryService()

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> DashboardStatusResponse:
        return DashboardStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def _deny_restricted_workflow_actor(self, actor: dict[str, object]) -> None:
        """Phase-1 safety: prevent dashboard aggregates from leaking hidden workflows."""
        if self.roles_manager is not None and self.roles_manager.get_workflow_access_scope(actor):
            raise AuthorizationError(
                "Dashboards are unavailable for workflow-restricted roles"
            )

    @staticmethod
    def _to_read(record: Any) -> DashboardRead:
        return DashboardRead(
            id=record.id,
            key=record.key,
            display_name=record.display_name,
            description=record.description,
            config=record.config or {},
            is_default=bool(record.is_default),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def get_dashboard_for_actor(self, actor: dict[str, object], key: str) -> DashboardRead:
        self._deny_restricted_workflow_actor(actor)
        try:
            organization_id = str(actor.get("organization_id", ""))
            record = self.db.ensure_dashboard(organization_id, key)
            return self._to_read(record)
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Failed to load dashboard: {exc}") from exc

    def update_dashboard_for_actor(
        self,
        actor: dict[str, object],
        key: str,
        config: dict[str, Any],
        display_name: str | None = None,
        description: str | None = None,
    ) -> DashboardRead:
        self._deny_restricted_workflow_actor(actor)
        try:
            organization_id = str(actor.get("organization_id", ""))
            record = self.db.update_dashboard(
                organization_id,
                key,
                config=config,
                display_name=display_name,
                description=description,
            )
            return self._to_read(record)
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Failed to update dashboard: {exc}") from exc

    def list_metrics(
        self, actor: dict[str, object], workflow_id: str | None = None
    ) -> DashboardMetricsResponse:
        self._deny_restricted_workflow_actor(actor)
        organization_id = str(actor.get("organization_id", ""))
        # Entity-data columns are per-org (driven by entity type schemas) by
        # default, appended at request time onto the entity-instances metric.
        # When the caller has picked one specific workflow (not "All"), scope
        # to that workflow's own entity type instead of every type in the org.
        entity_type: str | None = None
        if workflow_id:
            try:
                entity_type = self.db.resolve_workflow_entity_type(organization_id, workflow_id)
            except Exception as exc:
                logger.warning(
                    "Failed to resolve workflow entity type, falling back to org-wide fields: %s",
                    exc,
                    extra={"organization_id": organization_id, "workflow_id": workflow_id},
                )
                entity_type = None
            if entity_type is None:
                logger.warning(
                    "No entity type bound to workflow; listing org-wide data fields instead",
                    extra={"organization_id": organization_id, "workflow_id": workflow_id},
                )
        fields_scoped = not workflow_id or entity_type is not None

        data_fields: list[tuple[str, str]] = []
        try:
            data_fields = self.db.entity_data_fields(organization_id, entity_type=entity_type)
        except Exception as exc:  # noqa: BLE001 — data columns are best-effort
            logger.warning(
                "Failed to load entity data fields, continuing without them: %s",
                exc,
                extra={"organization_id": organization_id},
            )
            data_fields = []

        # A field name never appears in a catalog unless the actor's role can see it
        # (INV-3) — checked as a real permission evaluation, not a best-effort one:
        # a failure here must fail the whole request closed, never silently list
        # nothing (which would look identical to "you have zero permissions").
        if data_fields:
            visible_names = self._visible_org_data_field_names(actor, organization_id)
            if visible_names is not None:
                data_fields = [
                    (key, label) for key, label in data_fields if key[len("data."):] in visible_names
                ]

        metrics = [
            DashboardMetricRead(
                key=spec.key,
                label=spec.label,
                description=spec.description,
                output=spec.output,  # type: ignore[arg-type]
                default_visuals=list(spec.default_visuals),
                params=[
                    DashboardMetricParamRead(
                        key=p.key,
                        label=p.label,
                        type=p.type,  # type: ignore[arg-type]
                        source=p.source,  # type: ignore[arg-type]
                    )
                    for p in spec.params
                ],
                fields=[
                    DashboardMetricFieldRead(key=key, label=label)
                    for key, label in spec.fields
                ]
                + (
                    [
                        DashboardMetricFieldRead(key=key, label=label)
                        for key, label in data_fields
                    ]
                    if spec.key == "instances.list"
                    else []
                ),
            )
            for spec in METRIC_REGISTRY
        ]
        return DashboardMetricsResponse(metrics=metrics, fields_scoped=fields_scoped)

    def get_filter_options_for_actor(
        self, actor: dict[str, object], workflow_id: str | None = None
    ) -> DashboardFilterOptionsResponse:
        self._deny_restricted_workflow_actor(actor)
        try:
            organization_id = str(actor.get("organization_id", ""))
            options = self.db.filter_options(organization_id, workflow_id=workflow_id)
            entity_fields = options["entity_fields"]
            visible_names = self._visible_org_data_field_names(actor, organization_id)
            if visible_names is not None:
                entity_fields = [
                    o for o in entity_fields if o["value"][len("data."):] in visible_names
                ]
            return DashboardFilterOptionsResponse(
                workflows=[DashboardFilterOption(**o) for o in options["workflows"]],
                entity_types=[DashboardFilterOption(**o) for o in options["entity_types"]],
                states=[DashboardFilterOption(**o) for o in options["states"]],
                event_types=[DashboardFilterOption(**o) for o in options["event_types"]],
                entity_fields=[DashboardFilterOption(**o) for o in entity_fields],
            )
        except (AuthorizationError, ServiceUnavailableError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Failed to load dashboard filter options: {exc}") from exc

    def get_data_for_actor(
        self,
        actor: dict[str, object],
        items: list[Any],
        anchor_entity_id: str | None = None,
    ) -> DashboardDataResponse:
        self._deny_restricted_workflow_actor(actor)
        organization_id = str(actor.get("organization_id", ""))
        allowed_entity_ids = self._global_filter_entity_ids(
            actor=actor,
            organization_id=organization_id,
            anchor_entity_id=anchor_entity_id,
        )
        results: dict[str, Any] = {}
        for item in items:
            try:
                filters = dict(item.filters or {})
                if allowed_entity_ids is not None:
                    filters[GLOBAL_ENTITY_IDS_FILTER] = sorted(allowed_entity_ids)
                if getattr(item, "query", None) is not None:
                    denied_fields, masked_fields = self._resolve_source_field_policy(
                        actor, organization_id, item.query.source, self._explicit_query_fields(item.query)
                    )
                    # A dashboard widget replays a config someone else may have
                    # saved with broader access than the current viewer — an
                    # inaccessible field is silently dropped/redacted (never
                    # rendered), not an error that blanks the whole dashboard.
                    results[item.widget_id] = self.db.run_query_widget(
                        organization_id,
                        item.query,
                        filters,
                        denied_fields=denied_fields,
                        masked_fields=masked_fields,
                    )
                elif item.metric == "events.activity":
                    # Activity list goes through the audit module's public service
                    # (not a direct model query), respecting its module boundary.
                    results[item.widget_id] = self._run_activity(actor, filters)
                elif item.metric == "instances.list":
                    resolver = self._entity_field_policy_resolver(actor, organization_id)
                    results[item.widget_id] = self.db.run_metric(
                        organization_id, item.metric, filters, field_policy_resolver=resolver
                    )
                elif item.metric == "entities.by_field":
                    # Unlike instances.list/query widgets, this metric has exactly
                    # one field and nothing else to fall back to — a forbidden
                    # field means an explicit error for this widget, not a silent
                    # empty chart or a batch-wide failure.
                    raw_field = str(filters.get("field") or "")
                    field_name = raw_field[5:] if raw_field.startswith("data.") else raw_field
                    if field_name:
                        try:
                            self._validate_data_field_grouping(actor, organization_id, field_name)
                        except AuthorizationError as exc:
                            logger.warning(
                                "entities.by_field denied for widget %s: %s",
                                item.widget_id,
                                exc,
                                extra={"organization_id": organization_id, "widget_id": item.widget_id},
                            )
                            results[item.widget_id] = {"kind": WIDGET_RESULT_KIND_ERROR, "error": str(exc)}
                            continue
                    results[item.widget_id] = self.db.run_metric(
                        organization_id, item.metric, filters
                    )
                else:
                    results[item.widget_id] = self.db.run_metric(
                        organization_id, item.metric, filters
                    )
            except ServiceUnavailableError:
                # The permission check itself couldn't be evaluated — fails the
                # whole request closed (INV-6), never a silently-degraded response.
                raise
            except AuthorizationError:
                # Defensive only at this point — every known field-visibility path
                # above already degrades instead of raising. Fails the batch closed
                # rather than risk showing data under an unexpected auth failure.
                raise
            except KeyError as exc:
                logger.warning(
                    "Widget %s failed with a missing key: %s",
                    item.widget_id,
                    exc,
                    extra={"organization_id": organization_id, "widget_id": item.widget_id},
                )
                results[item.widget_id] = {"kind": WIDGET_RESULT_KIND_ERROR, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Widget %s failed unexpectedly: %s",
                    item.widget_id,
                    exc,
                    extra={"organization_id": organization_id, "widget_id": item.widget_id},
                )
                results[item.widget_id] = {"kind": WIDGET_RESULT_KIND_ERROR, "error": f"widget failed: {exc}"}
        return DashboardDataResponse(results=results)

    def _global_filter_entity_ids(
        self,
        *,
        actor: dict[str, object],
        organization_id: str,
        anchor_entity_id: str | None,
    ) -> set[str] | None:
        if not anchor_entity_id:
            return None
        entities = EntitiesServiceManager(
            EntitiesModelService(self.database_service_manager),
            self.database_service_manager,
            self.config,
            roles_manager=self.roles_manager,
        )
        return entities.global_filter_entity_ids(
            actor=actor,
            organization_id=organization_id,
            anchor_entity_id=anchor_entity_id,
        )

    def _field_entity_type_map(self, organization_id: str, source: str) -> dict[str, tuple[str, str]]:
        """Field key -> (owning entity type name, real field-permission name), for
        every field this source can produce. Fixed workflow-runtime columns
        (entity_id, current_state, sla_risk, timestamps, heatmap aggregates, etc.)
        are intentionally absent — they carry no org-configurable field permission
        and are always visible.

        A real view's own `source_fields`/`denormalized_fields` name their field
        directly (no alias) — the field-permission name is the same string as the
        query field key there, unlike the hardcoded fallback map's prefixed aliases.
        """
        if source == "heatmap":
            return {"job_id": ("job", "id")}
        view_name = source.split("::", 1)[1] if source.startswith("projection::") else source
        # `preview_projection_query`'s base_field_map resolves these unconditionally
        # for every view (see FALLBACK_FIELD_ENTITY_TYPES's own comment) — always
        # included, then layered with the view's own declared fields, if any.
        field_map: dict[str, tuple[str, str]] = dict(FALLBACK_FIELD_ENTITY_TYPES)
        view = self.db.get_active_view_definition(organization_id, view_name)
        if view is None:
            return field_map
        for field_cfg in view.source_fields or []:
            name = str(field_cfg.get("name", "")).strip()
            if name:
                field_map[name] = (view.source_entity_type, name)
        for field_cfg in view.denormalized_fields or []:
            name = str(field_cfg.get("name", "")).strip()
            if name:
                # Denormalized fields join in another entity's data via a runtime
                # relation edge (`relation_type`), which has no static, declarative
                # mapping back to a single entity type in this codebase's data model
                # today (confirmed: `relation_type` here is a free-text instance-level
                # edge label, not tied to a declared `entity_type_relations` row) —
                # checked against the view's own primary entity type instead of
                # skipping the check outright. Flagged as an open item in
                # design_docs/jarvis_map.md; revisit if denormalized fields see real
                # usage with per-relation-type visibility requirements.
                field_map[name] = (view.source_entity_type, name)
        return field_map

    def _resolve_field_visibility(
        self, actor: dict[str, object], organization_id: str, entity_type: str
    ) -> tuple[set[str] | None, set[str]]:
        """(visible_fields, masked_fields) for one entity type. `None` visible means
        unrestricted (system actor, or an `is_system` role per `get_visible_fields`).

        Raises `ServiceUnavailableError` if the check cannot be evaluated at all
        (roles service not wired, or the DB call itself fails) — an unevaluable
        permission must never be treated as a granted one (INV-6).
        """
        if str(actor.get("actor_type") or "").lower() == "system":
            return None, set()
        if self.roles_manager is None:
            raise ServiceUnavailableError("Field permission service unavailable")
        # An actor with no resolvable user id has no role assignments to find —
        # `get_visible_fields`/`get_masked_fields` already deny-all for that case
        # ([] visible, no roles), which is the correct fail-secure outcome here too.
        user_id = str(actor.get("user_id") or "")
        try:
            visible, masked = self.db.resolve_field_visibility(
                self.roles_manager, organization_id, user_id, entity_type
            )
        except Exception as exc:  # noqa: BLE001
            raise ServiceUnavailableError(
                f"Unable to evaluate field permissions for '{entity_type}': {exc}"
            ) from exc
        return (set(visible) if visible is not None else None), set(masked)

    def _resolve_source_field_policy(
        self,
        actor: dict[str, object],
        organization_id: str,
        source: str,
        explicit_fields: set[str] | None = None,
    ) -> tuple[set[str], set[str]]:
        """(denied_fields, masked_fields) — field keys this source can produce that
        the actor's role either can't see at all, or can see only in masked form.
        Resolved once per distinct entity type the source's fields belong to, not
        once per field (a view can blend fields from several entity types via joins).

        Any `explicit_fields` entry that isn't a recognized fixed column and isn't
        in the known ownership map is unrecognized (a stale/undeclared key, or one
        this map simply doesn't know about yet) — denied by default rather than
        passed through, unless the actor is globally unrestricted.
        """
        field_entity_types = self._field_entity_type_map(organization_id, source)
        denied: set[str] = set()
        masked: set[str] = set()
        for entity_type in {owner for owner, _ in field_entity_types.values() if owner}:
            visible, entity_masked = self._resolve_field_visibility(actor, organization_id, entity_type)
            for field_key, (owner, raw_name) in field_entity_types.items():
                if owner != entity_type:
                    continue
                if visible is not None and raw_name not in visible:
                    denied.add(field_key)
                elif raw_name in entity_masked:
                    masked.add(field_key)

        fixed_columns = HEATMAP_FIXED_COLUMNS if source == "heatmap" else PROJECTION_FIXED_COLUMNS
        unknown_fields = {
            field
            for field in (explicit_fields or set())
            if field not in field_entity_types and field not in fixed_columns
        }
        if unknown_fields:
            visible, _ = self._resolve_field_visibility(actor, organization_id, _UNRECOGNIZED_ENTITY_TYPE)
            if visible is not None:
                denied |= unknown_fields
        return denied, masked

    def _validate_data_field_grouping(
        self, actor: dict[str, object], organization_id: str, field_name: str
    ) -> None:
        """`entities.by_field` groups by a single, caller-chosen entity data
        field — must not be usable to discover a field the role can't see, or
        to recover a masked field's real values by grouping on it."""
        if str(actor.get("actor_type") or "").lower() == "system":
            return
        visible_anywhere = False
        for entity_type in (record.name for record in self._list_entity_type_records(organization_id)):
            visible, masked = self._resolve_field_visibility(actor, organization_id, entity_type)
            if visible is None:
                return
            if field_name in visible:
                visible_anywhere = True
                if field_name in masked:
                    raise AuthorizationError(f"Not allowed to view field(s): data.{field_name}")
        if not visible_anywhere:
            raise AuthorizationError(f"Not allowed to view field(s): data.{field_name}")

    @staticmethod
    def _explicit_query_fields(query_def: DashboardQueryDefinitionRequest) -> set[str]:
        """Every field key explicitly named anywhere in a query definition — fed into
        `_resolve_source_field_policy` so an unrecognized field name is checked too,
        not just fields already on the known ownership map."""
        fields = {s.field for s in query_def.select}
        fields |= set(query_def.group_by)
        fields |= {a.field for a in query_def.aggregations}
        fields |= {f.field for f in query_def.filters}
        fields |= {s.field for s in query_def.sort}
        return fields

    def _list_entity_type_records(self, organization_id: str) -> list[Any]:
        """Entity type records for the org, via the entities module's manager
        (not a direct `entities.db_models` import). Fails closed if the
        dependency isn't wired or the lookup fails (INV-6)."""
        if self.entities_service_manager is None:
            raise ServiceUnavailableError("Entities service unavailable")
        try:
            return self.entities_service_manager.list_entity_type_records(
                organization_id=organization_id
            )
        except Exception as exc:  # noqa: BLE001
            raise ServiceUnavailableError(f"Unable to resolve entity types: {exc}") from exc

    def _entity_field_policy_resolver(
        self, actor: dict[str, object], organization_id: str
    ) -> Callable[[str], tuple[list[str] | None, list[str]]]:
        """`(entity_type_id) -> (visible_fields, masked_fields)` bound to this
        actor/org, for `instances.list` — the one metric that reads raw entity `data`
        fields per-row rather than through a view. Resolves the entity type id to its
        name — the roles module's field-permission methods key on entity type name,
        not id, matching `entities/manager.py`'s own `get_visible_fields` callers —
        before delegating to `_resolve_field_visibility`. The org's entity type
        records are fetched once (lazily, on first use) and cached for the
        lifetime of this resolver, not once per distinct entity type id.
        """
        id_to_name: dict[str, str] | None = None

        def resolve(entity_type_id: str) -> tuple[list[str] | None, list[str]]:
            nonlocal id_to_name
            if id_to_name is None:
                id_to_name = {
                    record.entity_type_id: record.name
                    for record in self._list_entity_type_records(organization_id)
                }
            entity_type_name = id_to_name.get(entity_type_id)
            if entity_type_name is None:
                return [], []  # unknown type — deny all rather than bypass (INV-1)
            visible, masked = self._resolve_field_visibility(actor, organization_id, entity_type_name)
            return (list(visible) if visible is not None else None), list(masked)

        return resolve

    def _visible_org_data_field_names(
        self, actor: dict[str, object], organization_id: str
    ) -> set[str] | None:
        """Union of visible data-field names across every entity type in the org.

        `None` means unrestricted (system actor) — callers must skip filtering
        entirely rather than treat `None` as "hide everything." Raises
        `ServiceUnavailableError` if any per-type check can't be evaluated (INV-6).
        """
        if str(actor.get("actor_type") or "").lower() == "system":
            return None
        entity_types = [record.name for record in self._list_entity_type_records(organization_id)]
        if not entity_types:
            return set()
        visible_names: set[str] = set()
        for entity_type in entity_types:
            visible, _ = self._resolve_field_visibility(actor, organization_id, entity_type)
            if visible is None:
                return None
            visible_names.update(visible)
        return visible_names

    def _run_activity(self, actor: dict[str, object], filters: dict[str, Any]) -> dict[str, Any]:
        """Render the Activity list widget via the audit module's service.

        Resolves the global time filter to a [since, until) window (reusing the
        dashboard's own helpers), asks the audit manager for the events, and maps
        the response to the ``rows`` widget-data shape.
        """
        audit = AuditServiceManager(
            AuditEventsModelService(self.database_service_manager),
            roles_manager=self.roles_manager,
            entities_service=self.entities_service_manager,
        )
        entity_ids = global_entity_ids(filters)
        resp = audit.list_audit_events_for_actor(
            actor,
            metadata_type=filters.get("metadata_type") or None,
            entity_ids=entity_ids,
            date_from=_range_since(filters),
            date_to=_range_until(filters),
            limit=_filter_int(filters, "limit", default=25, lo=1, hi=200),
        )
        columns = [{"key": key, "label": label} for key, label in ACTIVITY_FIELDS]
        rows = [
            {
                "event_type": it.event_type,
                "entity_type": it.entity_type,
                "entity_id": it.entity_id,
                "entity_identifier": it.entity_identifier,
                "actor_type": it.actor_type,
                "actor_id": it.actor_id,
                "actor_name": it.actor_name,
                "before_state": it.before_state,
                "after_state": it.after_state,
                "occurred_at": it.event_timestamp.isoformat() if it.event_timestamp else None,
            }
            for it in resp.items
        ]
        return {"kind": "rows", "columns": columns, "rows": rows}

    def list_query_sources_for_actor(self, actor: dict[str, object]) -> DashboardQuerySourcesResponse:
        self._deny_restricted_workflow_actor(actor)
        try:
            organization_id = str(actor.get("organization_id", ""))
            view_defs = self.db.list_active_view_definitions(organization_id)
            response = self.query_service.list_sources(view_defs)
            for source in response.sources:
                denied_fields, _ = self._resolve_source_field_policy(actor, organization_id, source.id)
                if denied_fields:
                    source.fields = [f for f in source.fields if f.key not in denied_fields]
            return response
        except (AuthorizationError, ServiceUnavailableError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Failed to load dashboard query sources: {exc}") from exc

    def preview_query_for_actor(
        self,
        actor: dict[str, object],
        query_def: DashboardQueryDefinitionRequest,
    ) -> DashboardQueryPreviewResponse:
        """Builds a live preview of a query definition. A field the actor can't
        see is dropped from the select/group-by/filter/sort clauses that named
        it — same graceful degradation as a rendered dashboard widget — rather
        than rejecting the whole preview over one forbidden field among others."""
        self._deny_restricted_workflow_actor(actor)
        try:
            organization_id = str(actor.get("organization_id", ""))
            explicit_fields = self._explicit_query_fields(query_def)
            if query_def.source == "heatmap":
                explicit_fields = explicit_fields | {"job_id"}
            denied_fields, masked_fields = self._resolve_source_field_policy(
                actor, organization_id, query_def.source, explicit_fields
            )
            if query_def.source == "heatmap":
                payload = self.db.preview_heatmap_query(
                    organization_id,
                    query_def,
                    denied_fields=denied_fields,
                    masked_fields=masked_fields,
                )
            else:
                view_name = (
                    query_def.source.split("::", 1)[1]
                    if query_def.source.startswith("projection::")
                    else query_def.source
                )
                payload = self.db.preview_projection_query(
                    organization_id,
                    view_name,
                    query_def,
                    denied_fields=denied_fields,
                    masked_fields=masked_fields,
                )
            return DashboardQueryPreviewResponse(
                source=str(payload["source"]),
                columns=[DashboardQueryFieldRead(**col) for col in payload["columns"]],
                rows=list(payload["rows"]),
                row_count=int(payload["row_count"]),
                suggested_visuals=list(payload["suggested_visuals"]),
            )
        except (AuthorizationError, ServiceUnavailableError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Failed to preview dashboard query: {exc}") from exc

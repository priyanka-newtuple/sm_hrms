"""Persistence layer for dashboard definitions."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import Float, cast, func
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Session
from sqlalchemy.types import JSON

from common.protocols import MASKED_FIELD_VALUE, RolesServiceProtocol
from database.manager import Base
from dashboard.global_filters import global_entity_ids
from dashboard.metrics import resolve_workflow_entity_type
from dashboard.models.request import DashboardQueryDefinitionRequest
from exceptions import PersistenceError
from projections.db_models import ProjectionRow, ViewDefinition


def _coerce_number(value: Any) -> float | int:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0
    return int(n) if n.is_integer() else n


class DashboardDefinition(Base):
    """Stores the entire dashboard as one JSON document."""

    __tablename__ = "dashboard_definitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_dashboard_definitions_org_key"),
    )

    id = Column(String(36), primary_key=True)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key = Column(String(64), nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSON, nullable=False, default=dict)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc))


def build_default_dashboard_config() -> dict[str, Any]:
    """Default dashboard document seeded for each org.

    Widgets are bound to metric keys (resolved live via POST /dashboards/data),
    with react-grid-layout coordinates embedded per widget.
    """
    return {
        "version": 2,
        "widgets": [
            {
                "id": "w-entities",
                "type": "stat",
                "title": "Active Entities",
                "metric": "entities.count",
                "filters": {},
                "viz": "number",
                "layout": {"x": 0, "y": 0, "w": 3, "h": 2},
            },
            {
                "id": "w-sla",
                "type": "stat",
                "title": "SLA Breaches",
                "metric": "sla.breaches",
                "filters": {},
                "viz": "number",
                "layout": {"x": 3, "y": 0, "w": 3, "h": 2},
            },
            {
                "id": "w-pipeline",
                "type": "chart",
                "title": "Pipeline by State",
                "metric": "pipeline.by_state",
                "filters": {},
                "viz": "bar",
                "layout": {"x": 0, "y": 2, "w": 8, "h": 5},
            },
            {
                "id": "w-events",
                "type": "table",
                "title": "Recent Events",
                "metric": "events.recent",
                "filters": {"limit": 10},
                "viz": "table",
                "layout": {"x": 8, "y": 2, "w": 4, "h": 5},
            },
        ],
    }


class DashboardModelService:
    """DB operations for dashboard definitions."""

    def __init__(self, database_service_manager: Any = None) -> None:
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )
        self.module_name = "dashboard"

    def _session(self) -> Session:
        if self.current_db is None:
            raise PersistenceError("Database service unavailable")
        return self.current_db.get_db_session()

    @contextmanager
    def _db_session(self):  # noqa: ANN201
        session = self._session()
        try:
            yield session
        finally:
            session.close()

    def ensure_dashboard(self, organization_id: str, key: str = "primary") -> DashboardDefinition:
        with self._db_session() as session:
            try:
                dashboard = (
                    session.query(DashboardDefinition)
                    .filter_by(organization_id=organization_id, key=key)
                    .first()
                )
                if dashboard:
                    return dashboard

                dashboard = DashboardDefinition(
                    id=str(uuid.uuid4()),
                    organization_id=organization_id,
                    key=key,
                    display_name="Workflow Dashboard",
                    description="Primary dashboard layout for the workflow cockpit.",
                    config=build_default_dashboard_config(),
                    is_default=(key == "primary"),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(dashboard)
                session.commit()
                session.refresh(dashboard)
                return dashboard
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                raise PersistenceError(f"Unable to ensure dashboard definition: {exc}") from exc

    def list_active_view_definitions(self, organization_id: str) -> list[ViewDefinition]:
        with self._db_session() as session:
            return (
                session.query(ViewDefinition)
                .filter(
                    ViewDefinition.organization_id == organization_id,
                    ViewDefinition.is_active == True,  # noqa: E712
                )
                .order_by(ViewDefinition.name.asc())
                .all()
            )

    def get_active_view_definition(
        self, organization_id: str, view_name: str
    ) -> ViewDefinition | None:
        """Single active view lookup by name — used to resolve field ownership for
        the field-level RBAC check (see design_docs/tony_dashboard_field_rbac_fix.md)."""
        with self._db_session() as session:
            return (
                session.query(ViewDefinition)
                .filter(
                    ViewDefinition.organization_id == organization_id,
                    ViewDefinition.name == view_name,
                    ViewDefinition.is_active == True,  # noqa: E712
                )
                .first()
            )

    def resolve_field_visibility(
        self,
        roles_manager: RolesServiceProtocol,
        organization_id: str,
        user_id: str,
        entity_type: str,
    ) -> tuple[list[str] | None, list[str]]:
        """Open one session and resolve (visible_fields, masked_fields) for one entity
        type via the roles module's own field-permission logic — no query construction
        of this module's own tables here, purely session plumbing for a cross-module
        read (see `RolesServiceManager.get_visible_fields`/`get_masked_fields`)."""
        with self._db_session() as session:
            visible = roles_manager.get_visible_fields(session, user_id, organization_id, entity_type)
            masked = roles_manager.get_masked_fields(session, user_id, organization_id, entity_type)
            return visible, masked

    def update_dashboard(
        self,
        organization_id: str,
        key: str,
        config: dict[str, Any],
        display_name: str | None = None,
        description: str | None = None,
    ) -> DashboardDefinition:
        with self._db_session() as session:
            try:
                dashboard = (
                    session.query(DashboardDefinition)
                    .filter_by(organization_id=organization_id, key=key)
                    .first()
                )
                if dashboard is None:
                    dashboard = DashboardDefinition(
                        id=str(uuid.uuid4()),
                        organization_id=organization_id,
                        key=key,
                        display_name=display_name or "Workflow Dashboard",
                        description=description,
                        config=config,
                        is_default=(key == "primary"),
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(dashboard)
                else:
                    dashboard.config = config
                    if display_name is not None:
                        dashboard.display_name = display_name
                    if description is not None:
                        dashboard.description = description
                    dashboard.updated_at = datetime.now(timezone.utc)
                    session.add(dashboard)

                session.commit()
                session.refresh(dashboard)
                return dashboard
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                raise PersistenceError(f"Unable to update dashboard definition: {exc}") from exc

    def run_metric(
        self,
        organization_id: str,
        metric_key: str,
        filters: dict[str, Any] | None = None,
        field_policy_resolver: Callable[[str], tuple[list[str] | None, list[str]]] | None = None,
    ) -> dict[str, Any]:
        from dashboard.metrics import execute_metric

        with self._db_session() as session:
            return execute_metric(
                session, organization_id, metric_key, filters, field_policy_resolver=field_policy_resolver
            )

    def run_query_widget(
        self,
        organization_id: str,
        query_def: Any,
        filters: dict[str, Any] | None = None,
        denied_fields: set[str] | None = None,
        masked_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        from dashboard.metrics import _range_since, _range_until

        filters = filters or {}
        since = _range_since(filters)
        until = _range_until(filters)
        time_window = (since, until) if (since or until) else None

        if query_def.source == "heatmap":
            # ponytail: heatmap path skips time_window; extend preview_heatmap_query if needed
            payload = self.preview_heatmap_query(
                organization_id,
                query_def,
                entity_ids=global_entity_ids(filters),
                denied_fields=denied_fields,
                masked_fields=masked_fields,
            )
        else:
            view_name = (
                query_def.source.split("::", 1)[1]
                if query_def.source.startswith("projection::")
                else query_def.source
            )
            payload = self.preview_projection_query(
                organization_id,
                view_name,
                query_def,
                time_window=time_window,
                entity_ids=global_entity_ids(filters),
                denied_fields=denied_fields,
                masked_fields=masked_fields,
            )

        rows = list(payload["rows"])
        group_by = list(query_def.group_by or [])
        aggregations = list(query_def.aggregations or [])
        if len(group_by) == 1 and len(aggregations) >= 1:
            label_key = group_by[0]
            value_key = aggregations[0].alias
            series = [
                {
                    "label": "" if row.get(label_key) is None else str(row.get(label_key)),
                    "value": _coerce_number(row.get(value_key)),
                }
                for row in rows
            ]
            return {"kind": "series", "series": series}
        return {"kind": "rows", "columns": list(payload["columns"]), "rows": rows}

    def filter_options(
        self, organization_id: str, workflow_id: str | None = None
    ) -> dict[str, list[dict[str, str]]]:
        from dashboard.metrics import filter_options

        with self._db_session() as session:
            return filter_options(session, organization_id, workflow_id=workflow_id)

    def entity_data_fields(
        self, organization_id: str, entity_type: str | None = None
    ) -> list[tuple[str, str]]:
        from dashboard.metrics import entity_data_fields

        with self._db_session() as session:
            return entity_data_fields(session, organization_id, entity_type=entity_type)

    def resolve_workflow_entity_type(
        self, organization_id: str, workflow_id: str
    ) -> str | None:
        """Entity type id for workflow_id's family, or None if unbound.

        Joins by name to drop placeholder/stale versions (e.g. blank drafts),
        and reads the active version first.
        """
        with self._db_session() as session:
            return resolve_workflow_entity_type(session, organization_id, workflow_id)

    @staticmethod
    def _column_type_name(sqlalchemy_type: Any) -> str:
        name = sqlalchemy_type.__class__.__name__.lower() if sqlalchemy_type is not None else ""
        if any(token in name for token in ["int", "float", "numeric", "decimal", "double", "real"]):
            return "number"
        if "bool" in name:
            return "boolean"
        if any(token in name for token in ["date", "time"]):
            return "date"
        return "string"

    def _field_read_dict(self, key: str, sqlalchemy_type: Any) -> dict[str, Any]:
        field_type = self._column_type_name(sqlalchemy_type)
        return {
            "key": key,
            "label": key.replace("_", " ").replace(".", " / ").title(),
            "type": field_type,
            "groupable": True,
            "filterable": True,
            "aggregatable": field_type == "number",
        }

    def preview_projection_query(
        self,
        organization_id: str,
        view_name: str,
        query_def: DashboardQueryDefinitionRequest,
        time_window: tuple[Any, Any] | None = None,
        entity_ids: list[str] | None = None,
        denied_fields: set[str] | None = None,
        masked_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """`denied_fields`/`masked_fields` are field-level RBAC decisions the manager
        already resolved and validated (see `DashboardServiceManager._resolve_source_field_policy`).
        Re-checked here defensively: a denied field named in `select`/`group_by`/
        `filters`/`sort` is dropped from that clause rather than surfaced — one
        forbidden field never blocks the rest of the query, whether it's a live
        preview or a saved widget being rendered."""
        denied_fields = denied_fields or set()
        masked_fields = masked_fields or set()
        db = self._session()
        try:
            query = db.query().select_from(ProjectionRow).filter(
                ProjectionRow.organization_id == organization_id,
                ProjectionRow.view_name == view_name,
            )
            if time_window is not None:
                since, until = time_window
                if since is not None:
                    query = query.filter(ProjectionRow.created_at >= since)
                if until is not None:
                    query = query.filter(ProjectionRow.created_at < until)
            if entity_ids is not None:
                query = query.filter(ProjectionRow.entity_id.in_(entity_ids))

            base_field_map = {
                "entity_id": ProjectionRow.entity_id,
                "current_state": ProjectionRow.current_state,
                "sla_risk": ProjectionRow.sla_risk,
                "machine_name": ProjectionRow.machine_name,
                "machine_version": ProjectionRow.machine_version,
                "state_entered_at": ProjectionRow.state_entered_at,
                "sla_due_at": ProjectionRow.sla_due_at,
                "candidate_id": ProjectionRow.data["candidate_id"].as_string(),
                "candidate_name": ProjectionRow.data["candidate_name"].as_string(),
                "candidate_email": ProjectionRow.data["candidate_email"].as_string(),
                "job_id": ProjectionRow.data["job_id"].as_string(),
                "job_title": ProjectionRow.data["job_title"].as_string(),
                "job_department": ProjectionRow.data["job_department"].as_string(),
                "created_at": ProjectionRow.created_at,
                "updated_at": ProjectionRow.updated_at,
            }

            def resolve_expr(field_key: str):  # noqa: ANN202
                if field_key in base_field_map:
                    return base_field_map[field_key]
                return ProjectionRow.data[field_key].as_string()

            def resolve_numeric_expr(field_key: str):  # noqa: ANN202
                return cast(resolve_expr(field_key), Float)

            def is_denied(field_key: str) -> bool:
                """True if `field_key` is denied — the clause naming it is dropped."""
                return field_key in denied_fields

            for filter_item in query_def.filters:
                if is_denied(filter_item.field):
                    continue
                expr = resolve_expr(filter_item.field)
                value = filter_item.value
                if filter_item.op == "eq":
                    query = query.filter(expr == value)
                elif filter_item.op == "neq":
                    query = query.filter(expr != value)
                elif filter_item.op == "contains":
                    query = query.filter(cast(expr, String).ilike(f"%{value}%"))
                elif filter_item.op == "gt":
                    query = query.filter(resolve_numeric_expr(filter_item.field) > value)
                elif filter_item.op == "gte":
                    query = query.filter(resolve_numeric_expr(filter_item.field) >= value)
                elif filter_item.op == "lt":
                    query = query.filter(resolve_numeric_expr(filter_item.field) < value)
                elif filter_item.op == "lte":
                    query = query.filter(resolve_numeric_expr(filter_item.field) <= value)
                elif filter_item.op == "in":
                    query = query.filter(expr.in_(value if isinstance(value, list) else [value]))

            selected_exprs: list[Any] = []
            selected_columns: list[dict[str, Any]] = []
            expr_by_alias: dict[str, Any] = {}
            masked_output_keys: set[str] = set()
            allowed_group_by = [field_key for field_key in query_def.group_by if not is_denied(field_key)]

            for field_key in allowed_group_by:
                expr = resolve_expr(field_key).label(field_key)
                selected_exprs.append(expr)
                expr_by_alias[field_key] = expr
                selected_columns.append(self._field_read_dict(field_key, None))
                if field_key in masked_fields:
                    masked_output_keys.add(field_key)

            if query_def.aggregations:
                for aggregation in query_def.aggregations:
                    if aggregation.op != "count" and is_denied(aggregation.field):
                        continue
                    if aggregation.op == "count":
                        expr = func.count().label(aggregation.alias)
                    else:
                        numeric_expr = resolve_numeric_expr(aggregation.field)
                        if aggregation.op == "sum":
                            expr = func.sum(numeric_expr).label(aggregation.alias)
                        elif aggregation.op == "avg":
                            expr = func.avg(numeric_expr).label(aggregation.alias)
                        elif aggregation.op == "min":
                            expr = func.min(numeric_expr).label(aggregation.alias)
                        else:
                            expr = func.max(numeric_expr).label(aggregation.alias)
                    selected_exprs.append(expr)
                    expr_by_alias[aggregation.alias] = expr
                    selected_columns.append(
                        {
                            "key": aggregation.alias,
                            "label": aggregation.alias.replace("_", " ").title(),
                            "type": "number",
                            "groupable": True,
                            "filterable": True,
                            "aggregatable": True,
                        }
                    )
                    if aggregation.op != "count" and aggregation.field in masked_fields:
                        masked_output_keys.add(aggregation.alias)
                query = query.with_entities(*selected_exprs).group_by(
                    *[resolve_expr(field_key) for field_key in allowed_group_by]
                )
            else:
                for select_item in query_def.select:
                    if is_denied(select_item.field):
                        continue
                    alias = select_item.alias or select_item.field
                    expr = resolve_expr(select_item.field).label(alias)
                    selected_exprs.append(expr)
                    expr_by_alias[alias] = expr
                    selected_columns.append(self._field_read_dict(alias, None))
                    if select_item.field in masked_fields:
                        masked_output_keys.add(alias)
                if not selected_exprs:
                    expr = ProjectionRow.entity_id.label("entity_id")
                    selected_exprs.append(expr)
                    expr_by_alias["entity_id"] = expr
                    selected_columns.append(self._field_read_dict("entity_id", None))
                query = query.with_entities(*selected_exprs)

            for sort_item in query_def.sort:
                if is_denied(sort_item.field):
                    continue
                expr = expr_by_alias.get(sort_item.field)
                if expr is None:
                    expr = resolve_expr(sort_item.field)
                query = query.order_by(expr.desc() if sort_item.direction == "desc" else expr.asc())

            rows = [dict(row._mapping) for row in query.limit(query_def.limit).all()]
            if masked_output_keys:
                for row in rows:
                    for key in masked_output_keys:
                        if key in row:
                            row[key] = MASKED_FIELD_VALUE
            return {
                "source": f"projection::{view_name}",
                "columns": selected_columns,
                "rows": rows,
                "row_count": len(rows),
                "suggested_visuals": ["table", "bar", "line", "area", "pie", "kpi"],
            }
        finally:
            db.close()

    def preview_heatmap_query(
        self,
        organization_id: str,
        query_def: DashboardQueryDefinitionRequest,
        entity_ids: list[str] | None = None,
        denied_fields: set[str] | None = None,
        masked_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """`denied_fields`/`masked_fields` re-checked defensively for consistency with
        `preview_projection_query`. Heatmap rows are structurally grouped by job/state,
        so a denied field (e.g. `job_id`) can't simply be omitted the way an optional
        projection column can — it's redacted in the output instead."""
        denied_fields = denied_fields or set()
        masked_fields = masked_fields or set()
        db = self._session()
        try:
            projection_rows = db.query(ProjectionRow).filter(
                ProjectionRow.organization_id == organization_id,
                ProjectionRow.view_name == "application_pipeline",
            )
            if entity_ids is not None:
                projection_rows = projection_rows.filter(ProjectionRow.entity_id.in_(entity_ids))
            projection_rows = projection_rows.all()

            raw_index: dict[tuple[str, str], dict[str, Any]] = {}
            for projection in projection_rows:
                job_id = projection.data.get("job_id") if projection.data else None
                state = projection.current_state or ""
                if not job_id or not state:
                    continue
                key = (str(job_id), state)
                if key not in raw_index:
                    raw_index[key] = {
                        "job_id": str(job_id),
                        "state": state,
                        "application_count": 0,
                        "breached_count": 0,
                        "avg_time_in_state_seconds": None,
                        "updated_at": projection.updated_at.isoformat() if projection.updated_at else None,
                    }
                raw_index[key]["application_count"] += 1
                if projection.sla_risk == "CRITICAL":
                    raw_index[key]["breached_count"] += 1

            rows: list[dict[str, Any]] = []
            for row in raw_index.values():
                include = True
                for filter_item in query_def.filters:
                    if filter_item.field in denied_fields:
                        continue  # drop this filter condition silently
                    value = row.get(filter_item.field)
                    target = filter_item.value
                    if filter_item.op == "eq" and value != target:
                        include = False
                    elif filter_item.op == "contains" and str(target).lower() not in str(value or "").lower():
                        include = False
                if include:
                    rows.append(row)

            rows = rows[: query_def.limit]
            # Fixed columns can't be omitted the way a select-able projection field
            # can — a denied one is redacted in the output instead.
            redact_keys = set(masked_fields) | denied_fields
            if redact_keys:
                for row in rows:
                    for key in redact_keys:
                        if key in row:
                            row[key] = MASKED_FIELD_VALUE
            return {
                "source": query_def.source,
                "columns": [
                    self._field_read_dict("job_id", None),
                    self._field_read_dict("state", None),
                    self._field_read_dict("application_count", Float()),
                    self._field_read_dict("breached_count", Float()),
                    self._field_read_dict("avg_time_in_state_seconds", Float()),
                    self._field_read_dict("updated_at", DateTime(timezone=True)),
                ],
                "rows": rows,
                "row_count": len(rows),
                "suggested_visuals": ["table", "bar", "pie"],
            }
        finally:
            db.close()

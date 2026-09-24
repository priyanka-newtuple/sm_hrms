"""Persistence layer for projections — ORM models, helpers, and DB operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from common.configuration import get_configuration
from sqlalchemy.orm import Session

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.types import JSON

from database.manager import Base
from entities.db_models import (
    EntityRecordModel,
    EntityRelationModel,
    EntityStateRuntimeModel,
    EntityTypeModel,
)
from exceptions import PersistenceError
from workflow.db_models import WorkflowStateMachineModel


# ── ORM Models ────────────────────────────────────────────────────────────────

class ViewDefinition(Base):
    __tablename__ = "view_definitions"

    id = Column(String(36), primary_key=True)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(64), nullable=False)
    display_name = Column(String(128), nullable=True)
    description = Column(Text, nullable=True)
    source_entity_type = Column(String(64), nullable=False)
    primary_key_field = Column(String(64), default="entity_id")
    source_fields = Column(JSON, nullable=True)
    denormalized_fields = Column(JSON, nullable=True)
    include_state = Column(Boolean, default=True)
    group_by_field = Column(String(64), nullable=True)
    available_filters = Column(JSON, nullable=True)
    sla_config = Column(JSON, nullable=True)
    aggregations = Column(JSON, nullable=True)
    default_sort = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)


class ProjectionRow(Base):
    __tablename__ = "projection_rows"

    view_name = Column(String(64), primary_key=True)
    entity_id = Column(String(36), primary_key=True)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type = Column(String(64), nullable=False, index=True)
    current_state = Column(String(128), nullable=True, index=True)
    state_entered_at = Column(DateTime(timezone=True), nullable=True)
    machine_name = Column(String(128), nullable=True, index=True)
    machine_version = Column(Integer, nullable=True)
    sla_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    sla_risk = Column(String(32), nullable=True, index=True)
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    @property
    def application_id(self) -> str:
        """Property accessor for the projection's application_id field."""
        return self.entity_id

    @property
    def applied_at(self):
        """Property accessor for the projection's applied_at timestamp."""
        if self.data and "applied_at" in self.data:
            return self.data["applied_at"]
        return self.created_at

    @property
    def candidate_id(self):
        """Property accessor for the projected candidate_id."""
        return self.data.get("candidate_id") if self.data else None

    @property
    def candidate_name(self):
        """Property accessor for the projected candidate display name."""
        return self.data.get("candidate_name") if self.data else None

    @property
    def candidate_email(self):
        """Property accessor for the projected candidate email."""
        return self.data.get("candidate_email") if self.data else None

    @property
    def job_id(self):
        """Property accessor for the projected job_id."""
        return self.data.get("job_id") if self.data else None

    @property
    def job_title(self):
        """Property accessor for the projected job title."""
        return self.data.get("job_title") if self.data else None

    @property
    def job_department(self):
        """Property accessor for the projected job department."""
        return self.data.get("job_department") if self.data else None


# ── DB service ────────────────────────────────────────────────────────────────

class ProjectionsModelService:
    """DB operations for projections (pipeline, heatmap, funnels, rebuild)."""

    def __init__(self, database_service_manager: Any = None) -> None:
        """Build the projection reader against the runtime/audit schemas."""
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )
        self.module_name = "projections"

    def _session(self):
        """Yield a session for the projections' read-only queries."""
        if not self.current_db:
            raise PersistenceError("Database service unavailable")
        return self.current_db.get_db_session()

    # ── SLA helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _compute_sla_risk(
        sla_due_at: datetime | None,
        warning_hours: float,
        critical_hours: float,
    ) -> str | None:
        """Bucket an enrollment's SLA risk based on time-to-due thresholds."""
        if not sla_due_at:
            return None
        now = datetime.now(timezone.utc)
        if sla_due_at.tzinfo is None:
            sla_due_at = sla_due_at.replace(tzinfo=timezone.utc)
        hours_remaining = (sla_due_at - now).total_seconds() / 3600
        if hours_remaining <= 0 or hours_remaining <= critical_hours:
            return "CRITICAL"
        if hours_remaining <= warning_hours:
            return "WARNING"
        return "OK"

    @staticmethod
    def _get_sla_thresholds(view_def: ViewDefinition | None) -> tuple:
        """Resolve per-state SLA thresholds for the active workflow."""
        sla_cfg = get_configuration().sla_configuration
        default_warning = sla_cfg.warning_hours
        default_critical = sla_cfg.critical_hours
        if view_def and view_def.sla_config:
            cfg = view_def.sla_config
            return cfg.get("warning_hours", default_warning), cfg.get("critical_hours", default_critical)
        return default_warning, default_critical

    # ── Field / relation resolution ───────────────────────────────────────────

    @staticmethod
    def _resolve_field_value(entity: EntityRecordModel | None, source: str, fallback: str | None = None) -> Any:
        """Pull a denormalized value out of an entity's data dict by spec."""
        parts = source.split(".")
        value: Any = entity
        for part in parts:
            if value is None:
                break
            value = value.get(part) if isinstance(value, dict) else getattr(value, part, None)
        if value is None and fallback:
            return ProjectionsModelService._resolve_field_value(entity, fallback)
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @staticmethod
    def _entity_type_id_for_name(db: Session, org_id: str, name: str) -> str | None:
        """Reverse-lookup: entity_type_id by name within the org."""
        row = (
            db.query(EntityTypeModel.entity_type_id)
            .filter(
                EntityTypeModel.organization_id == org_id,
                EntityTypeModel.name == name,
            )
            .first()
        )
        return row[0] if row else None

    @staticmethod
    def _entity_type_name_map(db: Session, org_id: str) -> dict[str, str]:
        """Cache mapping entity_type_id → name for the actor's org."""
        rows = (
            db.query(EntityTypeModel.entity_type_id, EntityTypeModel.name)
            .filter(EntityTypeModel.organization_id == org_id)
            .all()
        )
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def _resolve_related_entity(
        db: Session, entity_id: str, relation_type: str, org_id: str | None = None
    ) -> EntityRecordModel | None:
        """Find a related entity via `relation_type`. Looks at edges in either
        direction. The new EntityRelationModel does not store entity_type on
        the edge, so we filter purely by `relation_type` and follow to the
        opposite entity_id."""
        candidates: list[str] = []
        rel_outgoing = (
            db.query(EntityRelationModel)
            .filter(
                EntityRelationModel.from_entity_id == entity_id,
                EntityRelationModel.relation_type == relation_type,
                *([EntityRelationModel.organization_id == org_id] if org_id else []),
            )
            .first()
        )
        if rel_outgoing is not None:
            candidates.append(rel_outgoing.to_entity_id)
        rel_incoming = (
            db.query(EntityRelationModel)
            .filter(
                EntityRelationModel.to_entity_id == entity_id,
                EntityRelationModel.relation_type == relation_type,
                *([EntityRelationModel.organization_id == org_id] if org_id else []),
            )
            .first()
        )
        if rel_incoming is not None:
            candidates.append(rel_incoming.from_entity_id)
        for related_id in candidates:
            q = db.query(EntityRecordModel).filter(EntityRecordModel.entity_id == related_id)
            if org_id:
                q = q.filter(EntityRecordModel.organization_id == org_id)
            related = q.first()
            if related is not None:
                return related
        return None

    @staticmethod
    def _build_denormalized_data(
        db: Session, entity: EntityRecordModel, view_def: ViewDefinition, org_id: str | None = None
    ) -> dict[str, Any]:
        """Project per-row denormalized fields (candidate_name, etc.) for fast UI reads."""
        data: dict[str, Any] = {}
        if view_def.source_fields:
            for field in view_def.source_fields:
                data[field["name"]] = ProjectionsModelService._resolve_field_value(entity, field["source"], field.get("fallback"))
        if view_def.denormalized_fields:
            related_cache: dict[str, EntityRecordModel | None] = {}
            for field in view_def.denormalized_fields:
                rtype = field["relation_type"]
                if rtype not in related_cache:
                    related_cache[rtype] = ProjectionsModelService._resolve_related_entity(db, entity.entity_id, rtype, org_id=org_id)
                related = related_cache[rtype]
                data[field["name"]] = ProjectionsModelService._resolve_field_value(related, field["source_field"], field.get("fallback_field")) if related else None
        return data

    @staticmethod
    def _get_view_definition_by_entity_type(
        db: Session, org_id: str, entity_type: str
    ) -> ViewDefinition | None:
        """Look up the projection view config registered for an entity type."""
        simple_type = entity_type.split(".")[-1] if "." in entity_type else entity_type
        return (
            db.query(ViewDefinition)
            .filter(
                ViewDefinition.organization_id == org_id,
                ViewDefinition.source_entity_type == simple_type,
                ViewDefinition.is_active == True,  # noqa: E712
            )
            .first()
        )

    @staticmethod
    def _create_projection_for_entity(
        db: Session,
        org_id: str,
        entity: EntityRecordModel,
        state: EntityStateRuntimeModel | None,
        *,
        entity_type_name: str,
        machine_name: str | None,
        machine_version: int | None,
    ) -> ProjectionRow | None:
        """Compose a single projection row from runtime + denormalized data."""
        view_def = ProjectionsModelService._get_view_definition_by_entity_type(
            db, org_id, entity_type_name
        )
        if not view_def:
            return None
        denorm_data = ProjectionsModelService._build_denormalized_data(db, entity, view_def, org_id=org_id)
        warning_hours, critical_hours = ProjectionsModelService._get_sla_thresholds(view_def)
        now = datetime.now(timezone.utc)
        sla_due_at = state.sla_due_at if state else None
        projection = ProjectionRow(
            view_name=view_def.name,
            entity_id=entity.entity_id,
            organization_id=org_id,
            entity_type=entity_type_name,
            current_state=state.current_state if state else None,
            state_entered_at=state.state_entered_at if state else now,
            machine_name=machine_name,
            machine_version=machine_version,
            sla_due_at=sla_due_at,
            sla_risk=ProjectionsModelService._compute_sla_risk(sla_due_at, warning_hours, critical_hours),
            data=denorm_data,
            created_at=entity.created_at,
            updated_at=now,
        )
        db.add(projection)
        return projection

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def list_pipeline(
        self,
        org_id: str,
        current_state: str | None = None,
        job_id: str | None = None,
        sla_risk: str | None = None,
    ) -> list:
        """Return the pipeline-board projection rows for the actor's org."""
        db = self._session()
        try:
            query = db.query(ProjectionRow).filter(
                ProjectionRow.view_name == "application_pipeline",
                ProjectionRow.organization_id == org_id,
            )
            if current_state:
                query = query.filter(ProjectionRow.current_state == current_state)
            if sla_risk:
                query = query.filter(ProjectionRow.sla_risk == sla_risk)
            if job_id:
                query = query.filter(ProjectionRow.data["job_id"].as_string() == job_id)
            return query.order_by(ProjectionRow.sla_due_at.asc().nullslast()).all()
        finally:
            db.close()

    def get_pipeline_entry(self, org_id: str, application_id: str) -> Any:
        """Fetch a single pipeline-board row by entity_id."""
        db = self._session()
        try:
            entity = (
                db.query(EntityRecordModel)
                .filter(EntityRecordModel.entity_id == application_id)
                .first()
            )
            if not entity:
                return None
            type_name = (
                db.query(EntityTypeModel.name)
                .filter(EntityTypeModel.entity_type_id == entity.entity_type_id)
                .scalar()
            )
            if not type_name:
                return None
            view_def = self._get_view_definition_by_entity_type(db, org_id, type_name)
            if not view_def:
                return None
            return (
                db.query(ProjectionRow)
                .filter(
                    ProjectionRow.view_name == view_def.name,
                    ProjectionRow.entity_id == application_id,
                    ProjectionRow.organization_id == org_id,
                )
                .first()
            )
        finally:
            db.close()

    # ── Funnels ──────────────────────────────────────────────────────────────

    def list_funnels(self, org_id: str, job_id: str | None = None) -> dict:
        """Return aggregated funnel-stage counts for dashboards."""
        db = self._session()
        try:
            query = (
                db.query(
                    ProjectionRow.machine_name,
                    ProjectionRow.machine_version,
                    func.count(ProjectionRow.entity_id).label("count"),
                )
                .filter(
                    ProjectionRow.view_name == "application_pipeline",
                    ProjectionRow.organization_id == org_id,
                    ProjectionRow.machine_name.isnot(None),
                )
                .group_by(ProjectionRow.machine_name, ProjectionRow.machine_version)
            )
            if job_id:
                query = query.filter(ProjectionRow.data["job_id"].as_string() == job_id)
            results = query.all()
            funnels = [
                {"machine_name": r.machine_name, "machine_version": r.machine_version, "count": r.count}
                for r in results
            ]
            total = sum(f["count"] for f in funnels)
            return {
                "funnels": funnels,
                "total": total,
                "is_multi_funnel": len({f["machine_name"] for f in funnels}) > 1,
            }
        finally:
            db.close()

    # ── Heatmap ──────────────────────────────────────────────────────────────

    def aggregate_heatmap(self, org_id: str, job_id: str | None = None) -> list:
        """Aggregate per-state SLA-risk counts for the heatmap chart."""
        db = self._session()
        try:
            query = db.query(ProjectionRow).filter(
                ProjectionRow.view_name == "application_pipeline",
                ProjectionRow.organization_id == org_id,
            )
            if job_id:
                query = query.filter(ProjectionRow.data["job_id"].as_string() == job_id)
            projections = query.all()
            heatmap: dict[tuple, dict[str, Any]] = {}
            now = datetime.now(timezone.utc)
            for p in projections:
                job = p.data.get("job_id") if p.data else None
                if not job:
                    continue
                key = (job, p.current_state)
                if key not in heatmap:
                    heatmap[key] = {
                        "job_id": job,
                        "state": p.current_state,
                        "application_count": 0,
                        "breached_count": 0,
                        "avg_time_in_state_seconds": None,
                        "updated_at": now,
                    }
                heatmap[key]["application_count"] += 1
                if p.sla_risk == "CRITICAL":
                    heatmap[key]["breached_count"] += 1
            return list(heatmap.values())
        finally:
            db.close()

    def list_heatmap(self, org_id: str, job_id: str | None = None) -> list:
        """Return heatmap rows in the shape the frontend expects."""
        return self.aggregate_heatmap(org_id, job_id=job_id)

    # ── Rebuild ──────────────────────────────────────────────────────────────

    def rebuild_projections(self, org_id: str, entity_type: str | None = None) -> dict:
        """No-op stub: projections are computed on read, not materialized."""
        db = self._session()
        try:
            type_map = self._entity_type_name_map(db, org_id)
            type_id_filter: str | None = None
            if entity_type:
                type_id_filter = self._entity_type_id_for_name(db, org_id, entity_type)
                if type_id_filter is None:
                    return {"deleted": 0, "created": 0}

            query = db.query(EntityRecordModel).filter(
                EntityRecordModel.organization_id == org_id,
                EntityRecordModel.archived_at.is_(None),
            )
            if type_id_filter is not None:
                query = query.filter(EntityRecordModel.entity_type_id == type_id_filter)
            entities = query.all()

            entity_ids = [e.entity_id for e in entities]
            states = (
                db.query(EntityStateRuntimeModel)
                .filter(
                    EntityStateRuntimeModel.organization_id == org_id,
                    EntityStateRuntimeModel.entity_id.in_(entity_ids),
                )
                .all()
                if entity_ids
                else []
            )
            state_map = {s.entity_id: s for s in states}

            workflow_ids = {s.workflow_id for s in states if s.workflow_id}
            workflow_map: dict[str, tuple[str, int]] = {}
            if workflow_ids:
                wf_rows = (
                    db.query(
                        WorkflowStateMachineModel.id,
                        WorkflowStateMachineModel.machine_name,
                        WorkflowStateMachineModel.version,
                    )
                    .filter(WorkflowStateMachineModel.id.in_(workflow_ids))
                    .all()
                )
                workflow_map = {row[0]: (row[1], row[2]) for row in wf_rows}

            delete_q = db.query(ProjectionRow).filter(ProjectionRow.organization_id == org_id)
            if entity_type:
                delete_q = delete_q.filter(ProjectionRow.entity_type == entity_type)
            deleted = delete_q.delete(synchronize_session=False)

            created = 0
            for entity in entities:
                state = state_map.get(entity.entity_id)
                machine_name: str | None = None
                machine_version: int | None = None
                if state is not None and state.workflow_id in workflow_map:
                    machine_name, machine_version = workflow_map[state.workflow_id]
                type_name = type_map.get(entity.entity_type_id, "")
                if not type_name:
                    continue
                projection = self._create_projection_for_entity(
                    db,
                    org_id,
                    entity,
                    state,
                    entity_type_name=type_name,
                    machine_name=machine_name,
                    machine_version=machine_version,
                )
                if projection:
                    created += 1

            db.commit()
            return {"deleted": deleted, "created": created}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

"""Business logic manager for projections (pipeline board, heatmap, funnels)."""

from __future__ import annotations

from typing import Any
from common.protocols import MASKED_FIELD_VALUE, SYSTEM_USER, RolesServiceProtocol

from exceptions import NotFoundError, ServiceError

from projections.db_models import ProjectionsModelService
from projections.models.response import (
    FunnelInUse,
    FunnelsInUseResponse,
    HeatmapRead,
    HeatmapRefreshResponse,
    PipelineViewRead,
    ProjectionsStatusResponse,
    RebuildProjectionsResponse,
)


class ProjectionsServiceManager:
    """Orchestrates projection queries — pipeline, heatmap, and funnels."""

    def __init__(
        self,
        projections_db_model_service: ProjectionsModelService,
        database_service_manager: Any = None,
        config: Any = None,
        roles_manager: RolesServiceProtocol | None = None,
    ) -> None:
        super().__init__()
        self.db = projections_db_model_service
        self.database_service_manager = database_service_manager
        self.module_name = "projections"
        self._started = False
        self.roles_manager = roles_manager

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> ProjectionsStatusResponse:
        return ProjectionsStatusResponse(
            module=self.module_name,
            status="ready",
            started=self._started,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _apply_field_permissions_to_row(
        self,
        db: Any,
        user_id: str,
        org_id: str,
        entity_type_name: str,
        row: Any,
    ) -> Any:
        """Filter and mask `row.data` according to the actor's field permissions.

        Returns the same row object (mutated in place) so existing callers need
        no structural changes. No-ops when `roles_manager` is None or when the
        actor has unrestricted access (roles_manager returns None for visible/masked).
        """
        if self.roles_manager is None or not entity_type_name:
            return row
        visible = self.roles_manager.get_visible_fields(db, user_id, org_id, entity_type_name)
        masked = self.roles_manager.get_masked_fields(db, user_id, org_id, entity_type_name)
        if visible is None and not masked:
            return row
        data: dict = dict(row.data or {})
        if visible is not None:
            data = {k: v for k, v in data.items() if k in visible}
        for field in masked:
            if field in data:
                data[field] = MASKED_FIELD_VALUE
        row.data = data
        return row

    @staticmethod
    def _row_to_pipeline_read(row: Any) -> PipelineViewRead:
        data: dict = row.data or {}
        return PipelineViewRead(
            application_id=data.get("application_id") or row.entity_id,
            candidate_id=data.get("candidate_id"),
            candidate_name=data.get("candidate_name"),
            candidate_email=data.get("candidate_email"),
            job_id=data.get("job_id"),
            job_title=data.get("job_title"),
            job_department=data.get("job_department"),
            machine_name=row.machine_name,
            machine_version=row.machine_version,
            current_state=row.current_state or "",
            state_entered_at=row.state_entered_at or row.created_at,
            sla_due_at=row.sla_due_at,
            sla_risk=row.sla_risk,
            applied_at=row.created_at,
            updated_at=row.updated_at,
        )

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def list_pipeline(
        self,
        org_id: str,
        current_state: str | None = None,
        job_id: str | None = None,
        sla_risk: str | None = None,
        actor: Any = None,
    ) -> list[PipelineViewRead]:
        try:
            rows = self.db.list_pipeline(
                org_id, current_state=current_state, job_id=job_id, sla_risk=sla_risk
            )
            if self.roles_manager is not None and actor is not None:
                user_id = str(actor.get("user_id") or "").strip() if isinstance(actor, dict) else ""
                if user_id and user_id != SYSTEM_USER and self.database_service_manager is not None:
                    _db = self.database_service_manager.get_db_session()
                    try:
                        rows = [
                            self._apply_field_permissions_to_row(
                                _db, user_id, org_id,
                                str(getattr(r, "entity_type", "") or ""),
                                r,
                            )
                            for r in rows
                        ]
                    finally:
                        _db.close()
            return [self._row_to_pipeline_read(r) for r in rows]
        except Exception as exc:
            raise ServiceError(f"Failed to list pipeline: {exc}") from exc

    def get_pipeline_entry(
        self, org_id: str, application_id: str, actor: Any = None
    ) -> PipelineViewRead:
        try:
            row = self.db.get_pipeline_entry(org_id, application_id)
        except Exception as exc:
            raise ServiceError(f"Failed to get pipeline entry: {exc}") from exc
        if not row:
            raise NotFoundError(f"Pipeline entry not found: {application_id}")
        if self.roles_manager is not None and actor is not None:
            user_id = str(actor.get("user_id") or "").strip() if isinstance(actor, dict) else ""
            if user_id and user_id != SYSTEM_USER and self.database_service_manager is not None:
                _db = self.database_service_manager.get_db_session()
                try:
                    row = self._apply_field_permissions_to_row(
                        _db, user_id, org_id,
                        str(getattr(row, "entity_type", "") or ""),
                        row,
                    )
                finally:
                    _db.close()
        return self._row_to_pipeline_read(row)

    # ── Funnels ──────────────────────────────────────────────────────────────

    def list_funnels(
        self, org_id: str, job_id: str | None = None
    ) -> FunnelsInUseResponse:
        try:
            result = self.db.list_funnels(org_id, job_id=job_id)
            funnels = [
                FunnelInUse(
                    machine_name=f["machine_name"],
                    machine_version=f.get("machine_version"),
                    application_count=f.get("count", 0),
                )
                for f in result.get("funnels", [])
            ]
            return FunnelsInUseResponse(
                funnels=funnels,
                total_applications=result.get("total", 0),
                is_multi_funnel=result.get("is_multi_funnel", False),
            )
        except Exception as exc:
            raise ServiceError(f"Failed to list funnels: {exc}") from exc

    # ── Heatmap ──────────────────────────────────────────────────────────────

    def list_heatmap(
        self, org_id: str, job_id: str | None = None
    ) -> list[HeatmapRead]:
        try:
            rows = self.db.list_heatmap(org_id, job_id=job_id)
            return [
                HeatmapRead(
                    job_id=r["job_id"],
                    state=r["state"],
                    application_count=r["application_count"],
                    breached_count=r["breached_count"],
                    avg_time_in_state_seconds=r.get("avg_time_in_state_seconds"),
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]
        except Exception as exc:
            raise ServiceError(f"Failed to list heatmap: {exc}") from exc

    def refresh_heatmap(
        self, org_id: str, job_id: str | None = None
    ) -> HeatmapRefreshResponse:
        try:
            rows = self.db.aggregate_heatmap(org_id, job_id=job_id)
            return HeatmapRefreshResponse(
                rows_updated=len(rows),
                message=f"Heatmap refreshed: {len(rows)} rows updated",
            )
        except Exception as exc:
            raise ServiceError(f"Failed to refresh heatmap: {exc}") from exc

    # ── Rebuild ──────────────────────────────────────────────────────────────

    def rebuild_projections(
        self, org_id: str, entity_type: str | None = None
    ) -> RebuildProjectionsResponse:
        try:
            result = self.db.rebuild_projections(org_id, entity_type=entity_type)
            return RebuildProjectionsResponse(
                deleted=result["deleted"],
                created=result["created"],
                message=f"Projections rebuilt: {result['deleted']} deleted, {result['created']} created",
            )
        except Exception as exc:
            raise ServiceError(f"Failed to rebuild projections: {exc}") from exc

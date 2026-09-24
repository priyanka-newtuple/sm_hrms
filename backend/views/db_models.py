"""Persistence adapters for views."""

from __future__ import annotations

from dataclasses import dataclass, field

try:
    from common.enums import ProjectionSlaRisk
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.enums import ProjectionSlaRisk

try:
    from exceptions import PersistenceError
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.exceptions import PersistenceError

from .models.interface import HeatmapBucket, PipelineProjectionContract, compute_sla_risk
from .models.request import UpsertPipelineProjectionRequest


@dataclass
class PipelineProjectionRecord:
    organization_id: str
    subject_entity_id: str
    group_entity_id: str
    state_key: str
    sla_due_at: str | None = None
    lifecycle_key: str | None = None
    denormalized_data: dict[str, object] = field(default_factory=dict)


class ViewsModelService:
    """In-memory persistence service for projection rows."""

    def __init__(self, database_service_manager) -> None:  # noqa: ANN001
        super().__init__()
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            self.database_manager.postgres_db_service()
            if self.database_manager and hasattr(self.database_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.module_name = "views"
        self._projection_rows: dict[tuple[str, str], PipelineProjectionRecord] = {}

    def upsert_projection(self, request: UpsertPipelineProjectionRequest) -> PipelineProjectionContract:
        try:
            key = (request.organization_id, request.subject_entity_id)
            record = PipelineProjectionRecord(
                organization_id=request.organization_id,
                subject_entity_id=request.subject_entity_id,
                group_entity_id=request.group_entity_id,
                state_key=request.state_key,
                sla_due_at=request.sla_due_at,
                lifecycle_key=request.lifecycle_key,
                denormalized_data=dict(request.denormalized_data),
            )
            self._projection_rows[key] = record
            return self._to_contract(record)
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to upsert lifecycle projection: {exc}") from exc

    def get_projection(self, organization_id: str, subject_entity_id: str) -> PipelineProjectionContract | None:
        record = self._projection_rows.get((organization_id, subject_entity_id))
        if record is None:
            return None
        return self._to_contract(record)

    def list_pipeline(
        self,
        organization_id: str,
        state_key: str | None = None,
        group_entity_id: str | None = None,
        lifecycle_key: str | None = None,
        sla_risk: str | None = None,
    ) -> list[PipelineProjectionContract]:
        try:
            rows: list[PipelineProjectionContract] = []
            for (org_id, _), record in self._projection_rows.items():
                if org_id != organization_id:
                    continue
                if state_key and record.state_key != state_key:
                    continue
                if group_entity_id and record.group_entity_id != group_entity_id:
                    continue
                if lifecycle_key and record.lifecycle_key != lifecycle_key:
                    continue
                row = self._to_contract(record)
                if sla_risk and compute_sla_risk(row.sla_due_at) != sla_risk:
                    continue
                rows.append(row)
            return sorted(rows, key=lambda item: (item.group_entity_id, item.state_key, item.subject_entity_id))
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to list lifecycle views: {exc}") from exc

    def aggregate_heatmap(self, organization_id: str, group_entity_id: str | None = None) -> list[HeatmapBucket]:
        try:
            bucket_stats: dict[tuple[str, str], dict[str, int]] = {}
            for row in self.list_pipeline(organization_id=organization_id, group_entity_id=group_entity_id):
                key = (row.group_entity_id, row.state_key)
                stats = bucket_stats.setdefault(key, {"total": 0, "critical": 0, "warning": 0})
                stats["total"] += 1
                risk = compute_sla_risk(row.sla_due_at)
                if risk == ProjectionSlaRisk.CRITICAL.value:
                    stats["critical"] += 1
                elif risk == ProjectionSlaRisk.WARNING.value:
                    stats["warning"] += 1

            result: list[HeatmapBucket] = []
            for (bucket_group_entity_id, bucket_state), stats in sorted(bucket_stats.items()):
                result.append(
                    HeatmapBucket(
                        organization_id=organization_id,
                        group_entity_id=bucket_group_entity_id,
                        state_key=bucket_state,
                        total_count=stats["total"],
                        critical_count=stats["critical"],
                        warning_count=stats["warning"],
                    )
                )
            return result
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to aggregate lifecycle heatmap: {exc}") from exc

    @staticmethod
    def _to_contract(record: PipelineProjectionRecord) -> PipelineProjectionContract:
        return PipelineProjectionContract(
            organization_id=record.organization_id,
            subject_entity_id=record.subject_entity_id,
            group_entity_id=record.group_entity_id,
            state_key=record.state_key,
            sla_due_at=record.sla_due_at,
            lifecycle_key=record.lifecycle_key,
            denormalized_data=dict(record.denormalized_data),
        )

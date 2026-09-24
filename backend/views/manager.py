"""Business logic manager for views."""

from __future__ import annotations

from common.enums import ModuleStatus
from common.auth import actor_str
from exceptions import AuthorizationError, NotFoundError, ServiceError, ValidationError

from .models.interface import compute_sla_risk
from .models.request import HeatmapRefreshRequest, PipelineListRequest, UpsertPipelineProjectionRequest
from .models.response import (
    FunnelUsageResponse,
    HeatmapBucketResponse,
    HeatmapRefreshResponse,
    PipelineProjectionListResponse,
    PipelineProjectionResponse,
    ProjectionsStatusResponse,
)


class ViewsServiceManager:
    """Projection and lifecycle heatmap orchestration service."""

    def __init__(
        self,
        views_db_model_service,
        database_service_manager,
        config,
        auth_service_manager=None,
        *dependencies,
    ) -> None:  # noqa: ANN001
        self.views_db_model_service = views_db_model_service
        self.db_model_service = views_db_model_service
        self.model_service = views_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.module_name = "views"
        self._started = False
        self.auth_service_manager = auth_service_manager or self._resolve_identity_service(
            dependencies
        )

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> ProjectionsStatusResponse:
        return ProjectionsStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def upsert_lifecycle_projection(
        self,
        request: UpsertPipelineProjectionRequest | dict[str, object],
    ) -> PipelineProjectionResponse:
        """Canonical lifecycle upsert entrypoint."""
        return self.upsert_pipeline_projection(request)

    def upsert_pipeline_projection(
        self,
        request: UpsertPipelineProjectionRequest | dict[str, object],
    ) -> PipelineProjectionResponse:
        """Legacy pipeline upsert entrypoint kept for compatibility."""
        try:
            upsert = (
                request
                if isinstance(request, UpsertPipelineProjectionRequest)
                else UpsertPipelineProjectionRequest.from_dict(request)
            )
            contract = self.db_model_service.upsert_projection(upsert)
            return PipelineProjectionResponse(
                organization_id=contract.organization_id,
                subject_entity_id=contract.subject_entity_id,
                group_entity_id=contract.group_entity_id,
                state_key=contract.state_key,
                sla_due_at=contract.sla_due_at,
                sla_risk=compute_sla_risk(contract.sla_due_at),
                lifecycle_key=contract.lifecycle_key,
                denormalized_data=dict(contract.denormalized_data),
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to upsert lifecycle projection: {exc}") from exc

    def get_lifecycle_projection(
        self,
        organization_id: str,
        subject_entity_id: str,
    ) -> PipelineProjectionResponse | None:
        """Canonical lifecycle get entrypoint."""
        return self.get_pipeline_projection(organization_id=organization_id, subject_entity_id=subject_entity_id)

    def get_pipeline_projection(
        self,
        organization_id: str,
        subject_entity_id: str,
    ) -> PipelineProjectionResponse | None:
        """Legacy pipeline get entrypoint kept for compatibility."""
        try:
            contract = self.db_model_service.get_projection(
                organization_id=organization_id,
                subject_entity_id=subject_entity_id,
            )
            if contract is None:
                return None
            return PipelineProjectionResponse(
                organization_id=contract.organization_id,
                subject_entity_id=contract.subject_entity_id,
                group_entity_id=contract.group_entity_id,
                state_key=contract.state_key,
                sla_due_at=contract.sla_due_at,
                sla_risk=compute_sla_risk(contract.sla_due_at),
                lifecycle_key=contract.lifecycle_key,
                denormalized_data=dict(contract.denormalized_data),
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to fetch lifecycle projection: {exc}") from exc

    def list_lifecycle_views(
        self,
        request: PipelineListRequest | dict[str, object],
    ) -> list[PipelineProjectionResponse]:
        """Canonical lifecycle list entrypoint."""
        return self.list_pipeline_view(request)

    def list_pipeline_view(
        self,
        request: PipelineListRequest | dict[str, object],
    ) -> list[PipelineProjectionResponse]:
        """Legacy pipeline list entrypoint kept for compatibility."""
        try:
            query = request if isinstance(request, PipelineListRequest) else PipelineListRequest.from_dict(request)
            rows = self.db_model_service.list_pipeline(
                organization_id=query.organization_id,
                state_key=query.state_key,
                group_entity_id=query.group_entity_id,
                lifecycle_key=query.lifecycle_key,
                sla_risk=query.sla_risk,
            )
            return [
                PipelineProjectionResponse(
                    organization_id=row.organization_id,
                    subject_entity_id=row.subject_entity_id,
                    group_entity_id=row.group_entity_id,
                    state_key=row.state_key,
                    sla_due_at=row.sla_due_at,
                    sla_risk=compute_sla_risk(row.sla_due_at),
                    lifecycle_key=row.lifecycle_key,
                    denormalized_data=dict(row.denormalized_data),
                )
                for row in rows
            ]
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to list lifecycle views: {exc}") from exc

    def list_lifecycle_usage(self, organization_id: str, group_entity_id: str | None = None) -> dict[str, object]:
        """Canonical lifecycle usage summary."""
        return self.list_funnels_in_use(organization_id=organization_id, group_entity_id=group_entity_id)

    def list_funnels_in_use(self, organization_id: str, group_entity_id: str | None = None) -> dict[str, object]:
        """Legacy funnel usage summary kept for compatibility."""
        try:
            rows = self.db_model_service.list_pipeline(
                organization_id=organization_id,
                group_entity_id=group_entity_id,
            )
            lifecycle_keys = sorted({row.lifecycle_key for row in rows if row.lifecycle_key})
            return {
                "organization_id": organization_id,
                "group_entity_id": group_entity_id,
                "lifecycle_keys": lifecycle_keys,
                "is_multi_lifecycle": len(lifecycle_keys) > 1,
                "job_id": group_entity_id,
                "funnels": lifecycle_keys,
                "is_multi_funnel": len(lifecycle_keys) > 1,
            }
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to list lifecycle usage: {exc}") from exc

    def refresh_lifecycle_heatmap(self, request: HeatmapRefreshRequest | dict[str, object]) -> HeatmapRefreshResponse:
        """Canonical lifecycle heatmap refresh."""
        return self.refresh_heatmap(request)

    def refresh_heatmap(self, request: HeatmapRefreshRequest | dict[str, object]) -> HeatmapRefreshResponse:
        """Legacy heatmap refresh kept for compatibility."""
        try:
            refresh = request if isinstance(request, HeatmapRefreshRequest) else HeatmapRefreshRequest.from_dict(request)
            buckets = self.db_model_service.aggregate_heatmap(
                organization_id=refresh.organization_id,
                group_entity_id=refresh.group_entity_id,
            )
            responses = [
                HeatmapBucketResponse(
                    organization_id=bucket.organization_id,
                    group_entity_id=bucket.group_entity_id,
                    state_key=bucket.state_key,
                    total_count=bucket.total_count,
                    critical_count=bucket.critical_count,
                    warning_count=bucket.warning_count,
                )
                for bucket in buckets
            ]
            return HeatmapRefreshResponse(rows_updated=len(responses), buckets=responses)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to refresh lifecycle heatmap: {exc}") from exc

    def upsert_lifecycle_projection_for_actor(
        self,
        actor: dict[str, object],
        request: UpsertPipelineProjectionRequest,
    ) -> PipelineProjectionResponse:
        """Canonical actor-scoped lifecycle upsert."""
        return self.upsert_pipeline_projection_for_actor(actor=actor, request=request)

    def upsert_pipeline_projection_for_actor(
        self,
        actor: dict[str, object],
        request: UpsertPipelineProjectionRequest,
    ) -> PipelineProjectionResponse:
        """Legacy actor-scoped pipeline upsert kept for compatibility."""
        organization_id = request.organization_id or self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(actor, "projection", "write", organization_id)
        normalized_request = UpsertPipelineProjectionRequest(
            organization_id=organization_id,
            subject_entity_id=request.subject_entity_id,
            group_entity_id=request.group_entity_id,
            state_key=request.state_key,
            sla_due_at=request.sla_due_at,
            lifecycle_key=request.lifecycle_key,
            denormalized_data=dict(request.denormalized_data),
        )
        return self.upsert_pipeline_projection(normalized_request)

    def list_lifecycle_views_for_actor(
        self,
        actor: dict[str, object],
        request: PipelineListRequest,
    ) -> PipelineProjectionListResponse:
        """Canonical actor-scoped lifecycle list."""
        return self.list_pipeline_view_for_actor(actor=actor, request=request)

    def list_lifecycle_projections_for_actor(
        self,
        actor: dict[str, object],
        request: PipelineListRequest,
    ) -> PipelineProjectionListResponse:
        """Canonical lifecycle projection list alias used by controllers."""
        return self.list_lifecycle_views_for_actor(actor=actor, request=request)

    def list_pipeline_view_for_actor(
        self,
        actor: dict[str, object],
        request: PipelineListRequest,
    ) -> PipelineProjectionListResponse:
        """Legacy actor-scoped pipeline list kept for compatibility."""
        organization_id = request.organization_id or self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(actor, "projection", "read", organization_id)
        normalized_request = PipelineListRequest(
            organization_id=organization_id,
            state_key=request.state_key,
            group_entity_id=request.group_entity_id,
            lifecycle_key=request.lifecycle_key,
            sla_risk=request.sla_risk,
        )
        rows = self.list_pipeline_view(normalized_request)
        return PipelineProjectionListResponse(items=rows)

    def get_lifecycle_projection_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        subject_entity_id: str,
    ) -> PipelineProjectionResponse:
        """Canonical actor-scoped lifecycle get."""
        return self.get_pipeline_projection_for_actor(
            actor=actor,
            organization_id=organization_id,
            subject_entity_id=subject_entity_id,
        )

    def get_pipeline_projection_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        subject_entity_id: str,
    ) -> PipelineProjectionResponse:
        """Legacy actor-scoped pipeline get kept for compatibility."""
        self._authorize_actor_operation(actor, "projection", "read", organization_id)
        response = self.get_pipeline_projection(organization_id=organization_id, subject_entity_id=subject_entity_id)
        if response is None:
            raise NotFoundError("projection not found")
        return response

    def list_lifecycle_usage_for_actor(
        self,
        actor: dict[str, object],
        request: PipelineListRequest,
    ) -> FunnelUsageResponse:
        """Canonical actor-scoped lifecycle usage."""
        return self.list_funnels_for_actor(actor=actor, request=request)

    def list_funnels_for_actor(
        self,
        actor: dict[str, object],
        request: PipelineListRequest,
    ) -> FunnelUsageResponse:
        """Legacy actor-scoped funnel usage kept for compatibility."""
        organization_id = request.organization_id or self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(actor, "projection", "read", organization_id)
        summary = self.list_funnels_in_use(
            organization_id=organization_id,
            group_entity_id=request.group_entity_id,
        )
        return FunnelUsageResponse(
            organization_id=str(summary["organization_id"]),
            group_entity_id=summary.get("group_entity_id"),  # type: ignore[arg-type]
            lifecycle_keys=list(summary["lifecycle_keys"]),  # type: ignore[arg-type]
            is_multi_lifecycle=bool(summary["is_multi_lifecycle"]),
        )

    def refresh_lifecycle_heatmap_for_actor(
        self,
        actor: dict[str, object],
        request: HeatmapRefreshRequest,
    ) -> HeatmapRefreshResponse:
        """Canonical actor-scoped lifecycle heatmap refresh."""
        return self.refresh_heatmap_for_actor(actor=actor, request=request)

    def refresh_heatmap_for_actor(
        self,
        actor: dict[str, object],
        request: HeatmapRefreshRequest,
    ) -> HeatmapRefreshResponse:
        """Legacy actor-scoped heatmap refresh kept for compatibility."""
        organization_id = request.organization_id or self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(actor, "projection", "write", organization_id)
        normalized_request = HeatmapRefreshRequest(
            organization_id=organization_id,
            group_entity_id=request.group_entity_id,
        )
        return self.refresh_heatmap(normalized_request)

    def _authorize_actor_operation(
        self,
        actor: dict[str, object],
        resource: str,
        action: str,
        organization_id: str,
    ) -> None:
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_organization_id:
            raise AuthorizationError("Forbidden organization scope")

    @staticmethod
    def _resolve_identity_service(dependencies: tuple[object, ...]) -> object | None:
        for dependency in dependencies:
            if hasattr(dependency, "check_access"):
                return dependency
        return None

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field_name: str) -> str:
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"Missing actor field: {field_name}")
        return value

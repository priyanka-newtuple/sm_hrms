"""Response models for views with legacy compatibility aliases."""

from __future__ import annotations

from pydantic import Field, model_validator

try:
    from common.data_model import BaseModel as PydanticBaseModel
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.data_model import BaseModel as PydanticBaseModel


class ProjectionsStatusResponse(PydanticBaseModel):
    module: str
    status: str
    started: bool

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class PipelineProjectionResponse(PydanticBaseModel):
    organization_id: str
    subject_entity_id: str
    group_entity_id: str
    state_key: str
    sla_due_at: str | None = None
    sla_risk: str | None = None
    lifecycle_key: str | None = None
    denormalized_data: dict[str, object] = Field(default_factory=dict)
    application_id: str | None = None
    job_id: str | None = None
    current_state: str | None = None
    funnel_key: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> PipelineProjectionResponse:
        self.application_id = self.application_id or self.subject_entity_id
        self.job_id = self.job_id or self.group_entity_id
        self.current_state = self.current_state or self.state_key
        self.funnel_key = self.funnel_key if self.funnel_key is not None else self.lifecycle_key
        self.denormalized_data = dict(self.denormalized_data or {})
        return self

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class PipelineProjectionListResponse(PydanticBaseModel):
    items: list[PipelineProjectionResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"count": len(self.items), "items": [item.to_dict() for item in self.items]}


class FunnelUsageResponse(PydanticBaseModel):
    organization_id: str
    group_entity_id: str | None = None
    lifecycle_keys: list[str] = Field(default_factory=list)
    is_multi_lifecycle: bool = False
    job_id: str | None = None
    funnels: list[str] = Field(default_factory=list)
    is_multi_funnel: bool = False

    @model_validator(mode="after")
    def normalize_fields(self) -> FunnelUsageResponse:
        self.job_id = self.job_id if self.job_id is not None else self.group_entity_id
        if not self.group_entity_id:
            self.group_entity_id = self.job_id
        if not self.lifecycle_keys and self.funnels:
            self.lifecycle_keys = list(self.funnels)
        if not self.funnels and self.lifecycle_keys:
            self.funnels = list(self.lifecycle_keys)
        if not self.is_multi_lifecycle:
            self.is_multi_lifecycle = len(set(self.lifecycle_keys)) > 1
        if not self.is_multi_funnel:
            self.is_multi_funnel = self.is_multi_lifecycle
        return self

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class HeatmapBucketResponse(PydanticBaseModel):
    organization_id: str
    group_entity_id: str
    state_key: str
    total_count: int
    critical_count: int
    warning_count: int
    job_id: str | None = None
    current_state: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> HeatmapBucketResponse:
        self.job_id = self.job_id or self.group_entity_id
        self.current_state = self.current_state or self.state_key
        return self

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class HeatmapRefreshResponse(PydanticBaseModel):
    rows_updated: int
    buckets: list[HeatmapBucketResponse] = Field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"rows_updated": self.rows_updated, "buckets": [bucket.to_dict() for bucket in self.buckets]}

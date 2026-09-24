"""Dashboard response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from common.data_model import BaseModel as PydanticBaseModel


class DashboardRead(PydanticBaseModel):
    """Dashboard definition returned to the UI."""

    id: str
    key: str
    display_name: str
    description: str | None = None
    config: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime | None = None


class DashboardStatusResponse(PydanticBaseModel):
    """Dashboard module status."""

    module: str
    status: str
    started: bool


class DashboardQueryFieldRead(PydanticBaseModel):
    key: str
    label: str
    type: Literal["string", "number", "boolean", "date"]
    groupable: bool = True
    filterable: bool = True
    aggregatable: bool = False


class DashboardQueryJoinRead(PydanticBaseModel):
    alias: str
    label: str
    description: str | None = None
    fields: list[DashboardQueryFieldRead]


class DashboardQuerySourceRead(PydanticBaseModel):
    id: str
    label: str
    description: str | None = None
    fields: list[DashboardQueryFieldRead]
    joins: list[DashboardQueryJoinRead] = []


class DashboardQuerySourcesResponse(PydanticBaseModel):
    sources: list[DashboardQuerySourceRead]


class DashboardQueryPreviewResponse(PydanticBaseModel):
    source: str
    columns: list[DashboardQueryFieldRead]
    rows: list[dict[str, Any]]
    row_count: int
    suggested_visuals: list[str]


class DashboardMetricParamRead(PydanticBaseModel):
    key: str
    label: str
    type: Literal["string", "number", "date"]
    source: Literal["workflows", "entity_types", "states", "event_types", "entity_fields"] | None = None


class DashboardMetricFieldRead(PydanticBaseModel):
    key: str
    label: str


class DashboardMetricRead(PydanticBaseModel):
    """A metric available to bind a widget to."""

    key: str
    label: str
    description: str
    output: Literal["series", "scalar", "rows", "gauge", "multiseries"]
    default_visuals: list[str]
    params: list[DashboardMetricParamRead] = []
    fields: list[DashboardMetricFieldRead] = []


class DashboardMetricsResponse(PydanticBaseModel):
    metrics: list[DashboardMetricRead]
    fields_scoped: bool = True


class DashboardDataResponse(PydanticBaseModel):
    """Map of widget_id -> rendered metric payload (or an error per widget)."""

    results: dict[str, Any]


class DashboardFilterOption(PydanticBaseModel):
    value: str
    label: str


class DashboardFilterOptionsResponse(PydanticBaseModel):
    """Org-scoped option lists keyed by MetricParam.source."""

    workflows: list[DashboardFilterOption] = []
    entity_types: list[DashboardFilterOption] = []
    states: list[DashboardFilterOption] = []
    event_types: list[DashboardFilterOption] = []
    entity_fields: list[DashboardFilterOption] = []

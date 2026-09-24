"""Dashboard request models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from exceptions import ValidationError


class DashboardUpdateRequest(PydanticBaseModel):
    """Update dashboard JSON document."""

    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model(self) -> "DashboardUpdateRequest":
        if not isinstance(self.config, dict):
            raise ValidationError("config must be a JSON object")
        if not isinstance(self.config.get("widgets"), list):
            raise ValidationError("config must include a widgets array")
        return self


class DashboardQuerySelect(PydanticBaseModel):
    field: str = Field(min_length=1, max_length=128)
    alias: str | None = Field(default=None, max_length=128)


class DashboardQueryJoin(PydanticBaseModel):
    alias: str = Field(min_length=1, max_length=64)


class DashboardQueryFilter(PydanticBaseModel):
    field: str = Field(min_length=1, max_length=128)
    op: Literal["eq", "neq", "contains", "gt", "gte", "lt", "lte", "in"]
    value: Any


class DashboardQueryAggregation(PydanticBaseModel):
    field: str = Field(min_length=1, max_length=128)
    op: Literal["count", "sum", "avg", "min", "max"]
    alias: str = Field(min_length=1, max_length=128)


class DashboardQuerySort(PydanticBaseModel):
    field: str = Field(min_length=1, max_length=128)
    direction: Literal["asc", "desc"] = "asc"


class DashboardQueryDefinitionRequest(PydanticBaseModel):
    id: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, max_length=128)
    source: str = Field(min_length=1, max_length=64)
    select: list[DashboardQuerySelect] = Field(default_factory=list)
    joins: list[DashboardQueryJoin] = Field(default_factory=list)
    filters: list[DashboardQueryFilter] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[DashboardQueryAggregation] = Field(default_factory=list)
    sort: list[DashboardQuerySort] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)


class DashboardQueryPreviewRequest(PydanticBaseModel):
    query: DashboardQueryDefinitionRequest


class DashboardDataItem(PydanticBaseModel):
    """A single widget's data request: a metric key or an inline query, plus filters."""

    widget_id: str = Field(min_length=1, max_length=128)
    metric: str | None = Field(default=None, max_length=128)
    query: DashboardQueryDefinitionRequest | None = Field(default=None)
    filters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_one_source(self) -> "DashboardDataItem":
        if bool(self.metric) == bool(self.query):
            raise ValidationError("exactly one of 'metric' or 'query' must be set")
        return self


class DashboardDataRequest(PydanticBaseModel):
    """Batched data request to hydrate a whole dashboard in one call."""

    items: list[DashboardDataItem] = Field(default_factory=list)
    anchor_entity_id: str | None = Field(default=None, max_length=128)

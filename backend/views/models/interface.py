"""Interface models and contracts for views."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from pydantic import ConfigDict, Field

try:
    from common.data_model import BaseModel as PydanticBaseModel
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.data_model import BaseModel as PydanticBaseModel

try:
    from common.enums import ProjectionSlaRisk
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.enums import ProjectionSlaRisk


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class PipelineProjectionContract(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: str
    subject_entity_id: str
    group_entity_id: str
    state_key: str
    sla_due_at: str | None = None
    lifecycle_key: str | None = None
    denormalized_data: dict[str, object] = Field(default_factory=dict)

    @property
    def application_id(self) -> str:
        return self.subject_entity_id

    @property
    def job_id(self) -> str:
        return self.group_entity_id

    @property
    def current_state(self) -> str:
        return self.state_key

    @property
    def funnel_key(self) -> str | None:
        return self.lifecycle_key


class HeatmapBucket(PydanticBaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: str
    group_entity_id: str
    state_key: str
    total_count: int
    critical_count: int
    warning_count: int

    @property
    def job_id(self) -> str:
        return self.group_entity_id

    @property
    def current_state(self) -> str:
        return self.state_key


class ProjectionReadPort(Protocol):
    """Read contract consumed by dependent managers."""

    def list_pipeline(
        self,
        organization_id: str,
        state_key: str | None = None,
        group_entity_id: str | None = None,
        lifecycle_key: str | None = None,
        sla_risk: str | None = None,
    ) -> list[PipelineProjectionContract]:
        """Return filtered pipeline views."""


def compute_sla_risk(sla_due_at: str | None, now: datetime | None = None) -> str | None:
    """Compute SLA risk from due timestamp.

    - CRITICAL: due time passed or <= 2 hours
    - WARNING: <= 8 hours
    - OK: > 8 hours
    - None: no SLA due timestamp
    """
    due = _parse_datetime(sla_due_at)
    if due is None:
        return None

    current = now or datetime.now(timezone.utc)
    remaining_hours = (due - current).total_seconds() / 3600

    if remaining_hours <= 2:
        return ProjectionSlaRisk.CRITICAL.value
    if remaining_hours <= 8:
        return ProjectionSlaRisk.WARNING.value
    return ProjectionSlaRisk.OK.value

"""Request models for views with legacy compatibility aliases."""

from __future__ import annotations

from pydantic import Field, model_validator

try:
    from common.data_model import BaseModel as PydanticBaseModel
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.data_model import BaseModel as PydanticBaseModel

try:
    from common.enums import ProjectionSlaRisk
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.enums import ProjectionSlaRisk

try:
    from exceptions import ValidationError
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.exceptions import ValidationError


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _append_legacy_field(items: list[str], field_name: str, used: bool) -> None:
    if used and field_name not in items:
        items.append(field_name)


class UpsertPipelineProjectionRequest(PydanticBaseModel):
    organization_id: str
    subject_entity_id: str | None = None
    group_entity_id: str | None = None
    state_key: str | None = None
    sla_due_at: str | None = None
    lifecycle_key: str | None = None
    denormalized_data: dict[str, object] = Field(default_factory=dict)

    application_id: str | None = None
    job_id: str | None = None
    current_state: str | None = None
    funnel_key: str | None = None

    deprecated_fields: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def normalize_fields(self) -> UpsertPipelineProjectionRequest:
        self.organization_id = _non_empty(str(self.organization_id), "organization_id")

        used_application_id = _optional_text(self.application_id) is not None
        used_job_id = _optional_text(self.job_id) is not None
        used_current_state = _optional_text(self.current_state) is not None
        used_funnel_key = _optional_text(self.funnel_key) is not None

        subject_entity_id = _optional_text(self.subject_entity_id) or _optional_text(self.application_id)
        group_entity_id = _optional_text(self.group_entity_id) or _optional_text(self.job_id)
        state_key = _optional_text(self.state_key) or _optional_text(self.current_state)
        lifecycle_key = _optional_text(self.lifecycle_key) or _optional_text(self.funnel_key)

        self.subject_entity_id = _non_empty(subject_entity_id or "", "subject_entity_id")
        self.group_entity_id = _non_empty(group_entity_id or "", "group_entity_id")
        self.state_key = _non_empty(state_key or "", "state_key").upper()
        self.lifecycle_key = lifecycle_key
        self.sla_due_at = _optional_text(self.sla_due_at)

        if not isinstance(self.denormalized_data, dict):
            raise ValueError("denormalized_data must be a dict")
        self.denormalized_data = dict(self.denormalized_data)

        self.application_id = self.subject_entity_id
        self.job_id = self.group_entity_id
        self.current_state = self.state_key
        self.funnel_key = self.lifecycle_key

        self.deprecated_fields = []
        _append_legacy_field(self.deprecated_fields, "application_id", used_application_id)
        _append_legacy_field(self.deprecated_fields, "job_id", used_job_id)
        _append_legacy_field(self.deprecated_fields, "current_state", used_current_state)
        _append_legacy_field(self.deprecated_fields, "funnel_key", used_funnel_key)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> UpsertPipelineProjectionRequest:
        try:
            return cls.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(str(exc)) from exc

    def deprecated_field_names(self) -> list[str]:
        return list(dict.fromkeys(self.deprecated_fields))


class PipelineListRequest(PydanticBaseModel):
    organization_id: str
    state_key: str | None = None
    group_entity_id: str | None = None
    lifecycle_key: str | None = None
    sla_risk: str | None = None

    current_state: str | None = None
    job_id: str | None = None
    funnel_key: str | None = None

    deprecated_fields: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def normalize_fields(self) -> PipelineListRequest:
        self.organization_id = _non_empty(str(self.organization_id), "organization_id")

        used_current_state = _optional_text(self.current_state) is not None
        used_job_id = _optional_text(self.job_id) is not None
        used_funnel_key = _optional_text(self.funnel_key) is not None

        state_key = _optional_text(self.state_key) or _optional_text(self.current_state)
        group_entity_id = _optional_text(self.group_entity_id) or _optional_text(self.job_id)
        lifecycle_key = _optional_text(self.lifecycle_key) or _optional_text(self.funnel_key)

        self.state_key = state_key.upper() if state_key else None
        self.group_entity_id = group_entity_id
        self.lifecycle_key = lifecycle_key

        self.sla_risk = _optional_text(self.sla_risk)
        if self.sla_risk:
            self.sla_risk = self.sla_risk.upper()
            valid = set(ProjectionSlaRisk.list())
            if self.sla_risk not in valid:
                raise ValueError(f"sla_risk must be one of {sorted(valid)}")

        self.current_state = self.state_key
        self.job_id = self.group_entity_id
        self.funnel_key = self.lifecycle_key

        self.deprecated_fields = []
        _append_legacy_field(self.deprecated_fields, "current_state", used_current_state)
        _append_legacy_field(self.deprecated_fields, "job_id", used_job_id)
        _append_legacy_field(self.deprecated_fields, "funnel_key", used_funnel_key)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> PipelineListRequest:
        try:
            return cls.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(str(exc)) from exc

    def deprecated_field_names(self) -> list[str]:
        return list(dict.fromkeys(self.deprecated_fields))


class HeatmapRefreshRequest(PydanticBaseModel):
    organization_id: str
    group_entity_id: str | None = None

    job_id: str | None = None

    deprecated_fields: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def normalize_fields(self) -> HeatmapRefreshRequest:
        self.organization_id = _non_empty(str(self.organization_id), "organization_id")
        used_job_id = _optional_text(self.job_id) is not None
        self.group_entity_id = _optional_text(self.group_entity_id) or _optional_text(self.job_id)
        self.job_id = self.group_entity_id

        self.deprecated_fields = []
        _append_legacy_field(self.deprecated_fields, "job_id", used_job_id)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> HeatmapRefreshRequest:
        try:
            return cls.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(str(exc)) from exc

    def deprecated_field_names(self) -> list[str]:
        return list(dict.fromkeys(self.deprecated_fields))

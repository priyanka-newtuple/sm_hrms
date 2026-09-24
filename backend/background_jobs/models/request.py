"""Request models for background_jobs."""

from __future__ import annotations

from pydantic import Field, field_validator

from common.data_model import BaseModel as PydanticBaseModel


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class IntakeSourceFileRequest(PydanticBaseModel):
    """Request model for a single intake source file."""

    filename: str = Field(..., min_length=1, max_length=1024, description="Source filename")
    content_type: str = Field(..., min_length=1, max_length=255, description="MIME type")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    metadata: dict[str, object] = Field(default_factory=dict, description="Optional file metadata")

    @field_validator("filename", "content_type", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: object) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("field must be a non-empty string")
        return normalized

    @field_validator("metadata", mode="before")
    @classmethod
    def _validate_metadata(cls, value: object) -> dict[str, object]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("metadata must be a dictionary")
        return dict(value)


class CreateIntakeJobRequest(PydanticBaseModel):
    """Request model for creating an intake job."""

    organization_id: str = Field(..., min_length=1, description="Organization identifier")
    source_type: str = Field(..., min_length=1, max_length=100, description="Input source type")
    subject_entity_type: str | None = Field(
        default=None, max_length=255, description="Target entity type"
    )
    files: list[IntakeSourceFileRequest] = Field(..., min_length=1, description="Input files")
    context: dict[str, object] = Field(
        default_factory=dict, description="Additional contextual payload"
    )

    @field_validator("organization_id", "source_type", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: object) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("field must be a non-empty string")
        return normalized

    @field_validator("source_type")
    @classmethod
    def _normalize_source_type(cls, value: str) -> str:
        return value.lower()

    @field_validator("subject_entity_type", mode="before")
    @classmethod
    def _normalize_optional_subject_entity_type(cls, value: object) -> str | None:
        return _normalize_optional_text(str(value) if value is not None else None)

    @field_validator("context", mode="before")
    @classmethod
    def _validate_context(cls, value: object) -> dict[str, object]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("context must be a dictionary")
        return dict(value)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> CreateIntakeJobRequest:
        return cls.model_validate(payload)


class UploadIntakeSourceRequest(CreateIntakeJobRequest):
    """Request model for upload intake source endpoint."""

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> UploadIntakeSourceRequest:
        return cls.model_validate(payload)

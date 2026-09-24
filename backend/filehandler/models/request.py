"""Request models for filehandler."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel


class FileUploadRequest(PydanticBaseModel):
    """Upload request payload."""

    type_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    owner_entity_id: str | None = None
    owner_entity_type: str | None = None
    upload_folder: str | None = Field(default=None, description="Optional subfolder within the type directory (e.g. '2026-Q2'). Injected between type_id and file_id in the storage path.")
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> Self:
        self.type_id = self.type_id.strip()
        self.filename = self.filename.strip()
        self.content_type = self.content_type.strip().lower()
        if self.upload_folder is not None:
            self.upload_folder = self.upload_folder.strip().strip("/") or None
        return self


class FileListRequest(PydanticBaseModel):
    """List filter request."""

    type_id: str | None = None
    status: str | None = None
    owner_entity_id: str | None = None


class FileTypeCreateRequest(PydanticBaseModel):
    """Create one file type config."""

    type_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    description: str = ""
    folder: str = Field(..., min_length=1)
    allowed_extensions: list[str] = Field(default_factory=list)
    max_size_mb: int = Field(default=10, ge=1)
    is_active: bool = True
    is_system: bool = False
    version_control_enabled: bool = False
    is_preview_thumbnail: bool = False
    upload_contexts: list[dict[str, object]] | None = None
    agent_config: dict[str, object] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> Self:
        self.type_id = self.type_id.strip()
        self.display_name = self.display_name.strip()
        self.folder = self.folder.strip()
        self.allowed_extensions = [e.strip().lower() for e in self.allowed_extensions if e.strip()]
        return self


class FileTypeUpdateRequest(PydanticBaseModel):
    """Patch file type config fields."""

    display_name: str | None = None
    description: str | None = None
    folder: str | None = None
    allowed_extensions: list[str] | None = None
    max_size_mb: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    version_control_enabled: bool | None = None
    is_preview_thumbnail: bool | None = None
    upload_contexts: list[dict[str, object]] | None = None
    agent_config: dict[str, object] | None = None
    metadata: dict[str, object] | None = None

    @model_validator(mode="after")
    def normalize(self) -> Self:
        if self.display_name is not None:
            self.display_name = self.display_name.strip() or None
        if self.folder is not None:
            self.folder = self.folder.strip() or None
        if self.allowed_extensions is not None:
            self.allowed_extensions = [
                e.strip().lower() for e in self.allowed_extensions if e.strip()
            ]
        return self


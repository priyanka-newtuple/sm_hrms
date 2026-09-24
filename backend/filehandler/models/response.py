"""Response models for filehandler."""

from __future__ import annotations

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel


class FilehandlerStatusResponse(PydanticBaseModel):
    """Module lifecycle status response."""

    module: str
    status: str
    started: bool


class FileRecordResponse(PydanticBaseModel):
    """Single file metadata response."""

    file_id: str
    organization_id: str
    type_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    status: str
    uploaded_by: str
    owner_entity_id: str | None = None
    owner_entity_type: str | None = None
    storage_provider: str = "local"
    metadata: dict[str, object] = Field(default_factory=dict)
    failure_reason: str | None = None
    auto_dispatched: bool = False
    auto_deduplicated: bool = False
    created_at: str
    updated_at: str


class FileListResponse(PydanticBaseModel):
    """Collection response for file records."""

    count: int
    items: list[FileRecordResponse] = Field(default_factory=list)


class FileTypeResponse(PydanticBaseModel):
    """File type response payload."""

    organization_id: str
    type_id: str
    display_name: str
    description: str
    folder: str
    allowed_extensions: list[str] = Field(default_factory=list)
    max_size_mb: int
    is_active: bool
    is_system: bool
    version_control_enabled: bool = False
    is_preview_thumbnail: bool = False
    upload_contexts: list[dict[str, object]] | None = None
    agent_config: dict[str, object] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class FileTypeListResponse(PydanticBaseModel):
    """List response for file type configs."""

    count: int
    items: list[FileTypeResponse] = Field(default_factory=list)


class FileTypeSeedResponse(PydanticBaseModel):
    """Seed operation response."""

    message: str
    created_count: int


class DownloadUrlResponse(PydanticBaseModel):
    """Download URL response — either a SAS URL (Azure) or a relative proxy path (local)."""

    url: str
    provider: str
    expires_in: int | None = None

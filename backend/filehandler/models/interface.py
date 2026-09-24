"""Shared contracts for filehandler module."""

from __future__ import annotations

from typing import Protocol

from pydantic import ConfigDict, Field

from common.data_model import BaseModel as PydanticBaseModel


from common.data_model import ExtendedStrEnum


class FileRecordStatus(ExtendedStrEnum):
    """Lifecycle status of stored file metadata."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    DELETED = "DELETED"


class AgentRunOutcome(ExtendedStrEnum):
    """The one agent-run status value `filehandler` branches on when deciding a
    processed document's final status. Mirrors the "completed" value of the agent
    module's own `status` field (a plain `str` on `AgentRunResponse`) — kept here,
    not imported from `agent`, so this module doesn't reach into another module's
    internals for a comparison it alone needs."""

    COMPLETED = "completed"


class FileTypeContract(PydanticBaseModel):
    """Generic file type configuration."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    organization_id: str
    type_id: str
    display_name: str
    allowed_extensions: list[str]
    max_size_mb: int
    is_active: bool = True
    version_control_enabled: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class FileStoragePort(Protocol):
    """Filesystem storage adapter contract for filehandler."""

    def put(self, storage_key: str, content: bytes, content_type: str) -> None:
        """Persist file content by storage key."""

    def get(self, storage_key: str) -> bytes | None:
        """Read file content by storage key."""

    def delete(self, storage_key: str) -> bool:
        """Delete file content by storage key."""

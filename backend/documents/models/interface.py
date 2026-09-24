"""Interface models and contracts for documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

try:
    from common.enums import DocumentStatus
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.enums import DocumentStatus

try:
    from exceptions import ValidationError
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.exceptions import ValidationError


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must be a non-empty string")
    return normalized


VALID_DOCUMENT_STATUSES = set(DocumentStatus.list())


@dataclass(frozen=True)
class DocumentOwnership:
    organization_id: str
    entity_id: str
    uploaded_by: str


@dataclass(frozen=True)
class ExtractionSummary:
    document_id: str
    extracted_text_length: int
    metadata_keys: tuple[str, ...]


class DocumentStoragePort(Protocol):
    """Abstract storage port for document binaries."""

    def store(self, document_id: str, content: str) -> None:
        """Persist document content."""

    def get(self, document_id: str) -> str | None:
        """Retrieve document content."""


class DocumentStatusGuard(Protocol):
    """Status validation contract."""

    def ensure_valid_status(self, status: str) -> str:
        """Return normalized status or raise ValueError."""


def normalize_status(status: str) -> str:
    normalized = _non_empty(status, "status").upper()
    if normalized not in VALID_DOCUMENT_STATUSES:
        raise ValidationError(
            f"status must be one of {sorted(VALID_DOCUMENT_STATUSES)}"
        )
    return normalized

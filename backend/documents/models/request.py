"""Request models for documents."""

from __future__ import annotations

from dataclasses import dataclass, field

from .interface import normalize_status


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


@dataclass
class UploadDocumentRequest:
    organization_id: str
    entity_id: str
    filename: str
    content_type: str
    uploaded_by: str
    content: str
    field_key: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> UploadDocumentRequest:
        organization_id = _non_empty(str(payload.get("organization_id", "")), "organization_id")
        entity_id = _non_empty(str(payload.get("entity_id", "")), "entity_id")
        field_key_raw = payload.get("field_key")
        field_key = (
            _non_empty(str(field_key_raw), "field_key")
            if field_key_raw is not None
            else None
        )
        filename = _non_empty(str(payload.get("filename", "")), "filename")
        content_type = _non_empty(str(payload.get("content_type", "")), "content_type").lower()
        uploaded_by = _non_empty(str(payload.get("uploaded_by", "")), "uploaded_by")
        content = _non_empty(str(payload.get("content", "")), "content")
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")
        return cls(
            organization_id=organization_id,
            entity_id=entity_id,
            field_key=field_key,
            filename=filename,
            content_type=content_type,
            uploaded_by=uploaded_by,
            content=content,
            metadata=dict(metadata),
        )


@dataclass
class UpdateDocumentStatusRequest:
    organization_id: str
    document_id: str
    status: str
    reason: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> UpdateDocumentStatusRequest:
        organization_id = _non_empty(str(payload.get("organization_id", "")), "organization_id")
        document_id = _non_empty(str(payload.get("document_id", "")), "document_id")
        status = normalize_status(str(payload.get("status", "")))
        reason_raw = payload.get("reason")
        reason = str(reason_raw).strip() if reason_raw else None
        return cls(
            organization_id=organization_id,
            document_id=document_id,
            status=status,
            reason=reason,
        )


@dataclass
class ListDocumentsRequest:
    organization_id: str
    entity_id: str | None = None
    status: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> ListDocumentsRequest:
        organization_id = _non_empty(str(payload.get("organization_id", "")), "organization_id")
        entity_raw = payload.get("entity_id")
        entity_id = str(entity_raw).strip() if entity_raw else None
        status_raw = payload.get("status")
        status = normalize_status(str(status_raw)) if status_raw else None
        return cls(organization_id=organization_id, entity_id=entity_id, status=status)

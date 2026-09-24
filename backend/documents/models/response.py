"""Response models for documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class DocumentsStatusResponse:
    module: str
    status: str
    started: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class DocumentResponse:
    document_id: str
    organization_id: str
    entity_id: str
    filename: str
    content_type: str
    status: str
    uploaded_by: str
    created_at: str
    updated_at: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class DocumentStatusResponse:
    document_id: str
    organization_id: str
    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class DocumentListResponse:
    items: list[DocumentResponse] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "count": len(self.items),
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class DocumentExtractionSummaryResponse:
    document_id: str
    extracted_text_length: int
    metadata_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

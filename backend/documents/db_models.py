"""Persistence adapters for documents."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from common.enums import DocumentStatus
from exceptions import NotFoundError, PersistenceError, ValidationError
from filehandler.models.interface import FileRecordStatus
from filehandler.models.request import FileListRequest, FileUploadRequest

from .models.interface import normalize_status
from .models.request import UpdateDocumentStatusRequest, UploadDocumentRequest


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentRecord:
    document_id: str
    organization_id: str
    entity_id: str
    filename: str
    content_type: str
    status: str
    uploaded_by: str
    metadata: dict[str, object] = field(default_factory=dict)
    extraction_text: str | None = None
    failure_reason: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


class DocumentsModelService:
    """Document persistence backed by filehandler in production.

    The in-memory path remains only for dependency-free unit tests. Production
    passes the shared filehandler manager, which stores metadata in PostgreSQL
    and bytes through its configured local/Azure/S3 storage provider.
    """

    _DOCUMENT_MARKER = "_documents_api"
    _EXTRACTION_TEXT = "_documents_extraction_text"
    _TEXT_TYPE_ID = "generic_text"
    _BINARY_TYPE_ID = "generic_document"

    def __init__(
        self, database_service_manager, *, filehandler_service_manager=None
    ) -> None:  # noqa: ANN001
        super().__init__()
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            self.database_manager.postgres_db_service()
            if self.database_manager and hasattr(self.database_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.filehandler_service_manager = filehandler_service_manager
        self.module_name = "documents"
        self._documents: dict[tuple[str, str], DocumentRecord] = {}
        self._blob_store: dict[str, str] = {}

    def create_document(self, request: UploadDocumentRequest) -> DocumentRecord:
        try:
            if self.filehandler_service_manager is not None:
                return self._create_durable_document(request)
            document_id = str(uuid4())
            now = _utc_now()
            record = DocumentRecord(
                document_id=document_id,
                organization_id=request.organization_id,
                entity_id=request.entity_id,
                filename=request.filename,
                content_type=request.content_type,
                status=DocumentStatus.PENDING.value,
                uploaded_by=request.uploaded_by,
                metadata=dict(request.metadata),
                created_at=now,
                updated_at=now,
            )
            self._documents[(request.organization_id, document_id)] = record
            self._blob_store[document_id] = request.content
            return record
        except (NotFoundError, PersistenceError, ValidationError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(f"Unable to create document: {exc}") from exc

    def update_status(self, request: UpdateDocumentStatusRequest) -> DocumentRecord:
        if self.filehandler_service_manager is not None:
            record = self.get_document(request.organization_id, request.document_id)
            if record is None:
                raise NotFoundError("document not found")
            status = normalize_status(request.status)
            storage_status = (
                FileRecordStatus.UPLOADED.value
                if status == DocumentStatus.PENDING.value
                else status
            )
            self.filehandler_service_manager.db_model_service.set_file_status(
                request.organization_id,
                request.document_id,
                storage_status,
                request.reason if status == DocumentStatus.FAILED.value else None,
            )
            updated = self.get_document(request.organization_id, request.document_id)
            if updated is None:
                raise NotFoundError("document not found")
            return updated
        key = (request.organization_id, request.document_id)
        if key not in self._documents:
            raise NotFoundError("document not found")
        record = self._documents[key]
        record.status = normalize_status(request.status)
        record.failure_reason = request.reason if record.status == DocumentStatus.FAILED.value else None
        record.updated_at = _utc_now()
        return record

    def set_extraction_text(self, organization_id: str, document_id: str, text: str) -> DocumentRecord:
        if self.filehandler_service_manager is not None:
            updated = self.filehandler_service_manager.db_model_service.merge_file_metadata(
                organization_id, document_id, {self._EXTRACTION_TEXT: text}
            )
            if updated is None:
                raise NotFoundError("document not found")
            record = self._durable_record(updated)
            if record is None:
                raise NotFoundError("document not found")
            return record
        key = (organization_id, document_id)
        if key not in self._documents:
            raise NotFoundError("document not found")
        record = self._documents[key]
        record.extraction_text = text
        record.updated_at = _utc_now()
        return record

    def get_document(self, organization_id: str, document_id: str) -> DocumentRecord | None:
        if self.filehandler_service_manager is not None:
            try:
                row = self.filehandler_service_manager.get_file(
                    organization_id, document_id
                )
            except NotFoundError:
                return None
            return self._durable_record(row)
        return self._documents.get((organization_id, document_id))

    def list_documents(
        self,
        organization_id: str,
        entity_id: str | None = None,
        status: str | None = None,
    ) -> list[DocumentRecord]:
        if self.filehandler_service_manager is not None:
            storage_status = (
                FileRecordStatus.UPLOADED.value
                if status == DocumentStatus.PENDING.value
                else status
            )
            response = self.filehandler_service_manager.list_files(
                organization_id,
                FileListRequest(
                    status=storage_status,
                    owner_entity_id=entity_id,
                ),
            )
            records = [self._durable_record(row) for row in response.items]
            return [record for record in records if record is not None]
        rows: list[DocumentRecord] = []
        for (org_id, _), record in self._documents.items():
            if org_id != organization_id:
                continue
            if entity_id and record.entity_id != entity_id:
                continue
            if status and record.status != status:
                continue
            rows.append(record)
        return sorted(rows, key=lambda row: row.created_at)

    def get_blob(self, document_id: str) -> str | None:
        if self.filehandler_service_manager is not None:
            row = self.filehandler_service_manager.db_model_service.get_file_by_id(
                document_id
            )
            if row is None or not self._is_document(row):
                return None
            content = self.filehandler_service_manager.get_file_content(
                row.organization_id, document_id
            )
            if content is None:
                return None
            return content[0].decode("utf-8", errors="replace")
        return self._blob_store.get(document_id)

    def _create_durable_document(
        self, request: UploadDocumentRequest
    ) -> DocumentRecord:
        """Store one document through the shared filehandler persistence path."""
        type_id = (
            self._TEXT_TYPE_ID
            if request.content_type.startswith("text/")
            else self._BINARY_TYPE_ID
        )
        try:
            self.filehandler_service_manager.get_file_type(
                request.organization_id, type_id
            )
        except NotFoundError:
            self.filehandler_service_manager.seed_file_types(request.organization_id)
        response = self.filehandler_service_manager.upload_file(
            request.organization_id,
            request.uploaded_by,
            FileUploadRequest(
                type_id=type_id,
                filename=request.filename,
                content_type=request.content_type,
                content=self._filehandler_content(request),
                owner_entity_id=request.entity_id,
                metadata={
                    **dict(request.metadata),
                    self._DOCUMENT_MARKER: True,
                },
            ),
            skip_agent_dispatch=True,
        )
        record = self._durable_record(response)
        if record is None:
            raise PersistenceError("Unable to create document: durable record is missing")
        return record

    @staticmethod
    def _filehandler_content(request: UploadDocumentRequest) -> str:
        """Base64 payload the filehandler will decode back to real file bytes.

        Text content arrives as plain text and is base64-encoded here for the
        first time. Binary content (pdf/doc/docx) can only travel through this
        JSON string field pre-encoded as base64, so it is decoded back to real
        bytes and re-encoded rather than encoded a second time — encoding the
        base64 text itself left the filehandler's single decode recovering
        base64 text instead of the document.
        """
        if request.content_type.startswith("text/"):
            return base64.b64encode(request.content.encode("utf-8")).decode("ascii")
        try:
            raw_bytes = base64.b64decode(request.content.encode("utf-8"), validate=True)
        except Exception as exc:
            raise ValidationError("document content must be valid base64") from exc
        return base64.b64encode(raw_bytes).decode("ascii")

    @classmethod
    def _is_document(cls, row) -> bool:  # noqa: ANN001
        return bool(dict(getattr(row, "metadata", {}) or {}).get(cls._DOCUMENT_MARKER))

    @classmethod
    def _durable_record(cls, row) -> DocumentRecord | None:  # noqa: ANN001
        """Map a filehandler row while hiding documents-internal metadata."""
        if not cls._is_document(row):
            return None
        metadata = dict(row.metadata or {})
        extraction_text = metadata.pop(cls._EXTRACTION_TEXT, None)
        metadata.pop(cls._DOCUMENT_MARKER, None)
        storage_status = str(row.status)
        status = (
            DocumentStatus.PENDING.value
            if storage_status == FileRecordStatus.UPLOADED.value
            else storage_status
        )
        return DocumentRecord(
            document_id=row.file_id,
            organization_id=row.organization_id,
            entity_id=str(row.owner_entity_id or ""),
            filename=row.filename,
            content_type=row.content_type,
            status=status,
            uploaded_by=row.uploaded_by,
            metadata=metadata,
            extraction_text=str(extraction_text) if extraction_text is not None else None,
            failure_reason=row.failure_reason,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

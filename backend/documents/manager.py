"""Business logic manager for documents."""

from __future__ import annotations

from common.auth import actor_str
from common.enums import DocumentStatus, ModuleStatus
from exceptions import AuthorizationError, NotFoundError, ServiceError, ValidationError

from .models.interface import ExtractionSummary
from .models.request import ListDocumentsRequest, UpdateDocumentStatusRequest, UploadDocumentRequest
from .models.response import (
    DocumentExtractionSummaryResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentsStatusResponse,
    DocumentStatusResponse,
)


class DocumentsServiceManager:
    """Document ingestion and lifecycle orchestration service."""

    _SUPPORTED_CONTENT_TYPES = {
        "application/pdf",
        "text/plain",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    def __init__(
        self,
        documents_db_model_service,
        database_service_manager,
        config,
        identity_access_service_manager=None,
        *dependencies,
        entities_service_manager=None,
    ) -> None:  # noqa: ANN001
        self.documents_db_model_service = documents_db_model_service
        self.db_model_service = documents_db_model_service
        self.model_service = documents_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.module_name = "documents"
        self._started = False
        self.identity_access_service_manager = identity_access_service_manager or self._resolve_identity_service(
            dependencies
        )
        self.entities_service_manager = entities_service_manager

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> DocumentsStatusResponse:
        return DocumentsStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def upload_document(self, request: UploadDocumentRequest | dict[str, object]) -> DocumentResponse:
        try:
            upload = request if isinstance(request, UploadDocumentRequest) else UploadDocumentRequest.from_dict(request)
            if upload.content_type not in self._SUPPORTED_CONTENT_TYPES:
                raise ValidationError("unsupported content_type")

            if upload.field_key is not None:
                self._validate_document_field(upload)
            record = self.db_model_service.create_document(upload)

            # Stage-1 extraction placeholder: for text/*, persist normalized text preview.
            if upload.content_type.startswith("text/"):
                extracted = upload.content.strip()
                self.db_model_service.set_extraction_text(upload.organization_id, record.document_id, extracted)
                self.db_model_service.update_status(
                    UpdateDocumentStatusRequest(
                        organization_id=upload.organization_id,
                        document_id=record.document_id,
                        status=DocumentStatus.PROCESSED.value,
                    )
                )
                record = self.db_model_service.get_document(upload.organization_id, record.document_id) or record

            if upload.field_key is not None:
                self._append_document_reference(upload, record.document_id)
            return self._to_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceError(f"Unable to upload document: {exc}") from exc

    def update_document_status(
        self,
        request: UpdateDocumentStatusRequest | dict[str, object],
    ) -> DocumentStatusResponse:
        update = request if isinstance(request, UpdateDocumentStatusRequest) else UpdateDocumentStatusRequest.from_dict(request)
        record = self.db_model_service.update_status(update)
        return DocumentStatusResponse(
            document_id=record.document_id,
            organization_id=record.organization_id,
            status=record.status,
            reason=record.failure_reason,
        )

    def get_document(self, organization_id: str, document_id: str) -> DocumentResponse | None:
        record = self.db_model_service.get_document(organization_id=organization_id, document_id=document_id)
        if record is None:
            return None
        return self._to_response(record)

    def list_documents(
        self,
        request: ListDocumentsRequest | dict[str, object],
    ) -> DocumentListResponse:
        query = request if isinstance(request, ListDocumentsRequest) else ListDocumentsRequest.from_dict(request)
        rows = self.db_model_service.list_documents(
            organization_id=query.organization_id,
            entity_id=query.entity_id,
            status=query.status,
        )
        return DocumentListResponse(items=[self._to_response(row) for row in rows])

    def summarize_extraction(self, organization_id: str, document_id: str) -> ExtractionSummary | None:
        record = self.db_model_service.get_document(organization_id=organization_id, document_id=document_id)
        if record is None or not record.extraction_text:
            return None
        metadata_keys = tuple(sorted(record.metadata.keys()))
        return ExtractionSummary(
            document_id=record.document_id,
            extracted_text_length=len(record.extraction_text),
            metadata_keys=metadata_keys,
        )

    def upload_document_for_actor(
        self,
        actor: dict[str, object],
        request: UploadDocumentRequest,
    ) -> DocumentResponse:
        actor_user_id = self._require_actor_field(actor, "user_id")
        organization_id = request.organization_id or self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(actor, "document", "write", organization_id)
        if request.field_key is not None:
            self._authorize_field_write(actor, organization_id, request.entity_id, request.field_key)
        normalized_request = UploadDocumentRequest(
            organization_id=organization_id,
            entity_id=request.entity_id,
            field_key=request.field_key,
            filename=request.filename,
            content_type=request.content_type,
            uploaded_by=actor_user_id,
            content=request.content,
            metadata=dict(request.metadata),
        )
        return self.upload_document(normalized_request)

    def _authorize_field_write(
        self, actor: dict[str, object], organization_id: str, entity_id: str, field_key: str
    ) -> None:
        """Guard the target entity/field the same way a normal record edit would.

        upload_document is a system-level path with no actor, mirroring
        update_entity_record; this is upload_document_for_actor's equivalent of
        the guard_write update_entity_record_for_actor already performs before
        touching a record's data.
        """
        if self.entities_service_manager is None:
            raise ServiceError("documents service is not configured with the entities service")
        entity = self.entities_service_manager.get_entity_record(
            organization_id=organization_id, entity_id=entity_id
        )
        if entity is None:
            raise NotFoundError(f"entity '{entity_id}' was not found")
        self.entities_service_manager.guard_write(
            actor, organization_id, entity.entity_type_id, "edit", {field_key}
        )

    def _validate_document_field(self, upload: UploadDocumentRequest) -> None:
        """Require the requested key to be a document field on the entity schema."""
        entity, fields = self._entity_and_schema_fields(upload)
        matching_field = next(
            (field for field in fields if self._schema_field_key(field) == upload.field_key),
            None,
        )
        if matching_field is None:
            raise ValidationError(
                f"field_key '{upload.field_key}' does not exist on the entity schema"
            )
        field_type = str(
            matching_field.get("type") or matching_field.get("field_type") or ""
        ).strip()
        if field_type != "document":
            raise ValidationError(
                f"field_key '{upload.field_key}' must be type 'document', found "
                f"'{field_type or 'unknown'}'"
            )

        current_value = dict(entity.data or {}).get(upload.field_key)
        if current_value is not None and (
            not isinstance(current_value, list)
            or not all(isinstance(item, str) for item in current_value)
        ):
            raise ValidationError(
                f"document field '{upload.field_key}' must contain a list of document ids"
            )

    def _append_document_reference(
        self, upload: UploadDocumentRequest, document_id: str
    ) -> None:
        """Append one uploaded document id without replacing prior references.

        Goes through append_to_list_field's locked read-append-write rather
        than reading `data` here and writing the whole object back: two
        uploads racing the same field (or one racing an unrelated edit) would
        otherwise each replace `data` from their own stale snapshot, and the
        loser's change — a document id, or the unrelated edit — is silently
        lost.
        """
        updated = self.entities_service_manager.append_to_list_field(
            organization_id=upload.organization_id,
            entity_id=upload.entity_id,
            field_key=upload.field_key,
            value=document_id,
        )
        if updated is None:
            raise NotFoundError(f"entity '{upload.entity_id}' was not found")

    def _entity_and_schema_fields(
        self, upload: UploadDocumentRequest
    ) -> tuple[object, list[dict[str, object]]]:
        """Resolve one tenant-scoped entity and its configured field definitions."""
        if self.entities_service_manager is None:
            raise ServiceError("documents service is not configured with the entities service")
        entity = self.entities_service_manager.get_entity_record(
            organization_id=upload.organization_id,
            entity_id=upload.entity_id,
        )
        if entity is None:
            raise NotFoundError(f"entity '{upload.entity_id}' was not found")

        entity_type_name = self.entities_service_manager.get_entity_type_name_for_entity(
            upload.organization_id, upload.entity_id
        )
        if not entity_type_name:
            raise NotFoundError(f"entity schema for '{upload.entity_id}' was not found")

        form_fields = self.entities_service_manager.get_form_fields(
            upload.organization_id, entity_type_name
        )
        entity_type = self.entities_service_manager.get_entity_type_record(
            organization_id=upload.organization_id,
            name=entity_type_name,
        )
        schema_definition = dict(getattr(entity_type, "schema_definition", {}) or {})
        raw_fields = schema_definition.get("fields") or []
        fields = [dict(field) for field in form_fields if isinstance(field, dict)]
        fields.extend(dict(field) for field in raw_fields if isinstance(field, dict))
        return entity, fields

    @staticmethod
    def _schema_field_key(field: dict[str, object]) -> str:
        """Accept the key spellings used by form and entity-type schemas."""
        return str(field.get("field") or field.get("name") or field.get("id") or "").strip()

    def update_document_status_for_actor(
        self,
        actor: dict[str, object],
        request: UpdateDocumentStatusRequest,
    ) -> DocumentStatusResponse:
        organization_id = request.organization_id or self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(actor, "document", "write", organization_id)
        normalized_request = UpdateDocumentStatusRequest(
            organization_id=organization_id,
            document_id=request.document_id,
            status=request.status,
            reason=request.reason,
        )
        return self.update_document_status(normalized_request)

    def list_documents_for_actor(
        self,
        actor: dict[str, object],
        request: ListDocumentsRequest,
    ) -> DocumentListResponse:
        organization_id = request.organization_id or self._require_actor_field(actor, "organization_id")
        self._authorize_actor_operation(actor, "document", "read", organization_id)
        normalized_request = ListDocumentsRequest(
            organization_id=organization_id,
            entity_id=request.entity_id,
            status=request.status,
        )
        return self.list_documents(normalized_request)

    def get_document_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        document_id: str,
    ) -> DocumentResponse:
        self._authorize_actor_operation(actor, "document", "read", organization_id)
        response = self.get_document(organization_id=organization_id, document_id=document_id)
        if response is None:
            raise NotFoundError("document not found")
        return response

    def get_extraction_summary_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        document_id: str,
    ) -> DocumentExtractionSummaryResponse:
        self._authorize_actor_operation(actor, "document", "read", organization_id)
        summary = self.summarize_extraction(organization_id=organization_id, document_id=document_id)
        if summary is None:
            raise NotFoundError("document extraction summary not found")
        return DocumentExtractionSummaryResponse(
            document_id=summary.document_id,
            extracted_text_length=summary.extracted_text_length,
            metadata_keys=list(summary.metadata_keys),
        )

    def _authorize_actor_operation(
        self,
        actor: dict[str, object],
        resource: str,
        action: str,
        organization_id: str,
    ) -> None:
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_organization_id:
            raise AuthorizationError("Forbidden organization scope")

    @staticmethod
    def _resolve_identity_service(dependencies: tuple[object, ...]) -> object | None:
        for dependency in dependencies:
            if hasattr(dependency, "check_access"):
                return dependency
        return None

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field_name: str) -> str:
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"Missing actor field: {field_name}")
        return value

    @staticmethod
    def _to_response(record) -> DocumentResponse:  # noqa: ANN001
        return DocumentResponse(
            document_id=record.document_id,
            organization_id=record.organization_id,
            entity_id=record.entity_id,
            filename=record.filename,
            content_type=record.content_type,
            status=record.status,
            uploaded_by=record.uploaded_by,
            created_at=record.created_at,
            updated_at=record.updated_at,
            metadata=dict(record.metadata),
        )

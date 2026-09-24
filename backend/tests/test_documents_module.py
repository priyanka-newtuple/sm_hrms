from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from documents.controller import DocumentsRestController
from documents.db_models import DocumentsModelService
from documents.manager import DocumentsServiceManager
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import EntityRecordCreateRequest, EntityTypeCreateRequest
from exceptions import AuthorizationError, ValidationError
from filehandler.db_models import FilehandlerModelService
from filehandler.manager import FilehandlerServiceManager
from filehandler.models.request import FileTypeUpdateRequest
from workflow.models.interface import Guard, GuardType, Transition, matches_workflow_value
from workflow.services.transition_evaluation import TransitionEvaluationService


class _EntitiesService:
    def __init__(
        self,
        *,
        fields: list[dict[str, object]] | None = None,
        initial_data: dict[str, object] | None = None,
        deny_field_write: bool = False,
    ) -> None:
        self.fields = fields or [{"field": "attachments", "type": "document"}]
        self.initial_data = dict(initial_data or {})
        self.records: dict[str, SimpleNamespace] = {}
        self.deny_field_write = deny_field_write
        self.guard_write_calls: list[tuple] = []

    def get_entity_record(self, *, organization_id: str, entity_id: str):
        return self.records.setdefault(
            entity_id,
            SimpleNamespace(
                entity_id=entity_id,
                organization_id=organization_id,
                entity_type_id="type-1",
                data=dict(self.initial_data),
            ),
        )

    def get_entity_type_name_for_entity(
        self, organization_id: str, entity_id: str
    ) -> str:
        return "document_entity"

    def get_form_fields(self, organization_id: str, form_key: str):
        return list(self.fields)

    def get_entity_type_record(self, *, organization_id: str, name: str):
        return SimpleNamespace(schema_definition={"fields": list(self.fields)})

    def update_entity_record(self, *, organization_id: str, entity_id: str, request):
        record = self.get_entity_record(
            organization_id=organization_id, entity_id=entity_id
        )
        record.data = dict(request.data or {})
        return record

    def append_to_list_field(
        self, *, organization_id: str, entity_id: str, field_key: str, value: str
    ):
        record = self.get_entity_record(
            organization_id=organization_id, entity_id=entity_id
        )
        items = list(record.data.get(field_key) or [])
        items.append(value)
        record.data = {**record.data, field_key: items}
        return record

    def guard_write(self, actor, organization_id, entity_type_id, action, fields=None):
        self.guard_write_calls.append((actor, organization_id, entity_type_id, action, fields))
        if self.deny_field_write:
            raise AuthorizationError("Not allowed to edit fields: " + ", ".join(sorted(fields or [])))


def _build_manager() -> DocumentsServiceManager:
    db_service = DocumentsModelService(database_service_manager=None)
    return DocumentsServiceManager(db_service, database_service_manager=None, config=None)


def _build_capture_manager(
    *,
    fields: list[dict[str, object]] | None = None,
    initial_data: dict[str, object] | None = None,
    deny_field_write: bool = False,
) -> tuple[DocumentsServiceManager, _EntitiesService]:
    db_service = DocumentsModelService(database_service_manager=None)
    entities = _EntitiesService(
        fields=fields, initial_data=initial_data, deny_field_write=deny_field_write
    )
    return (
        DocumentsServiceManager(
            db_service,
            database_service_manager=None,
            config=None,
            entities_service_manager=entities,
        ),
        entities,
    )


def _upload_payload(*, entity_id: str = "ent-1", field_key: str = "attachments"):
    return {
        "organization_id": "org-1",
        "entity_id": entity_id,
        "field_key": field_key,
        "filename": "resume.txt",
        "content_type": "text/plain",
        "uploaded_by": "u-1",
        "content": "hello world",
        "metadata": {"source": "upload"},
    }


def test_documents_upload_and_extraction_summary() -> None:
    manager = _build_manager()

    uploaded = manager.upload_document(
        {
            "organization_id": "org-1",
            "entity_id": "ent-1",
            "filename": "resume.txt",
            "content_type": "text/plain",
            "uploaded_by": "u-1",
            "content": "hello world",
            "metadata": {"source": "upload"},
        }
    )

    assert uploaded.status == "PROCESSED"
    summary = manager.summarize_extraction("org-1", uploaded.document_id)
    assert summary is not None
    assert summary.extracted_text_length == 11


def test_documents_status_updates_and_filters() -> None:
    manager = _build_manager()

    uploaded = manager.upload_document(
        {
            "organization_id": "org-2",
            "entity_id": "ent-2",
            "filename": "resume.pdf",
            "content_type": "application/pdf",
            "uploaded_by": "u-2",
            "content": "binary-content",
        }
    )
    assert uploaded.status == "PENDING"

    status = manager.update_document_status(
        {
            "organization_id": "org-2",
            "document_id": uploaded.document_id,
            "status": "FAILED",
            "reason": "parse_error",
        }
    )
    assert status.status == "FAILED"

    failed = manager.list_documents(
        {
            "organization_id": "org-2",
            "status": "FAILED",
        }
    )
    assert failed.to_dict()["count"] == 1

    with pytest.raises(ValidationError):
        manager.upload_document(
            {
                "organization_id": "org-2",
                "entity_id": "ent-2",
                "filename": "bad.bin",
                "content_type": "application/octet-stream",
                "uploaded_by": "u-2",
                "content": "xxx",
            }
        )


def test_binary_document_content_is_encoded_exactly_once() -> None:
    """The filehandler expects base64 it can decode straight to real bytes.
    Binary content (pdf/doc/docx) can only travel through this JSON string
    field pre-encoded as base64 in the first place, so this must round-trip
    to the same bytes rather than encoding the base64 text a second time."""
    import base64

    from documents.db_models import DocumentsModelService
    from documents.models.request import UploadDocumentRequest

    raw_pdf_bytes = b"%PDF-1.4 fake binary content \x00\x01\x02"
    request = UploadDocumentRequest(
        organization_id="org-1",
        entity_id="ent-1",
        filename="doc.pdf",
        content_type="application/pdf",
        uploaded_by="u-1",
        content=base64.b64encode(raw_pdf_bytes).decode("ascii"),
    )

    filehandler_content = DocumentsModelService._filehandler_content(request)

    assert base64.b64decode(filehandler_content) == raw_pdf_bytes


def test_binary_document_content_must_be_valid_base64() -> None:
    from documents.db_models import DocumentsModelService
    from documents.models.request import UploadDocumentRequest

    request = UploadDocumentRequest(
        organization_id="org-1",
        entity_id="ent-1",
        filename="doc.pdf",
        content_type="application/pdf",
        uploaded_by="u-1",
        content="not valid base64 !!!",
    )

    with pytest.raises(ValidationError, match="valid base64"):
        DocumentsModelService._filehandler_content(request)


def test_text_document_content_is_still_encoded_once_for_the_filehandler() -> None:
    """Text content arrives as plain text, unlike binary — must keep being
    base64-encoded exactly once, the same as before this fix."""
    import base64

    from documents.db_models import DocumentsModelService
    from documents.models.request import UploadDocumentRequest

    request = UploadDocumentRequest(
        organization_id="org-1",
        entity_id="ent-1",
        filename="notes.txt",
        content_type="text/plain",
        uploaded_by="u-1",
        content="hello world",
    )

    filehandler_content = DocumentsModelService._filehandler_content(request)

    assert base64.b64decode(filehandler_content).decode("utf-8") == "hello world"


def test_documents_controller_prepare_and_calls() -> None:
    manager = _build_manager()
    controller = DocumentsRestController(manager)
    router = APIRouter()

    controller.prepare(router)
    paths = {route.path for route in router.routes}
    assert "/documents/status" in paths
    assert "/documents/upload" in paths
    assert "/documents/list" in paths


def test_upload_rejects_a_field_key_missing_from_the_entity_schema() -> None:
    manager, _ = _build_capture_manager(
        fields=[{"field": "name", "type": "string"}]
    )

    with pytest.raises(
        ValidationError,
        match="field_key 'attachments' does not exist on the entity schema",
    ):
        manager.upload_document(_upload_payload())

    assert manager.list_documents({"organization_id": "org-1"}).items == []


def test_upload_rejects_a_field_key_that_is_not_a_document() -> None:
    manager, _ = _build_capture_manager(
        fields=[{"field": "attachments", "type": "string"}]
    )

    with pytest.raises(
        ValidationError,
        match="field_key 'attachments' must be type 'document', found 'string'",
    ):
        manager.upload_document(_upload_payload())

    assert manager.list_documents({"organization_id": "org-1"}).items == []


def test_upload_captures_first_document_and_field_present_guard_passes(
    entities_db_service_manager, clean_entities_tables
) -> None:
    entities_db = EntitiesModelService(entities_db_service_manager)
    entities = EntitiesServiceManager(
        entities_db,
        entities_db_service_manager,
        config=None,
        auth_service_manager=None,
    )
    entity_type = entities.create_entity_type(
        EntityTypeCreateRequest(
            organization_id="test-org-1",
            name=f"document_capture_{uuid4().hex[:8]}",
            schema_definition={
                "fields": [{"name": "attachments", "type": "document"}]
            },
        )
    )
    created_entity = entities.create_entity_record(
        EntityRecordCreateRequest(
            organization_id="test-org-1",
            entity_type_id=entity_type.entity_type_id,
            data={"name": "Integration entity"},
        )
    )
    manager = DocumentsServiceManager(
        DocumentsModelService(database_service_manager=None),
        database_service_manager=None,
        config=None,
        entities_service_manager=entities,
    )
    payload = _upload_payload(entity_id=created_entity.entity_id)
    payload["organization_id"] = "test-org-1"

    uploaded = manager.upload_document(payload)
    entity = entities.get_entity_record(
        organization_id="test-org-1", entity_id=created_entity.entity_id
    )

    assert entity.data["attachments"] == [uploaded.document_id]
    assert entity.data["name"] == "Integration entity"
    assert matches_workflow_value("document", entity.data["attachments"])
    assert not matches_workflow_value("document", uploaded.document_id)

    transition = Transition(
        key="submit",
        trigger="submit",
        label="Submit",
        to_state="done",
        guards=[Guard(type=GuardType.FIELD_PRESENT, field="attachments")],
        **{"from": "draft"},
    )

    blocked, guards, missing = TransitionEvaluationService().evaluate(transition, entity.data, {})

    assert blocked == []
    assert missing == []
    assert len(guards) == 1 and guards[0].passed is True


def test_two_uploads_append_document_references_in_order() -> None:
    manager, entities = _build_capture_manager(initial_data={"name": "Example"})

    first = manager.upload_document(_upload_payload())
    second_payload = _upload_payload()
    second_payload["filename"] = "cover-letter.txt"
    second_payload["content"] = "cover letter"
    second = manager.upload_document(second_payload)
    entity = entities.get_entity_record(organization_id="org-1", entity_id="ent-1")

    assert entity.data == {
        "name": "Example",
        "attachments": [first.document_id, second.document_id],
    }


def test_upload_for_actor_is_blocked_when_the_actor_cannot_edit_the_field() -> None:
    """upload_document_for_actor must not be able to attach a file to a field
    the actor's role can't edit — before this, `document:write` alone was
    enough, regardless of the target entity or field."""
    from documents.models.request import UploadDocumentRequest

    manager, entities = _build_capture_manager(deny_field_write=True)

    with pytest.raises(AuthorizationError):
        manager.upload_document_for_actor(
            {"user_id": "u-1", "organization_id": "org-1"},
            UploadDocumentRequest(**_upload_payload()),
        )

    assert entities.get_entity_record(organization_id="org-1", entity_id="ent-1").data == {}
    assert manager.list_documents({"organization_id": "org-1"}).items == []


def test_upload_for_actor_checks_the_target_fields_write_permission() -> None:
    """Proves the wiring, not just the outcome: guard_write must be asked
    about the exact entity type and field this upload targets."""
    from documents.models.request import UploadDocumentRequest

    manager, entities = _build_capture_manager()

    manager.upload_document_for_actor(
        {"user_id": "u-1", "organization_id": "org-1"},
        UploadDocumentRequest(**_upload_payload()),
    )

    assert len(entities.guard_write_calls) == 1
    _actor, org, entity_type_id, action, fields = entities.guard_write_calls[0]
    assert org == "org-1"
    assert entity_type_id == "type-1"
    assert action == "edit"
    assert fields == {"attachments"}


def test_upload_for_actor_succeeds_when_the_actor_can_edit_the_field() -> None:
    from documents.models.request import UploadDocumentRequest

    manager, entities = _build_capture_manager()

    uploaded = manager.upload_document_for_actor(
        {"user_id": "u-1", "organization_id": "org-1"},
        UploadDocumentRequest(**_upload_payload()),
    )

    entity = entities.get_entity_record(organization_id="org-1", entity_id="ent-1")
    assert entity.data["attachments"] == [uploaded.document_id]


def test_upload_route_marks_field_key_optional_in_openapi() -> None:
    manager = _build_manager()
    router = APIRouter()
    DocumentsRestController(manager).prepare(router)
    app = FastAPI()
    app.include_router(router)

    request_schema = app.openapi()["paths"]["/documents/upload"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    schema_name = request_schema["$ref"].rsplit("/", 1)[-1]
    upload_schema = app.openapi()["components"]["schemas"][schema_name]

    assert "field_key" in upload_schema["properties"]
    assert "field_key" not in upload_schema.get("required", [])


def _install_filehandler_db_context(postgres, monkeypatch) -> None:
    """Adapt the entity-suite DB fixture to filehandler's context API."""

    @contextmanager
    def _db_context(_engine):
        context_session = postgres.get_db_session()
        try:
            yield context_session
        finally:
            context_session.close()

    monkeypatch.setattr(
        postgres,
        "get_custom_db_contxt_session",
        _db_context,
        raising=False,
    )


def _delete_durable_document_rows(db, organization_id: str) -> None:
    for table in ("files", "file_types"):
        db.execute(
            text(
                f"DELETE FROM modular_backend.{table} "
                "WHERE organization_id = :organization_id"
            ),
            {"organization_id": organization_id},
        )
    db.commit()


def _documents_over_filehandler(
    entities_db_service_manager, integrations
) -> tuple[DocumentsServiceManager, FilehandlerServiceManager]:
    filehandler = FilehandlerServiceManager(
        FilehandlerModelService(entities_db_service_manager),
        None,
        None,
        integrations_service_manager=integrations,
    )
    documents = DocumentsServiceManager(
        DocumentsModelService(
            entities_db_service_manager,
            filehandler_service_manager=filehandler,
        ),
        entities_db_service_manager,
        config=None,
    )
    return documents, filehandler


def test_production_documents_survive_a_new_service_instance_via_postgres_and_s3(
    entities_db_service_manager, monkeypatch
) -> None:
    """A later worker resolves both metadata and content from shared stores."""
    organization_id = "durable-doc-org"
    postgres = entities_db_service_manager.postgres_db_service()
    _install_filehandler_db_context(postgres, monkeypatch)
    db = postgres.get_db_session()
    try:
        _delete_durable_document_rows(db, organization_id)

        objects: dict[tuple[str, str], bytes] = {}

        class _S3Client:
            def put_object(self, *, Bucket, Key, Body, ContentType):
                objects[(Bucket, Key)] = Body

            def get_object(self, *, Bucket, Key):
                return {"Body": SimpleNamespace(read=lambda: objects[(Bucket, Key)])}

        integrations = Mock()
        integrations.get_credentials_for_capability.return_value = (
            "s3",
            {
                "bucket": "shared-documents",
                "region": "eu-west-1",
                "access_key_id": "test-key",
                "secret_access_key": "test-secret",
            },
        )
        monkeypatch.setattr(
            FilehandlerServiceManager,
            "_s3_client",
            staticmethod(lambda _credentials: _S3Client()),
        )

        first, first_filehandler = _documents_over_filehandler(
            entities_db_service_manager, integrations
        )
        first_filehandler.seed_file_types(organization_id)
        first_filehandler.update_file_type(
            organization_id,
            "generic_text",
            FileTypeUpdateRequest(metadata={"storage_provider": "s3"}),
        )

        uploaded = first.upload_document(
            {
                "organization_id": organization_id,
                "entity_id": "entity-1",
                "filename": "restart-proof.txt",
                "content_type": "text/plain",
                "uploaded_by": "user-1",
                "content": "durable content",
                "metadata": {"source": "test"},
            }
        )
        assert objects, "the content was written to shared object storage"

        second, _ = _documents_over_filehandler(
            entities_db_service_manager, integrations
        )

        fetched = second.get_document(organization_id, uploaded.document_id)
        assert fetched is not None
        assert fetched.document_id == uploaded.document_id
        assert fetched.entity_id == "entity-1"
        assert fetched.metadata == {"source": "test"}
        assert second.db_model_service.get_blob(uploaded.document_id) == "durable content"
        assert second.summarize_extraction(
            organization_id, uploaded.document_id
        ).extracted_text_length == len("durable content")
        second.update_document_status(
            {
                "organization_id": organization_id,
                "document_id": uploaded.document_id,
                "status": "FAILED",
                "reason": "cross-worker-check",
            }
        )
        third, _ = _documents_over_filehandler(
            entities_db_service_manager, integrations
        )
        failed = third.list_documents(
            {"organization_id": organization_id, "status": "FAILED"}
        )
        assert [item.document_id for item in failed.items] == [uploaded.document_id]
    finally:
        _delete_durable_document_rows(db, organization_id)
        db.close()

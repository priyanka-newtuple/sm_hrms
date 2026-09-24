"""S3 storage for filehandler, and the Document field type.

Two additions that meet in the same place: a Document field holds file ids, and
those files may live in S3. The S3 tests drive the real manager against a stubbed
boto3 client, since the branch worth testing is ours, not Amazon's. The Document
tests cover the split the validation deliberately takes: shape on the contract,
existence at publish, where the organization is known.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError as PydanticValidationError

from entities.manager import EntitiesServiceManager
from entities.models.request import EntityRecordCreateRequest, EntityRecordUpdateRequest
from exceptions import NotFoundError, ValidationError
from filehandler.manager import S3_PROVIDER, FilehandlerServiceManager
from workflow_manager_factory import NoActiveFormsManager
from workflow.models.interface import (
    EntityField,
    EntityFieldType,
    EntitySchema,
    State,
    StateMachineDefinition,
    Transition,
    ValidationIssueCode,
)
from workflow.services import (
    DefinitionAnalysisService,
    SimulationService,
    TransitionEvaluationService,
)

ORG_A = "test-org-1"
ORG_B = "test-org-2"

S3_CREDS = {
    "bucket": "ssv-documents",
    "region": "eu-west-1",
    "access_key_id": "AKIAEXAMPLE",
    "secret_access_key": "secret",
}


class _FakeS3Client:
    """Stands in for boto3's client, recording what it was asked to do."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict] = []

    def put_object(self, *, Bucket, Key, Body, ContentType):  # boto3's own argument names
        self.put_calls.append({"bucket": Bucket, "key": Key, "content_type": ContentType})
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):  # boto3's own argument names
        if (Bucket, Key) not in self.objects:
            raise KeyError(f"no object {Key} in {Bucket}")
        return {"Body": SimpleNamespace(read=lambda: self.objects[(Bucket, Key)])}


@pytest.fixture
def s3_client() -> _FakeS3Client:
    return _FakeS3Client()


@pytest.fixture
def filehandler(s3_client, monkeypatch) -> FilehandlerServiceManager:
    """The real manager, with only the integrations lookup and boto3 stubbed."""
    integrations = Mock()
    integrations.get_credentials_for_capability.return_value = (S3_PROVIDER, dict(S3_CREDS))
    manager = FilehandlerServiceManager(
        Mock(),
        None,
        None,
        integrations_service_manager=integrations,
    )
    monkeypatch.setattr(
        FilehandlerServiceManager, "_s3_client", staticmethod(lambda creds: s3_client)
    )
    return manager


# ── S3 credentials ────────────────────────────────────────────────────────────


def test_s3_credentials_resolve_for_an_org_configured_on_s3(filehandler) -> None:
    assert filehandler._get_s3_creds(ORG_A) == S3_CREDS


def test_another_storage_provider_is_left_alone(filehandler) -> None:
    """An org on Azure or local must not be pulled down the S3 path."""
    filehandler.integrations_service_manager.get_credentials_for_capability.return_value = (
        "azure_blob",
        {"account_url": "https://x", "container": "c", "account_key": "k"},
    )
    assert filehandler._get_s3_creds(ORG_A) is None


@pytest.mark.parametrize(
    "missing", ["bucket", "region", "access_key_id", "secret_access_key"]
)
def test_incomplete_s3_credentials_are_refused(filehandler, missing) -> None:
    creds = dict(S3_CREDS)
    creds.pop(missing)
    filehandler.integrations_service_manager.get_credentials_for_capability.return_value = (
        S3_PROVIDER,
        creds,
    )
    assert filehandler._get_s3_creds(ORG_A) is None, f"missing {missing} must not pass"


def test_an_optional_endpoint_url_is_allowed(filehandler) -> None:
    """S3-compatible stores need it; real AWS does not."""
    creds = {**S3_CREDS, "endpoint_url": "https://minio.internal"}
    filehandler.integrations_service_manager.get_credentials_for_capability.return_value = (
        S3_PROVIDER,
        creds,
    )
    assert filehandler._get_s3_creds(ORG_A) == creds


def test_no_integrations_service_means_no_s3(s3_client) -> None:
    manager = FilehandlerServiceManager(Mock(), None, None, integrations_service_manager=None)
    assert manager._get_s3_creds(ORG_A) is None


# ── Upload and download ───────────────────────────────────────────────────────


def test_bytes_round_trip_through_s3(filehandler, s3_client) -> None:
    filehandler._s3_upload(S3_CREDS, "org/file.pdf", b"hello bench", "application/pdf")

    assert s3_client.put_calls == [
        {"bucket": "ssv-documents", "key": "org/file.pdf", "content_type": "application/pdf"}
    ]
    assert filehandler._s3_download(S3_CREDS, "org/file.pdf") == b"hello bench"


def test_a_file_row_marked_s3_reads_from_s3(filehandler, s3_client) -> None:
    """The row's storage_provider is what routes the read."""
    filehandler._s3_upload(S3_CREDS, "org/report.pdf", b"report bytes", "application/pdf")
    row = SimpleNamespace(storage_provider=S3_PROVIDER, storage_key="org/report.pdf")

    assert filehandler._get_file_bytes(ORG_A, row) == b"report bytes"


def test_an_s3_row_without_credentials_reports_clearly(filehandler) -> None:
    filehandler.integrations_service_manager.get_credentials_for_capability.return_value = (
        "local",
        {},
    )
    row = SimpleNamespace(storage_provider=S3_PROVIDER, storage_key="org/report.pdf")

    with pytest.raises(ValidationError, match="S3 credentials not configured"):
        filehandler._get_file_bytes(ORG_A, row)


def test_a_local_row_still_reads_from_the_filesystem(filehandler) -> None:
    """The addition is purely additive: local and azure rows are untouched."""
    filehandler.db_model_service.get_filesystem_content_by_storage_key.return_value = b"local"
    row = SimpleNamespace(storage_provider="local", storage_key="org/local.pdf")

    assert filehandler._get_file_bytes(ORG_A, row) == b"local"


def test_the_stored_provider_value_is_s3_for_both_halves() -> None:
    """Unlike azure, which stores "azure" but integrates as "azure_blob"."""
    assert S3_PROVIDER == "s3"


# ── Document field: shape ─────────────────────────────────────────────────────


def test_a_document_field_holds_a_list_of_file_ids() -> None:
    field = EntityField(field="reports", type="document", default=["file-1", "file-2"])
    assert field.type == EntityFieldType.DOCUMENT
    assert field.default == ["file-1", "file-2"]


def test_a_document_field_may_hold_nothing() -> None:
    assert EntityField(field="reports", type="document").default is None


def test_a_document_field_rejects_a_single_value() -> None:
    with pytest.raises(PydanticValidationError, match="must hold a list of file ids"):
        EntityField(field="reports", type="document", default="file-1")


def test_a_document_field_rejects_a_blank_or_non_string_id() -> None:
    for bad in ([""], ["  "], [None], [123]):
        with pytest.raises(PydanticValidationError, match="not a string"):
            EntityField(field="reports", type="document", default=bad)


def test_a_document_field_rejects_the_same_file_twice() -> None:
    with pytest.raises(PydanticValidationError, match="lists the same file twice"):
        EntityField(field="reports", type="document", default=["file-1", "file-1"])


def test_document_ids_are_stripped() -> None:
    assert EntityField(field="reports", type="document", default=[" file-1 "]).default == [
        "file-1"
    ]


# ── Document field: existence, at publish ─────────────────────────────────────


def _definition(fields: list[EntityField]) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key="doc_machine",
        name="Doc Machine",
        entity_type="doc_entity",
        entity_schema=EntitySchema(entity_type="doc_entity", fields=fields),
        states=[
            State(name="start", tags=["initial"], order=1),
            State(name="end", tags=["terminal"], order=2),
        ],
        initial_state="start",
        transitions=[
            Transition(
                key="start_to_end",
                trigger="complete",
                label="Complete",
                to_state="end",
                **{"from": "start"},
            )
        ],
    )


def _workflow_manager(known_files: dict[str, set[str]]):
    """A manager whose filehandler knows only the given files, per organization."""
    from workflow.manager import WorkflowServiceManager

    filehandler = Mock()

    def _get_file(organization_id, file_id, owner_entity_id=None):
        if file_id not in known_files.get(organization_id, set()):
            raise NotFoundError("file not found")
        return SimpleNamespace(file_id=file_id)

    filehandler.get_file.side_effect = _get_file
    return WorkflowServiceManager(
        workflow_db_model_service=None,
        database_service_manager=None,
        config=None,
        entities_service_manager=None,
        roles_manager=None,
        audit_events_service=None,
        forms_service_manager=NoActiveFormsManager(),
        filehandler_service_manager=filehandler,
        user_service_manager=None,
        blob_storage_service=None,
    )


def test_a_document_field_pointing_at_a_real_file_raises_no_issue() -> None:
    manager = _workflow_manager({ORG_A: {"file-1"}})
    definition = _definition([EntityField(field="reports", type="document", default=["file-1"])])

    assert manager._validate_document_fields(ORG_A, definition) == []


def test_a_document_field_pointing_at_a_missing_file_blocks_the_publish() -> None:
    manager = _workflow_manager({ORG_A: {"file-1"}})
    definition = _definition(
        [EntityField(field="reports", type="document", default=["file-1", "ghost"])]
    )

    issues = manager._validate_document_fields(ORG_A, definition)

    assert len(issues) == 1
    assert issues[0].code == ValidationIssueCode.UNKNOWN_DOCUMENT_FILE
    assert issues[0].severity == "error", "a dangling reference must block, not warn"
    assert "reports" in issues[0].message and "ghost" in issues[0].message


def test_a_file_belonging_to_another_org_is_treated_as_missing() -> None:
    """get_file filters by organization, so a foreign file is simply not there."""
    manager = _workflow_manager({ORG_A: set(), ORG_B: {"their-file"}})
    definition = _definition(
        [EntityField(field="reports", type="document", default=["their-file"])]
    )

    issues = manager._validate_document_fields(ORG_A, definition)

    assert len(issues) == 1
    assert "their-file" in issues[0].message


def test_a_document_field_with_no_files_raises_no_issue() -> None:
    manager = _workflow_manager({ORG_A: set()})
    definition = _definition([EntityField(field="reports", type="document")])

    assert manager._validate_document_fields(ORG_A, definition) == []


def test_fields_that_are_not_documents_are_left_alone() -> None:
    """Nothing else should be dragged into a file existence check."""
    manager = _workflow_manager({ORG_A: set()})
    definition = _definition([EntityField(field="volume", type="int", default=5)])

    assert manager._validate_document_fields(ORG_A, definition) == []


def test_without_a_filehandler_the_check_is_skipped_rather_than_crashing() -> None:
    from workflow.manager import WorkflowServiceManager

    manager = WorkflowServiceManager(
        workflow_db_model_service=None,
        database_service_manager=None,
        config=None,
        entities_service_manager=None,
        roles_manager=None,
        audit_events_service=None,
        forms_service_manager=NoActiveFormsManager(),
        filehandler_service_manager=None,
        user_service_manager=None,
        blob_storage_service=None,
    )
    definition = _definition([EntityField(field="reports", type="document", default=["x"])])

    assert manager._validate_document_fields(ORG_A, definition) == []


# ── Document field: entity writes ─────────────────────────────────────────────


def _entity_manager_for_document_writes(known_files: dict[str, set[str]]):
    db = Mock()
    db.entity_type_exists_in_org.return_value = True
    record = SimpleNamespace(
        entity_id="entity-1",
        entity_type_id="type-1",
        organization_id=ORG_A,
        data={},
    )
    db.create_entity_record.return_value = record
    db.get_entity_record_by_id.return_value = record
    db.update_entity_record.return_value = record
    db.list_entity_relations_for_entity.return_value = []
    manager = EntitiesServiceManager(db, database_service_manager=None, config=None)
    schema_fields = [
        {"field": "reports", "type": "document"},
        {"field": "notes", "type": "text"},
    ]
    manager._schema_field_dicts_by_type_id = Mock(return_value=schema_fields)
    manager._document_schema_fields_by_type_id = Mock(return_value=schema_fields)
    manager._entity_record_response_with_inherited = Mock(return_value=record)
    filehandler = Mock()

    def _get_file(organization_id, file_id, owner_entity_id=None):
        if file_id not in known_files.get(organization_id, set()):
            raise NotFoundError("file not found")
        return SimpleNamespace(file_id=file_id)

    filehandler.get_file.side_effect = _get_file
    manager.filehandler_service_manager = filehandler
    return manager, db, filehandler


def test_entity_create_validates_and_persists_real_document_ids() -> None:
    manager, db, filehandler = _entity_manager_for_document_writes(
        {ORG_A: {"file-1", "file-2"}}
    )
    request = EntityRecordCreateRequest(
        organization_id=ORG_A,
        entity_type_id="type-1",
        data={"reports": ["file-1", "file-2"], "notes": "ready"},
    )

    manager._create_entity_record_raw(request)

    assert [call.args[:2] for call in filehandler.get_file.call_args_list] == [
        (ORG_A, "file-1"),
        (ORG_A, "file-2"),
    ]
    db.create_entity_record.assert_called_once()


def test_entity_create_claims_an_unowned_document_field_file_for_pipeline_preview() -> None:
    manager, _, filehandler = _entity_manager_for_document_writes({ORG_A: {"file-1"}})
    filehandler.get_file.side_effect = None
    filehandler.get_file.return_value = SimpleNamespace(
        file_id="file-1", owner_entity_id=None
    )
    request = EntityRecordCreateRequest(
        organization_id=ORG_A,
        entity_type_id="type-1",
        data={"reports": ["file-1"]},
    )

    manager._create_entity_record_raw(request)

    filehandler.db_model_service.set_file_owner.assert_called_once_with(
        ORG_A, "file-1", "entity-1"
    )


def test_entity_create_does_not_reassign_a_document_owned_by_another_entity() -> None:
    manager, _, filehandler = _entity_manager_for_document_writes({ORG_A: {"file-1"}})
    filehandler.get_file.side_effect = None
    filehandler.get_file.return_value = SimpleNamespace(
        file_id="file-1", owner_entity_id="other-entity"
    )
    request = EntityRecordCreateRequest(
        organization_id=ORG_A,
        entity_type_id="type-1",
        data={"reports": ["file-1"]},
    )

    manager._create_entity_record_raw(request)

    filehandler.db_model_service.set_file_owner.assert_not_called()


@pytest.mark.parametrize("file_id", ["missing", "foreign-file"])
def test_entity_create_rejects_missing_or_foreign_document_ids_before_persisting(
    file_id,
) -> None:
    known = {ORG_B: {"foreign-file"}}
    manager, db, _ = _entity_manager_for_document_writes(known)
    request = EntityRecordCreateRequest(
        organization_id=ORG_A,
        entity_type_id="type-1",
        data={"reports": [file_id]},
    )

    with pytest.raises(
        ValidationError, match=f"reports.*{file_id}.*does not exist in this organization"
    ):
        manager._create_entity_record_raw(request)

    db.create_entity_record.assert_not_called()


def test_entity_update_validates_document_ids_before_persisting() -> None:
    manager, db, filehandler = _entity_manager_for_document_writes({ORG_A: {"file-1"}})

    manager.update_entity_record(
        organization_id=ORG_A,
        entity_id="entity-1",
        request=EntityRecordUpdateRequest(data={"reports": ["file-1"]}),
    )

    filehandler.get_file.assert_called_once_with(ORG_A, "file-1")
    db.update_entity_record.assert_called_once()


def test_entity_update_rejects_a_missing_document_before_persisting() -> None:
    manager, db, _ = _entity_manager_for_document_writes({ORG_A: set()})

    with pytest.raises(
        ValidationError, match=r"reports.*missing.*does not exist in this organization"
    ):
        manager.update_entity_record(
            organization_id=ORG_A,
            entity_id="entity-1",
            request=EntityRecordUpdateRequest(data={"reports": ["missing"]}),
        )

    db.update_entity_record.assert_not_called()


def test_non_document_entity_values_do_not_trigger_file_lookups() -> None:
    manager, db, filehandler = _entity_manager_for_document_writes({})
    request = EntityRecordCreateRequest(
        organization_id=ORG_A,
        entity_type_id="type-1",
        data={"notes": "there is no file here"},
    )

    manager._create_entity_record_raw(request)

    filehandler.get_file.assert_not_called()
    db.create_entity_record.assert_called_once()


# ── Document field: synthetic value ───────────────────────────────────────────


def test_a_document_field_synthesizes_an_empty_list() -> None:
    """Same shape as multi_select with no enum_values: empty, not invented."""
    field = EntityField(field="reports", type="document", nullable=False)
    value = SimulationService(
        TransitionEvaluationService(), DefinitionAnalysisService()
    ).default_value_for_field(field, prefer_concrete=True)

    assert value == []

from __future__ import annotations

import base64
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bulk_import.manager import BULK_IMPORT_AGENT, BULK_IMPORT_SOURCE, BulkImportServiceManager
from bulk_import.models import (
    BulkImportDraft,
    BulkImportRemoteFileReference,
    BulkImportReviewRequest,
    BulkImportSpreadsheetMapping,
    BulkImportSpreadsheetMappingRequest,
)
from bulk_import.services.agent_results import (
    MULTIPLE_JSON_OBJECTS_WARNING,
    parse_agent_payload_with_metadata,
)
from bulk_import.services.spreadsheet import SpreadsheetImportService
from exceptions import ConflictError, NotFoundError, ServiceError, ValidationError
from fileprocessor.models.interface import TabularColumn, TabularRow, TabularSheet
from remote_files.models.interface import FetchedRemoteFile

ACTOR = {"organization_id": "org-1", "user_id": "user-1"}


def _tabular_sheet(
    sheet_name: str,
    columns: list[str],
    rows: list[dict[str, object]],
) -> TabularSheet:
    return TabularSheet(
        sheet_name=sheet_name,
        row_count=len(rows),
        columns=[
            TabularColumn(
                name=column,
                inferred_type="string",
                sample_values=list(
                    dict.fromkeys(
                        str(row[column])[:160]
                        for row in rows
                        if row.get(column) not in (None, "")
                    )
                )[:3],
            )
            for column in columns
        ],
        rows=[
            TabularRow(source_row_number=index, values=row)
            for index, row in enumerate(rows, start=1)
        ],
    )


class _Jobs:
    """Fake BackgroundJobsModelService mirroring update_job's real compare-and-set."""

    def __init__(self, job: SimpleNamespace) -> None:
        self.job = job

    def get_job(self, organization_id: str, job_id: str):
        return self.job if organization_id == "org-1" and job_id == self.job.job_id else None

    def update_job(self, organization_id: str, job_id: str, **updates):
        expected = updates.pop("expected_statuses", None)
        if expected is not None and self.job.status not in expected:
            raise ConflictError(
                f"intake job '{job_id}' cannot be updated from status '{self.job.status}'"
            )
        for key, value in updates.items():
            if value is not None:
                setattr(self.job, key, value)
        return self.job


class _MultiJobs:
    """Fake BackgroundJobsModelService over several jobs, for worker/sweep tests."""

    def __init__(self, jobs: list[SimpleNamespace]) -> None:
        self.jobs = {job.job_id: job for job in jobs}

    def get_job(self, organization_id: str, job_id: str):
        job = self.jobs.get(job_id)
        return job if job is not None and job.organization_id == organization_id else None

    def list_jobs(
        self,
        organization_id: str,
        status: str | None = None,
        source_type: str | None = None,
        limit: int | None = None,
    ):
        matches = [job for job in self.jobs.values() if job.organization_id == organization_id]
        if status is not None:
            matches = [job for job in matches if job.status == status]
        if source_type is not None:
            matches = [job for job in matches if job.source_type == source_type]
        matches = sorted(matches, key=lambda job: job.job_id, reverse=True)
        return matches[:limit] if limit is not None else matches

    def list_jobs_by_source_and_status(self, source_type: str, status: str, limit: int = 25):
        matches = [
            job
            for job in self.jobs.values()
            if job.source_type == source_type and job.status == status
        ]
        return matches[:limit]

    def list_stale_jobs_for_source(
        self, source_type: str, statuses: set[str], older_than: datetime, limit: int = 25
    ):
        matches = [
            job
            for job in self.jobs.values()
            if job.source_type == source_type
            and job.status in statuses
            and job.updated_at < older_than
        ]
        return matches[:limit]

    def update_job(self, organization_id: str, job_id: str, **updates):
        job = self.jobs[job_id]
        expected = updates.pop("expected_statuses", None)
        if expected is not None and job.status not in expected:
            raise ConflictError(
                f"intake job '{job_id}' cannot be updated from status '{job.status}'"
            )
        for key, value in updates.items():
            if value is not None:
                setattr(job, key, value)
        return job


def _job(
    *,
    job_id: str = "job-1",
    status: str = "READY_FOR_REVIEW",
    drafts: list[dict] | None = None,
    actor_user_id: str | None = "user-1",
    queued_for: str | None = None,
    updated_at: datetime | None = None,
):
    context: dict[str, object] = {
        "entity_type_id": "candidate",
        "entity_type_name": "Candidate",
        "workflow_name": "Hiring",
        "files": [
            {
                "file_id": "file-1",
                "filename": "resume.pdf",
                "content_type": "application/pdf",
                "size_bytes": 12,
            }
        ],
        "drafts": drafts or [],
        "unmapped_file_ids": [],
        "errors": [],
    }
    if actor_user_id is not None:
        context["actor_user_id"] = actor_user_id
    if queued_for is not None:
        context["queued_for"] = queued_for
    return SimpleNamespace(
        job_id=job_id,
        organization_id="org-1",
        source_type=BULK_IMPORT_SOURCE,
        status=status,
        context=context,
        processed_count=1,
        failed_count=0,
        created_at="2026-08-03T00:00:00Z",
        updated_at=updated_at or datetime.now(UTC),
    )


def _build_manager(jobs):
    from bulk_import.services.relation_bindings import BulkImportRelationBindingService
    filehandler = MagicMock()
    remote_files = MagicMock()
    remote_files.fetch_many.return_value = {}
    fileprocessor = MagicMock()
    entities = MagicMock()
    agents = MagicMock()
    relations = BulkImportRelationBindingService(entities=entities)
    spreadsheets = SpreadsheetImportService(
        filehandler=filehandler,
        fileprocessor=fileprocessor,
        entities=entities,
        agents=agents,
        relations=relations,
    )
    manager = BulkImportServiceManager(
        jobs=jobs,
        database=MagicMock(),
        organizations=MagicMock(),
        roles=MagicMock(),
        filehandler=filehandler,
        spreadsheets=spreadsheets,
        entities=entities,
        agents=agents,
        workflows=MagicMock(),
        remote_files=remote_files,
        relations=relations,
    )
    manager.entities.get_identifier_template_for_actor.return_value = None
    manager._require_enabled = MagicMock()
    manager._require_permission = MagicMock()
    return manager, filehandler


def _manager(job: SimpleNamespace):
    return _build_manager(_Jobs(job))


def _run_analyze(manager, job_id: str = "job-1", organization_id: str = "org-1"):
    """Queue then run analysis synchronously, as the worker's poll loop would."""
    queued = manager.analyze(ACTOR, job_id)
    assert queued.status == "QUEUED"
    manager._run_queued_analysis(job_id, organization_id)
    return manager.get_job(ACTOR, job_id)


def _run_commit(manager, idempotency_key: str, job_id: str = "job-1", organization_id: str = "org-1"):
    """Queue then run commit synchronously, as the worker's poll loop would."""
    queued = manager.commit(ACTOR, job_id, idempotency_key)
    assert queued.status == "QUEUED"
    manager._run_queued_commit(job_id, organization_id)
    return manager.get_job(ACTOR, job_id)


def test_candidates_with_same_identifier_merge_and_keep_all_files() -> None:
    drafts: list[BulkImportDraft] = []
    BulkImportServiceManager._merge_candidate(
        drafts,
        {
            "data": {"identifier": "a@b.com", "name": "A"},
            "confidence": 0.7,
            "file_ids": ["file-1"],
        },
    )
    BulkImportServiceManager._merge_candidate(
        drafts,
        {
            "data": {"identifier": "A@B.COM", "phone": "1"},
            "confidence": 0.9,
            "file_ids": ["file-2"],
        },
    )

    assert len(drafts) == 1
    assert drafts[0].data == {"identifier": "A@B.COM", "name": "A", "phone": "1"}
    assert drafts[0].file_ids == ["file-1", "file-2"]
    assert drafts[0].confidence == 0.9


def test_safe_confidence_defaults_malformed_values_instead_of_raising() -> None:
    assert BulkImportServiceManager._safe_confidence("high") == 0.0
    assert BulkImportServiceManager._safe_confidence(None) == 0.0
    assert BulkImportServiceManager._safe_confidence({}) == 0.0
    assert BulkImportServiceManager._safe_confidence(0.9) == 0.9


def test_merge_candidate_does_not_raise_on_a_malformed_confidence_value() -> None:
    """A malformed confidence must never crash the merge pass — defensive against
    untrusted agent output, same precedent as `_safe_confidence`'s own docstring."""
    drafts: list[BulkImportDraft] = []

    BulkImportServiceManager._merge_candidate(
        drafts, {"data": {"identifier": "a@b.com"}, "confidence": "high", "file_ids": ["file-1"]}
    )

    assert len(drafts) == 1
    assert drafts[0].confidence == 0.0


def test_build_drafts_from_payload_dedupes_by_identifier() -> None:
    payload = {
        "entities": [
            {
                "data": {"identifier": "a@b.com", "name": "A"},
                "confidence": 0.7,
                "file_ids": ["file-1"],
            },
            {
                "data": {"identifier": "A@B.COM", "phone": "1"},
                "confidence": 0.9,
                "file_ids": ["file-2"],
            },
        ]
    }

    drafts = BulkImportServiceManager._build_drafts_from_payload(payload)

    assert len(drafts) == 1
    assert drafts[0].file_ids == ["file-1", "file-2"]
    assert drafts[0].data == {"identifier": "A@B.COM", "name": "A", "phone": "1"}


def test_build_drafts_from_payload_returns_empty_when_no_entities() -> None:
    assert BulkImportServiceManager._build_drafts_from_payload({"entities": []}) == []
    assert BulkImportServiceManager._build_drafts_from_payload({}) == []


def test_extractor_json_allows_explanatory_text_around_fenced_payload() -> None:
    payload = BulkImportServiceManager._parse_extractor_payload(
        "I found one candidate.\n"
        "```json\n"
        '{"entities":[{"data":{"identifier":"a@b.com"},"confidence":0.9}]}'
        "\n```\n"
        "The document was parsed successfully."
    )

    assert payload["entities"][0]["data"]["identifier"] == "a@b.com"


def test_extractor_json_prefers_last_valid_fenced_payload() -> None:
    payload = BulkImportServiceManager._parse_extractor_payload(
        "```text\nnot json\n```\n"
        "Use this result:\n"
        "```JSON\n"
        '{"entities":[],"attachment_only":true}'
        "\n```"
    )

    assert payload == {"entities": [], "attachment_only": True}


def test_agent_json_allows_adjacent_objects_and_returns_last_with_warning() -> None:
    parsed = parse_agent_payload_with_metadata(
        '{"entities":[{"data":{"identifier":"old"}}]}'
        '{"entities":[{"data":{"identifier":"new"}}]}'
    )

    assert parsed.payload["entities"][0]["data"]["identifier"] == "new"
    assert parsed.warnings == [MULTIPLE_JSON_OBJECTS_WARNING]


def test_agent_json_rejects_adjacent_non_object_values() -> None:
    with pytest.raises(ValidationError, match="non-object"):
        parse_agent_payload_with_metadata('[]{"entities":[]}')


def test_extractor_json_rejects_explanatory_text_without_json() -> None:
    with pytest.raises(ValidationError, match="invalid JSON"):
        BulkImportServiceManager._parse_extractor_payload("No structured result was produced.")


def test_review_rejects_files_from_outside_the_job() -> None:
    job = _job()
    manager, _ = _manager(job)
    request = BulkImportReviewRequest(
        drafts=[BulkImportDraft(draft_id="draft-1", data={"identifier": "A"}, file_ids=["other"])],
    )

    with pytest.raises(ValidationError, match="unknown file"):
        manager.update_review({"organization_id": "org-1", "user_id": "user-1"}, "job-1", request)


def test_review_can_select_workflow_after_analysis() -> None:
    job = _job()
    job.context["workflow_name"] = None
    job.context["workflow_preselected"] = False
    manager, _ = _manager(job)
    request = BulkImportReviewRequest(
        drafts=[],
        workflow_name="Candidate Hiring Demo",
    )

    response = manager.update_review(
        {"organization_id": "org-1", "user_id": "user-1"},
        "job-1",
        request,
    )

    assert response.workflow_name == "Candidate Hiring Demo"
    manager._require_permission.assert_any_call(
        {"organization_id": "org-1", "user_id": "user-1"},
        "workflow:write",
    )


def test_review_cannot_replace_preselected_workflow() -> None:
    job = _job()
    job.context["workflow_preselected"] = True
    manager, _ = _manager(job)
    request = BulkImportReviewRequest(drafts=[], workflow_name="Another Workflow")

    with pytest.raises(ValidationError, match="preselected"):
        manager.update_review(
            {"organization_id": "org-1", "user_id": "user-1"},
            "job-1",
            request,
        )


def test_review_preserves_server_owned_attachment_progress() -> None:
    stored = BulkImportDraft(
        draft_id="draft-1",
        data={"identifier": "A"},
        file_ids=["file-1"],
        entity_id="entity-1",
        attached_file_ids=["file-1"],
        files_attached=True,
    )
    job = _job(drafts=[stored.model_dump(mode="json")])
    manager, _ = _manager(job)
    request = BulkImportReviewRequest(
        drafts=[
            BulkImportDraft(
                draft_id="draft-1",
                data={"identifier": "A"},
                file_ids=["file-1"],
                attached_file_ids=[],
                files_attached=False,
            )
        ],
        workflow_name="Hiring",
    )

    response = manager.update_review(
        {"organization_id": "org-1", "user_id": "user-1"},
        "job-1",
        request,
    )

    assert response.drafts[0].entity_id == "entity-1"
    assert response.drafts[0].attached_file_ids == ["file-1"]
    assert response.drafts[0].files_attached is True


def test_review_keeps_unmaterialized_remote_attachment_pending() -> None:
    stored = BulkImportDraft(
        draft_id="draft-1",
        data={"identifier": "Lamp"},
        remote_file_references=[
            BulkImportRemoteFileReference(
                source_column="Image URL",
                source_value="https://cdn.example/lamp.jpg",
                source_url="https://cdn.example/lamp.jpg",
                status="referenced",
            )
        ],
    )
    job = _job(drafts=[stored.model_dump(mode="json")])
    manager, _ = _manager(job)

    response = manager.update_review(
        ACTOR,
        "job-1",
        BulkImportReviewRequest(drafts=[stored], workflow_name="Hiring"),
    )

    assert response.drafts[0].files_attached is False
    assert response.drafts[0].attached_file_ids == []


def test_review_can_remove_an_unresolved_remote_attachment() -> None:
    stored = BulkImportDraft(
        draft_id="draft-1",
        data={"identifier": "Lamp"},
        remote_file_references=[
            BulkImportRemoteFileReference(
                source_column="Image URL",
                source_value="missing.webp",
                filename="missing.webp",
                status="missing",
                error="no uploaded file matches this filename",
            )
        ],
    )
    manager, _ = _manager(_job(drafts=[stored.model_dump(mode="json")]))
    reviewed = stored.model_copy(update={"remote_file_references": []})

    response = manager.update_review(
        ACTOR,
        "job-1",
        BulkImportReviewRequest(drafts=[reviewed], workflow_name="Hiring"),
    )

    assert response.drafts[0].remote_file_references == []


def test_review_rejects_an_unknown_remote_attachment() -> None:
    stored = BulkImportDraft(draft_id="draft-1", data={"identifier": "Lamp"})
    manager, _ = _manager(_job(drafts=[stored.model_dump(mode="json")]))
    reviewed = stored.model_copy(
        update={
            "remote_file_references": [
                BulkImportRemoteFileReference(
                    source_column="Image URL",
                    source_value="https://untrusted.example/image.jpg",
                    source_url="https://untrusted.example/image.jpg",
                    status="referenced",
                )
            ]
        }
    )

    with pytest.raises(ValidationError, match="unknown remote attachment"):
        manager.update_review(
            ACTOR,
            "job-1",
            BulkImportReviewRequest(drafts=[reviewed], workflow_name="Hiring"),
        )


def test_review_persists_exception_decision() -> None:
    stored = BulkImportDraft(draft_id="draft-1", data={"identifier": "Lamp"})
    manager, _ = _manager(_job(drafts=[stored.model_dump(mode="json")]))
    reviewed = stored.model_copy(update={"review_decision": "accepted"})

    response = manager.update_review(
        ACTOR,
        "job-1",
        BulkImportReviewRequest(drafts=[reviewed], workflow_name="Hiring"),
    )

    assert response.drafts[0].review_decision == "accepted"


def test_legacy_files_attached_payload_populates_per_file_progress() -> None:
    legacy = BulkImportDraft(
        draft_id="draft-1",
        data={"identifier": "A"},
        file_ids=["file-1"],
        entity_id="entity-1",
        files_attached=True,
    ).model_dump(mode="json")
    legacy.pop("attached_file_ids")
    job = _job(drafts=[legacy])
    manager, _ = _manager(job)

    response = manager.get_job(
        {"organization_id": "org-1", "user_id": "user-1"},
        "job-1",
    )

    assert response.drafts[0].attached_file_ids == ["file-1"]


def test_shared_attachment_copy_is_idempotent_after_progress_write_gap() -> None:
    job = _job()
    manager, filehandler = _manager(job)
    filehandler.db_model_service.list_files.return_value = [
        SimpleNamespace(metadata={"bulk_import_source_file_id": "file-1"})
    ]

    manager._attach_file(
        "org-1",
        "user-1",
        "entity-1",
        "file-1",
        shared=True,
    )

    filehandler.copy_file_to_entity.assert_not_called()


def test_remote_attachment_commit_preserves_spreadsheet_provenance() -> None:
    manager, filehandler = _manager(_job())
    filehandler.db_model_service.get_file.return_value = SimpleNamespace(owner_entity_id=None)
    draft = BulkImportDraft(
        draft_id="draft-1",
        data={"identifier": "Lamp"},
        file_ids=["remote-1"],
        entity_id="entity-1",
        source_kind="spreadsheet",
        source_sheet_name="Products",
        source_row_number=7,
        remote_file_references=[
            BulkImportRemoteFileReference(
                source_column="Image URL",
                source_value="https://cdn.example/lamp.jpg",
                source_url="https://cdn.example/lamp.jpg",
                file_id="remote-1",
                status="staged",
            )
        ],
    )

    manager._attach_files(ACTOR, draft, Counter({"remote-1": 1}), on_file_attached=lambda: None)

    filehandler.db_model_service.merge_file_metadata.assert_called_once_with(
        "org-1",
        "remote-1",
        {
            "bulk_import_source_sheet": "Products",
            "bulk_import_source_row": 7,
            "bulk_import_source_column": "Image URL",
            "bulk_import_source_value": "https://cdn.example/lamp.jpg",
        },
    )


class _CreateJobs:
    def __init__(self) -> None:
        self.created_context: dict | None = None

    def create_job(self, request):
        self.created_context = request.context
        return SimpleNamespace(
            job_id="job-2",
            status="UPLOADED",
            context=request.context,
            processed_count=0,
            failed_count=0,
            source_type=BULK_IMPORT_SOURCE,
        )

    def update_job(self, organization_id: str, job_id: str, **updates):
        return SimpleNamespace(
            job_id=job_id,
            status=updates.get("status", "UPLOADED"),
            context=updates.get("context", {}),
            processed_count=0,
            failed_count=0,
            source_type=BULK_IMPORT_SOURCE,
        )


def _stored_file(**overrides) -> dict[str, object]:
    payload = {
        "file_id": "file-1",
        "filename": "resume.pdf",
        "content_type": "application/pdf",
        "size_bytes": 12,
    }
    payload.update(overrides)
    return payload


def test_create_job_builds_context_from_stored_files() -> None:
    jobs = _CreateJobs()
    manager, _ = _build_manager(jobs)
    manager.entities.list_entity_type_records.return_value = [
        SimpleNamespace(entity_type_id="candidate", name="Candidate")
    ]

    response = manager.create_job(
        {"organization_id": "org-1", "user_id": "user-1"},
        entity_type_id="candidate",
        workflow_name=None,
        files=[_stored_file()],
    )

    assert manager.entities.list_entity_type_records.call_count == 2
    manager.entities.list_entity_type_records.assert_called_with(
        organization_id="org-1", include_inactive=False
    )
    assert response.entity_type_id == "candidate"
    assert response.entity_type_name == "Candidate"
    assert response.files[0]["file_id"] == "file-1"
    assert jobs.created_context is not None
    assert jobs.created_context["files"][0]["file_id"] == "file-1"


def test_create_job_stores_actor_user_id_snapshot() -> None:
    jobs = _CreateJobs()
    manager, _ = _build_manager(jobs)
    manager.entities.list_entity_type_records.return_value = [
        SimpleNamespace(entity_type_id="candidate", name="Candidate")
    ]

    manager.create_job(
        {"organization_id": "org-1", "user_id": "user-1"},
        entity_type_id="candidate",
        workflow_name=None,
        files=[_stored_file()],
    )

    assert jobs.created_context["actor_user_id"] == "user-1"


def test_create_job_rejects_unknown_entity_type() -> None:
    manager, _ = _build_manager(_CreateJobs())
    manager.entities.list_entity_type_records.return_value = []

    with pytest.raises(NotFoundError, match="not found"):
        manager.create_job(
            {"organization_id": "org-1", "user_id": "user-1"},
            entity_type_id="candidate",
            workflow_name=None,
            files=[_stored_file()],
        )


def test_create_job_rejects_when_no_files_supplied() -> None:
    manager, _ = _build_manager(_CreateJobs())
    manager.entities.list_entity_type_records.return_value = [
        SimpleNamespace(entity_type_id="candidate", name="Candidate")
    ]

    with pytest.raises(ValidationError, match="at least one supported file"):
        manager.create_job(
            {"organization_id": "org-1", "user_id": "user-1"},
            entity_type_id="candidate",
            workflow_name=None,
            files=[],
        )


def test_create_job_requires_fixed_reference_parent_for_document_sources() -> None:
    manager, _ = _build_manager(_CreateJobs())
    manager.entities.list_entity_type_records.return_value = [
        SimpleNamespace(entity_type_id="candidate", name="Candidate"),
        SimpleNamespace(entity_type_id="provider", name="Provider"),
    ]
    manager.entities.list_entity_relation_declarations_for_actor.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                relation_def_id="rel-1",
                from_entity_type_id="provider",
                to_entity_type_id="candidate",
                relation_name=None,
                relation_type=SimpleNamespace(value="REFERENCE"),
            )
        ]
    )

    with pytest.raises(ValidationError, match="Select a fixed Provider"):
        manager.create_job(
            ACTOR,
            entity_type_id="candidate",
            workflow_name=None,
            files=[_stored_file(filename="resume.pdf")],
        )


def test_required_relation_binding_validation_rejects_unresolved_reference() -> None:
    draft = BulkImportDraft(
        draft_id="draft-1",
        relation_bindings=[
            {
                "relation_def_id": "rel-1",
                "source_entity_type_id": "provider",
                "source_entity_type_name": "Provider",
                "relation_type": "REFERENCE",
                "mode": "column",
                "status": "missing",
                "error": "Provider was not found",
            }
        ],
    )

    with pytest.raises(ValidationError, match="Provider was not found"):
        BulkImportServiceManager._validate_required_relation_bindings(draft)


def test_store_file_uploads_with_agent_dispatch_skipped() -> None:
    job = _job()
    manager, filehandler = _manager(job)
    filehandler.upload_file.return_value = SimpleNamespace(
        file_id="file-9",
        filename="resume.pdf",
        content_type="application/pdf",
        size_bytes=3,
    )

    result = manager.store_file(
        {"organization_id": "org-1", "user_id": "user-1"},
        filename="resume.pdf",
        content_type="application/pdf",
        content=b"abc",
    )

    assert result == {
        "file_id": "file-9",
        "filename": "resume.pdf",
        "content_type": "application/pdf",
        "size_bytes": 3,
    }
    assert filehandler.upload_file.call_args.kwargs["skip_agent_dispatch"] is True
    upload_request = filehandler.upload_file.call_args.args[2]
    assert upload_request.content == base64.b64encode(b"abc").decode("ascii")


# --- analyze: queue-and-return + worker-facing _run_queued_analysis ---------------


def test_analyze_queues_the_job_and_returns_immediately() -> None:
    job = _job(status="UPLOADED", drafts=[])
    manager, _ = _manager(job)

    response = manager.analyze(ACTOR, "job-1")

    assert response.status == "QUEUED"
    assert response.operation == "analyze"
    assert job.context["queued_for"] == "analyze"
    manager.agents.run_agent_for_actor.assert_not_called()


def test_analyze_rejects_a_job_that_is_not_uploaded_or_failed() -> None:
    job = _job(status="PROCESSING", drafts=[])
    manager, _ = _manager(job)

    with pytest.raises(ConflictError):
        manager.analyze(ACTOR, "job-1")


def test_analyze_rejects_unknown_job() -> None:
    job = _job(status="UPLOADED")
    manager, _ = _manager(job)

    with pytest.raises(NotFoundError, match="not found"):
        manager.analyze(ACTOR, "missing-job")


def test_run_queued_analysis_raises_conflict_when_job_is_not_queued() -> None:
    job = _job(status="UPLOADED", drafts=[])
    manager, _ = _manager(job)

    with pytest.raises(ConflictError):
        manager._run_queued_analysis("job-1", "org-1")


def test_run_queued_analysis_raises_when_actor_snapshot_missing() -> None:
    job = _job(status="QUEUED", drafts=[], actor_user_id=None)
    manager, _ = _manager(job)

    with pytest.raises(ValidationError, match="actor_user_id snapshot"):
        manager._run_queued_analysis("job-1", "org-1")

    # Must land on FAILED (retryable via analyze), never stuck at PROCESSING —
    # analyze() only re-queues from UPLOADED/FAILED.
    assert job.status == "FAILED"


def test_run_queued_commit_raises_when_actor_snapshot_missing() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"identifier": "A"}, file_ids=["file-1"])
    job = _job(status="QUEUED", drafts=[draft.model_dump(mode="json")], actor_user_id=None)
    manager, _ = _manager(job)

    with pytest.raises(ValidationError, match="actor_user_id snapshot"):
        manager._run_queued_commit("job-1", "org-1")

    # Must land on a status commit() will re-queue from, never stuck at COMMITTING.
    assert job.status == "COMPLETED_WITH_ERRORS"


def test_analyze_backfills_a_missing_actor_snapshot_from_the_live_caller() -> None:
    """Legacy job created before this feature shipped has no actor_user_id at all."""
    job = _job(status="UPLOADED", drafts=[], actor_user_id=None)
    manager, _ = _manager(job)

    manager.analyze(ACTOR, "job-1")

    assert job.context["actor_user_id"] == "user-1"


def test_analyze_does_not_overwrite_an_existing_actor_snapshot() -> None:
    job = _job(status="UPLOADED", drafts=[], actor_user_id="original-user")
    manager, _ = _manager(job)

    manager.analyze({"organization_id": "org-1", "user_id": "someone-else"}, "job-1")

    assert job.context["actor_user_id"] == "original-user"


def test_commit_backfills_a_missing_actor_snapshot_from_the_live_caller() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"identifier": "A"}, file_ids=["file-1"])
    job = _job(drafts=[draft.model_dump(mode="json")], actor_user_id=None)
    manager, _ = _manager(job)

    manager.commit(ACTOR, "job-1", "key-1")

    assert job.context["actor_user_id"] == "user-1"


def test_analyze_extracts_drafts_from_agent_output() -> None:
    job = _job(status="UPLOADED", drafts=[])
    manager, _ = _manager(job)
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="completed",
        output=(
            '{"entities":[{"data":{"identifier":"a@b.com","name":"A"},'
            '"confidence":0.9,"file_ids":["file_1"]}],"skipped_files":[]}'
        ),
        error=None,
        metadata={
            "tool_calls": [
                {"tool": "get_form_schema", "args": {}, "result": {"success": True}},
                {
                    "tool": "read_job_document",
                    "args": {"file_ids": ["file_1"]},
                    "result": {
                        "success": True,
                        "output": {
                            "results": [{"file_id": "file_1", "status": "ok", "text": "..."}]
                        },
                    },
                },
            ]
        },
    )
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[]
    )

    response = _run_analyze(manager)

    assert response.status == "READY_FOR_REVIEW"
    assert len(response.drafts) == 1
    assert response.drafts[0].data["identifier"] == "a@b.com"
    # The model's slug ("file_1") is translated back to the real file id before
    # the draft is built — nothing downstream ever sees a slug.
    assert response.drafts[0].file_ids == ["file-1"]
    assert response.processed_count == 1
    assert response.failed_count == 0
    # One job = one agent call, whatever the file count.
    assert manager.agents.run_agent_for_actor.call_count == 1
    request = manager.agents.run_agent_for_actor.call_args.args[1]
    assert request.document_id is None  # no single fixed document anymore
    assert request.file_slug_map == {"file_1": "file-1"}
    assert "populate identifier with its best human-readable record name" in request.input
    # The prompt itself only ever contains the slug and filename, never the real id.
    assert "file_1" in request.input
    assert "resume.pdf" in request.input
    assert "file-1" not in request.input
    # Job-audit summary: recorded even on a fully successful extraction.
    summary = job.context["extraction_summary"]
    assert summary["tool_call_count"] == 2
    assert summary["read_job_document_call_count"] == 1
    assert summary["rejected_files"] == []


def test_analyze_uses_agent_mapping_then_applies_spreadsheet_rows_deterministically() -> None:
    job = _job(status="UPLOADED", drafts=[])
    job.context["files"] = [
        {
            "file_id": "sheet-1",
            "filename": "candidates.csv",
            "content_type": "text/csv",
            "size_bytes": 50,
        }
    ]
    manager, _ = _manager(job)
    manager.filehandler.read_document_source.return_value = {
        "filename": "candidates.csv",
        "content_type": "text/csv",
        "file_bytes": b"Full Name,Email Address\nJane,jane@example.com\n",
    }
    manager.spreadsheets.fileprocessor.extract_tabular_sheets.return_value = [
        _tabular_sheet(
            "CSV",
            ["Full Name", "Email Address"],
            [
                {"Full Name": "Jane", "Email Address": "jane@example.com"},
                {"Full Name": "John", "Email Address": "john@example.com"},
            ],
        )
    ]
    manager.entities.get_form_fields.return_value = [
        {"field": "full_name", "type": "string"},
        {"field": "email_address", "type": "string"},
    ]
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[]
    )
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="completed",
        output=(
            '{"mappings":[{"file_id":"file_1","sheet_name":"CSV",'
            '"column_mapping":{"Full Name":["full_name"],'
            '"Email Address":["email_address"]}}]}'
        ),
        error=None,
        run_id="run-map-1",
    )

    response = _run_analyze(manager)

    assert response.status == "READY_FOR_REVIEW"
    assert [draft.data for draft in response.drafts] == [
        {"full_name": "Jane", "identifier": "Jane", "email_address": "jane@example.com"},
        {"full_name": "John", "identifier": "John", "email_address": "john@example.com"},
    ]
    assert all(draft.source_kind == "spreadsheet" for draft in response.drafts)
    assert [draft.source_row_number for draft in response.drafts] == [1, 2]
    assert all(draft.file_ids == [] for draft in response.drafts)
    assert response.unmapped_file_ids == []
    assert response.spreadsheet_sources[0].row_count == 2
    assert response.spreadsheet_sources[0].column_mapping == {
        "Full Name": ["full_name", "identifier"],
        "Email Address": ["email_address"],
    }
    request = manager.agents.run_agent_for_actor.call_args.args[1]
    assert "Mode: spreadsheet_mapping" in request.input
    assert "Product Name can map to both identifier and product_name" in request.input
    assert "file_1" in request.input
    assert "sheet-1" not in request.input


def test_spreadsheet_mapping_accepts_adjacent_agent_json_and_exposes_diagnostics() -> None:
    job = _job(status="UPLOADED", drafts=[])
    job.context["files"] = [
        {
            "file_id": "sheet-1",
            "filename": "candidates.csv",
            "content_type": "text/csv",
            "size_bytes": 50,
        }
    ]
    manager, _ = _manager(job)
    manager.filehandler.read_document_source.return_value = {
        "filename": "candidates.csv",
        "content_type": "text/csv",
        "file_bytes": b"Full Name,Email Address\nJane,jane@example.com\n",
    }
    manager.spreadsheets.fileprocessor.extract_tabular_sheets.return_value = [
        _tabular_sheet(
            "CSV",
            ["Full Name", "Email Address"],
            [{"Full Name": "Jane", "Email Address": "jane@example.com"}],
        )
    ]
    manager.entities.get_form_fields.return_value = [
        {"field": "full_name", "type": "string"},
        {"field": "email_address", "type": "string"},
    ]
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[]
    )
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="completed",
        output=(
            '{"mappings":[{"file_id":"file_1","sheet_name":"CSV",'
            '"column_mapping":{"Full Name":["full_name"]}}]}'
            '{"mappings":[{"file_id":"file_1","sheet_name":"CSV",'
            '"column_mapping":{"Full Name":["full_name"],'
            '"Email Address":["email_address"]}}]}'
        ),
        error=None,
        run_id="run-map-1",
    )

    response = _run_analyze(manager)

    assert response.status == "READY_FOR_REVIEW"
    assert response.drafts[0].data == {
        "full_name": "Jane",
        "identifier": "Jane",
        "email_address": "jane@example.com",
    }
    assert response.diagnostics is not None
    assert response.diagnostics.analysis_stage == "spreadsheet_mapping"
    assert response.diagnostics.mapping_agent_run_id == "run-map-1"
    assert response.diagnostics.parser_warnings == [MULTIPLE_JSON_OBJECTS_WARNING]
    manager.filehandler.read_document_source.assert_called_once()
    manager.spreadsheets.fileprocessor.extract_tabular_sheets.assert_called_once()


def test_spreadsheet_mapping_failure_preserves_agent_run_diagnostics() -> None:
    job = _job(status="UPLOADED", drafts=[])
    job.context["files"] = [
        {
            "file_id": "sheet-1",
            "filename": "candidates.csv",
            "content_type": "text/csv",
            "size_bytes": 50,
        }
    ]
    manager, _ = _manager(job)
    manager.filehandler.read_document_source.return_value = {
        "filename": "candidates.csv",
        "content_type": "text/csv",
        "file_bytes": b"Full Name\nJane\n",
    }
    manager.spreadsheets.fileprocessor.extract_tabular_sheets.return_value = [
        _tabular_sheet("CSV", ["Full Name"], [{"Full Name": "Jane"}])
    ]
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="completed",
        output="No structured result was produced.",
        error=None,
        run_id="run-map-1",
    )

    queued = manager.analyze(ACTOR, "job-1")
    assert queued.status == "QUEUED"
    with pytest.raises(ValidationError, match="invalid JSON"):
        manager._run_queued_analysis("job-1", "org-1")
    response = manager.get_job(ACTOR, "job-1")

    assert response.status == "FAILED"
    assert response.diagnostics is not None
    assert response.diagnostics.analysis_stage == "spreadsheet_mapping"
    assert response.diagnostics.mapping_agent_run_id == "run-map-1"
    assert response.errors == ["extractor returned invalid JSON"]


def test_spreadsheet_remote_url_is_referenced_without_downloading_before_review() -> None:
    job = _job(status="UPLOADED", drafts=[])
    job.context["files"] = [
        {"file_id": "sheet-1", "filename": "products.csv", "content_type": "text/csv", "size_bytes": 40}
    ]
    manager, filehandler = _manager(job)
    manager.filehandler.read_document_source.return_value = {
        "filename": "products.csv", "content_type": "text/csv", "file_bytes": b"Name,Image URL\nLamp,https://cdn.example/lamp.jpg\n"
    }
    manager.spreadsheets.fileprocessor.extract_tabular_sheets.return_value = [
        _tabular_sheet(
            "CSV",
            ["Name", "Image URL"],
            [{"Name": "Lamp", "Image URL": "https://cdn.example/lamp.jpg"}],
        )
    ]
    manager.entities.get_form_fields.return_value = [{"id": "name", "label": "Name"}]
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(items=[])
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="completed",
        output=(
            '{"mappings":[{"file_id":"file_1","sheet_name":"CSV",'
            '"column_mapping":{"Name":["name"]},"remote_file_columns":["Image URL"]}]}'
        ),
        error=None,
        run_id="run-map-1",
    )
    response = _run_analyze(manager)

    draft = response.drafts[0]
    assert draft.file_ids == []
    assert draft.remote_file_references[0].status == "referenced"
    assert draft.remote_file_references[0].source_url == "https://cdn.example/lamp.jpg"
    assert response.spreadsheet_sources[0].remote_file_columns == ["Image URL"]
    assert response.spreadsheet_sources[0].unmapped_columns == []
    manager.remote_files.fetch_many.assert_not_called()
    filehandler.upload_file.assert_not_called()


def test_final_commit_downloads_and_stores_only_selected_remote_references() -> None:
    selected = BulkImportDraft(
        draft_id="selected",
        data={"identifier": "Lamp"},
        selected=True,
        remote_file_references=[
            BulkImportRemoteFileReference(
                source_column="Image URL",
                source_value="https://cdn.example/lamp.jpg",
                source_url="https://cdn.example/lamp.jpg",
                status="referenced",
            )
        ],
    )
    rejected = BulkImportDraft(
        draft_id="rejected",
        data={"identifier": "Desk"},
        selected=False,
        remote_file_references=[
            BulkImportRemoteFileReference(
                source_column="Image URL",
                source_value="https://cdn.example/desk.jpg",
                source_url="https://cdn.example/desk.jpg",
                status="referenced",
            )
        ],
    )
    job = _job(
        status="COMMITTING",
        drafts=[selected.model_dump(mode="json"), rejected.model_dump(mode="json")],
    )
    manager, filehandler = _manager(job)
    manager.remote_files.fetch_many.return_value = {
        "https://cdn.example/lamp.jpg": FetchedRemoteFile(
            source_url="https://cdn.example/lamp.jpg",
            final_url="https://cdn.example/lamp.jpg",
            filename="lamp.jpg",
            content_type="image/jpeg",
            content=b"jpeg-bytes",
            sha256="abc123",
        )
    }
    filehandler.upload_file.return_value = SimpleNamespace(
        file_id="remote-1",
        filename="lamp.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        metadata={"source_url": "https://cdn.example/lamp.jpg"},
    )

    manager._materialize_selected_remote_files(
        ACTOR, job.context, job.job_id, [selected, rejected]
    )

    manager.remote_files.fetch_many.assert_called_once_with(
        ["https://cdn.example/lamp.jpg"]
    )
    assert selected.file_ids == ["remote-1"]
    assert selected.remote_file_references[0].status == "stored"
    assert rejected.file_ids == []
    upload = filehandler.upload_file.call_args.args[2]
    assert upload.metadata["bulk_import_job_id"] == "job-1"
    assert upload.metadata["source_url"] == "https://cdn.example/lamp.jpg"


def test_commit_materializes_three_records_then_creates_them_before_next_batch() -> None:
    drafts = [
        BulkImportDraft(draft_id=f"draft-{index}", data={"identifier": f"item-{index}"})
        for index in range(4)
    ]
    job = _job(
        status="COMMITTING",
        drafts=[draft.model_dump(mode="json") for draft in drafts],
    )
    manager, _ = _manager(job)
    manager._commit_batch_size = 3
    events: list[str] = []

    def materialize(_actor, _context, _job_id, batch):
        events.append("fetch:" + ",".join(draft.draft_id for draft in batch))

    def create(_actor, _context, draft, _identifier_template):
        events.append(f"create:{draft.draft_id}")
        draft.entity_id = f"entity-{draft.draft_id}"

    manager._materialize_selected_remote_files = MagicMock(side_effect=materialize)
    manager._resolve_or_create_entity = MagicMock(side_effect=create)
    manager._attach_files = MagicMock()
    manager._enroll_workflow_if_needed = MagicMock()

    failures = manager._process_selected_drafts(
        ACTOR, job.context, "org-1", job.job_id, drafts
    )

    assert failures == 0
    assert events == [
        "fetch:draft-0,draft-1,draft-2",
        "create:draft-0",
        "create:draft-1",
        "create:draft-2",
        "fetch:draft-3",
        "create:draft-3",
    ]
    assert set(job.context["commit_processed_draft_ids"]) == {
        "draft-0", "draft-1", "draft-2", "draft-3"
    }
    assert job.context["commit_total_count"] == 4


def test_materialization_reuses_a_remote_file_stored_by_an_earlier_batch() -> None:
    reference = BulkImportRemoteFileReference(
        source_column="Image URL",
        source_value="https://cdn.example/lamp.jpg",
        source_url="https://cdn.example/lamp.jpg",
        status="referenced",
    )
    draft = BulkImportDraft(
        draft_id="later-batch",
        data={"identifier": "Lamp"},
        remote_file_references=[reference],
    )
    job = _job(status="COMMITTING", drafts=[draft.model_dump(mode="json")])
    job.context["remote_files"] = [{
        "file_id": "remote-1",
        "filename": "lamp.jpg",
        "content_type": "image/jpeg",
        "size_bytes": 10,
        "metadata": {"source_url": "https://cdn.example/lamp.jpg"},
    }]
    manager, _ = _manager(job)

    manager._materialize_selected_remote_files(ACTOR, job.context, job.job_id, [draft])

    manager.remote_files.fetch_many.assert_not_called()
    assert draft.file_ids == ["remote-1"]
    assert reference.file_id == "remote-1"
    assert reference.status == "stored"


def test_spreadsheet_filename_reference_reuses_an_uploaded_file_without_fetching() -> None:
    job = _job(status="UPLOADED", drafts=[])
    job.context["files"] = [
        {"file_id": "sheet-1", "filename": "products.csv", "content_type": "text/csv", "size_bytes": 20},
        {"file_id": "image-1", "filename": "lamp.jpg", "content_type": "image/jpeg", "size_bytes": 10},
    ]
    manager, _ = _manager(job)
    manager.filehandler.read_document_source.return_value = {
        "filename": "products.csv", "content_type": "text/csv", "file_bytes": b"Name,Image\nLamp,lamp.jpg\n"
    }
    manager.spreadsheets.fileprocessor.extract_tabular_sheets.return_value = [
        _tabular_sheet(
            "CSV",
            ["Name", "Image"],
            [{"Name": "Lamp", "Image": "lamp.jpg"}],
        )
    ]
    manager.entities.get_form_fields.return_value = [{"id": "name", "label": "Name"}]
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(items=[])
    manager.agents.list_definitions_for_actor.return_value = [SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")]
    manager.agents.run_agent_for_actor.side_effect = [
        SimpleNamespace(
            status="completed",
            output='{"mappings":[{"file_id":"file_1","sheet_name":"CSV","column_mapping":{"Name":["name"]},"remote_file_columns":["Image"]}]}',
            error=None,
            run_id="run-map-1",
        ),
        SimpleNamespace(
            status="completed",
            output='{"entities":[],"skipped_files":[]}',
            error=None,
            metadata={},
        ),
    ]

    response = _run_analyze(manager)

    assert response.drafts[0].file_ids == ["image-1"]
    assert response.drafts[0].remote_file_references[0].status == "resolved"
    manager.remote_files.fetch_many.assert_not_called()


def test_review_accepts_staged_remote_file_ids_owned_by_the_job() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"identifier": "Lamp"}, file_ids=["remote-1"])
    job = _job(drafts=[draft.model_dump(mode="json")])
    job.context["remote_files"] = [{"file_id": "remote-1", "filename": "lamp.jpg"}]
    manager, _ = _manager(job)

    response = manager.update_review(
        ACTOR,
        job.job_id,
        BulkImportReviewRequest(drafts=[draft], workflow_name="Hiring"),
    )

    assert response.drafts[0].file_ids == ["remote-1"]


def test_analyze_mixed_job_sends_only_documents_to_agent() -> None:
    job = _job(status="UPLOADED", drafts=[])
    job.context["files"] = [
        {"file_id": "sheet-1", "filename": "people.csv", "content_type": "text/csv", "size_bytes": 10},
        {"file_id": "doc-1", "filename": "resume.pdf", "content_type": "application/pdf", "size_bytes": 20},
    ]
    manager, _ = _manager(job)
    manager.filehandler.read_document_source.return_value = {
        "filename": "people.csv",
        "content_type": "text/csv",
        "file_bytes": b"Name\nJane\n",
    }
    manager.spreadsheets.fileprocessor.extract_tabular_sheets.return_value = [
        _tabular_sheet("CSV", ["Name"], [{"Name": "Jane"}])
    ]
    manager.entities.get_form_fields.return_value = [{"id": "name", "label": "Name"}]
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(items=[])
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.side_effect = [
        SimpleNamespace(
            status="completed",
            output=(
                '{"mappings":[{"file_id":"file_1","sheet_name":"CSV",'
                '"column_mapping":{"Name":["name"]}}]}'
            ),
            error=None,
            run_id="run-map-1",
        ),
        SimpleNamespace(
            status="completed",
            output='{"entities":[{"data":{"name":"From PDF"},"file_ids":["file_1"]}],"skipped_files":[]}',
            error=None,
            metadata={},
        ),
    ]

    response = _run_analyze(manager)

    assert len(response.drafts) == 2
    assert manager.agents.run_agent_for_actor.call_count == 2
    request = manager.agents.run_agent_for_actor.call_args.args[1]
    assert request.file_slug_map == {"file_1": "doc-1"}
    assert "resume.pdf" in request.input
    assert "people.csv" not in request.input


def test_spreadsheet_mapping_supports_many_to_many_without_another_agent_run() -> None:
    job = _job(status="UPLOADED", drafts=[])
    job.context["files"] = [
        {"file_id": "sheet-1", "filename": "people.csv", "content_type": "text/csv", "size_bytes": 10}
    ]
    manager, _ = _manager(job)
    manager.filehandler.read_document_source.return_value = {
        "filename": "people.csv",
        "content_type": "text/csv",
        "file_bytes": b"First Name,Last Name\nJane,Doe\n",
    }
    manager.spreadsheets.fileprocessor.extract_tabular_sheets.return_value = [
        _tabular_sheet(
            "CSV",
            ["First Name", "Last Name"],
            [{"First Name": "Jane", "Last Name": "Doe"}],
        )
    ]
    manager.entities.get_form_fields.return_value = [
        {"id": "full_name", "label": "Full Name"},
        {"id": "display_name", "label": "Display Name"},
    ]
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(items=[])
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="completed",
        output=(
            '{"mappings":[{"file_id":"file_1","sheet_name":"CSV",'
            '"column_mapping":{}}]}'
        ),
        error=None,
        run_id="run-map-1",
    )
    analyzed = _run_analyze(manager)
    assert analyzed.drafts[0].selected is False

    response = manager.update_spreadsheet_mapping(
        ACTOR,
        job.job_id,
        BulkImportSpreadsheetMappingRequest(
            mappings=[
                BulkImportSpreadsheetMapping(
                    file_id="sheet-1",
                    sheet_name="CSV",
                    column_mapping={
                        "First Name": ["full_name", "display_name"],
                        "Last Name": ["full_name"],
                    },
                )
            ]
        ),
    )

    assert response.drafts[0].data == {"full_name": "Jane Doe", "display_name": "Jane"}
    assert response.drafts[0].selected is True
    assert response.spreadsheet_sources[0].unmapped_columns == []
    assert manager.agents.run_agent_for_actor.call_count == 1


def test_analyze_records_skipped_files_without_failing_the_job() -> None:
    """The agent notes a file it couldn't read via skipped_files — the job still
    completes; only that file is recorded as failed/unmapped."""
    job = _job(status="UPLOADED", drafts=[])
    manager, _ = _manager(job)
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="completed",
        output=(
            '{"entities":[],"skipped_files":'
            '[{"file_id":"file_1","reason":"could not parse document"}]}'
        ),
        error=None,
        metadata={},
    )
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[]
    )

    response = _run_analyze(manager)

    assert response.status == "READY_FOR_REVIEW"
    assert response.drafts == []
    assert response.failed_count == 1
    assert "file-1" in response.unmapped_file_ids
    assert response.errors


def test_analyze_records_whole_run_failure_without_failing_permanently() -> None:
    """The agent run itself fails (not a per-file skip) — the whole job fails and
    is retryable via analyze() again. The failure message is enriched with the
    tool-activity summary (tool call count, read attempts, rejections, misuse) so
    it's diagnosable later without a debugger."""
    job = _job(status="UPLOADED", drafts=[])
    manager, _ = _manager(job)
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="failed",
        output=None,
        error="extraction timed out",
        metadata={
            "tool_calls": [
                {
                    "tool": "read_job_document",
                    "args": {"file_ids": ["file-1", "file-2", "file-3", "file-4"]},
                    "result": {
                        "success": False,
                        "error": "read_job_document accepts at most 3 file_ids per call",
                    },
                }
            ]
        },
    )

    queued = manager.analyze(ACTOR, "job-1")
    assert queued.status == "QUEUED"
    with pytest.raises(ServiceError, match="extraction timed out"):
        manager._run_queued_analysis("job-1", "org-1")

    assert job.status == "FAILED"
    assert any("extraction timed out" in str(err) for err in job.context["errors"])
    assert any("1 tool misuse" in str(err) for err in job.context["errors"])
    summary = job.context["extraction_summary"]
    assert summary["tool_call_count"] == 1
    assert len(summary["misused_tool_calls"]) == 1
    assert "at most 3 file_ids" in summary["misused_tool_calls"][0]["error"]


def test_summarize_agent_run_flags_rejected_files_and_tool_misuse() -> None:
    files = [{"file_id": "file-1", "filename": "resume.pdf"}]
    run_metadata = {
        "tool_calls": [
            {"tool": "get_form_schema", "args": {}, "result": {"success": True}},
            {
                "tool": "read_job_document",
                "args": {"file_ids": ["file_1"]},
                "result": {
                    "success": True,
                    "output": {
                        "results": [
                            {"file_id": "file_1", "status": "error", "message": "document not found: file_1"}
                        ]
                    },
                },
            },
            {
                "tool": "read_job_document",
                "args": {"file_ids": ["a", "b", "c", "d"]},
                "result": {"success": False, "error": "accepts at most 3 file_ids per call"},
            },
        ]
    }
    slug_map = {"file_1": "file-1"}

    summary = BulkImportServiceManager._summarize_agent_run(run_metadata, files, slug_map)

    assert summary["tool_call_count"] == 3
    assert summary["read_job_document_call_count"] == 2
    # The trace itself is in slugs (same as everything else the model sees) —
    # the summary translates back to the real file id via slug_map.
    assert summary["rejected_files"] == [
        {"file_id": "file-1", "filename": "resume.pdf", "reason": "document not found: file_1"}
    ]
    assert len(summary["misused_tool_calls"]) == 1
    assert summary["misused_tool_calls"][0]["error"] == "accepts at most 3 file_ids per call"


def test_analyze_marks_job_failed_when_extraction_agent_missing() -> None:
    job = _job(status="UPLOADED", drafts=[])
    manager, _ = _manager(job)
    manager.agents.list_definitions_for_actor.return_value = []  # no bulk_import_extractor agent

    queued = manager.analyze(ACTOR, "job-1")
    assert queued.status == "QUEUED"
    with pytest.raises(ServiceError, match="agent is unavailable"):
        manager._run_queued_analysis("job-1", "org-1")

    assert job.status == "FAILED"


def test_analyze_handles_a_job_with_zero_files_without_crashing() -> None:
    job = _job(status="UPLOADED", drafts=[])
    job.context["files"] = []
    manager, _ = _manager(job)
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[]
    )

    response = _run_analyze(manager)

    assert response.status == "READY_FOR_REVIEW"
    assert response.drafts == []
    manager.agents.run_agent_for_actor.assert_not_called()


def test_retried_analyze_recalls_the_agent_for_the_whole_job() -> None:
    """No per-file checkpointing anymore — a retry re-runs the whole job's
    extraction from scratch in one fresh agent call."""
    job = _job(status="FAILED", drafts=[])
    job.context["files"].append(
        {
            "file_id": "file-2",
            "filename": "cover-letter.pdf",
            "content_type": "application/pdf",
            "size_bytes": 12,
        }
    )
    manager, _ = _manager(job)
    manager.agents.list_definitions_for_actor.return_value = [
        SimpleNamespace(name=BULK_IMPORT_AGENT, definition_id="def-1")
    ]
    manager.agents.run_agent_for_actor.return_value = SimpleNamespace(
        status="completed",
        output=json.dumps(
            {
                "entities": [
                    {
                        "data": {"identifier": "a@b.com"},
                        "confidence": 0.9,
                        "file_ids": ["file_1"],
                    },
                    {
                        "data": {"identifier": "b@c.com"},
                        "confidence": 0.8,
                        "file_ids": ["file_2"],
                    },
                ],
                "skipped_files": [],
            }
        ),
        error=None,
        metadata={},
    )
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[]
    )

    response = _run_analyze(manager)

    assert manager.agents.run_agent_for_actor.call_count == 1
    request = manager.agents.run_agent_for_actor.call_args.args[1]
    assert request.file_slug_map == {"file_1": "file-1", "file_2": "file-2"}
    assert "file_1" in request.input and "file_2" in request.input
    assert "resume.pdf" in request.input and "cover-letter.pdf" in request.input
    assert response.status == "READY_FOR_REVIEW"
    identifiers = {draft.data["identifier"] for draft in response.drafts}
    assert identifiers == {"a@b.com", "b@c.com"}


# --- commit: queue-and-return + worker-facing _run_queued_commit ------------------


def test_commit_queues_the_job_and_returns_immediately() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"identifier": "A"}, file_ids=["file-1"])
    job = _job(drafts=[draft.model_dump(mode="json")])
    manager, _ = _manager(job)

    response = manager.commit(ACTOR, "job-1", "key-1")

    assert response.status == "QUEUED"
    assert response.operation == "commit"
    assert job.context["queued_for"] == "commit"
    assert job.context["commit_idempotency_key"] == "key-1"
    manager.entities.create_entity_record_for_actor.assert_not_called()


def test_commit_is_a_noop_when_job_already_completed() -> None:
    job = _job(status="COMPLETED", drafts=[])
    manager, _ = _manager(job)

    response = manager.commit(ACTOR, "job-1", "key-1")

    assert response.status == "COMPLETED"
    assert job.status == "COMPLETED"  # never queued a second time


def test_commit_rejects_blank_idempotency_key() -> None:
    job = _job()
    manager, _ = _manager(job)

    with pytest.raises(ValidationError, match="Idempotency-Key"):
        manager.commit({"organization_id": "org-1", "user_id": "user-1"}, "job-1", "   ")


def test_cancel_running_commit_requests_a_safe_stop() -> None:
    job = _job(status="COMMITTING", drafts=[])
    manager, _ = _manager(job)

    response = manager.cancel(ACTOR, "job-1")

    assert response.status == "CANCELLING"
    assert response.cancel_requested is True


def test_cancel_queued_job_is_immediately_terminal_and_resumable() -> None:
    job = _job(status="QUEUED", drafts=[], queued_for="commit")
    manager, _ = _manager(job)

    stopped = manager.cancel(ACTOR, "job-1")
    resumed = manager.resume(ACTOR, "job-1")

    assert stopped.status == "CANCELLED"
    assert resumed.status == "QUEUED"
    assert resumed.operation == "commit"
    assert resumed.cancel_requested is False


def test_commit_rejects_a_job_that_is_not_ready_or_partially_completed() -> None:
    job = _job(status="PROCESSING", drafts=[])
    manager, _ = _manager(job)

    with pytest.raises(ConflictError):
        manager.commit(ACTOR, "job-1", "key-1")


def test_run_queued_commit_raises_conflict_when_job_is_not_queued() -> None:
    job = _job(status="READY_FOR_REVIEW", drafts=[])
    manager, _ = _manager(job)

    with pytest.raises(ConflictError):
        manager._run_queued_commit("job-1", "org-1")


def test_commit_creates_new_entity_when_no_existing_match() -> None:
    draft = BulkImportDraft(
        draft_id="draft-1",
        data={"identifier": "new@example.com", "name": "New"},
        file_ids=["file-1"],
    )
    job = _job(drafts=[draft.model_dump(mode="json")])
    manager, filehandler = _manager(job)
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[]
    )
    manager.entities.create_entity_record_for_actor.return_value = SimpleNamespace(
        entity_id="entity-new"
    )
    filehandler.db_model_service.get_file.return_value = SimpleNamespace(owner_entity_id=None)

    response = _run_commit(manager, "key-1")

    manager.entities.create_entity_record_for_actor.assert_called_once()
    assert manager.entities.create_entity_record_for_actor.call_args.kwargs[
        "require_reference_sources"
    ] is True
    assert response.status == "COMPLETED"
    assert response.drafts[0].entity_id == "entity-new"
    assert response.drafts[0].existing_entity is False
    assert response.created_count == 1


def test_link_existing_entity_uses_idempotent_source_link_update() -> None:
    manager, _ = _manager(_job())
    draft = BulkImportDraft(
        draft_id="draft-1",
        entity_id="entity-1",
        existing_entity=True,
        relation_bindings=[
            {
                "relation_def_id": "rel-1",
                "source_entity_type_id": "provider",
                "source_entity_type_name": "Provider",
                "relation_type": "SNAPSHOT",
                "mode": "fixed",
                "source_entity_id": "provider-1",
                "status": "resolved",
            }
        ],
    )

    manager._link_existing_entity(ACTOR, draft)

    actor, entity_id, request = manager.entities.update_entity_record_for_actor.call_args.args
    assert actor == ACTOR
    assert entity_id == "entity-1"
    assert request.source_entity_ids == ["provider-1"]


def _setup_new_entity_commit(manager, filehandler, *, identifier_template=None, taken=None):
    """Common wiring for a commit that should reach _create_entity."""
    manager.entities.get_identifier_template_for_actor.return_value = identifier_template
    manager.entities.is_identifier_taken_for_actor.side_effect = taken
    manager.entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[]
    )
    manager.entities.create_entity_record_for_actor.return_value = SimpleNamespace(
        entity_id="entity-new"
    )
    filehandler.db_model_service.get_file.return_value = SimpleNamespace(owner_entity_id=None)


def _created_data(manager) -> dict:
    """Return the `data` dict passed to the last create_entity_record_for_actor call."""
    _, request = manager.entities.create_entity_record_for_actor.call_args.args
    return request.data


def test_commit_synthesizes_identifier_from_priority_field_in_manual_mode() -> None:
    draft = BulkImportDraft(
        draft_id="draft-1", data={"full_name": "Mandeep Singh"}, file_ids=["file-1"]
    )
    job = _job(drafts=[draft.model_dump(mode="json")])
    manager, filehandler = _manager(job)
    _setup_new_entity_commit(manager, filehandler, identifier_template=None, taken=[False])

    response = _run_commit(manager, "key-1")

    assert response.status == "COMPLETED"
    assert _created_data(manager)["identifier"] == "Mandeep Singh"


def test_commit_skips_synthesis_when_identifier_template_configured() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"full_name": "Mandeep Singh"}, file_ids=["file-1"])
    job = _job(drafts=[draft.model_dump(mode="json")])
    manager, filehandler = _manager(job)
    _setup_new_entity_commit(manager, filehandler, identifier_template="CUST-{{seq}}", taken=None)

    response = _run_commit(manager, "key-1")

    assert response.status == "COMPLETED"
    manager.entities.is_identifier_taken_for_actor.assert_not_called()
    assert "identifier" not in _created_data(manager)


def test_commit_suffixes_synthesized_identifier_on_collision() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"full_name": "Susan Anderson"}, file_ids=["file-1"])
    job = _job(drafts=[draft.model_dump(mode="json")])
    manager, filehandler = _manager(job)
    _setup_new_entity_commit(manager, filehandler, identifier_template=None, taken=[True, False])

    response = _run_commit(manager, "key-1")

    assert response.status == "COMPLETED"
    assert _created_data(manager)["identifier"] == "Susan Anderson_2"


def test_commit_synthesizes_identifier_from_any_string_field_when_priority_fields_absent() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"country": "India"}, file_ids=["file-1"])
    job = _job(drafts=[draft.model_dump(mode="json")])
    manager, filehandler = _manager(job)
    _setup_new_entity_commit(manager, filehandler, identifier_template=None, taken=[False])

    response = _run_commit(manager, "key-1")

    assert response.status == "COMPLETED"
    assert _created_data(manager)["identifier"] == "India"


def test_commit_synthesizes_generic_identifier_when_no_string_fields_at_all() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"satisfaction_score": 5}, file_ids=["file-1"])
    job = _job(drafts=[draft.model_dump(mode="json")])
    manager, filehandler = _manager(job)
    _setup_new_entity_commit(manager, filehandler, identifier_template=None, taken=[False])

    response = _run_commit(manager, "key-1")

    assert response.status == "COMPLETED"
    assert _created_data(manager)["identifier"] == "record"


def test_commit_does_not_resynthesize_identifier_already_present() -> None:
    draft = BulkImportDraft(
        draft_id="draft-1", data={"identifier": "manual@example.com"}, file_ids=["file-1"]
    )
    job = _job(drafts=[draft.model_dump(mode="json")])
    manager, filehandler = _manager(job)
    _setup_new_entity_commit(manager, filehandler, identifier_template=None, taken=None)

    response = _run_commit(manager, "key-1")

    assert response.status == "COMPLETED"
    manager.entities.is_identifier_taken_for_actor.assert_not_called()
    assert _created_data(manager)["identifier"] == "manual@example.com"


def test_retry_finishes_files_and_workflow_without_recreating_entity() -> None:
    draft = BulkImportDraft(
        draft_id="draft-1",
        data={"identifier": "A"},
        file_ids=["file-1"],
        entity_id="entity-1",
        error="previous attachment failure",
    )
    job = _job(status="COMPLETED_WITH_ERRORS", drafts=[draft.model_dump(mode="json")])
    manager, filehandler = _manager(job)

    response = _run_commit(manager, "retry-key")

    manager.entities.create_entity_record_for_actor.assert_not_called()
    filehandler.db_model_service.set_file_owner.assert_called_once_with(
        "org-1", "file-1", "entity-1"
    )
    manager.workflows.enroll_entity_for_actor.assert_called_once()
    assert response.status == "COMPLETED"
    assert response.drafts[0].files_attached is True
    assert response.drafts[0].workflow_enrolled is True


def test_retry_skips_files_attached_before_a_later_failure() -> None:
    draft = BulkImportDraft(
        draft_id="draft-1",
        data={"identifier": "A"},
        file_ids=["file-1", "file-2"],
        entity_id="entity-1",
    )
    job = _job(drafts=[draft.model_dump(mode="json")])
    job.context["files"].append(
        {
            "file_id": "file-2",
            "filename": "cover-letter.pdf",
            "content_type": "application/pdf",
            "size_bytes": 12,
        }
    )
    manager, filehandler = _manager(job)
    filehandler.db_model_service.get_file.return_value = SimpleNamespace(owner_entity_id=None)
    filehandler.db_model_service.set_file_owner.side_effect = [
        None,
        RuntimeError("storage failed"),
    ]

    first = _run_commit(manager, "first-key")

    assert first.status == "COMPLETED_WITH_ERRORS"
    assert first.drafts[0].attached_file_ids == ["file-1"]

    filehandler.db_model_service.set_file_owner.side_effect = None
    retried = _run_commit(manager, "retry-key")

    attached_ids = [
        call.args[1]
        for call in filehandler.db_model_service.set_file_owner.call_args_list
    ]
    assert attached_ids.count("file-1") == 1
    assert attached_ids.count("file-2") == 2
    assert retried.status == "COMPLETED"
    assert retried.drafts[0].attached_file_ids == ["file-1", "file-2"]
    assert retried.drafts[0].files_attached is True


# --- _reconstruct_actor ------------------------------------------------------------


def test_reconstruct_actor_rebuilds_actor_from_stored_snapshot() -> None:
    job = _job(actor_user_id="user-42")

    actor = BulkImportServiceManager._reconstruct_actor(job)

    assert actor == {"organization_id": "org-1", "user_id": "user-42"}


def test_reconstruct_actor_raises_when_snapshot_missing() -> None:
    job = _job(actor_user_id=None)

    with pytest.raises(ValidationError, match="actor_user_id snapshot"):
        BulkImportServiceManager._reconstruct_actor(job)


# --- list_jobs (recent-imports list) -----------------------------------------------


def test_list_jobs_returns_only_bulk_import_jobs() -> None:
    draft = BulkImportDraft(draft_id="draft-1", data={"identifier": "A"}, file_ids=["file-1"])
    bulk_job = _job(job_id="job-1", status="READY_FOR_REVIEW", drafts=[draft.model_dump(mode="json")])
    other_job = _job(job_id="job-2", status="READY_FOR_REVIEW", drafts=[])
    other_job.source_type = "other_source"
    manager, _ = _build_manager(_MultiJobs([bulk_job, other_job]))

    response = manager.list_jobs(ACTOR)

    job_ids = {item.job_id for item in response.items}
    assert job_ids == {"job-1"}
    summary = next(item for item in response.items if item.job_id == "job-1")
    assert summary.status == "READY_FOR_REVIEW"
    assert summary.entity_type_name == "Candidate"
    assert summary.file_count == 1
    assert summary.draft_count == 1


def test_list_jobs_respects_the_recent_jobs_limit() -> None:
    jobs = [_job(job_id=f"job-{i}", status="READY_FOR_REVIEW", drafts=[]) for i in range(3)]
    manager, _ = _build_manager(_MultiJobs(jobs))
    manager._recent_jobs_limit = 2

    response = manager.list_jobs(ACTOR)

    assert len(response.items) == 2


def test_list_jobs_returns_empty_when_no_jobs_exist() -> None:
    manager, _ = _build_manager(_MultiJobs([]))

    response = manager.list_jobs(ACTOR)

    assert response.items == []


# --- worker dispatch (_dispatch_queued_job / _claim_and_process_next_batch) -------


def test_dispatch_queued_job_routes_to_analyze_by_default() -> None:
    job = _job(status="QUEUED", drafts=[])
    manager, _ = _manager(job)
    manager._run_queued_analysis = MagicMock()
    manager._run_queued_commit = MagicMock()

    manager._dispatch_queued_job(job)

    manager._run_queued_analysis.assert_called_once_with("job-1", "org-1")
    manager._run_queued_commit.assert_not_called()


def test_dispatch_queued_job_routes_to_commit_when_marked() -> None:
    job = _job(status="QUEUED", drafts=[], queued_for="commit")
    manager, _ = _manager(job)
    manager._run_queued_analysis = MagicMock()
    manager._run_queued_commit = MagicMock()

    manager._dispatch_queued_job(job)

    manager._run_queued_commit.assert_called_once_with("job-1", "org-1")
    manager._run_queued_analysis.assert_not_called()


def test_dispatch_queued_job_swallows_conflict_error() -> None:
    job = _job(status="QUEUED", drafts=[], queued_for="analyze")
    manager, _ = _manager(job)
    manager._run_queued_analysis = MagicMock(side_effect=ConflictError("already claimed"))

    manager._dispatch_queued_job(job)  # must not raise


def test_dispatch_queued_job_swallows_unexpected_errors() -> None:
    job = _job(status="QUEUED", drafts=[], queued_for="analyze")
    manager, _ = _manager(job)
    manager._run_queued_analysis = MagicMock(side_effect=RuntimeError("boom"))

    manager._dispatch_queued_job(job)  # must not raise — worker loop must survive


def test_claim_and_process_next_batch_returns_false_when_nothing_queued() -> None:
    manager, _ = _build_manager(_MultiJobs([]))

    assert manager._claim_and_process_next_batch() is False


def test_claim_and_process_next_batch_dispatches_every_queued_job() -> None:
    analyze_job = _job(job_id="job-1", status="QUEUED", drafts=[], queued_for="analyze")
    commit_job = _job(job_id="job-2", status="QUEUED", drafts=[], queued_for="commit")
    other_org_job = _job(job_id="job-3", status="READY_FOR_REVIEW", drafts=[])
    manager, _ = _build_manager(_MultiJobs([analyze_job, commit_job, other_org_job]))
    manager._run_queued_analysis = MagicMock()
    manager._run_queued_commit = MagicMock()

    claimed_any = manager._claim_and_process_next_batch()

    assert claimed_any is True
    manager._run_queued_analysis.assert_called_once_with("job-1", "org-1")
    manager._run_queued_commit.assert_called_once_with("job-2", "org-1")


# --- stale-job sweep (_sweep_stale_jobs / _sweep_one_stale_job) -------------------


def test_sweep_forces_a_stale_processing_job_to_failed() -> None:
    stale = _job(
        status="PROCESSING", drafts=[], updated_at=datetime.now(UTC) - timedelta(hours=1)
    )
    manager, _ = _build_manager(_MultiJobs([stale]))

    manager._sweep_stale_jobs()

    assert stale.status == "FAILED"
    assert any("stale" in str(err) for err in stale.context["errors"])


def test_sweep_forces_a_stale_committing_job_to_completed_with_errors() -> None:
    stale = _job(
        status="COMMITTING", drafts=[], updated_at=datetime.now(UTC) - timedelta(hours=1)
    )
    manager, _ = _build_manager(_MultiJobs([stale]))

    manager._sweep_stale_jobs()

    assert stale.status == "COMPLETED_WITH_ERRORS"


def test_sweep_never_marks_a_stale_job_completed() -> None:
    """Core invariant: the sweep may never assert unproven success."""
    stale = _job(
        status="COMMITTING", drafts=[], updated_at=datetime.now(UTC) - timedelta(hours=1)
    )
    manager, _ = _build_manager(_MultiJobs([stale]))

    manager._sweep_stale_jobs()

    assert stale.status != "COMPLETED"


def test_sweep_leaves_a_job_within_the_threshold_untouched() -> None:
    fresh = _job(status="PROCESSING", drafts=[], updated_at=datetime.now(UTC))
    manager, _ = _build_manager(_MultiJobs([fresh]))

    manager._sweep_stale_jobs()

    assert fresh.status == "PROCESSING"


def test_sweep_skips_a_job_that_moved_on_before_the_write() -> None:
    """A job the sweep read as stale-PROCESSING but that finished right before
    the sweep's own write must not be forced — the conflict is swallowed."""
    stale_snapshot = _job(
        status="PROCESSING", drafts=[], updated_at=datetime.now(UTC) - timedelta(hours=1)
    )
    jobs = _MultiJobs([stale_snapshot])
    manager, _ = _build_manager(jobs)
    jobs.jobs["job-1"].status = "READY_FOR_REVIEW"  # moved on since the sweep's read

    manager._sweep_one_stale_job(stale_snapshot)  # must not raise

    assert jobs.jobs["job-1"].status == "READY_FOR_REVIEW"  # untouched


# --- start() / stop() gating -------------------------------------------------------


def test_start_is_a_noop_when_worker_is_disabled(monkeypatch) -> None:
    manager, _ = _build_manager(_MultiJobs([]))
    fake_config = SimpleNamespace(bulk_import_configuration=SimpleNamespace(worker_enabled=False))
    monkeypatch.setattr("bulk_import.manager.get_configuration", lambda: fake_config)

    manager.start()

    assert manager._started is True
    assert manager._worker_thread.is_alive() is False
    assert manager._sweep_thread is None
    manager.stop()


def test_start_launches_worker_and_sweep_threads_when_enabled(monkeypatch) -> None:
    manager, _ = _build_manager(_MultiJobs([]))
    manager._poll_interval_seconds = 0.01
    manager._sweep_interval_seconds = 0.01
    manager._worker_shutdown_join_seconds = 1.0
    fake_config = SimpleNamespace(bulk_import_configuration=SimpleNamespace(worker_enabled=True))
    monkeypatch.setattr("bulk_import.manager.get_configuration", lambda: fake_config)

    manager.start()
    try:
        assert manager._worker_thread.is_alive()
        assert manager._sweep_thread is not None
        assert manager._sweep_thread.is_alive()
    finally:
        manager.stop()

    assert manager._worker_thread.is_alive() is False
    assert manager._sweep_thread.is_alive() is False

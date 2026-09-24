from __future__ import annotations

from types import SimpleNamespace
from typing import Annotated
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

import bulk_import.controller as controller_module
from bulk_import.controller import FALLBACK_UPLOAD_PREFIX, _upload_filename
from bulk_import.models import BulkImportJobResponse
from exceptions import AuthorizationError, NotFoundError, ValidationError

ACTOR = {"organization_id": "org-1", "user_id": "user-1"}


def test_upload_filename_preserves_supplied_name() -> None:
    assert _upload_filename("candidates.csv") == "candidates.csv"


def test_upload_filename_generates_unique_fallbacks() -> None:
    first = _upload_filename(None)
    second = _upload_filename("")

    assert first.startswith(f"{FALLBACK_UPLOAD_PREFIX}_")
    assert second.startswith(f"{FALLBACK_UPLOAD_PREFIX}_")
    assert first != second


def _fixed_actor_dependency() -> dict[str, object]:
    return ACTOR


@pytest.fixture
def bulk_import_client(monkeypatch):
    """Build a real FastAPI app around the controller with permission checks stubbed out."""
    monkeypatch.setattr(
        controller_module,
        "BulkImportActor",
        Annotated[dict, Depends(_fixed_actor_dependency)],
    )
    monkeypatch.setattr(
        controller_module,
        "require_permission",
        lambda resource, action: _fixed_actor_dependency,
    )

    manager = MagicMock()
    controller = controller_module.BulkImportRestController(manager)
    router = APIRouter()
    controller.prepare(router)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), manager


def _response(**overrides) -> BulkImportJobResponse:
    payload = {
        "job_id": "job-1",
        "status": "UPLOADED",
        "entity_type_id": "candidate",
        "entity_type_name": "Candidate",
    }
    payload.update(overrides)
    return BulkImportJobResponse(**payload)


def test_create_job_endpoint_stores_files_and_delegates_to_manager(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.store_file.return_value = {
        "file_id": "file-1",
        "filename": "resume.pdf",
        "content_type": "application/pdf",
        "size_bytes": 3,
    }
    manager.create_job.return_value = _response()

    response = client.post(
        "/bulk-import/jobs",
        data={"entity_type_id": "candidate"},
        files={"files": ("resume.pdf", b"abc", "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["job_id"] == "job-1"
    manager.store_file.assert_called_once_with(
        ACTOR,
        filename="resume.pdf",
        content_type="application/pdf",
        content=b"abc",
    )
    manager.create_job.assert_called_once_with(
        ACTOR,
        entity_type_id="candidate",
        workflow_name=None,
        files=[manager.store_file.return_value],
        fixed_relation_bindings=[],
    )


def test_create_job_endpoint_rejects_too_many_files(bulk_import_client) -> None:
    client, manager = bulk_import_client

    files = [("files", (f"file-{i}.pdf", b"x", "application/pdf")) for i in range(21)]
    response = client.post(
        "/bulk-import/jobs",
        data={"entity_type_id": "candidate"},
        files=files,
    )

    assert response.status_code == 400
    manager.create_job.assert_not_called()


def test_create_job_endpoint_rejects_invalid_fixed_parent_json_before_upload(
    bulk_import_client,
) -> None:
    client, manager = bulk_import_client

    response = client.post(
        "/bulk-import/jobs",
        data={"entity_type_id": "candidate", "fixed_relation_bindings": "not-json"},
        files={"files": ("resume.pdf", b"abc", "application/pdf")},
    )

    assert response.status_code == 400
    manager.store_file.assert_not_called()
    manager.create_job.assert_not_called()


def test_list_jobs_endpoint_delegates_to_manager(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.list_jobs.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                job_id="job-1",
                status="READY_FOR_REVIEW",
                entity_type_id="candidate",
                entity_type_name="Candidate",
                file_count=2,
                draft_count=1,
                created_at=None,
                updated_at=None,
            )
        ]
    )

    response = client.get("/bulk-import/jobs")

    assert response.status_code == 200
    assert response.json()["items"][0]["job_id"] == "job-1"
    manager.list_jobs.assert_called_once_with(ACTOR)


def test_list_jobs_endpoint_maps_manager_error_to_http_status(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.list_jobs.side_effect = AuthorizationError("permission denied")

    response = client.get("/bulk-import/jobs")

    assert response.status_code == 403


def test_get_job_endpoint_delegates_to_manager(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.get_job.return_value = _response(status="READY_FOR_REVIEW")

    response = client.get("/bulk-import/jobs/job-1")

    assert response.status_code == 200
    assert response.json()["status"] == "READY_FOR_REVIEW"
    manager.get_job.assert_called_once_with(ACTOR, "job-1")


def test_get_job_endpoint_maps_not_found_to_404(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.get_job.side_effect = NotFoundError("bulk import job 'job-1' not found")

    response = client.get("/bulk-import/jobs/job-1")

    assert response.status_code == 404


def test_analyze_endpoint_delegates_to_manager(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.analyze.return_value = _response(status="READY_FOR_REVIEW")

    response = client.post("/bulk-import/jobs/job-1/analyze")

    assert response.status_code == 200
    manager.analyze.assert_called_once_with(ACTOR, "job-1")


def test_review_endpoint_delegates_to_manager(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.update_review.return_value = _response(status="READY_FOR_REVIEW")

    response = client.put(
        "/bulk-import/jobs/job-1/review",
        json={"drafts": [], "unmapped_file_ids": [], "workflow_name": None},
    )

    assert response.status_code == 200
    assert manager.update_review.call_args[0][0] == ACTOR
    assert manager.update_review.call_args[0][1] == "job-1"


def test_spreadsheet_mapping_endpoint_delegates_to_manager(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.update_spreadsheet_mapping.return_value = _response(status="READY_FOR_REVIEW")

    response = client.put(
        "/bulk-import/jobs/job-1/spreadsheet-mapping",
        json={
            "mappings": [
                {
                    "file_id": "file-1",
                    "sheet_name": "CSV",
                    "column_mapping": {"Candidate Name": ["full_name"]},
                }
            ]
        },
    )

    assert response.status_code == 200
    manager.update_spreadsheet_mapping.assert_called_once()


def test_commit_endpoint_requires_idempotency_key_header(bulk_import_client) -> None:
    client, manager = bulk_import_client

    response = client.post("/bulk-import/jobs/job-1/commit")

    assert response.status_code == 422
    manager.commit.assert_not_called()


def test_commit_endpoint_delegates_to_manager(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.commit.return_value = _response(status="COMPLETED")

    response = client.post(
        "/bulk-import/jobs/job-1/commit",
        headers={"Idempotency-Key": "key-1"},
    )

    assert response.status_code == 200
    manager.commit.assert_called_once_with(ACTOR, "job-1", "key-1")


def test_cancel_and_resume_endpoints_delegate_to_manager(bulk_import_client) -> None:
    client, manager = bulk_import_client
    manager.cancel.return_value = _response(status="CANCELLING")
    manager.resume.return_value = _response(status="QUEUED")

    cancelled = client.post("/bulk-import/jobs/job-1/cancel")
    resumed = client.post("/bulk-import/jobs/job-1/resume")

    assert cancelled.status_code == 200
    assert resumed.status_code == 200
    manager.cancel.assert_called_once_with(ACTOR, "job-1")
    manager.resume.assert_called_once_with(ACTOR, "job-1")


def _invoke_endpoint(client, method_name: str):
    """Issue a valid request to the named endpoint so its error path can be exercised."""
    if method_name == "create_job":
        return client.post(
            "/bulk-import/jobs",
            data={"entity_type_id": "candidate"},
            files={"files": ("resume.pdf", b"abc", "application/pdf")},
        )
    if method_name == "analyze":
        return client.post("/bulk-import/jobs/job-1/analyze")
    if method_name == "update_review":
        return client.put("/bulk-import/jobs/job-1/review", json={"drafts": []})
    if method_name == "commit":
        return client.post(
            "/bulk-import/jobs/job-1/commit", headers={"Idempotency-Key": "key-1"}
        )
    raise AssertionError(f"unknown endpoint: {method_name}")


@pytest.mark.parametrize(
    "method_name, exc, expected_status",
    [
        ("create_job", ValidationError("invalid entity type"), 400),
        ("analyze", AuthorizationError("permission denied"), 403),
        ("update_review", NotFoundError("job missing"), 404),
        ("commit", ValidationError("blank idempotency key"), 400),
    ],
)
def test_endpoint_maps_manager_error_to_http_status(
    bulk_import_client, method_name, exc, expected_status
) -> None:
    client, manager = bulk_import_client
    getattr(manager, method_name).side_effect = exc

    response = _invoke_endpoint(client, method_name)

    assert response.status_code == expected_status

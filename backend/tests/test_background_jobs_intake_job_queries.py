"""Real-DB tests for the two cross-tenant intake-job query methods added for the
bulk-import worker (`design_docs/tony_bulk_import_worker_handoff.md`, PR2).

These specifically need real Postgres filtering behaviour (status/source_type/
updated_at predicates across multiple rows) — the existing fake session in
`test_background_jobs_module.py` is a no-op pass-through on `.filter(...)` and
would not actually exercise these queries. Requires the same live Postgres the
rest of the suite's DB-backed tests use (see the Test & Verification Runbook in
`design_docs/jarvis_map.md`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from background_jobs.db_models import BackgroundJobsModelService, IntakeJobModel
from common.configuration import Configuration
from database.manager import DatabaseServiceManager

SOURCE_TYPE = "bulk_import"


@pytest.fixture
def db_service() -> BackgroundJobsModelService:
    """Real BackgroundJobsModelService wired to the same Postgres the app uses."""
    config = Configuration()
    database_service_manager = DatabaseServiceManager(config)
    return BackgroundJobsModelService(database_service_manager)


def _insert_job(
    db_service: BackgroundJobsModelService,
    *,
    status: str,
    source_type: str = SOURCE_TYPE,
    updated_at: datetime | None = None,
    organization_id: str | None = None,
) -> str:
    """Insert a bare intake_jobs row directly and return its job_id (bypassing create_job,
    which doesn't accept an arbitrary status/updated_at)."""
    job_id = str(uuid4())
    with db_service._db_session() as db:
        row = IntakeJobModel(
            job_id=job_id,
            organization_id=organization_id or str(uuid4()),
            status=status,
            source_type=source_type,
            file_count=0,
            files_json=[],
            context_json={},
        )
        db.add(row)
        db.commit()
        if updated_at is not None:
            db.query(IntakeJobModel).filter(IntakeJobModel.job_id == job_id).update(
                {"updated_at": updated_at}
            )
            db.commit()
    return job_id


def _delete_job(db_service: BackgroundJobsModelService, job_id: str) -> None:
    with db_service._db_session() as db:
        db.query(IntakeJobModel).filter(IntakeJobModel.job_id == job_id).delete()
        db.commit()


def test_list_jobs_by_source_and_status_finds_only_matching_cross_org_rows(
    db_service: BackgroundJobsModelService,
) -> None:
    queued_id = _insert_job(db_service, status="QUEUED")
    processing_id = _insert_job(db_service, status="PROCESSING")
    other_source_id = _insert_job(db_service, status="QUEUED", source_type="other_source")
    try:
        results = db_service.list_jobs_by_source_and_status(SOURCE_TYPE, "QUEUED", limit=50)
        result_ids = {row.job_id for row in results}

        assert queued_id in result_ids
        assert processing_id not in result_ids
        assert other_source_id not in result_ids
    finally:
        _delete_job(db_service, queued_id)
        _delete_job(db_service, processing_id)
        _delete_job(db_service, other_source_id)


def test_list_jobs_by_source_and_status_respects_limit(
    db_service: BackgroundJobsModelService,
) -> None:
    ids = [_insert_job(db_service, status="QUEUED") for _ in range(3)]
    try:
        results = db_service.list_jobs_by_source_and_status(SOURCE_TYPE, "QUEUED", limit=2)
        assert len(results) <= 2
    finally:
        for job_id in ids:
            _delete_job(db_service, job_id)


def test_update_job_survives_a_nul_byte_in_context(
    db_service: BackgroundJobsModelService,
) -> None:
    """Regression test: a NUL byte anywhere in extracted data (e.g. garbled OCR/PDF
    text) used to make `update_job` raise `psycopg2.errors.UntranslatableCharacter`
    — and since the failure path's own write carried the same poisoned data, the
    job could never even be marked FAILED, leaving it stuck at PROCESSING forever.
    """
    organization_id = str(uuid4())
    job_id = _insert_job(db_service, status="PROCESSING", organization_id=organization_id)
    try:
        result = db_service.update_job(
            organization_id,
            job_id,
            status="FAILED",
            expected_statuses={"PROCESSING"},
            context={"errors": ["boom: IG52PJ4I\x00garbage"]},
        )

        assert result.status == "FAILED"
        assert "\x00" not in result.context["errors"][0]
        assert "IG52PJ4Igarbage" in result.context["errors"][0]
    finally:
        _delete_job(db_service, job_id)


def test_list_jobs_filters_by_source_type_and_respects_limit(
    db_service: BackgroundJobsModelService,
) -> None:
    organization_id = str(uuid4())
    bulk_import_ids = [
        _insert_job(db_service, status="QUEUED", organization_id=organization_id)
        for _ in range(3)
    ]
    other_source_id = _insert_job(
        db_service, status="QUEUED", source_type="other_source", organization_id=organization_id
    )
    try:
        results = db_service.list_jobs(organization_id, source_type=SOURCE_TYPE, limit=2)
        result_ids = {row.job_id for row in results}

        assert len(results) == 2
        assert result_ids.issubset(set(bulk_import_ids))
        assert other_source_id not in result_ids
    finally:
        for job_id in bulk_import_ids:
            _delete_job(db_service, job_id)
        _delete_job(db_service, other_source_id)


def test_list_stale_jobs_for_source_only_returns_jobs_past_the_threshold(
    db_service: BackgroundJobsModelService,
) -> None:
    now = datetime.now(UTC)
    stale_id = _insert_job(
        db_service, status="PROCESSING", updated_at=now - timedelta(hours=1)
    )
    fresh_id = _insert_job(db_service, status="PROCESSING", updated_at=now)
    wrong_status_id = _insert_job(
        db_service, status="READY_FOR_REVIEW", updated_at=now - timedelta(hours=1)
    )
    try:
        threshold = now - timedelta(minutes=10)
        results = db_service.list_stale_jobs_for_source(
            SOURCE_TYPE, {"PROCESSING", "COMMITTING"}, threshold, limit=50
        )
        result_ids = {row.job_id for row in results}

        assert stale_id in result_ids
        assert fresh_id not in result_ids
        assert wrong_status_id not in result_ids
    finally:
        _delete_job(db_service, stale_id)
        _delete_job(db_service, fresh_id)
        _delete_job(db_service, wrong_status_id)

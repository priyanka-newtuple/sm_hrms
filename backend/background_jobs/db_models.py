"""Persistence adapters for background_jobs."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

from actions.db_models import ActionDefinitionModel
from background_jobs.models.interface import IntakeJobContract
from common.enums import IntakeJobStatus
from database.manager import Base
from exceptions import ConflictError, NotFoundError, PersistenceError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from background_jobs.models.request import CreateIntakeJobRequest, IntakeSourceFileRequest


def _strip_null_bytes(value: Any) -> Any:
    """Recursively strip NUL bytes (\\u0000) from strings in an arbitrary JSON-ish value.

    Postgres's text/JSONB storage cannot hold a literal NUL byte at all — writing
    one raises `psycopg2.errors.UntranslatableCharacter`, no matter how it got
    there. `files_json`/`context_json` on this table routinely carry untrusted,
    unpredictable content (AI-extracted document text, OCR output) that can
    contain a stray NUL byte from a garbled source — sanitizing here, at the
    actual DB-write boundary, is what keeps a poisoned value from being
    unwritable forever (including on every future write, e.g. marking a job
    FAILED or the stale-job sweep resolving it — both would hit the exact same
    error otherwise, since the same poisoned data would still be attached to
    the row).
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_strip_null_bytes(item) for item in value]
    if isinstance(value, dict):
        return {key: _strip_null_bytes(item) for key, item in value.items()}
    return value


@dataclass
class IntakeSourceFileRecord:
    filename: str
    content_type: str
    size_bytes: int
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class IntakeJobRecord:
    job_id: str
    organization_id: str
    status: str
    source_type: str
    files: list[IntakeSourceFileRecord] = field(default_factory=list)
    processed_count: int = 0
    failed_count: int = 0
    subject_entity_type: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    context: dict[str, object] = field(default_factory=dict)


class ActionRunModel(Base):
    __tablename__ = "action_runs"
    __table_args__: ClassVar[dict] = {"extend_existing": True}

    run_id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), nullable=False)
    entity_id = Column(String(36), nullable=False)
    definition_id = Column(String(36), nullable=True)
    action_kind = Column(String(128), nullable=False)
    config_json = Column(JSONB, nullable=False)
    resolved_config_json = Column(JSONB, nullable=True)
    status = Column(String(32), nullable=False)
    outcome = Column(String(64), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    idempotency_key = Column(String(256), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    external_timeout_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class IntakeJobModel(Base):
    __tablename__ = "intake_jobs"
    __table_args__: ClassVar[tuple] = (
        Index("ix_intake_jobs_org", "organization_id"),
        Index("ix_intake_jobs_org_status", "organization_id", "status"),
        {"extend_existing": True},
    )

    job_id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), nullable=False)
    status = Column(String(32), nullable=False)
    source_type = Column(String(100), nullable=False)
    file_count = Column(Integer, nullable=False, default=0, server_default="0")
    processed_count = Column(Integer, nullable=False, default=0, server_default="0")
    failed_count = Column(Integer, nullable=False, default=0, server_default="0")
    subject_entity_type = Column(String(255), nullable=True)
    files_json = Column(JSONB, nullable=False, default=list, server_default="[]")
    context_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BackgroundJobsModelService:
    """Persistence service for intake jobs and action runs."""

    STATUS_QUEUED = IntakeJobStatus.QUEUED.value
    STATUS_PROCESSING = IntakeJobStatus.PROCESSING.value
    STATUS_COMPLETED = IntakeJobStatus.COMPLETED.value
    STATUS_FAILED = IntakeJobStatus.FAILED.value

    def __init__(self, database_service_manager: Any = None) -> None:
        """Initialise the model service. Receives db: Session per call — no session management."""
        self.module_name = "background_jobs"
        self._database_service_manager = database_service_manager

    @contextlib.contextmanager
    def _db_session(self):
        """Yield a fresh DB session, rolling back on error."""
        if self._database_service_manager is None:
            raise PersistenceError("database_service_manager is not configured")
        session = self._database_service_manager.postgres_db_service().get_db_session()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_job(self, request: CreateIntakeJobRequest) -> IntakeJobContract:
        """Persist a new intake job record and return its contract."""
        try:
            with self._db_session() as db:
                job_status = self._resolve_initial_status_db(db, request.organization_id)
                # str(uuid4()) -> 36 chars (with dashes), matching the String(36)
                # job_id column and the convention used across the codebase.
                job_id = str(uuid4())
                files_json = [
                    {
                        "filename": f.filename,
                        "content_type": f.content_type,
                        "size_bytes": f.size_bytes,
                        "metadata": dict(f.metadata),
                    }
                    for f in request.files
                ]
                row = IntakeJobModel(
                    job_id=job_id,
                    organization_id=request.organization_id,
                    status=job_status,
                    source_type=request.source_type,
                    file_count=len(request.files),
                    subject_entity_type=request.subject_entity_type,
                    files_json=_strip_null_bytes(files_json),
                    context_json=_strip_null_bytes(dict(request.context)),
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return self._to_contract(row)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Unable to create intake job: {exc}") from exc

    def get_job(self, organization_id: str, job_id: str) -> IntakeJobContract | None:
        """Return a single intake job contract by org and job id, or None."""
        try:
            with self._db_session() as db:
                row = (
                    db.query(IntakeJobModel)
                    .filter(
                        IntakeJobModel.organization_id == organization_id,
                        IntakeJobModel.job_id == job_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                return self._to_contract(row)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Unable to get intake job: {exc}") from exc

    def list_jobs(
        self,
        organization_id: str,
        status: str | None = None,
        source_type: str | None = None,
        limit: int | None = None,
    ) -> list[IntakeJobContract]:
        """Return intake job contracts for an organisation, optionally filtered/limited."""
        try:
            with self._db_session() as db:
                query = db.query(IntakeJobModel).filter(
                    IntakeJobModel.organization_id == organization_id
                )
                if status is not None:
                    query = query.filter(IntakeJobModel.status == status)
                if source_type is not None:
                    query = query.filter(IntakeJobModel.source_type == source_type)
                query = query.order_by(IntakeJobModel.created_at.desc())
                if limit is not None:
                    query = query.limit(limit)
                rows = query.all()
                return [self._to_contract(row) for row in rows]
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Unable to list intake jobs: {exc}") from exc

    def list_jobs_by_source_and_status(
        self,
        source_type: str,
        status: str,
        limit: int = 25,
    ) -> list[IntakeJobContract]:
        """Return jobs of a given source type and status across every organization.

        Cross-tenant by design — used by a source-specific worker's poll loop
        (e.g. bulk_import), unlike `list_jobs`, which is scoped to one org for
        the API's own job-listing endpoint.
        """
        try:
            with self._db_session() as db:
                rows = (
                    db.query(IntakeJobModel)
                    .filter(
                        IntakeJobModel.source_type == source_type,
                        IntakeJobModel.status == status,
                    )
                    .order_by(IntakeJobModel.created_at.asc())
                    .limit(limit)
                    .all()
                )
                return [self._to_contract(row) for row in rows]
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(
                f"Unable to list jobs by source and status: {exc}"
            ) from exc

    def list_stale_jobs_for_source(
        self,
        source_type: str,
        statuses: set[str],
        older_than: datetime,
        limit: int = 25,
    ) -> list[IntakeJobContract]:
        """Return jobs of a given source type stuck in one of `statuses` since before `older_than`.

        Used by a source-specific worker's stale-job sweep to find jobs whose
        owning worker likely died mid-processing.
        """
        try:
            with self._db_session() as db:
                rows = (
                    db.query(IntakeJobModel)
                    .filter(
                        IntakeJobModel.source_type == source_type,
                        IntakeJobModel.status.in_(statuses),
                        IntakeJobModel.updated_at < older_than,
                    )
                    .order_by(IntakeJobModel.updated_at.asc())
                    .limit(limit)
                    .all()
                )
                return [self._to_contract(row) for row in rows]
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Unable to list stale jobs: {exc}") from exc

    def update_job(
        self,
        organization_id: str,
        job_id: str,
        *,
        status: str | None = None,
        expected_statuses: set[str] | None = None,
        files: list[dict[str, object]] | None = None,
        context: dict[str, object] | None = None,
        processed_count: int | None = None,
        failed_count: int | None = None,
    ) -> IntakeJobContract:
        """Atomically update one tenant-scoped intake job.

        ``expected_statuses`` is a compare-and-set guard used before side
        effects such as AI analysis and entity creation.
        """
        try:
            with self._db_session() as db:
                row = (
                    db.query(IntakeJobModel)
                    .filter(
                        IntakeJobModel.organization_id == organization_id,
                        IntakeJobModel.job_id == job_id,
                    )
                    .with_for_update()
                    .first()
                )
                if row is None:
                    raise NotFoundError(f"intake job '{job_id}' not found")
                if expected_statuses is not None and row.status not in expected_statuses:
                    raise ConflictError(
                        f"intake job '{job_id}' cannot be updated from status '{row.status}'"
                    )
                if status is not None:
                    row.status = status
                if files is not None:
                    row.files_json = _strip_null_bytes([dict(item) for item in files])
                    row.file_count = len(files)
                if context is not None:
                    row.context_json = _strip_null_bytes(dict(context))
                if processed_count is not None:
                    row.processed_count = processed_count
                if failed_count is not None:
                    row.failed_count = failed_count
                row.updated_at = datetime.now(UTC)
                db.commit()
                db.refresh(row)
                return self._to_contract(row)
        except (ConflictError, NotFoundError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError(f"Unable to update intake job: {exc}") from exc

    @staticmethod
    def _to_file_record(file_input: IntakeSourceFileRequest) -> IntakeSourceFileRecord:
        """Convert an intake source file request into an internal file record."""
        return IntakeSourceFileRecord(
            filename=file_input.filename,
            content_type=file_input.content_type,
            size_bytes=file_input.size_bytes,
            metadata=dict(file_input.metadata),
        )

    def _resolve_initial_status_db(self, db: Any, organization_id: str) -> str:
        """Return PROCESSING if no active job exists for the org, otherwise QUEUED."""
        has_active = (
            db.query(IntakeJobModel)
            .filter(
                IntakeJobModel.organization_id == organization_id,
                IntakeJobModel.status == self.STATUS_PROCESSING,
            )
            .first()
        ) is not None
        return self.STATUS_QUEUED if has_active else self.STATUS_PROCESSING

    @staticmethod
    def _to_contract(row: IntakeJobModel) -> IntakeJobContract:
        """Map an IntakeJobModel row to the public IntakeJobContract."""
        created_at = row.created_at.isoformat() if row.created_at else None
        updated_at = row.updated_at.isoformat() if row.updated_at else None
        return IntakeJobContract(
            job_id=row.job_id,
            organization_id=row.organization_id,
            status=row.status,
            source_type=row.source_type,
            file_count=int(row.file_count or 0),
            processed_count=int(row.processed_count or 0),
            failed_count=int(row.failed_count or 0),
            subject_entity_type=row.subject_entity_type,
            created_at=created_at,
            updated_at=updated_at,
            context=dict(row.context_json or {}),
        )

    def list_pending_action_run_ids_for_reconciliation(self, db: Session) -> list[str]:
        """Return only eligible pending runs for worker startup reconciliation."""
        try:
            now = datetime.now(UTC)
            rows = (
                db.query(ActionRunModel.run_id)
                .filter(ActionRunModel.status == "pending")
                .filter(
                    (ActionRunModel.scheduled_at.is_(None))
                    | (ActionRunModel.scheduled_at <= now)
                )
                .order_by(ActionRunModel.created_at.asc())
                .all()
            )
            return [str(row.run_id) for row in rows]
        except Exception as exc:
            raise PersistenceError(f"Unable to list pending action run ids: {exc}") from exc

    def list_pending_action_runs(self, db: Session, limit: int = 25) -> list[dict[str, object]]:
        """Query the database for pending action runs up to the given limit."""
        try:
            now = datetime.now(UTC)
            rows = (
                db.query(ActionRunModel)
                .filter(ActionRunModel.status == "pending")
                .filter(
                    (ActionRunModel.scheduled_at.is_(None)) | (ActionRunModel.scheduled_at <= now)
                )
                .order_by(ActionRunModel.created_at.asc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "run_id": row.run_id,
                    "organization_id": row.organization_id,
                    "entity_id": row.entity_id,
                    "action_kind": row.action_kind,
                    "config_json": row.config_json,
                    "attempts": row.attempts,
                    "scheduled_at": row.scheduled_at,
                }
                for row in rows
            ]
        except Exception as exc:
            raise PersistenceError(f"Unable to list pending action runs: {exc}") from exc

    def mark_action_run_running(self, db: Session, run_id: str) -> bool:
        """Atomically claim an eligible pending action run."""
        try:
            now = datetime.now(UTC)
            updated = (
                db.query(ActionRunModel)
                .filter(ActionRunModel.run_id == run_id)
                .filter(ActionRunModel.status == "pending")
                .filter(
                    (ActionRunModel.scheduled_at.is_(None))
                    | (ActionRunModel.scheduled_at <= now)
                )
                .update(
                    {"status": "running", "updated_at": now, "scheduled_at": None},
                    synchronize_session=False,
                )
            )
            db.commit()
            return updated == 1
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to mark action run as running: {exc}") from exc

    def create_action_run(
        self,
        *,
        organization_id: str,
        entity_id: str,
        action_kind: str,
        config_json: dict[str, object],
        idempotency_key: str,
        scheduled_at: datetime | None = None,
    ) -> tuple[str, bool]:
        """Create one idempotent action run; return ``(run_id, created)``."""
        with self._db_session() as db:
            existing = (
                db.query(ActionRunModel)
                .filter(
                    ActionRunModel.organization_id == organization_id,
                    ActionRunModel.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing is not None:
                return str(existing.run_id), False
            definition = (
                db.query(ActionDefinitionModel)
                .filter(ActionDefinitionModel.kind == action_kind)
                .first()
            )
            run_id = str(uuid4())
            db.add(
                ActionRunModel(
                    run_id=run_id,
                    organization_id=organization_id,
                    entity_id=entity_id,
                    definition_id=str(definition.definition_id) if definition else None,
                    action_kind=action_kind,
                    config_json=dict(config_json),
                    status="pending",
                    attempts=0,
                    idempotency_key=idempotency_key,
                    scheduled_at=scheduled_at,
                )
            )
            try:
                db.commit()
                return run_id, True
            except IntegrityError:
                # Another worker may have materialized the same occurrence
                # between our lookup and insert. The database key is the final
                # idempotency guard, so return the winning run.
                db.rollback()
                existing = (
                    db.query(ActionRunModel)
                    .filter(ActionRunModel.idempotency_key == idempotency_key)
                    .first()
                )
                if existing is None:
                    raise
                return str(existing.run_id), False

    def find_scheduled_action_run(
        self,
        *,
        organization_id: str,
        invocation_id: str,
        schedule_target_id: str,
    ) -> dict[str, object] | None:
        """Find the action run already created for one manual schedule invocation target."""
        with self._db_session() as db:
            rows = (
                db.query(ActionRunModel)
                .filter(
                    ActionRunModel.organization_id == organization_id,
                    ActionRunModel.config_json["run_invocation_id"].astext == invocation_id,
                    ActionRunModel.config_json["schedule_target_id"].astext == schedule_target_id,
                )
                .order_by(ActionRunModel.created_at.asc())
                .all()
            )
            if not rows:
                return None
            return {
                "run_id": str(rows[0].run_id),
                "run_ids": [str(row.run_id) for row in rows],
                "config_json": dict(rows[0].config_json or {}),
            }

    def mark_action_run_result(
        self,
        db: Session,
        run_id: str,
        status: str,
        outcome: str,
        resolved_config_json: str,
        from_status: str | None = None,
    ) -> bool:
        """Persist the final result of an action run. Returns True if the row was updated.

        When from_status is provided the update only applies if the current row status
        matches, making the transition atomic and safe for concurrent callers.
        """
        try:
            query = db.query(ActionRunModel).filter(ActionRunModel.run_id == run_id)
            if from_status is not None:
                query = query.filter(ActionRunModel.status == from_status)
            row = query.first()
            if row is None:
                return False
            row.status = status
            row.outcome = outcome[:64] if outcome else outcome
            row.resolved_config_json = (
                json.loads(resolved_config_json)
                if isinstance(resolved_config_json, str)
                else resolved_config_json
            )
            row.updated_at = datetime.now(UTC)
            row.completed_at = datetime.now(UTC)
            row.scheduled_at = None
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to mark action run result: {exc}") from exc

    def mark_action_run_pending_external(
        self,
        db: Session,
        run_id: str,
        outcome: str,
        resolved_config_json: str,
        timeout_hours: int = 24,
    ) -> None:
        """Set an action run to pending_external while awaiting an external callback."""
        try:
            row = db.query(ActionRunModel).filter(ActionRunModel.run_id == run_id).first()
            if row is None:
                return
            row.status = "pending_external"
            row.outcome = outcome[:64] if outcome else outcome
            row.resolved_config_json = (
                json.loads(resolved_config_json)
                if isinstance(resolved_config_json, str)
                else resolved_config_json
            )
            row.updated_at = datetime.now(UTC)
            row.completed_at = None
            row.scheduled_at = None
            row.external_timeout_at = datetime.now(UTC) + timedelta(hours=timeout_hours)
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to mark action run as pending_external: {exc}") from exc

    def mark_action_run_failed(self, db: Session, run_id: str, outcome: str) -> None:
        """Mark an action run as failed with the provided outcome message."""
        try:
            row = db.query(ActionRunModel).filter(ActionRunModel.run_id == run_id).first()
            if row is None:
                return
            row.status = "failed"
            row.outcome = outcome[:64] if outcome else outcome
            row.updated_at = datetime.now(UTC)
            row.completed_at = datetime.now(UTC)
            row.scheduled_at = None
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to mark action run as failed: {exc}") from exc

    def schedule_action_run_retry(
        self,
        db: Session,
        run_id: str,
        outcome: str,
        resolved_config_json: str | dict[str, object],
        delay_seconds: int,
    ) -> None:
        """Reschedule the action run for a future retry without changing attempts."""
        try:
            row = db.query(ActionRunModel).filter(ActionRunModel.run_id == run_id).first()
            if row is None:
                return
            row.status = "pending"
            row.outcome = outcome[:64] if outcome else outcome
            row.resolved_config_json = (
                json.loads(resolved_config_json)
                if isinstance(resolved_config_json, str)
                else resolved_config_json
            )
            row.updated_at = datetime.now(UTC)
            row.completed_at = None
            row.scheduled_at = datetime.now(UTC) + timedelta(seconds=max(0, delay_seconds))
            db.commit()
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to schedule action run retry: {exc}") from exc

    def increment_action_run_attempts(self, db: Session, run_id: str) -> int:
        """Increment the attempt count for an action run and return the new value."""
        try:
            row = db.query(ActionRunModel).filter(ActionRunModel.run_id == run_id).first()
            if row is None:
                return 0
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = datetime.now(UTC)
            db.commit()
            return int(row.attempts or 0)
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to increment action run attempts: {exc}") from exc

    def get_action_run(self, db: Session, run_id: str) -> dict[str, object] | None:
        """Return a single action run by run_id using the provided session, or None if not found."""
        try:
            row = db.query(ActionRunModel).filter(ActionRunModel.run_id == run_id).first()
            if row is None:
                return None
            return {
                "run_id": str(row.run_id),
                "organization_id": str(row.organization_id),
                "entity_id": str(row.entity_id),
                "action_kind": str(row.action_kind),
                "status": str(row.status),
                "config_json": row.config_json if isinstance(row.config_json, dict) else {},
                "external_timeout_at": row.external_timeout_at,
                "scheduled_at": row.scheduled_at,
            }
        except Exception as exc:
            raise PersistenceError(f"Unable to get action run: {exc}") from exc

    def get_pending_external_run_for_entity(
        self, db: Session, entity_id: str
    ) -> dict[str, object] | None:
        """Return the most recent pending_external form.receive_data or standalone
        mail.send_email run for an entity, or None."""
        try:
            row = (
                db.query(ActionRunModel)
                .filter(ActionRunModel.entity_id == entity_id)
                .filter(ActionRunModel.action_kind.in_(["form.receive_data", "mail.send_email"]))
                .filter(ActionRunModel.status == "pending_external")
                .order_by(ActionRunModel.created_at.desc())
                .first()
            )
            if row is None:
                return None
            return {
                "run_id": str(row.run_id),
                "organization_id": str(row.organization_id),
                "entity_id": str(row.entity_id),
                "action_kind": str(row.action_kind),
                "status": str(row.status),
                "external_timeout_at": row.external_timeout_at,
                "config_json": row.config_json if isinstance(row.config_json, dict) else {},
            }
        except Exception as exc:
            raise PersistenceError(f"Unable to get pending external run for entity: {exc}") from exc

    def get_pending_external_run_by_run_id(
        self, db: Session, run_id: str
    ) -> dict[str, object] | None:
        """Return a pending_external action run by run_id, or None if not found or not pending."""
        try:
            row = (
                db.query(ActionRunModel)
                .filter(ActionRunModel.run_id == run_id)
                .filter(ActionRunModel.status == "pending_external")
                .first()
            )
            if row is None:
                return None
            return {
                "run_id": str(row.run_id),
                "organization_id": str(row.organization_id),
                "entity_id": str(row.entity_id),
                "action_kind": str(row.action_kind),
                "status": str(row.status),
                "external_timeout_at": row.external_timeout_at,
                "config_json": row.config_json if isinstance(row.config_json, dict) else {},
            }
        except Exception as exc:
            raise PersistenceError(f"Unable to get pending external run by run_id: {exc}") from exc

    def get_action_run_summary(self, db: Session, run_id: str) -> dict[str, object] | None:
        """Return basic action run fields needed for follow-up processing by run id."""
        try:
            row = db.query(ActionRunModel).filter(ActionRunModel.run_id == run_id).first()
            if row is None:
                return None
            return {
                "run_id": str(row.run_id),
                "organization_id": str(row.organization_id),
                "entity_id": str(row.entity_id),
                "action_kind": str(row.action_kind),
                "status": str(row.status),
            }
        except Exception as exc:
            raise PersistenceError(f"Unable to get action run summary: {exc}") from exc

    def update_action_run_submitted(
        self, db: Session, run_id: str, fields: dict[str, object]
    ) -> None:
        """Mark an action run as succeeded/submitted and persist the submitted fields."""
        try:
            row = db.query(ActionRunModel).filter(ActionRunModel.run_id == run_id).first()
            if row is not None:
                now = datetime.now(UTC)
                row.status = "succeeded"
                row.outcome = "received"
                row.resolved_config_json = {"submitted_fields": dict(fields or {})}
                row.updated_at = now
                row.completed_at = now
                db.commit()
        except Exception as exc:
            raise PersistenceError(f"Unable to update action run as submitted: {exc}") from exc

    def timeout_pending_external_runs(self, db: Session) -> list[str]:
        """Sweep timed-out pending_external runs, mark them failed, and return their run ids."""
        try:
            now = datetime.now(UTC)
            rows = (
                db.query(ActionRunModel)
                .filter(ActionRunModel.status == "pending_external")
                .filter(ActionRunModel.external_timeout_at.isnot(None))
                .filter(ActionRunModel.external_timeout_at < now)
                .all()
            )
            timed_out_ids: list[str] = []
            for row in rows:
                row.status = "failed"
                row.outcome = "timeout"
                row.updated_at = now
                row.completed_at = now
                row.scheduled_at = None
                timed_out_ids.append(str(row.run_id))
            db.commit()
            return timed_out_ids
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to timeout pending external runs: {exc}") from exc

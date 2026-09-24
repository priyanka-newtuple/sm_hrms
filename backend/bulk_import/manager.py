"""Bulk import orchestration built on existing platform services.

The same bulk-import agent handles two modes: semantic spreadsheet mapping from
headers/samples, and consolidated document extraction via `read_job_document`.
Spreadsheet rows are parsed and materialized deterministically after the agent
proposes a reviewer-editable mapping.

Files are given to the model only as slugs ("file_1", "file_2", ...) paired
with their filename — the real file id never appears in the prompt, any tool
call, or the model's final answer. `slug_map` (slug -> real id) is built once
per run, passed along so `read_job_document` can resolve a slug, and used
again at the end to translate the model's slug-based `file_ids` back to real
ids before anything downstream sees them.
"""

from __future__ import annotations

import base64
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from agent.models.request import AgentRunRequest
from background_jobs.models.request import CreateIntakeJobRequest, IntakeSourceFileRequest
from bulk_import.models import (
    EXTRACTION_USER_PROMPT_TEMPLATE,
    IDENTIFIER_SYNTHESIS_FIELD_PRIORITY,
    IDENTIFIER_SYNTHESIS_MAX_SUFFIX_ATTEMPTS,
    QUEUED_JOB_STATUS,
    BulkImportDiagnostics,
    BulkImportDraft,
    BulkImportFixedRelationBinding,
    BulkImportJobListResponse,
    BulkImportJobResponse,
    BulkImportJobSummary,
    BulkImportRelationDefinition,
    BulkImportRemoteFileReference,
    BulkImportReviewRequest,
    BulkImportSpreadsheetMappingRequest,
    BulkImportSpreadsheetSource,
)
from bulk_import.services.agent_results import parse_agent_payload_with_metadata
from common.configuration import get_configuration
from common.enums import IntakeJobStatus
from common.logger import logger
from entities.models.interface import IDENTIFIER_FIELD_KEY
from exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from filehandler.models.request import FileUploadRequest
from remote_files.models.interface import FetchedRemoteFile

if TYPE_CHECKING:
    from collections.abc import Callable

    from agent.manager import AgentServiceManager
    from background_jobs.db_models import BackgroundJobsModelService
    from background_jobs.models.interface import IntakeJobContract
    from bulk_import.services.relation_bindings import BulkImportRelationBindingService
    from bulk_import.services.spreadsheet import SpreadsheetImportService
    from database.manager import DatabaseServiceManager
    from entities.manager import EntitiesServiceManager
    from entities.models.response import EntityTypeRecordResponse
    from filehandler.manager import FilehandlerServiceManager
    from organizations.manager import OrganizationsServiceManager
    from remote_files.manager import RemoteFilesServiceManager
    from roles.manager import RolesServiceManager
    from workflow.manager import WorkflowServiceManager

BULK_IMPORT_SOURCE = "bulk_import"
BULK_IMPORT_AGENT = "bulk_import_extractor"


class _BulkImportCancellationRequested(Exception):
    """Internal control flow used to stop at a safe persistence boundary."""


DEFAULT_FILE_TYPE = "generic_document"
EXISTING_ENTITY_SEARCH_LIMIT = 20


class BulkImportServiceManager:
    """Upload, propose, review, and atomically claim bulk entity creation jobs."""

    def __init__(
        self,
        *,
        jobs: BackgroundJobsModelService,
        database: DatabaseServiceManager,
        organizations: OrganizationsServiceManager,
        roles: RolesServiceManager,
        filehandler: FilehandlerServiceManager,
        spreadsheets: SpreadsheetImportService,
        entities: EntitiesServiceManager,
        agents: AgentServiceManager,
        workflows: WorkflowServiceManager,
        remote_files: RemoteFilesServiceManager,
        relations: BulkImportRelationBindingService,
    ) -> None:
        """Store the platform service dependencies used across the import lifecycle."""
        self.jobs = jobs
        self.database = database
        self.organizations = organizations
        self.roles = roles
        self.filehandler = filehandler
        self.spreadsheets = spreadsheets
        self.entities = entities
        self.agents = agents
        self.workflows = workflows
        self.remote_files = remote_files
        self.relations = relations
        self._started = False
        self._worker_stop = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="bulk-import-worker"
        )
        self._sweep_thread: threading.Thread | None = None
        # Defaults for every one of these live once, in BulkImportConfiguration
        # (common/data_model.py) — not duplicated here.
        worker_config = get_configuration().bulk_import_configuration
        self._poll_interval_seconds = worker_config.poll_interval_seconds
        self._poll_batch_size = worker_config.poll_batch_size
        self._worker_error_backoff_seconds = worker_config.worker_error_backoff_seconds
        self._worker_shutdown_join_seconds = worker_config.worker_shutdown_join_seconds
        self._sweep_interval_seconds = worker_config.sweep_interval_seconds
        self._sweep_batch_size = worker_config.sweep_batch_size
        self._stale_threshold_seconds = worker_config.stale_threshold_seconds
        self._recent_jobs_limit = worker_config.recent_jobs_limit
        self._commit_batch_size = max(1, worker_config.commit_batch_size)

    @staticmethod
    def _actor_value(actor: dict[str, object], key: str) -> str:
        """Return a required non-empty string field from the actor, or raise ValidationError."""
        value = str(actor.get(key, "")).strip()
        if not value:
            raise ValidationError(f"actor must include {key}")
        return value

    def _db_session(self):
        """Open a new PostgreSQL session from the database service."""
        return self.database.postgres_db_service().get_db_session()

    def start(self) -> None:
        """Start the bulk-import worker + stale-job-sweep threads.

        Skipped in the web process unless bulk_import_configuration.worker_enabled
        is set — same on/off switch pattern as background_jobs' action-runs worker,
        so only the dedicated modular-worker container actually processes jobs.
        """
        self._started = True
        if not get_configuration().bulk_import_configuration.worker_enabled:
            return
        self._worker_stop.clear()
        self._worker_thread.start()
        self._sweep_thread = threading.Thread(
            target=self._stale_job_sweep_loop, daemon=True, name="bulk-import-sweep"
        )
        self._sweep_thread.start()

    def stop(self) -> None:
        """Stop the worker and sweep threads, waiting briefly for them to exit."""
        self._started = False
        self._worker_stop.set()
        for thread in (self._worker_thread, self._sweep_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=self._worker_shutdown_join_seconds)

    def _worker_loop(self) -> None:
        """Poll for QUEUED bulk_import jobs and claim/process them one at a time.

        Deliberately simpler than background_jobs' own worker: no separate queue
        substrate and no startup reconciliation needed — a job this worker
        previously claimed but didn't finish is picked up by the stale-job sweep,
        not by worker-restart logic. Multiple orgs' jobs queue behind each other
        here (one job processed at a time, with concurrency only *within* a job's
        own file extraction) — an accepted v1 simplification, see the design doc.
        """
        while not self._worker_stop.is_set():
            try:
                claimed_any = self._claim_and_process_next_batch()
                if not claimed_any:
                    self._worker_stop.wait(timeout=self._poll_interval_seconds)
            except Exception:
                logger.exception("bulk import worker iteration failed")
                self._worker_stop.wait(timeout=self._worker_error_backoff_seconds)

    def _claim_and_process_next_batch(self) -> bool:
        """Fetch a batch of QUEUED jobs and dispatch each one. Returns True if any were found."""
        queued_jobs = self.jobs.list_jobs_by_source_and_status(
            BULK_IMPORT_SOURCE,
            IntakeJobStatus.QUEUED.value,
            limit=self._poll_batch_size,
        )
        if not queued_jobs:
            return False
        for job in queued_jobs:
            if self._worker_stop.is_set():
                break
            self._dispatch_queued_job(job)
        return True

    def _dispatch_queued_job(self, job: IntakeJobContract) -> None:
        """Route one QUEUED job to the right worker method, based on `queued_for`.

        A ConflictError here means another worker already claimed the job (or it
        moved on its own between the poll read and this claim) — expected under
        concurrency, logged at debug and skipped, never treated as a failure.
        """
        queued_for = str(dict(job.context).get("queued_for") or "")
        try:
            if queued_for == QUEUED_JOB_STATUS.QUEUED_FOR_COMMIT.value:
                self._run_queued_commit(job.job_id, job.organization_id)
            else:
                # Any job queued before this marker existed can only have come
                # from analyze — commit didn't exist as a QUEUED path yet either.
                self._run_queued_analysis(job.job_id, job.organization_id)
        except ConflictError as exc:
            logger.debug("bulk import worker: claim skipped job=%s: %s", job.job_id, exc)
        except Exception as exc:
            logger.exception("bulk import worker: job=%s failed: %s", job.job_id, exc)

    def _stale_job_sweep_loop(self) -> None:
        """Periodically force stuck PROCESSING/COMMITTING jobs to a resolvable status."""
        while not self._worker_stop.is_set():
            try:
                self._sweep_stale_jobs()
            except Exception:
                logger.exception("bulk import stale-job sweep failed")
            self._worker_stop.wait(timeout=self._sweep_interval_seconds)

    def _sweep_stale_jobs(self) -> None:
        """Force every job stuck at PROCESSING/COMMITTING past the threshold to a resolvable status.

        Never asserts unproven success: PROCESSING always sweeps to FAILED,
        COMMITTING always sweeps to COMPLETED_WITH_ERRORS — regardless of partial
        progress — matching the design's core invariant that a swept job can only
        move to a *less* complete status, never COMPLETED.
        """
        threshold = datetime.now(UTC) - timedelta(seconds=self._stale_threshold_seconds)
        stale_jobs = self.jobs.list_stale_jobs_for_source(
            BULK_IMPORT_SOURCE,
            {
                IntakeJobStatus.PROCESSING.value,
                IntakeJobStatus.COMMITTING.value,
                IntakeJobStatus.CANCELLING.value,
            },
            threshold,
            limit=self._sweep_batch_size,
        )
        for job in stale_jobs:
            self._sweep_one_stale_job(job)

    def _sweep_one_stale_job(self, job: IntakeJobContract) -> None:
        """Force one stale job to FAILED (from PROCESSING) or COMPLETED_WITH_ERRORS (from COMMITTING)."""
        if job.status == IntakeJobStatus.CANCELLING.value:
            target_status = IntakeJobStatus.CANCELLED.value
            expected_status = IntakeJobStatus.CANCELLING.value
        elif job.status == IntakeJobStatus.PROCESSING.value:
            target_status = IntakeJobStatus.FAILED.value
            expected_status = IntakeJobStatus.PROCESSING.value
        else:
            target_status = IntakeJobStatus.COMPLETED_WITH_ERRORS.value
            expected_status = IntakeJobStatus.COMMITTING.value
        context = dict(job.context)
        context["errors"] = [
            *list(context.get("errors") or []),
            "swept: job exceeded the stale-processing threshold and was force-resolved",
        ]
        try:
            self.jobs.update_job(
                job.organization_id,
                job.job_id,
                status=target_status,
                expected_statuses={expected_status},
                context=context,
            )
            logger.info(
                "bulk import sweep: forced job=%s from %s to %s (stale)",
                job.job_id,
                expected_status,
                target_status,
            )
        except ConflictError:
            # The job moved on its own between the sweep's read and this write
            # (e.g. the owning worker finished right as the sweep fired) — fine.
            logger.debug(
                "bulk import sweep: job=%s no longer %s, skipped", job.job_id, expected_status
            )

    def _require_enabled(self, organization_id: str) -> None:
        """Raise AuthorizationError unless bulk import is enabled for the organization."""
        db = self._db_session()
        try:
            org = self.organizations.get_current(db, organization_id)
        finally:
            db.close()
        settings = dict(org.settings or {})
        flags = settings.get("featureFlags")
        enabled = isinstance(flags, dict) and flags.get("bulkImportEnabled") is True
        if not enabled:
            raise AuthorizationError("Bulk import is disabled in Settings → Display")

    def _require_permission(self, actor: dict[str, object], permission_key: str) -> None:
        """Raise AuthorizationError unless the actor holds the given permission."""
        db = self._db_session()
        try:
            result = self.roles.check_permission(
                db,
                self._actor_value(actor, "user_id"),
                self._actor_value(actor, "organization_id"),
                permission_key,
            )
        finally:
            db.close()
        if not result.allowed:
            raise AuthorizationError(result.reason or f"Missing permission: {permission_key}")

    def store_file(
        self,
        actor: dict[str, object],
        *,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> dict[str, object]:
        """Upload a source file for later inclusion in a bulk import job."""
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        response = self.filehandler.upload_file(
            organization_id,
            self._actor_value(actor, "user_id"),
            FileUploadRequest(
                type_id=DEFAULT_FILE_TYPE,
                filename=filename,
                content_type=content_type,
                content=base64.b64encode(content).decode("ascii"),
                metadata={"bulk_import_source": True},
            ),
            skip_agent_dispatch=True,
        )
        return {
            "file_id": response.file_id,
            "filename": response.filename,
            "content_type": response.content_type,
            "size_bytes": response.size_bytes,
        }

    def create_job(
        self,
        actor: dict[str, object],
        *,
        entity_type_id: str,
        workflow_name: str | None,
        files: list[dict[str, object]],
        fixed_relation_bindings: list[BulkImportFixedRelationBinding] | None = None,
    ) -> BulkImportJobResponse:
        """Create a bulk import job from previously stored files."""
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        if workflow_name:
            self._require_permission(actor, "workflow:write")
        entity_type = self._resolve_entity_type(organization_id, entity_type_id)
        relation_definitions = self.relations.apply_fixed_choices(
            actor,
            self.relations.discover(actor, entity_type_id),
            fixed_relation_bindings or [],
        )
        has_document_sources = any(
            not self.spreadsheets.is_spreadsheet_file(dict(item)) for item in files
        )
        missing_document_parent = next(
            (
                item
                for item in relation_definitions
                if item.relation_type == "REFERENCE" and not item.fixed_source_entity_id
            ),
            None,
        )
        if has_document_sources and missing_document_parent:
            raise ValidationError(
                f"Select a fixed {missing_document_parent.source_entity_type_name} "
                "before importing document sources"
            )
        unique_files: dict[str, dict[str, Any]] = {
            str(item["file_id"]): dict(item) for item in files
        }
        if not unique_files:
            raise ValidationError("at least one supported file is required")
        stored_files = list(unique_files.values())
        context: dict[str, Any] = {
            "actor_user_id": self._actor_value(actor, "user_id"),
            "entity_type_id": entity_type_id,
            "entity_type_name": entity_type.name,
            "workflow_name": workflow_name,
            "workflow_preselected": bool(workflow_name),
            "files": stored_files,
            "drafts": [],
            "unmapped_file_ids": [],
            "errors": [],
            "relation_definitions": [item.model_dump(mode="json") for item in relation_definitions],
        }
        job = self._persist_new_job(organization_id, entity_type_id, stored_files, context)
        return self._response(job)

    def _resolve_entity_type(
        self, organization_id: str, entity_type_id: str
    ) -> EntityTypeRecordResponse:
        """Return the active entity type with the given id or raise NotFoundError."""
        entity_type = next(
            (
                item
                for item in self.entities.list_entity_type_records(
                    organization_id=organization_id, include_inactive=False
                )
                if item.entity_type_id == entity_type_id
            ),
            None,
        )
        if entity_type is None:
            raise NotFoundError(f"entity type '{entity_type_id}' not found")
        return entity_type

    def _persist_new_job(
        self,
        organization_id: str,
        entity_type_id: str,
        stored_files: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> IntakeJobContract:
        """Create the intake job and mark it UPLOADED, returning the job contract."""
        job = self.jobs.create_job(
            CreateIntakeJobRequest(
                organization_id=organization_id,
                source_type=BULK_IMPORT_SOURCE,
                subject_entity_type=entity_type_id,
                files=[
                    IntakeSourceFileRequest(
                        filename=str(item["filename"]),
                        content_type=str(item["content_type"]),
                        size_bytes=int(item["size_bytes"]),
                        metadata={"file_id": str(item["file_id"])},
                    )
                    for item in stored_files
                ],
                context=context,
            )
        )
        return self.jobs.update_job(
            organization_id,
            job.job_id,
            status=IntakeJobStatus.UPLOADED.value,
            context=context,
        )

    def get_job(self, actor: dict[str, object], job_id: str) -> BulkImportJobResponse:
        """Fetch a bulk import job's current state."""
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        job = self.jobs.get_job(organization_id, job_id)
        if job is None or job.source_type != BULK_IMPORT_SOURCE:
            raise NotFoundError(f"bulk import job '{job_id}' not found")
        return self._response(job)

    def cancel(self, actor: dict[str, object], job_id: str) -> BulkImportJobResponse:
        """Stop a running import without rolling back records already committed."""
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        existing = self.jobs.get_job(organization_id, job_id)
        if existing is None or existing.source_type != BULK_IMPORT_SOURCE:
            raise NotFoundError(f"bulk import job '{job_id}' not found")
        if existing.status in {
            IntakeJobStatus.CANCELLED.value,
            IntakeJobStatus.CANCELLING.value,
        }:
            return self._response(existing)
        active_statuses = {
            IntakeJobStatus.QUEUED.value,
            IntakeJobStatus.PROCESSING.value,
            IntakeJobStatus.COMMITTING.value,
        }
        if existing.status not in active_statuses:
            raise ConflictError(f"bulk import job '{job_id}' is not running")
        context = dict(existing.context)
        context["cancel_requested"] = True
        context["cancel_requested_at"] = datetime.now(UTC).isoformat()
        target_status = (
            IntakeJobStatus.CANCELLED.value
            if existing.status == IntakeJobStatus.QUEUED.value
            else IntakeJobStatus.CANCELLING.value
        )
        job = self.jobs.update_job(
            organization_id,
            job_id,
            status=target_status,
            expected_statuses={existing.status},
            context=context,
        )
        return self._response(job)

    def resume(self, actor: dict[str, object], job_id: str) -> BulkImportJobResponse:
        """Resume a cancelled analysis or commit from its durable progress."""
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        existing = self.jobs.get_job(organization_id, job_id)
        if existing is None or existing.source_type != BULK_IMPORT_SOURCE:
            raise NotFoundError(f"bulk import job '{job_id}' not found")
        context = dict(existing.context)
        context["cancel_requested"] = False
        context.pop("cancel_requested_at", None)
        self._backfill_actor_snapshot(context, actor)
        job = self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.QUEUED.value,
            expected_statuses={IntakeJobStatus.CANCELLED.value},
            context=context,
        )
        return self._response(job)

    def _raise_if_cancel_requested(self, organization_id: str, job_id: str) -> None:
        """Interrupt worker work only at a boundary where partial effects are durable."""
        current = self.jobs.get_job(organization_id, job_id)
        if current is not None and current.status in {
            IntakeJobStatus.CANCELLING.value,
            IntakeJobStatus.CANCELLED.value,
        }:
            raise _BulkImportCancellationRequested()

    def _finalize_cancellation(
        self,
        organization_id: str,
        job_id: str,
        context: dict[str, Any],
    ) -> None:
        """Persist the worker's latest progress and make cancellation terminal."""
        context["cancel_requested"] = True
        context["cancelled_at"] = datetime.now(UTC).isoformat()
        self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.CANCELLED.value,
            expected_statuses={IntakeJobStatus.CANCELLING.value},
            context=context,
        )

    def _finalize_if_cancelling(
        self,
        organization_id: str,
        job_id: str,
        context: dict[str, Any],
    ) -> bool:
        current = self.jobs.get_job(organization_id, job_id)
        if current is None:
            return False
        if current.status == IntakeJobStatus.CANCELLED.value:
            return True
        if current.status != IntakeJobStatus.CANCELLING.value:
            return False
        self._finalize_cancellation(organization_id, job_id, context)
        return True

    def list_jobs(self, actor: dict[str, object]) -> BulkImportJobListResponse:
        """List the caller's organization's recent bulk import jobs, newest first.

        Lets a caller resume a job it no longer has the id for (e.g. after
        navigating away mid-processing) — `list_jobs` on the shared
        `intake_jobs` table isn't bulk-import-specific, so this filters to
        `source_type == BULK_IMPORT_SOURCE` and returns the lighter summary
        shape rather than every job's full files/drafts/errors payload.
        """
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        jobs = self.jobs.list_jobs(
            organization_id, source_type=BULK_IMPORT_SOURCE, limit=self._recent_jobs_limit
        )
        return BulkImportJobListResponse(items=[self._summary(job) for job in jobs])

    @staticmethod
    def _summary(job: IntakeJobContract) -> BulkImportJobSummary:
        """Build the lightweight list-view model for one job."""
        # dict[str, Any]: the job context is a freeform JSON blob persisted on the intake job.
        context: dict[str, Any] = dict(job.context)
        return BulkImportJobSummary(
            job_id=job.job_id,
            status=job.status,
            entity_type_id=str(context.get("entity_type_id") or ""),
            entity_type_name=str(context.get("entity_type_name") or ""),
            file_count=len(context.get("files") or []),
            draft_count=len(BulkImportServiceManager._drafts_from_context(context)),
            created_at=str(job.created_at) if job.created_at else None,
            updated_at=str(job.updated_at) if job.updated_at else None,
        )

    def analyze(self, actor: dict[str, object], job_id: str) -> BulkImportJobResponse:
        """Queue the job for background extraction and return its updated (QUEUED) state."""
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        existing = self.jobs.get_job(organization_id, job_id)
        if existing is None or existing.source_type != BULK_IMPORT_SOURCE:
            raise NotFoundError(f"bulk import job '{job_id}' not found")
        context = {
            **dict(existing.context),
            "queued_for": QUEUED_JOB_STATUS.QUEUED_FOR_ANALYZE.value,
        }
        self._backfill_actor_snapshot(context, actor)
        job = self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.QUEUED.value,
            expected_statuses={IntakeJobStatus.UPLOADED.value, IntakeJobStatus.FAILED.value},
            context=context,
        )
        return self._response(job)

    @staticmethod
    def _backfill_actor_snapshot(context: dict[str, Any], actor: dict[str, object]) -> None:
        """Stamp `actor_user_id` onto a job's context if it's missing.

        Jobs created before this feature shipped have no snapshot at all. Without
        this, a legacy job would queue successfully but the worker's claim would
        later fail in `_reconstruct_actor` with no way back to a retryable status
        (queuing only accepts UPLOADED/FAILED, and the job is already past that).
        Backfilling here, from the actor making the live analyze/commit call, makes
        the job self-healing on its first queue after this deploy.
        """
        if not str(context.get("actor_user_id", "")).strip():
            context["actor_user_id"] = str(actor.get("user_id", "")).strip()

    def _run_queued_analysis(self, job_id: str, organization_id: str) -> None:
        """Claim a QUEUED-for-analysis job and run extraction to completion.

        Worker-facing entry point (relocated body of today's synchronous `analyze`).
        Raises ConflictError if the job is no longer QUEUED (already claimed by
        another worker, or the compare-and-set otherwise fails) — the caller (the
        worker's poll loop) must catch this and treat it as a normal, non-fatal skip.
        """
        job = self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.PROCESSING.value,
            expected_statuses={IntakeJobStatus.QUEUED.value},
        )
        # dict[str, Any]: the job context is a freeform JSON blob persisted on the intake job.
        context: dict[str, Any] = dict(job.context)
        try:
            # Reconstructing the actor is inside the try deliberately: a legacy job
            # queued before this feature shipped (no actor_user_id snapshot) must
            # still be routed to FAILED on failure here, not left stuck at
            # PROCESSING with no way back (analyze only re-queues from
            # UPLOADED/FAILED).
            actor = self._reconstruct_actor(job)
            files = [dict(item) for item in context.get("files") or []]
            file_ids = [str(item.get("file_id") or "") for item in files]
            spreadsheet_files = [
                item for item in files if self.spreadsheets.is_spreadsheet_file(item)
            ]
            document_files = [
                item for item in files if not self.spreadsheets.is_spreadsheet_file(item)
            ]
            definition_id: str | None = None

            def definition_id_provider() -> str:
                nonlocal definition_id
                if definition_id is None:
                    definition_id = self._agent_definition_id(actor)
                return definition_id

            if spreadsheet_files:
                context["analysis_stage"] = "spreadsheet_mapping"
            spreadsheet_result = self.spreadsheets.prepare_drafts(
                actor,
                organization_id=organization_id,
                job_id=job_id,
                entity_type_id=str(context.get("entity_type_id") or ""),
                entity_type_name=str(context.get("entity_type_name") or ""),
                files=spreadsheet_files,
                uploaded_files=files,
                definition_id_provider=definition_id_provider,
                relation_definitions=self._relation_definitions_from_context(context),
            )
            if spreadsheet_result.mapping_agent_run_id:
                context["spreadsheet_mapping_agent_run_id"] = (
                    spreadsheet_result.mapping_agent_run_id
                )
            if spreadsheet_result.parser_warnings:
                context["parser_warnings"] = list(
                    dict.fromkeys(
                        [
                            *[str(item) for item in context.get("parser_warnings") or []],
                            *spreadsheet_result.parser_warnings,
                        ]
                    )
                )
            if document_files:
                context["analysis_stage"] = "document_extraction"
                payload = self._extract_job(
                    actor, definition_id_provider(), context, files=document_files
                )
            else:
                payload = {"entities": [], "skipped_files": []}
            document_drafts = self._build_drafts_from_payload(payload)
            relation_definitions = self._relation_definitions_from_context(context)
            for draft in document_drafts:
                draft.relation_bindings = self.relations.build_bindings(
                    actor, relation_definitions, {}, {}
                )
            drafts = [*spreadsheet_result.drafts, *document_drafts]
            self._resolve_existing_entities(actor, str(context.get("entity_type_name", "")), drafts)
            covered_file_ids = {file_id for draft in drafts for file_id in draft.file_ids} | {
                source.file_id for source in spreadsheet_result.sources
            }
            skipped = {
                str(item.get("file_id") or ""): str(item.get("reason") or "skipped by agent")
                for item in payload.get("skipped_files") or []
                if isinstance(item, dict) and item.get("file_id")
            }
            skipped.update(spreadsheet_result.skipped_files)
            unmapped = [file_id for file_id in file_ids if file_id not in covered_file_ids]
            errors = [f"{file_id}: {reason}" for file_id, reason in skipped.items()]
            failed = len(skipped)
            context.update(
                drafts=[draft.model_dump(mode="json") for draft in drafts],
                unmapped_file_ids=list(dict.fromkeys(unmapped)),
                errors=errors,
                spreadsheet_sources=[
                    item.model_dump(mode="json") for item in spreadsheet_result.sources
                ],
            )
            self._raise_if_cancel_requested(organization_id, job_id)
            try:
                self.jobs.update_job(
                    organization_id,
                    job_id,
                    status=IntakeJobStatus.READY_FOR_REVIEW.value,
                    expected_statuses={IntakeJobStatus.PROCESSING.value},
                    context=context,
                    processed_count=len(file_ids) - failed,
                    failed_count=failed,
                )
            except ConflictError:
                logger.warning(
                    "bulk import: job=%s finished analysis but was no longer PROCESSING — "
                    "likely swept as stale while still genuinely running; result discarded",
                    job_id,
                )
                raise
        except _BulkImportCancellationRequested:
            self._finalize_cancellation(organization_id, job_id, context)
            return
        except ConflictError:
            if self._finalize_if_cancelling(organization_id, job_id, context):
                return
            raise
        except Exception as exc:
            self._mark_analyze_failed(organization_id, job_id, context, exc)
            raise

    @staticmethod
    def _build_drafts_from_payload(payload: dict[str, Any]) -> list[BulkImportDraft]:
        """Build typed drafts from the agent's own consolidated entity list.

        The agent now reads every file in the job itself and returns one
        consolidated list — no cross-file merge runs in our own code anymore (see
        design_docs/tony_bulk_import_single_agent_pipeline.md). This only keeps the
        same defensive, per-entity normalization used everywhere else on untrusted
        LLM output (`_merge_candidate`/`_safe_confidence`), as a dedupe backstop in
        case the agent's own consolidation ever repeats an identifier.
        """
        drafts: list[BulkImportDraft] = []
        for candidate in payload.get("entities") or []:
            if isinstance(candidate, dict):
                BulkImportServiceManager._merge_candidate(drafts, candidate)
        return drafts

    def update_spreadsheet_mapping(
        self,
        actor: dict[str, object],
        job_id: str,
        request: BulkImportSpreadsheetMappingRequest,
    ) -> BulkImportJobResponse:
        """Reparse spreadsheet sources and regenerate their drafts with reviewer mappings."""
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        job = self.jobs.get_job(organization_id, job_id)
        if job is None or job.source_type != BULK_IMPORT_SOURCE:
            raise NotFoundError(f"bulk import job '{job_id}' not found")
        context: dict[str, Any] = dict(job.context)
        spreadsheet_files = [
            dict(item)
            for item in context.get("files") or []
            if isinstance(item, dict) and self.spreadsheets.is_spreadsheet_file(item)
        ]
        if not spreadsheet_files:
            raise ValidationError("this import has no spreadsheet sources")
        known_sources = [
            BulkImportSpreadsheetSource.model_validate(item)
            for item in context.get("spreadsheet_sources") or []
            if isinstance(item, dict)
        ]
        self.spreadsheets.validate_mappings(
            organization_id=organization_id,
            entity_type_name=str(context.get("entity_type_name") or ""),
            known_sources=known_sources,
            mappings=request.mappings,
            relation_definitions=self._relation_definitions_from_context(context),
        )
        mapping_overrides = {(item.file_id, item.sheet_name): item for item in request.mappings}
        spreadsheet_file_ids = {str(item.get("file_id") or "") for item in spreadsheet_files}
        spreadsheet_result = self.spreadsheets.prepare_drafts(
            actor,
            organization_id=organization_id,
            job_id=job_id,
            entity_type_id=str(context.get("entity_type_id") or ""),
            entity_type_name=str(context.get("entity_type_name") or ""),
            files=spreadsheet_files,
            uploaded_files=[
                dict(item) for item in context.get("files") or [] if isinstance(item, dict)
            ],
            mapping_overrides=mapping_overrides,
            relation_definitions=self._relation_definitions_from_context(context),
        )
        document_drafts = [
            draft
            for draft in self._drafts_from_context(context)
            if draft.source_kind != "spreadsheet"
        ]
        drafts = [*spreadsheet_result.drafts, *document_drafts]
        self._resolve_existing_entities(
            actor,
            str(context.get("entity_type_name", "")),
            spreadsheet_result.drafts,
        )
        covered_file_ids = {file_id for draft in drafts for file_id in draft.file_ids} | {
            source.file_id for source in spreadsheet_result.sources
        }
        all_file_ids = [
            str(item.get("file_id") or "")
            for item in context.get("files") or []
            if isinstance(item, dict)
        ]
        existing_errors = [
            str(error)
            for error in context.get("errors") or []
            if not any(str(error).startswith(f"{file_id}:") for file_id in spreadsheet_file_ids)
        ]
        context.update(
            drafts=[draft.model_dump(mode="json") for draft in drafts],
            spreadsheet_sources=[
                item.model_dump(mode="json") for item in spreadsheet_result.sources
            ],
            unmapped_file_ids=[
                file_id for file_id in all_file_ids if file_id not in covered_file_ids
            ],
            errors=[
                *existing_errors,
                *[
                    f"{file_id}: {reason}"
                    for file_id, reason in spreadsheet_result.skipped_files.items()
                ],
            ],
        )
        updated = self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.READY_FOR_REVIEW.value,
            expected_statuses={IntakeJobStatus.READY_FOR_REVIEW.value},
            context=context,
        )
        return self._response(updated)

    def _mark_analyze_failed(
        self,
        organization_id: str,
        job_id: str,
        context: dict[str, Any],
        exc: Exception,
    ) -> None:
        """Record a job-level analysis failure and transition the job to FAILED."""
        logger.exception("bulk import analysis failed for job %s: %s", job_id, exc)
        mapping_agent_run_id = str(getattr(exc, "mapping_agent_run_id", "") or "")
        if mapping_agent_run_id:
            context["spreadsheet_mapping_agent_run_id"] = mapping_agent_run_id
        context["errors"] = [*list(context.get("errors") or []), str(exc)]
        self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.FAILED.value,
            expected_statuses={IntakeJobStatus.PROCESSING.value},
            context=context,
        )

    def update_review(
        self,
        actor: dict[str, object],
        job_id: str,
        request: BulkImportReviewRequest,
    ) -> BulkImportJobResponse:
        """Apply reviewer edits to proposed drafts before commit."""
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        job = self.jobs.get_job(organization_id, job_id)
        if job is None or job.source_type != BULK_IMPORT_SOURCE:
            raise NotFoundError(f"bulk import job '{job_id}' not found")
        # dict[str, Any]: the job context is a freeform JSON blob persisted on the intake job.
        job_context: dict[str, Any] = dict(job.context)
        valid_file_ids = self._valid_file_ids(job_context)
        stored_drafts = {draft.draft_id: draft for draft in self._drafts_from_context(job_context)}
        reviewed_drafts = self._reconcile_reviewed_drafts(request, valid_file_ids, stored_drafts)
        if any(file_id not in valid_file_ids for file_id in request.unmapped_file_ids):
            raise ValidationError("unmapped_file_ids contains an unknown file")
        workflow_name = (request.workflow_name or "").strip() or None
        if job_context.get("workflow_preselected") and workflow_name != job_context.get(
            "workflow_name"
        ):
            raise ValidationError("the workflow for this import was preselected")
        if workflow_name:
            self._require_permission(actor, "workflow:write")
        context = {
            **job_context,
            "drafts": [item.model_dump(mode="json") for item in reviewed_drafts],
            "unmapped_file_ids": list(dict.fromkeys(request.unmapped_file_ids)),
            "workflow_name": workflow_name,
        }
        updated = self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.READY_FOR_REVIEW.value,
            expected_statuses={
                IntakeJobStatus.READY_FOR_REVIEW.value,
                IntakeJobStatus.COMPLETED_WITH_ERRORS.value,
            },
            context=context,
        )
        return self._response(updated)

    @staticmethod
    def _valid_file_ids(job_context: dict[str, Any]) -> set[str]:
        """Return the set of file ids that belong to this job."""
        return {
            str(item.get("file_id"))
            for item in [
                *list(job_context.get("files") or []),
                *list(job_context.get("remote_files") or []),
            ]
            if isinstance(item, dict) and item.get("file_id")
        }

    def _reconcile_reviewed_drafts(
        self,
        request: BulkImportReviewRequest,
        valid_file_ids: set[str],
        stored_drafts: dict[str, BulkImportDraft],
    ) -> list[BulkImportDraft]:
        """Validate reviewer drafts and re-apply server-owned commit progress onto them."""
        reviewed_drafts: list[BulkImportDraft] = []
        for draft in request.drafts:
            if any(file_id not in valid_file_ids for file_id in draft.file_ids):
                raise ValidationError(f"draft '{draft.draft_id}' contains an unknown file")
            stored = stored_drafts.get(draft.draft_id)
            if stored is not None:
                # Commit progress is server-owned. A review may change proposed data
                # and assignments, but it cannot forge or discard completed effects.
                draft.entity_id = stored.entity_id
                draft.existing_entity = stored.existing_entity
                draft.relation_bindings = list(stored.relation_bindings)
                requested_reference_keys = {
                    (reference.source_column, reference.source_value)
                    for reference in draft.remote_file_references
                }
                stored_reference_keys = {
                    (reference.source_column, reference.source_value)
                    for reference in stored.remote_file_references
                }
                unknown_reference_keys = requested_reference_keys - stored_reference_keys
                if unknown_reference_keys:
                    raise ValidationError(
                        f"draft '{draft.draft_id}' contains an unknown remote attachment"
                    )
                # A reviewer may discard proposed/unresolved references. Preserve
                # server-owned values for retained references and any reference
                # whose managed file has already been attached during a prior run.
                draft.remote_file_references = [
                    reference
                    for reference in stored.remote_file_references
                    if (reference.source_column, reference.source_value) in requested_reference_keys
                    or (
                        reference.file_id is not None
                        and reference.file_id in stored.attached_file_ids
                    )
                ]
                draft.attached_file_ids = list(stored.attached_file_ids)
                draft.files_attached = self._draft_files_attached(draft)
                draft.workflow_enrolled = stored.workflow_enrolled
            reviewed_drafts.append(draft)
        return reviewed_drafts

    @staticmethod
    def _draft_files_attached(draft: BulkImportDraft) -> bool:
        """Treat unresolved remote references as pending, even before they have file IDs."""
        has_unmaterialized_reference = any(
            reference.source_url and not reference.file_id
            for reference in draft.remote_file_references
        )
        return not has_unmaterialized_reference and all(
            file_id in draft.attached_file_ids for file_id in draft.file_ids
        )

    def commit(
        self,
        actor: dict[str, object],
        job_id: str,
        idempotency_key: str,
    ) -> BulkImportJobResponse:
        """Queue the job for background commit and return its updated state.

        A job already COMPLETED is a no-op — returns the existing result unchanged
        rather than queuing a second run.
        """
        organization_id = self._actor_value(actor, "organization_id")
        self._require_enabled(organization_id)
        self._require_permission(actor, "entity_record:write")
        if not idempotency_key.strip():
            raise ValidationError("Idempotency-Key header is required")
        existing = self.jobs.get_job(organization_id, job_id)
        if existing is None or existing.source_type != BULK_IMPORT_SOURCE:
            raise NotFoundError(f"bulk import job '{job_id}' not found")
        if existing.status == IntakeJobStatus.COMPLETED.value:
            return self._response(existing)
        # dict[str, Any]: the job context is a freeform JSON blob persisted on the intake job.
        context: dict[str, Any] = dict(existing.context)
        if context.get("workflow_name"):
            self._require_permission(actor, "workflow:write")
        context["commit_idempotency_key"] = idempotency_key
        context["queued_for"] = QUEUED_JOB_STATUS.QUEUED_FOR_COMMIT.value
        context["commit_processed_draft_ids"] = []
        context["commit_total_count"] = sum(
            1 for draft in self._drafts_from_context(context) if draft.selected
        )
        self._backfill_actor_snapshot(context, actor)
        job = self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.QUEUED.value,
            expected_statuses={
                IntakeJobStatus.READY_FOR_REVIEW.value,
                IntakeJobStatus.COMPLETED_WITH_ERRORS.value,
            },
            context=context,
        )
        return self._response(job)

    def _run_queued_commit(self, job_id: str, organization_id: str) -> None:
        """Claim a QUEUED-for-commit job and run commit to completion.

        Worker-facing entry point (relocated body of today's synchronous `commit`).
        Raises ConflictError if the job is no longer QUEUED (already claimed by
        another worker) — the caller (the worker's poll loop) must catch this and
        treat it as a normal, non-fatal skip.
        """
        job = self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.COMMITTING.value,
            expected_statuses={IntakeJobStatus.QUEUED.value},
        )
        # dict[str, Any]: the job context is a freeform JSON blob persisted on the intake job.
        context: dict[str, Any] = dict(job.context)
        try:
            # Reconstructing the actor is inside the try deliberately — see the
            # matching comment in `_run_queued_analysis`. Without this, a legacy
            # job (no actor_user_id snapshot) would get stuck at COMMITTING
            # forever with no way back to a status commit() will re-queue from.
            actor = self._reconstruct_actor(job)
            drafts = self._drafts_from_context(context)
            failures = self._process_selected_drafts(
                actor, context, organization_id, job_id, drafts
            )
            context["drafts"] = [item.model_dump(mode="json") for item in drafts]
            status = (
                IntakeJobStatus.COMPLETED_WITH_ERRORS.value
                if failures
                else IntakeJobStatus.COMPLETED.value
            )
            try:
                self.jobs.update_job(
                    organization_id,
                    job_id,
                    status=status,
                    expected_statuses={IntakeJobStatus.COMMITTING.value},
                    context=context,
                    failed_count=failures,
                )
            except ConflictError:
                logger.warning(
                    "bulk import: job=%s finished commit but was no longer COMMITTING — "
                    "likely swept as stale while still genuinely running; result discarded",
                    job_id,
                )
                raise
        except _BulkImportCancellationRequested:
            context["drafts"] = [item.model_dump(mode="json") for item in drafts]
            self._finalize_cancellation(organization_id, job_id, context)
            return
        except ConflictError:
            if self._finalize_if_cancelling(organization_id, job_id, context):
                return
            raise
        except Exception as exc:
            self._mark_commit_failed(organization_id, job_id, context, exc)
            raise

    def _mark_commit_failed(
        self,
        organization_id: str,
        job_id: str,
        context: dict[str, Any],
        exc: Exception,
    ) -> None:
        """Record an unexpected commit-time failure and move the job to a retryable status.

        COMMITTING has no dedicated FAILED status in the lifecycle model — a
        per-draft failure already lands on COMPLETED_WITH_ERRORS, and that's also
        the only non-COMPLETED status commit()'s own expected_statuses will
        re-queue from. Routing a whole-method failure (e.g. a missing actor
        snapshot) here too is what keeps the job from getting stuck at COMMITTING
        forever with zero recoverable path — never COMPLETED, which would assert
        unproven success.
        """
        logger.exception("bulk import commit failed for job %s: %s", job_id, exc)
        context["errors"] = [*list(context.get("errors") or []), str(exc)]
        self.jobs.update_job(
            organization_id,
            job_id,
            status=IntakeJobStatus.COMPLETED_WITH_ERRORS.value,
            expected_statuses={IntakeJobStatus.COMMITTING.value},
            context=context,
        )

    @staticmethod
    def _reconstruct_actor(job: IntakeJobContract) -> dict[str, object]:
        """Rebuild the actor dict every existing manager method expects, from the
        job's stored `actor_user_id` snapshot.

        No `roles` field is reconstructed: every permission check on this path is a
        live DB lookup keyed by user_id + organization_id, never a read of
        `actor["roles"]`.
        """
        user_id = str(dict(job.context).get("actor_user_id", "")).strip()
        if not user_id:
            raise ValidationError(f"intake job '{job.job_id}' has no actor_user_id snapshot")
        return {"organization_id": job.organization_id, "user_id": user_id}

    def _process_selected_drafts(
        self,
        actor: dict[str, object],
        context: dict[str, Any],
        organization_id: str,
        job_id: str,
        drafts: list[BulkImportDraft],
    ) -> int:
        """Commit each selected draft (entity, files, workflow), returning the failure count.

        Per-draft failures are recorded on the draft and counted; they do not abort the batch.
        """
        selected_drafts = [draft for draft in drafts if draft.selected]
        context["commit_total_count"] = len(selected_drafts)
        processed_ids = {str(item) for item in context.get("commit_processed_draft_ids") or []}
        usage = Counter(file_id for draft in drafts if draft.selected for file_id in draft.file_ids)
        remote_url_usage = Counter(
            url
            for draft in selected_drafts
            for url in {
                str(reference.source_url)
                for reference in draft.remote_file_references
                if reference.source_url
            }
        )
        identifier_template = self.entities.get_identifier_template_for_actor(
            actor, str(context["entity_type_id"])
        )
        failures = 0
        for offset in range(0, len(selected_drafts), self._commit_batch_size):
            self._raise_if_cancel_requested(organization_id, job_id)
            batch = selected_drafts[offset : offset + self._commit_batch_size]
            # Network-bound downloads happen concurrently inside this small batch.
            # Entity writes remain sequential because the manager owns one DB session.
            self._materialize_selected_remote_files(actor, context, job_id, batch)
            self._raise_if_cancel_requested(organization_id, job_id)
            for draft in batch:
                for reference in draft.remote_file_references:
                    if reference.file_id and reference.source_url:
                        usage[reference.file_id] = max(
                            usage[reference.file_id],
                            remote_url_usage[str(reference.source_url)],
                        )
                draft.files_attached = self._draft_files_attached(draft)
                try:
                    self._validate_required_relation_bindings(draft)
                    failed_references = [
                        reference
                        for reference in draft.remote_file_references
                        if reference.status in {"failed", "missing"}
                    ]
                    if failed_references:
                        raise ValidationError(
                            failed_references[0].error or "remote attachment could not be imported"
                        )
                    self._resolve_or_create_entity(actor, context, draft, identifier_template)
                    if not draft.files_attached:
                        self._attach_files(
                            actor,
                            draft,
                            usage,
                            on_file_attached=lambda: self._persist_commit_progress(
                                organization_id,
                                job_id,
                                context,
                                drafts,
                            ),
                        )
                    self._enroll_workflow_if_needed(actor, context, draft)
                    draft.error = None
                except _BulkImportCancellationRequested:
                    raise
                except Exception as exc:
                    failures += 1
                    draft.error = str(exc)
                finally:
                    processed_ids.add(draft.draft_id)
                    context["commit_processed_draft_ids"] = list(processed_ids)
                    self._persist_commit_progress(organization_id, job_id, context, drafts)
                self._raise_if_cancel_requested(organization_id, job_id)
        return failures

    def _materialize_selected_remote_files(
        self,
        actor: dict[str, object],
        context: dict[str, Any],
        job_id: str,
        drafts: list[BulkImportDraft],
    ) -> None:
        """Download accepted URL references and persist managed files at final commit."""
        organization_id = self._actor_value(actor, "organization_id")
        user_id = self._actor_value(actor, "user_id")
        pending = [
            reference
            for draft in drafts
            if draft.selected
            for reference in draft.remote_file_references
            if reference.source_url and not reference.file_id
        ]
        if not pending:
            return
        references_by_url: dict[str, list[BulkImportRemoteFileReference]] = {}
        for reference in pending:
            references_by_url.setdefault(str(reference.source_url), []).append(reference)
        remote_files = [
            dict(item) for item in context.get("remote_files") or [] if isinstance(item, dict)
        ]
        stored_by_url = {
            str(metadata.get("source_url")): item
            for item in remote_files
            if isinstance((metadata := item.get("metadata")), dict)
            and metadata.get("source_url")
            and item.get("file_id")
        }
        for url, references in references_by_url.items():
            stored = stored_by_url.get(url)
            if stored is None:
                continue
            for reference in references:
                reference.file_id = str(stored["file_id"])
                reference.filename = str(stored.get("filename") or "remote-file")
                reference.status = "stored"
                reference.error = None
            for draft in drafts:
                if any(reference in references for reference in draft.remote_file_references):
                    file_id = str(stored["file_id"])
                    if file_id not in draft.file_ids:
                        draft.file_ids.append(file_id)

        unique_urls = [url for url in references_by_url if url not in stored_by_url]
        outcomes = self.remote_files.fetch_many(unique_urls) if unique_urls else {}
        for url, outcome in outcomes.items():
            references = references_by_url[url]
            if not isinstance(outcome, FetchedRemoteFile):
                for reference in references:
                    reference.status = "failed"
                    reference.error = str(outcome)
                continue
            try:
                record = self.filehandler.upload_file(
                    organization_id,
                    user_id,
                    FileUploadRequest(
                        type_id=DEFAULT_FILE_TYPE,
                        filename=outcome.filename,
                        content_type=outcome.content_type,
                        content=base64.b64encode(outcome.content).decode("ascii"),
                        metadata={
                            "bulk_import_remote": True,
                            "bulk_import_job_id": job_id,
                            "source_url": outcome.source_url,
                            "final_url": outcome.final_url,
                            "fetched_at": datetime.now(UTC).isoformat(),
                            "sha256": outcome.sha256,
                            "etag": outcome.etag or "",
                            "last_modified": outcome.last_modified or "",
                        },
                    ),
                    skip_agent_dispatch=True,
                )
                remote_files.append(
                    {
                        "file_id": record.file_id,
                        "filename": record.filename,
                        "content_type": record.content_type,
                        "size_bytes": record.size_bytes,
                        "origin": "remote",
                        "metadata": dict(record.metadata),
                    }
                )
                for reference in references:
                    reference.file_id = record.file_id
                    reference.filename = record.filename
                    reference.status = "stored"
                    reference.error = None
                for draft in drafts:
                    if (
                        any(reference in references for reference in draft.remote_file_references)
                        and record.file_id not in draft.file_ids
                    ):
                        draft.file_ids.append(record.file_id)
            except Exception as exc:
                for reference in references:
                    reference.status = "failed"
                    reference.error = str(exc)
        context["remote_files"] = remote_files
        self._persist_commit_progress(organization_id, job_id, context, drafts)

    def _resolve_or_create_entity(
        self,
        actor: dict[str, object],
        context: dict[str, Any],
        draft: BulkImportDraft,
        identifier_template: str | None,
    ) -> None:
        """Ensure the draft has an entity id, reusing an existing match or creating a record."""
        if draft.entity_id:
            self._link_existing_entity(actor, draft)
            return
        if identifier_template is None and not draft.data.get(IDENTIFIER_FIELD_KEY):
            draft.data[IDENTIFIER_FIELD_KEY] = self._synthesize_manual_identifier(
                actor, str(context["entity_type_id"]), draft.data
            )
        existing_entity_id = self._find_existing_entity_id(
            actor,
            str(context.get("entity_type_name", "")),
            draft.data.get(IDENTIFIER_FIELD_KEY),
        )
        if existing_entity_id:
            draft.entity_id = existing_entity_id
            draft.existing_entity = True
            self._link_existing_entity(actor, draft)
        else:
            draft.entity_id = self._create_entity(actor, context, draft)

    def _link_existing_entity(
        self,
        actor: dict[str, object],
        draft: BulkImportDraft,
    ) -> None:
        """Idempotently add resolved parents to an existing record without relinking it."""
        source_entity_ids = self.relations.resolved_source_ids(draft.relation_bindings)
        if not draft.entity_id or not source_entity_ids:
            return
        from entities.models.request import EntityRecordUpdateRequest

        self.entities.update_entity_record_for_actor(
            actor,
            draft.entity_id,
            EntityRecordUpdateRequest(source_entity_ids=source_entity_ids),
        )

    def _enroll_workflow_if_needed(
        self,
        actor: dict[str, object],
        context: dict[str, Any],
        draft: BulkImportDraft,
    ) -> None:
        """Enroll the draft's entity into the configured workflow once, if any."""
        workflow_name = str(context.get("workflow_name", ""))
        if workflow_name and draft.entity_id and not draft.workflow_enrolled:
            self.workflows.enroll_entity_for_actor(actor, workflow_name, draft.entity_id)
            draft.workflow_enrolled = True

    def _agent_definition_id(self, actor: dict[str, object]) -> str:
        """Return the definition id of the bulk import extraction agent or raise ServiceError."""
        match = next(
            (
                item
                for item in self.agents.list_definitions_for_actor(actor)
                if item.name == BULK_IMPORT_AGENT
            ),
            None,
        )
        if match is None:
            raise ServiceError("bulk import extraction agent is unavailable")
        return match.definition_id

    def _extract_job(
        self,
        actor: dict[str, object],
        definition_id: str,
        context: dict[str, Any],
        *,
        files: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run the extraction agent once over every file in the job and return its parsed JSON payload.

        See the module docstring for the single-agent-per-job/slug-map design this
        method implements. Returns ``dict[str, Any]`` because the payload is
        untyped JSON from the agent.
        """
        entity_type_name = str(context["entity_type_name"])
        files = list(files if files is not None else context.get("files") or [])
        slug_map = {
            f"file_{index + 1}": str(item.get("file_id") or "") for index, item in enumerate(files)
        }
        file_manifest = "\n".join(
            f"{slug} = {item.get('filename') or 'unknown'}"
            for slug, item in zip(slug_map, files, strict=True)
        )
        run = self.agents.run_agent_for_actor(
            actor,
            AgentRunRequest(
                definition_id=definition_id,
                input=EXTRACTION_USER_PROMPT_TEMPLATE.format(
                    entity_type_name=entity_type_name,
                    file_count=len(files),
                    file_manifest=file_manifest,
                ),
                file_slug_map=slug_map,
            ),
        )
        run_id = str(getattr(run, "run_id", "") or "")
        if run_id:
            context["extraction_agent_run_ids"] = list(
                dict.fromkeys(
                    [
                        *[str(item) for item in context.get("extraction_agent_run_ids") or []],
                        run_id,
                    ]
                )
            )
        summary = self._summarize_agent_run(run.metadata, files, slug_map)
        context["extraction_summary"] = summary
        if run.status != "completed":
            raise ServiceError(
                f"{run.error or 'agent extraction did not complete'} "
                f"(after {summary['tool_call_count']} tool call(s), "
                f"{summary['read_job_document_call_count']} read attempt(s), "
                f"{len(summary['rejected_files'])} file(s) rejected, "
                f"{len(summary['misused_tool_calls'])} tool misuse(s))"
            )
        parsed = parse_agent_payload_with_metadata(str(run.output or ""))
        if parsed.warnings:
            context["parser_warnings"] = list(
                dict.fromkeys(
                    [
                        *[str(item) for item in context.get("parser_warnings") or []],
                        *parsed.warnings,
                    ]
                )
            )
        payload = parsed.payload
        return self._translate_payload_slugs(payload, slug_map)

    @staticmethod
    def _translate_payload_slugs(
        payload: dict[str, Any], slug_map: dict[str, str]
    ) -> dict[str, Any]:
        """Translate every slug the model used back to its real file id.

        The model's whole output is expressed in slugs (see `_extract_job`) — this
        is the one place that translation happens, so every caller downstream
        (`_build_drafts_from_payload`, the unmapped/skipped-file accounting in
        `_run_queued_analysis`) keeps working against real ids exactly as before,
        unchanged. An unrecognized slug (the model invented one) is dropped rather
        than kept — it can't refer to any real file.
        """
        entities = []
        for candidate in payload.get("entities") or []:
            if not isinstance(candidate, dict):
                continue
            raw_file_ids = candidate.get("file_ids")
            translated_ids = (
                [slug_map[slug] for slug in raw_file_ids if slug in slug_map]
                if isinstance(raw_file_ids, list)
                else []
            )
            entities.append({**candidate, "file_ids": translated_ids})

        skipped_files = []
        for item in payload.get("skipped_files") or []:
            if not isinstance(item, dict):
                continue
            real_file_id = slug_map.get(str(item.get("file_id") or ""))
            if real_file_id is None:
                continue
            skipped_files.append({**item, "file_id": real_file_id})

        return {**payload, "entities": entities, "skipped_files": skipped_files}

    @staticmethod
    def _summarize_agent_run(
        run_metadata: dict[str, Any], files: list[dict[str, Any]], slug_map: dict[str, str]
    ) -> dict[str, Any]:
        """Summarize one extraction run's tool activity for job-audit purposes.

        Pulled from the agent run's own trace metadata (`AgentRunResponse.metadata`,
        already persisted independently in `agent_trace_events` by the agent module)
        so a failed or partially-successful job can be diagnosed later without a
        debugger: how many tool calls it took, and which files (with filename) the
        agent itself reported as rejected. The trace itself is expressed in slugs
        (same as everything else the model sees) — translated back to real file ids
        here via `slug_map`, so this summary reads in real ids like the rest of the
        job's context.
        """
        filenames_by_file_id = {
            str(item.get("file_id") or ""): str(item.get("filename") or "") for item in files
        }
        tool_calls = list(run_metadata.get("tool_calls") or [])
        read_calls = [call for call in tool_calls if call.get("tool") == "read_job_document"]
        # Whole-call misuse (e.g. the agent sending more than 3 file_ids in one
        # call) never reaches the per-file array — the tool call itself fails and
        # comes back with success=False at the envelope level. Tracked separately
        # so a job audit can distinguish "the agent misused the tool" from
        # "a specific file was rejected".
        misused_calls: list[dict[str, Any]] = []
        rejected_files: list[dict[str, str]] = []
        for call in read_calls:
            result = call.get("result")
            if isinstance(result, dict) and result.get("success") is False:
                misused_calls.append(
                    {"args": call.get("args") or {}, "error": str(result.get("error") or "")}
                )
                continue
            rejected_files.extend(
                BulkImportServiceManager._collect_file_rejections(
                    result, slug_map, filenames_by_file_id
                )
            )
        return {
            "tool_call_count": len(tool_calls),
            "read_job_document_call_count": len(read_calls),
            "rejected_files": rejected_files,
            "misused_tool_calls": misused_calls,
        }

    @staticmethod
    def _collect_file_rejections(
        result: object, slug_map: dict[str, str], filenames_by_file_id: dict[str, str]
    ) -> list[dict[str, str]]:
        """Extract per-file error entries from one successful `read_job_document` call's result envelope.

        `result` is the tool's full `ToolExecutionResult` envelope (as captured
        in the run trace), not the inner tool payload directly — the per-file
        array lives at `result["output"]["results"]`.
        """
        output = result.get("output") if isinstance(result, dict) else None
        entries = output.get("results") if isinstance(output, dict) else None
        rejections: list[dict[str, str]] = []
        for entry in entries or []:
            if not isinstance(entry, dict) or entry.get("status") != "error":
                continue
            slug = str(entry.get("file_id") or "")
            file_id = slug_map.get(slug, slug)
            rejections.append(
                {
                    "file_id": file_id,
                    "filename": filenames_by_file_id.get(file_id, "unknown"),
                    "reason": str(entry.get("message") or "unknown error"),
                }
            )
        return rejections

    @staticmethod
    def _parse_extractor_payload(text: str) -> dict[str, Any]:
        """Compatibility wrapper around shared bulk-agent result parsing."""
        return parse_agent_payload_with_metadata(text).payload

    @staticmethod
    def _safe_confidence(raw_confidence: object) -> float:
        """Coerce an extractor-supplied confidence value to float, defaulting to 0.

        The merge pass runs after a file's raw result is already checkpointed as
        successful — a malformed value here (e.g. the model returning
        ``"confidence": "high"``) must never raise, or a retry would skip
        re-extracting the file (it's already checkpointed) and hit the exact
        same unparseable value forever, permanently stuck.
        """
        try:
            return float(raw_confidence or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _merge_candidate(
        drafts: list[BulkImportDraft],
        candidate: dict[str, Any],  # untyped extraction-agent entity payload
    ) -> None:
        """Merge one agent-returned entity into the drafts, deduping by identifier.

        `file_ids` now comes from the candidate itself (the agent attributes which
        file(s) support each entity) rather than being passed in per-file by the
        caller — see `_extract_job`.
        """
        data = candidate.get("data")
        if not isinstance(data, dict) or not data:
            # Defensive: the required shape nests fields under "data", but the
            # model has been observed flattening them directly onto the entity
            # object instead despite explicit instruction. Recover by treating
            # every other key as the data payload rather than silently
            # discarding an otherwise-valid, fully-extracted entity.
            data = {
                key: value
                for key, value in candidate.items()
                if key not in {"data", "confidence", "file_ids"}
            }
            if not data:
                return

        raw_file_ids = candidate.get("file_ids")
        file_ids = (
            [str(file_id) for file_id in raw_file_ids if str(file_id or "").strip()]
            if isinstance(raw_file_ids, list)
            else []
        )
        identity = str(data.get("identifier", "")).strip().casefold()
        existing = next(
            (
                draft
                for draft in drafts
                if identity and str(draft.data.get("identifier", "")).strip().casefold() == identity
            ),
            None,
        )
        confidence = BulkImportServiceManager._safe_confidence(candidate.get("confidence"))
        if existing is None:
            drafts.append(
                BulkImportDraft(
                    draft_id=str(uuid4()),
                    data=dict(data),
                    file_ids=file_ids,
                    confidence=max(0, min(1, confidence)),
                )
            )
            return
        existing.data = {**existing.data, **{k: v for k, v in data.items() if v not in (None, "")}}
        for file_id in file_ids:
            if file_id not in existing.file_ids:
                existing.file_ids.append(file_id)
        existing.confidence = max(existing.confidence, max(0, min(1, confidence)))

    def _resolve_existing_entities(
        self,
        actor: dict[str, object],
        entity_type_name: str,
        drafts: list[BulkImportDraft],
    ) -> None:
        """Resolve exact identifier matches before review.

        The entity service remains the source of truth for actor-visible records.
        A matched draft keeps its extracted data for review, but commit reuses the
        existing entity id and only performs file attachment/enrollment work.
        """
        for draft in drafts:
            entity_id = self._find_existing_entity_id(
                actor,
                entity_type_name,
                draft.data.get("identifier"),
            )
            if entity_id:
                draft.entity_id = entity_id
                draft.existing_entity = True

    def _find_existing_entity_id(
        self,
        actor: dict[str, object],
        entity_type_name: str,
        raw_identifier: object,
    ) -> str | None:
        """Return the id of an existing entity whose identifier matches, or None."""
        identifier = str(raw_identifier or "").strip()
        if not identifier:
            return None
        normalized = identifier.casefold()
        records = self.entities.list_entity_records_by_type_name_for_actor(
            actor,
            entity_type_name,
            search=identifier,
            limit=EXISTING_ENTITY_SEARCH_LIMIT,
        )
        match = next(
            (
                item
                for item in records.items
                if str((item.data or {}).get("identifier", "")).strip().casefold() == normalized
            ),
            None,
        )
        return match.entity_id if match else None

    def _create_entity(
        self,
        actor: dict[str, object],
        context: dict[str, object],
        draft: BulkImportDraft,
    ) -> str:
        """Create a new entity record from the draft's data and return its id."""
        from entities.models.request import EntityRecordCreateRequest

        self._validate_required_relation_bindings(draft)

        record = self.entities.create_entity_record_for_actor(
            actor,
            EntityRecordCreateRequest(
                organization_id=self._actor_value(actor, "organization_id"),
                entity_type_id=str(context["entity_type_id"]),
                data=dict(draft.data),
                owner_id=self._actor_value(actor, "user_id"),
                source_entity_ids=self.relations.resolved_source_ids(draft.relation_bindings),
            ),
            require_reference_sources=True,
        )
        return record.entity_id

    @staticmethod
    def _validate_required_relation_bindings(draft: BulkImportDraft) -> None:
        missing_required = [
            item
            for item in draft.relation_bindings
            if item.relation_type == "REFERENCE" and item.status != "resolved"
        ]
        if missing_required:
            raise ValidationError(missing_required[0].error or "a required parent is unresolved")

    def _synthesize_manual_identifier(
        self,
        actor: dict[str, object],
        entity_type_id: str,
        data: dict[str, Any],
    ) -> str:
        """Build a readable, unique-for-this-type identifier from the draft's own data."""
        base = self._identifier_base(data)
        candidate = base
        for attempt in range(2, IDENTIFIER_SYNTHESIS_MAX_SUFFIX_ATTEMPTS + 2):
            if not self.entities.is_identifier_taken_for_actor(actor, entity_type_id, candidate):
                return candidate
            candidate = f"{base}_{attempt}"
        logger.warning(
            "bulk import: exhausted identifier suffix attempts for base '%s'",
            base,
            extra={
                "entity_type_id": entity_type_id,
                "max_attempts": IDENTIFIER_SYNTHESIS_MAX_SUFFIX_ATTEMPTS,
            },
        )
        raise ServiceError(f"could not find a free identifier for base '{base}'")

    @staticmethod
    def _identifier_base(data: dict[str, Any]) -> str:
        """First non-empty value from the synthesis priority list, else any string field."""
        for key in IDENTIFIER_SYNTHESIS_FIELD_PRIORITY:
            value = str(data.get(key) or "").strip()
            if value:
                return value
        for value in data.values():
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "record"

    def _attach_files(
        self,
        actor: dict[str, object],
        draft: BulkImportDraft,
        usage: Counter[str],
        *,
        on_file_attached: Callable[[], None],
    ) -> None:
        """Attach unfinished files and durably record progress after every success."""
        organization_id = self._actor_value(actor, "organization_id")
        user_id = self._actor_value(actor, "user_id")
        if not draft.entity_id:
            return
        for file_id in draft.file_ids:
            if file_id in draft.attached_file_ids:
                continue
            remote_reference = next(
                (
                    reference
                    for reference in draft.remote_file_references
                    if reference.file_id == file_id
                ),
                None,
            )
            provenance = (
                {
                    "bulk_import_source_sheet": draft.source_sheet_name or "",
                    "bulk_import_source_row": draft.source_row_number or 0,
                    "bulk_import_source_column": remote_reference.source_column,
                    "bulk_import_source_value": remote_reference.source_value,
                }
                if remote_reference is not None
                else {}
            )
            self._attach_file(
                organization_id,
                user_id,
                draft.entity_id,
                file_id,
                shared=usage[file_id] > 1,
                metadata=provenance,
            )
            draft.attached_file_ids.append(file_id)
            draft.files_attached = self._draft_files_attached(draft)
            on_file_attached()

    def _attach_file(
        self,
        organization_id: str,
        user_id: str,
        entity_id: str,
        file_id: str,
        *,
        shared: bool,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Idempotently attach one source file to one entity."""
        if not shared:
            source = self.filehandler.db_model_service.get_file(organization_id, file_id)
            if source is not None and source.owner_entity_id == entity_id:
                if metadata:
                    self.filehandler.db_model_service.merge_file_metadata(
                        organization_id, file_id, metadata
                    )
                return
            self.filehandler.db_model_service.set_file_owner(
                organization_id,
                file_id,
                entity_id,
            )
            if metadata:
                self.filehandler.db_model_service.merge_file_metadata(
                    organization_id, file_id, metadata
                )
            return

        already_copied = any(
            str((record.metadata or {}).get("bulk_import_source_file_id", "")) == file_id
            for record in self.filehandler.db_model_service.list_files(
                organization_id,
                owner_entity_id=entity_id,
            )
        )
        if already_copied:
            return
        self.filehandler.copy_file_to_entity(
            organization_id,
            user_id,
            source_file_id=file_id,
            target_entity_id=entity_id,
            metadata={"bulk_import_source_file_id": file_id, **dict(metadata or {})},
        )

    def _persist_commit_progress(
        self,
        organization_id: str,
        job_id: str,
        context: dict[str, object],
        drafts: list[BulkImportDraft],
    ) -> None:
        """Persist per-file progress while the job remains in COMMITTING."""
        self._raise_if_cancel_requested(organization_id, job_id)
        context["drafts"] = [item.model_dump(mode="json") for item in drafts]
        self.jobs.update_job(
            organization_id,
            job_id,
            expected_statuses={IntakeJobStatus.COMMITTING.value},
            context=context,
        )

    @staticmethod
    def _drafts_from_context(context: dict[str, Any]) -> list[BulkImportDraft]:
        """Load drafts while remaining compatible with pre-progress job payloads."""
        drafts = [
            BulkImportDraft.model_validate(item)
            for item in list(context.get("drafts") or [])
            if isinstance(item, dict)
        ]
        for draft in drafts:
            if (
                draft.files_attached
                and not draft.attached_file_ids
                and not draft.remote_file_references
            ):
                draft.attached_file_ids = list(draft.file_ids)
        return drafts

    @staticmethod
    def _relation_definitions_from_context(
        context: dict[str, Any],
    ) -> list[BulkImportRelationDefinition]:
        return [
            BulkImportRelationDefinition.model_validate(item)
            for item in context.get("relation_definitions") or []
            if isinstance(item, dict)
        ]

    @staticmethod
    def _response(job: IntakeJobContract) -> BulkImportJobResponse:
        """Build the API response model from an intake job contract."""
        # dict[str, Any]: the job context is a freeform JSON blob persisted on the intake job.
        context: dict[str, Any] = dict(job.context)
        drafts = BulkImportServiceManager._drafts_from_context(context)
        return BulkImportJobResponse(
            job_id=job.job_id,
            status=job.status,
            operation=str(context.get("queued_for") or "") or None,
            entity_type_id=str(context.get("entity_type_id", "")),
            entity_type_name=str(context.get("entity_type_name", "")),
            workflow_name=str(context.get("workflow_name", "")) or None,
            files=[
                *[dict(item) for item in list(context.get("files") or [])],
                *[dict(item) for item in list(context.get("remote_files") or [])],
            ],
            drafts=drafts,
            unmapped_file_ids=[str(item) for item in context.get("unmapped_file_ids") or []],
            processed_count=job.processed_count,
            failed_count=job.failed_count,
            created_count=sum(
                1 for draft in drafts if draft.entity_id and not draft.existing_entity
            ),
            existing_count=sum(1 for draft in drafts if draft.existing_entity),
            commit_processed_count=len(
                {str(item) for item in context.get("commit_processed_draft_ids") or []}
            ),
            commit_total_count=int(
                context.get("commit_total_count") or sum(1 for draft in drafts if draft.selected)
            ),
            cancel_requested=bool(context.get("cancel_requested")),
            errors=[str(item) for item in context.get("errors") or []],
            spreadsheet_sources=[
                BulkImportSpreadsheetSource.model_validate(item)
                for item in context.get("spreadsheet_sources") or []
                if isinstance(item, dict)
            ],
            relation_definitions=BulkImportServiceManager._relation_definitions_from_context(
                context
            ),
            diagnostics=BulkImportServiceManager._diagnostics_from_context(context),
        )

    @staticmethod
    def _diagnostics_from_context(context: dict[str, Any]) -> BulkImportDiagnostics | None:
        """Build optional debug metadata from the persisted bulk-import context."""
        analysis_stage = str(context.get("analysis_stage") or "") or None
        mapping_agent_run_id = (
            str(context.get("spreadsheet_mapping_agent_run_id") or "")
            or str(context.get("mapping_agent_run_id") or "")
            or None
        )
        extraction_agent_run_ids = [
            str(item) for item in context.get("extraction_agent_run_ids") or [] if str(item)
        ]
        parser_warnings = [str(item) for item in context.get("parser_warnings") or [] if str(item)]
        if not any(
            [analysis_stage, mapping_agent_run_id, extraction_agent_run_ids, parser_warnings]
        ):
            return None
        return BulkImportDiagnostics(
            analysis_stage=analysis_stage,
            mapping_agent_run_id=mapping_agent_run_id,
            extraction_agent_run_ids=extraction_agent_run_ids,
            parser_warnings=parser_warnings,
        )

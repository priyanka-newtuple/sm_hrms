"""Business logic manager for background_jobs."""

from __future__ import annotations

import html
import json
import threading
from collections import deque
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Any

from background_jobs.models.interface import ActionRunIdempotencyKey
from background_jobs.models.request import CreateIntakeJobRequest, UploadIntakeSourceRequest
from background_jobs.models.response import (
    IntakeJobListResponse,
    IntakeJobResponse,
    IntakeOrchestrationStatusResponse,
)
from common.configuration import get_configuration
from common.data_model import DEFAULT_ACTION_RUNS_QUEUE, DEFAULT_AGENT_ASYNC_QUEUE
from common.enums import ModuleStatus
from common.logger import logger
from connectors.manager import (
    TABLE_MERGE_INSTRUCTION_KEY,
    TABLE_MERGE_LOOKUPS_KEY,
    TABLE_MERGE_MATCH_INSTRUCTION_KEY,
    TABLE_MERGE_RESPONSE_KEY,
    TABLE_MERGE_ROWS_KEY,
    TABLE_WILDCARD_FIELD,
    fill_lookup_columns,
)
from custom_forms.models.interface import (
    CUSTOM_FORM_RESPONSE_META_KEY,
    CUSTOM_FORM_WRITEBACK_TARGET,
    WRITEBACK_TARGET_META_KEY,
)
from exceptions import ServiceError, ValidationError
from executor.manager import resolve_config
from executor.models.interface import ExecutorBinding, ExecutorInput, ExecutorValue, ValueKind
from executor.models.request import ExecutorExecutionRequest
from mail.models.interface import EmailActionKind

if TYPE_CHECKING:
    from auth.manager import AuthServiceManager
    from background_jobs.db_models import BackgroundJobsModelService
    from database.manager import DatabaseServiceManager
    from executor.manager import ExecutorServiceManager


EMAIL_KIND_ACTION_FAILED = EmailActionKind.ACTION_FAILED.value


def _field_text_value(value: Any) -> str:
    """Stringify an entity/config field for placeholder substitution.

    Lists and dicts are JSON-encoded so raw-body templates that inline a
    structured `$entity.field` (e.g. an array of rows) receive valid JSON
    instead of a Python repr with single quotes, which the receiving API
    would reject as malformed. Scalars keep their plain string form since
    they sit inside quotes in the template.
    """
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


class BackgroundJobsServiceManager:
    """Domain-agnostic intake orchestration service."""

    def __init__(
        self,
        background_jobs_db_model_service: BackgroundJobsModelService,
        database_service_manager: DatabaseServiceManager | None,
        config: Any,
        auth_service_manager: AuthServiceManager | None = None,
        executor_service_manager: ExecutorServiceManager | None = None,
        workflow_service_manager: Any = None,
        mail_service_manager: Any = None,
        forms_db_model_service: Any = None,
        schedules_service_manager: Any = None,
        *dependencies: Any,
    ) -> None:
        """Initialise the manager, wiring up the db service and optional integrations."""
        self.db = background_jobs_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.auth_service_manager = auth_service_manager
        self.executor_service_manager = executor_service_manager
        self.workflow_service_manager = workflow_service_manager
        self.mail_service_manager = mail_service_manager
        self.forms_db_model_service = forms_db_model_service
        self.schedules_service_manager = schedules_service_manager
        # Late-bound in main.py (mirrors workflow_service_manager). Used only by
        # the dedicated agent-runs worker loop to execute standalone async runs.
        self.agent_service_manager = None
        # Late-bound in main.py too. Used only when an action declares
        # writeback_target: "custom_form".
        self.custom_forms_service_manager = None
        self.module_name = "background_jobs"
        self._started = False

        # Redis worker state
        self._worker_stop = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="action-runs-worker"
        )
        self._sweep_thread: threading.Thread | None = None
        self._local_queue: deque[str] = deque()
        self._local_queue_lock = threading.Lock()

        # Dedicated queue + worker for standalone async agent runs
        # (POST /agent/async_runs). Separate BLPOP key so it never contends with
        # the entity/workflow action-runs queue above.
        self._agent_worker_thread = threading.Thread(
            target=self._agent_worker_loop, daemon=True, name="agent-runs-worker"
        )
        self._agent_local_queue: deque[str] = deque()
        self._agent_local_queue_lock = threading.Lock()
        self.agent_runs_queue_name = DEFAULT_AGENT_ASYNC_QUEUE

        # Resolve Redis client
        self.redis_db_service = None
        try:
            if database_service_manager is not None and hasattr(
                database_service_manager, "redis_db_service"
            ):
                self.redis_db_service = database_service_manager.redis_db_service()
        except Exception as exc:
            logger.debug("__init__ redis_db_service unavailable: %s", exc)

        try:
            bg_config = get_configuration().background_jobs_configuration
            self.action_runs_queue_name = bg_config.redis_queue_name
            self.worker_backoff_seconds = bg_config.worker_backoff_seconds
            self.redis_blpop_timeout_seconds = bg_config.redis_blpop_timeout_seconds
            self.retry_sweep_interval_seconds = bg_config.retry_sweep_interval_seconds
            self.pending_action_run_batch_size = bg_config.pending_action_run_batch_size
            self.worker_shutdown_join_seconds = bg_config.worker_shutdown_join_seconds
        except Exception:
            self.action_runs_queue_name = DEFAULT_ACTION_RUNS_QUEUE
            self.worker_backoff_seconds = 0.1
            self.redis_blpop_timeout_seconds = 1
            self.retry_sweep_interval_seconds = 5
            self.pending_action_run_batch_size = 25
            self.worker_shutdown_join_seconds = 5.0

    @contextmanager
    def _db_session(self):
        """Yield a session from database_service_manager for sweep operations."""
        db = self.database_service_manager.postgres_db_service().get_db_session()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def start(self) -> None:
        """Start the background worker. Skipped in the web process unless the
        action-runs worker is enabled (background_jobs_configuration.worker_enabled)."""
        self._started = True
        if not get_configuration().background_jobs_configuration.worker_enabled:
            return
        self._worker_stop.clear()
        self._worker_thread.start()
        self._sweep_thread = threading.Thread(
            target=self._retry_sweep_loop, daemon=True, name="action-runs-sweep"
        )
        self._sweep_thread.start()
        self._reconcile_stale_action_runs()

        # Start the dedicated async agent-runs worker and re-enqueue any runs that
        # were persisted as queued but never drained (e.g. enqueued with no worker).
        self._agent_worker_thread.start()
        self._reconcile_queued_agent_runs()

    def stop(self) -> None:
        """Stop the background worker threads and wait briefly for them to exit."""
        self._started = False
        self._worker_stop.set()
        for thread in (self._worker_thread, self._sweep_thread, self._agent_worker_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=self.worker_shutdown_join_seconds)

    def get_status(self) -> IntakeOrchestrationStatusResponse:
        """Return the current operational status of the background_jobs module."""
        return IntakeOrchestrationStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def get_action_run(self, db: Any, run_id: str) -> dict[str, object] | None:
        """Return a single action run by run_id."""
        return self.db.get_action_run(db, run_id)

    def update_action_run_submitted(self, db: Any, run_id: str, fields: dict[str, object]) -> None:
        """Mark an action run as submitted with the provided fields."""
        self.db.update_action_run_submitted(db, run_id, fields)

    def advance_chain_for_run(self, db: Any, run_id: str, *, failed: bool = False) -> None:
        """Advance a run's chain by run_id; call after the entity write, not before."""
        run = self.db.get_action_run(db, run_id)
        if run is not None:
            self._advance_state_action_chain(
                organization_id=str(run.get("organization_id")),
                entity_id=str(run.get("entity_id")),
                run_id=run_id,
                action_kind=str(run.get("action_kind")),
                config=dict(run.get("config_json") or {}),
                failed=failed,
            )

    def get_pending_external_run_for_entity(
        self, db: Any, entity_id: str
    ) -> dict[str, object] | None:
        """Return the most recent pending_external form.receive_data run for an entity."""
        return self.db.get_pending_external_run_for_entity(db, entity_id)

    def get_pending_external_run_by_run_id(self, db: Any, run_id: str) -> dict[str, object] | None:
        """Return a pending_external action run by run_id."""
        return self.db.get_pending_external_run_by_run_id(db, run_id)

    def mark_action_run_result(
        self, db: Any, run_id: str, status: str, outcome: str, resolved_config_json: Any
    ) -> None:
        """Persist the final succeeded or failed result of an action run."""
        self.db.mark_action_run_result(
            db,
            run_id=run_id,
            status=status,
            outcome=outcome,
            resolved_config_json=resolved_config_json,
        )

    def create_intake_job(
        self,
        request: CreateIntakeJobRequest | dict[str, object],
    ) -> IntakeJobResponse:
        """Create a new intake job and return its response representation."""
        try:
            job_request = (
                request
                if isinstance(request, CreateIntakeJobRequest)
                else CreateIntakeJobRequest.from_dict(request)
            )
            contract = self.db.create_job(job_request)
            return IntakeJobResponse(
                job_id=contract.job_id,
                organization_id=contract.organization_id,
                status=contract.status,
                source_type=contract.source_type,
                file_count=contract.file_count,
                processed_count=contract.processed_count,
                failed_count=contract.failed_count,
                subject_entity_type=contract.subject_entity_type,
                created_at=contract.created_at,
                updated_at=contract.updated_at,
                context=dict(contract.context),
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            raise ServiceError(f"Unable to create intake job: {exc}") from exc

    def upload_sources(
        self,
        request: UploadIntakeSourceRequest | dict[str, object],
    ) -> IntakeJobResponse:
        """Convert an upload-sources request into a create-job call and return the result."""
        try:
            upload_request = (
                request
                if isinstance(request, UploadIntakeSourceRequest)
                else UploadIntakeSourceRequest.from_dict(request)
            )
            return self.create_intake_job(
                CreateIntakeJobRequest(
                    organization_id=upload_request.organization_id,
                    source_type=upload_request.source_type,
                    subject_entity_type=upload_request.subject_entity_type,
                    files=list(upload_request.files),
                    context=dict(upload_request.context),
                )
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            raise ServiceError(f"Unable to upload intake sources: {exc}") from exc

    def get_intake_job(self, organization_id: str, job_id: str) -> IntakeJobResponse | None:
        """Retrieve a single intake job by org and job id, or return None if not found."""
        contract = self.db.get_job(organization_id=organization_id, job_id=job_id)
        if contract is None:
            return None
        return IntakeJobResponse(
            job_id=contract.job_id,
            organization_id=contract.organization_id,
            status=contract.status,
            source_type=contract.source_type,
            file_count=contract.file_count,
            processed_count=contract.processed_count,
            failed_count=contract.failed_count,
            subject_entity_type=contract.subject_entity_type,
            created_at=contract.created_at,
            updated_at=contract.updated_at,
            context=dict(contract.context),
        )

    def list_intake_jobs(
        self,
        organization_id: str,
        status: str | None = None,
    ) -> IntakeJobListResponse:
        """Return a paginated list of intake jobs for the given organisation."""
        rows = self.db.list_jobs(organization_id=organization_id, status=status)
        return IntakeJobListResponse(
            items=[
                IntakeJobResponse(
                    job_id=row.job_id,
                    organization_id=row.organization_id,
                    status=row.status,
                    source_type=row.source_type,
                    file_count=row.file_count,
                    processed_count=row.processed_count,
                    failed_count=row.failed_count,
                    subject_entity_type=row.subject_entity_type,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    context=dict(row.context),
                )
                for row in rows
            ]
        )

    def enqueue_action_run(self, run_id: str) -> None:
        """Push a run_id onto the Redis action runs queue (local deque fallback if Redis unavailable)."""
        if self.redis_db_service is not None:
            try:
                self.redis_db_service.redis_client.rpush(self.action_runs_queue_name, run_id)
                logger.info("action runs: enqueued run %s", run_id)
                return
            except Exception as exc:
                logger.debug("Redis enqueue failed for run %s, falling back to local queue: %s", run_id, exc)
        with self._local_queue_lock:
            self._local_queue.append(run_id)
        logger.info("action runs: enqueued run %s (local queue)", run_id)

    def create_scheduled_action_run(
        self,
        *,
        organization_id: str,
        entity_id: str,
        action_kind: str,
        config_json: dict[str, object],
        idempotency_key: str,
        scheduled_at: datetime | None = None,
    ) -> str:
        """Persist an idempotent run and enqueue it only when currently eligible."""
        run_id, created = self.db.create_action_run(
            organization_id=organization_id,
            entity_id=entity_id,
            action_kind=action_kind,
            config_json=config_json,
            idempotency_key=idempotency_key,
            scheduled_at=scheduled_at,
        )
        if created and (scheduled_at is None or scheduled_at <= datetime.now(UTC)):
            self.enqueue_action_run(run_id)
        return run_id

    def find_scheduled_action_run(
        self,
        *,
        organization_id: str,
        invocation_id: str,
        schedule_target_id: str,
    ) -> dict[str, object] | None:
        """Return a run previously created for one manual schedule invocation target."""
        return self.db.find_scheduled_action_run(
            organization_id=organization_id,
            invocation_id=invocation_id,
            schedule_target_id=schedule_target_id,
        )

    def dequeue_action_run(self) -> str | None:
        """Pop a run_id from the Redis queue (local deque fallback if Redis unavailable)."""
        if self.redis_db_service is not None:
            try:
                payload = self.redis_db_service.redis_client.blpop(
                    self.action_runs_queue_name, timeout=self.redis_blpop_timeout_seconds
                )
                if payload:
                    _, run_id = payload
                    return str(run_id or "").strip() or None
            except Exception as exc:
                logger.debug("Redis dequeue failed, falling back to local queue: %s", exc)
        with self._local_queue_lock:
            if not self._local_queue:
                return None
            return self._local_queue.popleft()

    def enqueue_agent_run(self, run_id: str) -> None:
        """Push a run_id onto the async agent-runs queue (local deque fallback)."""
        if self.redis_db_service is not None:
            try:
                self.redis_db_service.redis_client.rpush(self.agent_runs_queue_name, run_id)
                logger.info("agent runs: enqueued run %s", run_id)
                return
            except Exception as exc:
                logger.debug(
                    "Redis enqueue failed for agent run %s, falling back to local queue: %s",
                    run_id,
                    exc,
                )
        with self._agent_local_queue_lock:
            self._agent_local_queue.append(run_id)
        logger.info("agent runs: enqueued run %s (local queue)", run_id)

    def dequeue_agent_run(self) -> str | None:
        """Pop a run_id from the async agent-runs queue (local deque fallback)."""
        if self.redis_db_service is not None:
            try:
                payload = self.redis_db_service.redis_client.blpop(
                    self.agent_runs_queue_name, timeout=self.redis_blpop_timeout_seconds
                )
                if payload:
                    _, run_id = payload
                    return str(run_id or "").strip() or None
            except Exception as exc:
                logger.debug("Redis dequeue failed for agent runs, falling back to local queue: %s", exc)
        with self._agent_local_queue_lock:
            if not self._agent_local_queue:
                return None
            return self._agent_local_queue.popleft()

    def _agent_worker_loop(self) -> None:
        """Worker thread: dequeues and executes standalone async agent runs.

        Unlike ``_worker_loop`` this has no entity/workflow coupling — it simply
        hands each run id to the agent service, which loads the run, executes it,
        and finalizes its own status.
        """
        while not self._worker_stop.is_set():
            run_id: str | None = None
            try:
                run_id = self.dequeue_agent_run()
                if run_id is None:
                    self._worker_stop.wait(timeout=self.worker_backoff_seconds)
                    continue
                logger.info(
                    "agent runs: dequeued run",
                    extra={"run_id": run_id, "queue": self.agent_runs_queue_name},
                )
                if self.agent_service_manager is None:
                    logger.warning(
                        "agent runs: no agent service bound; dropping run",
                        extra={"run_id": run_id, "queue": self.agent_runs_queue_name},
                    )
                    continue
                self.agent_service_manager.execute_async_run(run_id)
                logger.info(
                    "agent runs: finished run",
                    extra={"run_id": run_id, "queue": self.agent_runs_queue_name},
                )
            except Exception:
                # Keep the worker alive across a bad iteration; brief backoff so a
                # persistent fault (e.g. Redis down) doesn't hot-loop the logs.
                # logger.exception captures the active exception's full traceback.
                logger.exception(
                    "agent runs worker iteration failed",
                    extra={"run_id": run_id, "queue": self.agent_runs_queue_name},
                )
                self._worker_stop.wait(timeout=self.worker_backoff_seconds)

    def _reconcile_queued_agent_runs(self) -> None:
        """Re-enqueue async agent runs left in ``queued`` status on startup."""
        if self.agent_service_manager is None:
            return
        try:
            run_ids = self.agent_service_manager.list_queued_run_ids(
                self.pending_action_run_batch_size
            )
        except Exception:
            # logger.exception logs the active exception with its full traceback.
            logger.exception(
                "agent runs: failed to list queued runs for reconcile",
                extra={
                    "queue": self.agent_runs_queue_name,
                    "batch_size": self.pending_action_run_batch_size,
                },
            )
            return
        for run_id in run_ids:
            self.enqueue_agent_run(run_id)
        if run_ids:
            logger.info("agent runs: reconciled %d queued run(s)", len(run_ids))

    def _worker_loop(self) -> None:
        """Main worker thread: dequeues and executes action runs from the Redis queue."""
        while not self._worker_stop.is_set():
            try:
                run_id = self.dequeue_action_run()
                if run_id is None:
                    self._worker_stop.wait(timeout=self.worker_backoff_seconds)
                    continue
                logger.info("action runs: dequeued run %s", run_id)
                if self.database_service_manager is None:
                    continue
                with self._db_session() as db:
                    row = self.db.get_action_run(db, run_id)
                if row is None or row.get("status") != "pending":
                    logger.info("action runs: skipped run %s (not pending)", run_id)
                    continue
                scheduled_at = row.get("scheduled_at")
                if isinstance(scheduled_at, datetime) and scheduled_at > datetime.now(UTC):
                    logger.info("action runs: skipped early run %s", run_id)
                    continue
                self._execute_action_run(
                    run_id=run_id,
                    organization_id=str(row["organization_id"]),
                    entity_id=str(row["entity_id"]),
                    action_kind=str(row["action_kind"]),
                    config_json=row.get("config_json"),
                )
                logger.info("action runs: finished run %s", run_id)
            except Exception:
                # Keep the worker alive across a bad iteration, but make the
                # failure visible (with traceback). Brief backoff so a persistent
                # fault (e.g. Redis down) doesn't hot-loop and flood the logs.
                logger.exception("action runs worker iteration failed")
                self._worker_stop.wait(timeout=self.worker_backoff_seconds)

    def _retry_sweep_loop(self) -> None:
        """Sweep thread: re-enqueues due retry rows and handles external timeouts.

        Uses the stop event for the inter-sweep wait so stop() interrupts it
        immediately instead of blocking for the full interval.
        """
        while not self._worker_stop.is_set():
            try:
                self.run_timeout_sweep()
                if self.schedules_service_manager is not None:
                    self.schedules_service_manager.process_due_targets(
                        limit=self.pending_action_run_batch_size
                    )
                self._enqueue_due_retries()
            except Exception:
                logger.exception("background retry sweep failed")
            self._worker_stop.wait(timeout=self.retry_sweep_interval_seconds)

    def _enqueue_due_retries(self) -> None:
        """Re-enqueue action runs that have a past scheduled_at (retry rows now due)."""
        if self.database_service_manager is None:
            return
        with self._db_session() as db:
            rows = self.db.list_pending_action_runs(db, limit=self.pending_action_run_batch_size)
        for row in rows:
            if row.get("scheduled_at") is not None:
                self.enqueue_action_run(str(row["run_id"]))

    def _reconcile_stale_action_runs(self) -> None:
        """On worker startup, re-enqueue all pending action runs not yet in the Redis queue."""
        if self.database_service_manager is None:
            return
        try:
            with self._db_session() as db:
                run_ids = self.db.list_pending_action_run_ids_for_reconciliation(db)
            for run_id in run_ids:
                self.enqueue_action_run(run_id)
            logger.debug("Reconciled %d pending action runs on worker startup", len(run_ids))
        except Exception as exc:
            logger.debug("Action run reconciliation failed: %s", exc)

    def run_action_sweep(self) -> None:
        """Legacy sweep — kept as utility. No longer called by the worker loop."""
        if self.executor_service_manager is None or self.workflow_service_manager is None:
            return
        if self.database_service_manager is None:
            return
        with self._db_session() as db:
            rows = self.db.list_pending_action_runs(db, limit=self.pending_action_run_batch_size)
        for row in rows:
            self._execute_action_run(
                run_id=str(row["run_id"]),
                organization_id=str(row["organization_id"]),
                entity_id=str(row["entity_id"]),
                action_kind=str(row["action_kind"]),
                config_json=row.get("config_json"),
            )

    def run_timeout_sweep(self) -> None:
        """Mark externally-pending timed-out runs as failed and fire configured failure triggers."""
        if self.database_service_manager is None:
            return
        with self._db_session() as db:
            timed_out_run_ids = self.db.timeout_pending_external_runs(db)
            timed_out_runs = {
                run_id: self.db.get_action_run(db, run_id) for run_id in timed_out_run_ids
            }
        for run_id, run in timed_out_runs.items():
            if run is None:
                continue
            organization_id = str(run.get("organization_id"))
            entity_id = str(run.get("entity_id"))
            action_kind = str(run.get("action_kind"))
            resolved = dict(run.get("config_json") or {})
            self._emit_action_event(
                organization_id=organization_id,
                entity_id=entity_id,
                event_type="ACTION_FAILED",
                run_id=run_id,
                action_kind=action_kind,
                payload={"error": "timeout", "failure_policy": "timeout"},
                chain_config=resolved,
            )
            failure_policy = self._normalize_failure_policy(resolved)
            trigger = str(failure_policy.get("trigger") or "").strip()
            if trigger:
                self._fire_trigger(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    trigger=trigger,
                )
            self._advance_state_action_chain(
                organization_id=organization_id,
                entity_id=entity_id,
                run_id=run_id,
                action_kind=action_kind,
                config=resolved,
                failed=True,
            )

    def _emit_action_event(
        self,
        organization_id: str,
        entity_id: str,
        event_type: str,
        run_id: str,
        action_kind: str,
        payload: dict,
        actor_type: str = "system",
        actor_id: str | None = None,
        chain_config: dict | None = None,
    ) -> None:
        """Append an action lifecycle event to the entity audit timeline."""
        try:
            full_payload = {"run_id": run_id, "action_kind": action_kind, **payload}
            if chain_config and chain_config.get("action_display_name"):
                full_payload.setdefault("action_display_name", chain_config.get("action_display_name"))
            if chain_config and chain_config.get("state_action_index") is not None:
                full_payload.setdefault("chain_id", chain_config.get("chain_id"))
                full_payload.setdefault("action_index", chain_config.get("state_action_index"))
                full_payload.setdefault("action_total", chain_config.get("state_action_total"))
            self.workflow_service_manager.entities_service_manager._emit_entity_event(
                organization_id=organization_id,
                entity_id=entity_id,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor_id,
                correlation_id=run_id,
                payload=full_payload,
            )
        except Exception as exc:
            logger.warning(f"failed to emit action event {event_type} run_id={run_id}: {exc}")

    @staticmethod
    def _render_email_template(text: str, values: dict[str, str]) -> str:
        for key, value in values.items():
            text = text.replace(f"{{{{{key}}}}}", value)
        return text

    @staticmethod
    def _normalize_failure_policy(resolved: dict[str, Any]) -> dict[str, Any]:
        """Return a normalized failure policy payload from resolved config."""
        raw = resolved.get("failure_policy")
        return dict(raw) if isinstance(raw, dict) else {}

    @staticmethod
    def _is_mid_chain(config: dict[str, Any]) -> bool:
        """True when this run has more chain actions after it. `isolated_rerun` never cascades."""
        if config.get("isolated_rerun"):
            return False
        index, total = config.get("state_action_index"), config.get("state_action_total")
        return index is not None and total is not None and int(index) + 1 < int(total)

    def _advance_state_action_chain(
        self,
        *,
        organization_id: str,
        entity_id: str,
        run_id: str,
        action_kind: str,
        config: dict[str, Any],
        failed: bool,
    ) -> None:
        """Create the next chain run on any terminal result; stop/skip per policy and state guard."""
        emit_chain_event = partial(
            self._emit_action_event, organization_id=organization_id,
            entity_id=entity_id, run_id=run_id, action_kind=action_kind,
            chain_config=config,
        )
        try:
            if not self._is_mid_chain(config):
                return
            if failed:
                policy = self._normalize_failure_policy(config)
                if str(policy.get("on_chain_failure") or "continue").strip().lower() == "stop":
                    emit_chain_event(
                        event_type="ACTION_CHAIN_STOPPED",
                        payload={"reason": "action failed and on_chain_failure is 'stop'"},
                    )
                    return
            entity_state = self.workflow_service_manager._hydrate_entity_state(
                organization_id, entity_id
            )
            if (
                entity_state is None
                or entity_state.current_state != str(config.get("origin_state") or "")
                or entity_state.state_version != config.get("origin_state_version")
            ):
                emit_chain_event(
                    event_type="ACTION_CHAIN_SKIPPED",
                    payload={"reason": "entity left the state before the chain finished"},
                )
                return
            self._create_next_chain_run(
                organization_id=organization_id, entity_id=entity_id,
                entity_state=entity_state, config=config,
            )
        except Exception as exc:
            logger.error(
                f"action chain advance failed entity={entity_id} run_id={run_id}: {exc}"
            )
            try:
                emit_chain_event(
                    event_type="ACTION_CHAIN_STOPPED",
                    payload={"reason": f"chain advance error: {exc}"},
                )
            except Exception:
                logger.error(
                    f"failed to emit ACTION_CHAIN_STOPPED entity={entity_id} run_id={run_id}"
                )

    def _create_next_chain_run(
        self,
        *,
        organization_id: str,
        entity_id: str,
        entity_state: Any,
        config: dict[str, Any],
    ) -> None:
        """Look up the next action on the active definition and enqueue its run."""
        next_index = int(config.get("state_action_index")) + 1
        total = int(config.get("state_action_total"))
        chain_id = str(config.get("chain_id") or "")
        origin_state = str(config.get("origin_state") or "")
        machine = self.workflow_service_manager._runtime_machine(
            organization_id, entity_state.machine_name, entity_state
        )
        state_def = next((s for s in machine.definition.states if s.name == origin_state), None)
        actions = state_def.on_state_actions if state_def else []
        if next_index >= len(actions):
            logger.info(
                f"action chain ended: definition changed entity={entity_id} "
                f"state={origin_state} index={next_index}"
            )
            return
        action = actions[next_index]
        next_config: dict[str, Any] = {
            **action.config,
            "outcome_triggers": action.outcome_triggers,
            "failure_policy": action.failure_policy,
            "chain_id": chain_id,
            "state_action_index": next_index,
            "state_action_total": total,
            "origin_state": origin_state,
            "origin_state_version": config.get("origin_state_version"),
            **{k: config.get(k) for k in ("trigger_source", "triggered_by") if config.get(k) is not None},
        }
        next_run_id = self.create_scheduled_action_run(
            organization_id=organization_id,
            entity_id=entity_id,
            action_kind=action.kind,
            config_json=next_config,
            idempotency_key=ActionRunIdempotencyKey.chain_continuation(
                entity_id=entity_id, state=origin_state, chain_id=chain_id, action_index=next_index
            ),
        )
        logger.info(
            f"action chain advanced entity={entity_id} state={origin_state} "
            f"index={next_index}/{total} kind={action.kind} run_id={next_run_id}"
        )

    @staticmethod
    def _compute_retry_delay(base_delay_seconds: int, backoff: str, attempt: int) -> int:
        """Return the retry delay, doubling per attempt when exponential backoff is requested."""
        if base_delay_seconds <= 0:
            return 0
        if backoff != "exponential":
            return base_delay_seconds
        return base_delay_seconds * (2 ** max(0, attempt - 1))

    def _writeback_action_result(
        self,
        *,
        db: Any,
        services: Any,
        organization_id: str,
        entity_id: str,
        entity_type: str,
        current_data: dict[str, Any],
        result_fields: dict[str, ExecutorValue],
        meta: dict[str, Any],
    ) -> None:
        """Apply an executor's output to whichever target the executor declared.

        Routes on `meta`, not on the resolved action config: `meta` is what the
        executor actually produced, while config is only a request. An executor
        that ignores writeback_target leaves meta empty and correctly falls
        through to the entity path rather than being sent to a filing branch
        with no response body to apply.

        Merges an executor's returned fields into the entity's data (no-op when empty).

        A field whose value is a ``{"__table_merge__": {"match", "rows"}}`` instruction
        is merged into the field's *existing* table rows: each built row is matched to
        an existing row by the ``match`` column and only its mapped cells are updated,
        leaving all other rows/cells untouched. Unmatched rows are skipped. Every other
        field is written as-is (full replace, the prior behaviour)."""
        if meta.get(WRITEBACK_TARGET_META_KEY) == CUSTOM_FORM_WRITEBACK_TARGET:
            if self.custom_forms_service_manager is None:
                logger.error(
                    "action requested a custom form write-back but custom_forms is not wired: "
                    "entity=%s",
                    entity_id,
                )
                raise RuntimeError(
                    "action requested a custom form write-back but custom_forms is not wired"
                )
            self.custom_forms_service_manager.apply_connector_data(
                organization_id=organization_id,
                entity_id=entity_id,
                fetched=meta.get(CUSTOM_FORM_RESPONSE_META_KEY),
            )
            return

        # ── Entity field write-back (unchanged) ──────────────────────────────
        if not result_fields:
            # A call that succeeded and wrote nothing is indistinguishable from
            # a working action in the run record, and it is what an unmapped
            # connector looks like — or a filing action still left on the entity
            # target. Say so once, here, rather than leaving it to be traced
            # back from "the data never arrived".
            logger.warning(
                "action wrote nothing: entity=%s target=entity, executor returned no mapped "
                "fields. Check the connector's response mapping.",
                entity_id,
            )
            return

        def _table_field_names(data: dict[str, Any], match_col: str) -> list[str]:
            """Fields whose rows carry the match column.

            Shape alone is not enough: plenty of fields hold a list of dicts
            (history, attachment metadata) and `*` must not write into them.
            The match column is what makes a field one this mapping addresses.
            """
            return [
                name
                for name, value in data.items()
                if isinstance(value, list)
                and any(isinstance(row, dict) and match_col in row for row in value)
            ]

        def _fill_record_rows(
            existing: Any, match_col: str, instruction: dict[str, Any]
        ) -> list[Any]:
            """Deferred lookups: the record's own rows are the grid."""
            rows = existing if isinstance(existing, list) else []
            fill_lookup_columns(
                [row for row in rows if isinstance(row, dict)],
                match_col,
                instruction[TABLE_MERGE_LOOKUPS_KEY],
                instruction.get(TABLE_MERGE_RESPONSE_KEY),
            )
            return rows

        def _merge_incoming_rows(
            existing: Any, match_col: str, instruction: dict[str, Any]
        ) -> list[Any]:
            """Rows built from the response, matched onto the record's own."""
            rows = existing if isinstance(existing, list) else []
            incoming = instruction.get(TABLE_MERGE_ROWS_KEY) or []
            by_key: dict[str, dict[str, Any]] = {}
            for row in rows:
                if isinstance(row, dict):
                    by_key.setdefault(str(row.get(match_col)), row)
            for inc in incoming:
                if not isinstance(inc, dict):
                    continue
                target = by_key.get(str(inc.get(match_col)))
                if target is None:
                    continue  # no matching row — leave the fixed grid untouched
                for column_id, cell in inc.items():
                    if column_id == match_col:
                        continue  # don't overwrite the key we matched on
                    target[column_id] = cell
            return rows

        def _apply_instruction(existing: Any, instruction: dict[str, Any]) -> list[Any]:
            """Route an instruction to the merge its shape calls for."""
            match_col = instruction.get(TABLE_MERGE_MATCH_INSTRUCTION_KEY)
            if not isinstance(match_col, str) or not match_col:
                raise ValidationError("table merge instruction has no match column")
            return (
                _fill_record_rows(existing, match_col, instruction)
                if instruction.get(TABLE_MERGE_LOOKUPS_KEY)
                else _merge_incoming_rows(existing, match_col, instruction)
            )

        merged = dict(current_data or {})
        for field_name, executor_value in result_fields.items():
            value = getattr(executor_value, "value", executor_value)
            if isinstance(value, dict) and TABLE_MERGE_INSTRUCTION_KEY in value:
                instruction = value[TABLE_MERGE_INSTRUCTION_KEY]
                # `*` means every table on this record that this mapping addresses.
                targets = (
                    _table_field_names(
                        merged, str(instruction.get(TABLE_MERGE_MATCH_INSTRUCTION_KEY) or "")
                    )
                    if field_name == TABLE_WILDCARD_FIELD
                    else [field_name]
                )
                for target in targets:
                    merged[target] = _apply_instruction(merged.get(target), instruction)
            else:
                merged[field_name] = value
        services.update_entity_record_data(
            organization_id=organization_id,
            entity_id=entity_id,
            data=merged,
        )

    def _handle_action_failure(
        self,
        *,
        db: Any,
        run_id: str,
        organization_id: str,
        entity_id: str,
        action_kind: str,
        resolved: dict[str, Any],
        error_message: str,
    ) -> None:
        """Apply the configured failure policy for a failed action run."""
        failure_policy = self._normalize_failure_policy(resolved)
        on_failure = str(failure_policy.get("on_failure") or "block").strip().lower()
        advance_chain = partial(
            self._advance_state_action_chain,
            organization_id=organization_id,
            entity_id=entity_id,
            run_id=run_id,
            action_kind=action_kind,
            config=resolved,
        )

        if on_failure == "ignore":
            self.db.mark_action_run_result(
                db,
                run_id=run_id,
                status="succeeded",
                outcome=error_message,
                resolved_config_json=json.dumps(resolved),
            )
            mapped_trigger = str(
                (resolved.get("outcome_triggers") or {}).get("failed") or ""
            ).strip()
            self._emit_action_event(
                organization_id=organization_id,
                entity_id=entity_id,
                event_type="ACTION_COMPLETED",
                run_id=run_id,
                action_kind=action_kind,
                payload={
                    "status": "succeeded",
                    "outcome": error_message,
                    "failure_policy": on_failure,
                },
                chain_config=resolved,
            )
            advance_chain(failed=False)
            if mapped_trigger:
                self._fire_trigger(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    trigger=mapped_trigger,
                )
            return

        if on_failure == "fire_trigger":
            self.db.mark_action_run_failed(db, run_id=run_id, outcome=error_message)
            trigger = str(failure_policy.get("trigger") or "").strip()
            self._emit_action_event(
                organization_id=organization_id,
                entity_id=entity_id,
                event_type="ACTION_FAILED",
                run_id=run_id,
                action_kind=action_kind,
                payload={
                    "error": error_message,
                    "failure_policy": on_failure,
                    "trigger_fired": trigger or None,
                },
                chain_config=resolved,
            )
            if trigger:
                self._fire_trigger(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    trigger=trigger,
                )
            advance_chain(failed=True)
            return

        if on_failure == "alert":
            self.db.mark_action_run_failed(db, run_id=run_id, outcome=error_message)
            trigger = str(failure_policy.get("trigger") or "").strip()
            alert_to = str(failure_policy.get("alert_to") or "").strip()
            self._emit_action_event(
                organization_id=organization_id,
                entity_id=entity_id,
                event_type="ACTION_ALERT",
                run_id=run_id,
                action_kind=action_kind,
                payload={
                    "error": error_message,
                    "failure_policy": on_failure,
                    "trigger_fired": trigger or None,
                    "alert_to": alert_to or None,
                },
            )
            if alert_to and self.mail_service_manager:
                try:
                    values = {
                        "action_kind": html.escape(str(action_kind)),
                        "entity_id": html.escape(str(entity_id)),
                        "error": html.escape(str(error_message)),
                    }
                    template = self.mail_service_manager.get_default_email_template_for_kind(
                        db, organization_id, EMAIL_KIND_ACTION_FAILED
                    )
                    if template:
                        subject = self._render_email_template(template["subject"], values)
                        body_html = self._render_email_template(template["body_html"], values)
                    else:
                        subject = f"Action failed: {action_kind}"
                        body_html = (
                            f"<p>An action in your workflow has failed and requires human intervention.</p>"
                            f"<p><strong>Action:</strong> {action_kind}</p>"
                            f"<p><strong>Entity:</strong> {entity_id}</p>"
                            f"<p><strong>Error:</strong> {error_message}</p>"
                            f"<p>The workflow has been paused. Please review and take action.</p>"
                        )
                    self.mail_service_manager.send_email(
                        db,
                        org_id=organization_id,
                        to=alert_to,
                        subject=subject,
                        body_html=body_html,
                    )
                except Exception as exc:
                    logger.warning(f"alert: failed to send notification email run_id={run_id}: {exc}")
            if trigger:
                self._fire_trigger(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    trigger=trigger,
                )
            advance_chain(failed=True)
            return

        if on_failure == "retry":
            max_attempts = int(failure_policy.get("max_attempts") or 0)
            delay_seconds = int(failure_policy.get("delay_seconds") or 0)
            backoff = str(failure_policy.get("backoff") or "").strip().lower()
            next_attempt = self.db.increment_action_run_attempts(db, run_id)
            if max_attempts > 0 and next_attempt < max_attempts:
                retry_delay = self._compute_retry_delay(delay_seconds, backoff, next_attempt)
                self.db.schedule_action_run_retry(
                    db,
                    run_id=run_id,
                    outcome=error_message,
                    resolved_config_json=json.dumps(resolved),
                    delay_seconds=retry_delay,
                )
                self._emit_action_event(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    event_type="ACTION_RETRY_SCHEDULED",
                    run_id=run_id,
                    action_kind=action_kind,
                    payload={
                        "error": error_message,
                        "attempts": next_attempt,
                        "max_attempts": max_attempts,
                        "delay_seconds": retry_delay,
                    },
                    actor_type="user" if resolved.get("triggered_by") else "system",
                    actor_id=str(resolved.get("triggered_by")) if resolved.get("triggered_by") else None,
                    chain_config=resolved,
                )
                return
            self.db.mark_action_run_failed(db, run_id=run_id, outcome=error_message)
            self._emit_action_event(
                organization_id=organization_id,
                entity_id=entity_id,
                event_type="ACTION_FAILED",
                run_id=run_id,
                action_kind=action_kind,
                payload={
                    "error": error_message,
                    "failure_policy": on_failure,
                    "attempts": next_attempt,
                    "max_attempts": max_attempts,
                },
                chain_config=resolved,
            )
            failed_trigger = str(
                (resolved.get("outcome_triggers") or {}).get("failed") or ""
            ).strip()
            if failed_trigger:
                self._fire_trigger(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    trigger=failed_trigger,
                )
            advance_chain(failed=True)
            return

        self.db.mark_action_run_failed(db, run_id=run_id, outcome=error_message)
        self._emit_action_event(
            organization_id=organization_id,
            entity_id=entity_id,
            event_type="ACTION_FAILED",
            run_id=run_id,
            action_kind=action_kind,
            payload={"error": error_message, "failure_policy": on_failure or "block"},
            chain_config=resolved,
        )
        advance_chain(failed=True)

    def _execute_action_run(
        self,
        run_id: str,
        organization_id: str,
        entity_id: str,
        action_kind: str,
        config_json: object,
    ) -> None:
        """Execute one action run and transition entity on successful outcome mapping."""
        resolved: dict[str, Any] = {}
        config: dict[str, Any] = {}
        with self._db_session() as db:
            try:
                raw_config = config_json
                if isinstance(raw_config, str):
                    raw_config = json.loads(raw_config or "{}")
                config = dict(raw_config or {})
                if not self.db.mark_action_run_running(db, run_id):
                    logger.info("action runs: claim skipped run_id=%s", run_id)
                    return
                self._emit_action_event(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    event_type="ACTION_STARTED",
                    run_id=run_id,
                    action_kind=action_kind,
                    payload={
                        key: config[key]
                        for key in ("trigger_source", "triggered_by", "schedule_id")
                        if config.get(key) is not None
                    },
                    actor_type="user" if config.get("triggered_by") else "system",
                    actor_id=str(config.get("triggered_by")) if config.get("triggered_by") else None,
                    chain_config=config,
                )

                services = self.workflow_service_manager.entities_service_manager
                entity_record = services.get_entity_record(
                    organization_id=organization_id, entity_id=entity_id
                )
                if entity_record is None:
                    logger.warning(
                        "_execute_action_run: entity=%s not found run_id=%s", entity_id, run_id
                    )
                    self._handle_action_failure(
                        db=db,
                        run_id=run_id,
                        organization_id=organization_id,
                        entity_id=entity_id,
                        action_kind=action_kind,
                        resolved=resolved or config,
                        error_message=f"entity '{entity_id}' not found",
                    )
                    return
                entity_data = dict(entity_record.data or {})
                # The entity's own id lives in a DB column, not in `data`, so
                # `$entity.entity_id` (and `$entity.id`) would otherwise resolve
                # to empty. Inject it so body templates can reference it.
                entity_data.setdefault("entity_id", entity_id)
                entity_data.setdefault("id", entity_id)
                resolved = resolve_config(config, entity_data)

                entity_state = self.workflow_service_manager._hydrate_entity_state(
                    organization_id, entity_id
                )
                if entity_state is None and action_kind != "entity.create_and_enroll":
                    logger.warning(
                        "_execute_action_run: entity=%s state not found run_id=%s",
                        entity_id,
                        run_id,
                    )
                    self._handle_action_failure(
                        db=db,
                        run_id=run_id,
                        organization_id=organization_id,
                        entity_id=entity_id,
                        action_kind=action_kind,
                        resolved=resolved or config,
                        error_message=f"entity '{entity_id}' state not found",
                    )
                    return

                entity_type = entity_state.entity_type if entity_state is not None else (
                    services.get_entity_type_name_for_entity(
                        organization_id=organization_id,
                        entity_id=entity_id,
                    ) or "entity"
                )
                current_state = entity_state.current_state if entity_state is not None else "SCHEDULE_ANCHOR"

                fields: dict[str, ExecutorValue] = {}
                for key, value in entity_data.items():
                    fields[key] = ExecutorValue(
                        kind=ValueKind.TEXT, value=_field_text_value(value)
                    )
                for key, value in resolved.items():
                    if key in {"outcome_triggers", "failure_policy"}:
                        continue
                    fields[key] = ExecutorValue(
                        kind=ValueKind.TEXT, value=_field_text_value(value)
                    )

                fields["org_id"] = ExecutorValue(kind=ValueKind.TEXT, value=organization_id)
                fields["entity_id"] = ExecutorValue(kind=ValueKind.TEXT, value=entity_id)
                fields["run_id"] = ExecutorValue(kind=ValueKind.TEXT, value=run_id)
                fields["_raw_config"] = ExecutorValue(kind=ValueKind.TEXT, value=json.dumps(resolved))

                request = ExecutorExecutionRequest(
                    executor_name=action_kind,
                    execution_input=ExecutorInput(
                        entity_id=entity_id,
                        entity_type=entity_type,
                        current_state=current_state,
                        fields=fields,
                        context={},
                    ),
                    binding=ExecutorBinding(
                        executor_name=action_kind,
                        outcome_triggers=dict(resolved.get("outcome_triggers") or {}),
                        config={},
                    ),
                )
                result = self.executor_service_manager.execute_executor(request, db=db)
                outcome = result.result.data.outcome
                if result.result.is_external_wait and result.result.success:
                    self.db.mark_action_run_pending_external(
                        db,
                        run_id=run_id,
                        outcome=str(outcome),
                        resolved_config_json=json.dumps(resolved),
                        timeout_hours=result.result.timeout_hours,
                    )
                    self._emit_action_event(
                        organization_id=organization_id,
                        entity_id=entity_id,
                        event_type="ACTION_WAITING_EXTERNAL",
                        run_id=run_id,
                        action_kind=action_kind,
                        payload={"outcome": str(outcome)},
                        chain_config=resolved,
                    )
                    if result.result.fire_trigger_immediately and result.resolved_trigger:
                        self._fire_trigger(
                            organization_id=organization_id,
                            entity_id=entity_id,
                            trigger=result.resolved_trigger,
                        )
                    return

                if not result.result.success:
                    logger.error(
                        "action executor returned failure run_id=%s action_kind=%s outcome=%s message=%s",
                        run_id,
                        action_kind,
                        outcome,
                        result.result.message,
                    )
                    self._handle_action_failure(
                        db=db,
                        run_id=run_id,
                        organization_id=organization_id,
                        entity_id=entity_id,
                        action_kind=action_kind,
                        resolved=resolved or config,
                        error_message=str(outcome),
                    )
                    return

                # Call already succeeded — a writeback error must not trigger a retry (re-call).
                try:
                    self._writeback_action_result(
                        db=db,
                        services=services,
                        organization_id=organization_id,
                        entity_id=entity_id,
                        entity_type=entity_type,
                        current_data=entity_data,
                        result_fields=result.result.data.fields,
                        meta=dict(result.result.data.meta or {}),
                    )
                except Exception as writeback_exc:
                    logger.error(
                        f"entity writeback failed after successful action run_id={run_id} entity={entity_id}: {writeback_exc}"
                    )
                    self._emit_action_event(
                        organization_id=organization_id,
                        entity_id=entity_id,
                        event_type="ACTION_WRITEBACK_FAILED",
                        run_id=run_id,
                        action_kind=action_kind,
                        payload={"error": str(writeback_exc)},
                        chain_config=resolved,
                    )

                self.db.mark_action_run_result(
                    db,
                    run_id=run_id,
                    status="succeeded",
                    outcome=str(outcome),
                    resolved_config_json=json.dumps(resolved),
                )
                completed_payload: dict[str, Any] = {
                    "status": "succeeded",
                    "outcome": str(outcome),
                    "trigger_fired": result.resolved_trigger,
                }
                # The executor's own words for what happened. Without this the
                # timeline can only say "Action completed", which reads the same
                # whether a record was assigned or the action declined to assign
                # anyone. Omitted when the executor set no message.
                if result.result.message:
                    completed_payload["message"] = result.result.message
                # The run completed, but the executor declined to do the thing it
                # exists to do. Presentation only — the timeline shows it in the
                # failure style instead of as a green success. The run stays
                # `succeeded`, so outcome routing and the failure policy are
                # untouched. Opt-in: only executors that set it are affected.
                if result.result.data.meta.get("refused"):
                    completed_payload["refused"] = True
                self._emit_action_event(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    event_type="ACTION_COMPLETED",
                    run_id=run_id,
                    action_kind=action_kind,
                    payload=completed_payload,
                    chain_config=resolved,
                )

                # Mid-chain actions never have triggers by design — no event/warning.
                if result.resolved_trigger is None and not self._is_mid_chain(resolved):
                    logger.warning(
                        "action completed with no trigger mapping run_id=%s action_kind=%s outcome=%s",
                        run_id,
                        action_kind,
                        outcome,
                    )
                    self._emit_action_event(
                        organization_id=organization_id,
                        entity_id=entity_id,
                        event_type="ACTION_NO_TRIGGER",
                        run_id=run_id,
                        action_kind=action_kind,
                        payload={"outcome": str(outcome)},
                    )

                self._advance_state_action_chain(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    run_id=run_id,
                    action_kind=action_kind,
                    config=resolved,
                    failed=False,
                )

                if result.resolved_trigger:
                    self._fire_trigger(
                        organization_id=organization_id,
                        entity_id=entity_id,
                        trigger=result.resolved_trigger,
                    )
            except Exception as exc:
                logger.error(f"action run execution failed run_id={run_id} error={exc}")
                self._handle_action_failure(
                    db=db,
                    run_id=run_id,
                    organization_id=organization_id,
                    entity_id=entity_id,
                    action_kind=action_kind,
                    resolved=resolved or config,
                    error_message=str(exc),
                )

    def _fire_trigger(self, organization_id: str, entity_id: str, trigger: str) -> None:
        """Fire workflow transition in system context."""
        if self.workflow_service_manager is None:
            return
        self.workflow_service_manager.execute_transition_system(
            organization_id=organization_id,
            entity_id=entity_id,
            trigger=trigger,
        )

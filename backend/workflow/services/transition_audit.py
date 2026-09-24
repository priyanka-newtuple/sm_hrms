"""Record what happened to a transition attempt, and replay a successful one.

Every transition attempt — succeeded, blocked or conflicted — leaves one row in `audit_events`.
That row is a stored contract: rows written months ago are served by the same read endpoint as
rows written today, so its columns and metadata keys must not drift.

Writing it is best-effort by design. A transition that really happened must not be reported as
failed because its audit row could not be written, so emission never raises. The reverse is also
true: a failure is never reported as success, which is what the replay guards protect.

Its only I/O is the audit store, plus an optional user lookup to put a display name on the row.
No evaluation, no authorization, no state mutation, and nothing to do with the legacy
`transition_attempts` table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from common.enums import AuditMetadataType
from common.logger import logger
from workflow.models.interface import (
    SYSTEM_ACTOR_NAME,
    SYSTEM_ACTOR_ROLE,
    TRANSITION_AUDIT_SOURCE,
    TRANSITION_STATUS_TO_AUDIT_EVENT_TYPE,
    ActorType,
    TransitionAuditEventType,
    TransitionAuditMetadataKey,
)
from workflow.models.response import TransitionExecutionResponse

if TYPE_CHECKING:
    from audit.db_models import AuditEventsModelService
    from user.manager import UserServiceManager
    from workflow.models.interface import EntityState, Transition


class TransitionAuditService:
    """Owns the transition outcome record and the successful-replay contract."""

    def __init__(
        self,
        audit_events_service: AuditEventsModelService,
        user_service_manager: UserServiceManager | None,
    ) -> None:
        """Store the audit writer and the optional user lookup used for actor display names."""
        self.audit_events_service = audit_events_service
        self.user_service_manager = user_service_manager

    # ── replay ───────────────────────────────────────────────────────────────

    def find_successful_replay(
        self, organization_id: str, entity_id: str, idempotency_key: str
    ) -> TransitionExecutionResponse | None:
        """Rebuild a previous successful response for a repeated idempotency key.

        Declines unless the stored record is for this entity, records a success, and carries the
        outputs to rebuild from. Each guard matters on its own: without the entity check a key
        could replay another record's result, and without the event-type check a blocked attempt
        could be handed back to the caller as a success.
        """
        record = self.audit_events_service.find_by_idempotency_key(
            organization_id=organization_id,
            metadata_type=AuditMetadataType.TRANSITION,
            idempotency_key=idempotency_key,
        )
        if record is None or record.entity_id != entity_id:
            return None
        if record.event_type != TransitionAuditEventType.SUCCEEDED:
            return None
        outputs = record.metadata.get(TransitionAuditMetadataKey.OUTPUTS)
        if not outputs:
            return None
        return TransitionExecutionResponse.model_validate({**outputs, "idempotent": True})

    # ── outcome recording ────────────────────────────────────────────────────

    def emit_outcome(
        self,
        *,
        organization_id: str,
        entity_state: EntityState,
        transition: Transition,
        workflow_id: str | None,
        machine_version: int,
        actor_id: str | None,
        idempotency_key: str | None,
        is_system: bool,
        status: str,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        guard_evaluations: dict[str, Any] | None = None,
        blocked_reasons: list[str] | None = None,
    ) -> None:
        """Record one transition outcome. Never raises.

        The audit store swallows its own write failures; this catches whatever still escapes,
        so a broken audit path cannot turn a completed transition into a reported failure.
        """
        try:
            self._write_row(
                organization_id=organization_id,
                entity_state=entity_state,
                transition=transition,
                workflow_id=workflow_id,
                machine_version=machine_version,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                is_system=is_system,
                status=status,
                inputs=inputs,
                outputs=outputs,
                guard_evaluations=guard_evaluations,
                blocked_reasons=blocked_reasons,
            )
        except Exception as exc:
            logger.warning(
                "transition audit emit failed",
                extra={
                    "organization_id": organization_id,
                    "entity_id": entity_state.entity_id,
                    "status": status,
                    "trigger": transition.trigger,
                    "error": str(exc),
                },
                exc_info=True,
            )

    def _write_row(
        self,
        *,
        organization_id: str,
        entity_state: EntityState,
        transition: Transition,
        workflow_id: str | None,
        machine_version: int,
        actor_id: str | None,
        idempotency_key: str | None,
        is_system: bool,
        status: str,
        inputs: dict[str, Any] | None,
        outputs: dict[str, Any] | None,
        guard_evaluations: dict[str, Any] | None,
        blocked_reasons: list[str] | None,
    ) -> None:
        """Write the audit row. Raises; `emit_outcome` owns the best-effort guarantee."""
        actor_name, actor_role = self.resolve_actor(actor_id, is_system)
        self.audit_events_service.emit_audit_event(
            organization_id=organization_id,
            metadata_type=AuditMetadataType.TRANSITION,
            event_type=TRANSITION_STATUS_TO_AUDIT_EVENT_TYPE[status],
            actor_type=ActorType.SYSTEM if is_system else ActorType.USER,
            entity_type=entity_state.entity_type or None,
            entity_id=entity_state.entity_id,
            user_id=actor_id,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            source=TRANSITION_AUDIT_SOURCE,
            before_state=entity_state.current_state,
            after_state=transition.to_state,
            event_metadata=self._build_metadata(
                workflow_id=workflow_id,
                transition=transition,
                status=status,
                inputs=inputs,
                outputs=outputs,
                guard_evaluations=guard_evaluations,
                entity_state=entity_state,
                machine_version=machine_version,
                blocked_reasons=blocked_reasons,
            ),
        )

    def resolve_actor(
        self, actor_id: str | None, is_system: bool
    ) -> tuple[str | None, str | None]:
        """Return `(actor_name, actor_role)` for the audit row.

        A system attempt is labelled System regardless of which user triggered it; `actor_id` is
        still recorded separately, so who initiated it is not lost. A failed lookup yields no
        name rather than blocking the record — the ids on the row remain enough to identify the
        actor later.
        """
        if is_system or actor_id is None:
            return (SYSTEM_ACTOR_NAME, SYSTEM_ACTOR_ROLE)
        if self.user_service_manager is not None:
            try:
                actor_name, actor_role = self.user_service_manager.get_actor_display_info(
                    {"user_id": actor_id, "actor_type": ActorType.USER.value}
                )
                return (actor_name, actor_role)
            except Exception as exc:
                logger.warning(
                    "actor display info lookup failed for transition attempt",
                    extra={"actor_id": actor_id, "error": str(exc)},
                    exc_info=True,
                )
        return (None, None)

    @staticmethod
    def _build_metadata(
        *,
        workflow_id: str | None,
        transition: Transition,
        status: str,
        inputs: dict[str, Any] | None,
        outputs: dict[str, Any] | None,
        guard_evaluations: dict[str, Any] | None,
        entity_state: EntityState,
        machine_version: int,
        blocked_reasons: list[str] | None,
    ) -> dict[str, Any]:
        """Assemble the stored `metadata` payload.

        Every key is written on every outcome, including the ones that are None, because readers
        index into the stored shape. `blocked_reasons` is the one exception: it appears only
        when there is something to report.
        """
        metadata: dict[str, Any] = {
            TransitionAuditMetadataKey.WORKFLOW_ID: workflow_id,
            TransitionAuditMetadataKey.TRIGGER: transition.trigger,
            TransitionAuditMetadataKey.STATUS: status,
            TransitionAuditMetadataKey.FAILURE_CODE: None,
            TransitionAuditMetadataKey.INPUTS: inputs,
            TransitionAuditMetadataKey.OUTPUTS: outputs,
            TransitionAuditMetadataKey.GUARD_EVALUATIONS: guard_evaluations,
            TransitionAuditMetadataKey.MACHINE_NAME: entity_state.machine_name,
            TransitionAuditMetadataKey.MACHINE_VERSION: machine_version,
        }
        blocked_reasons_list = list(blocked_reasons or [])
        if blocked_reasons_list:
            metadata[TransitionAuditMetadataKey.BLOCKED_REASONS] = blocked_reasons_list
        return metadata

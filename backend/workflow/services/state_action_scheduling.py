"""Schedule what happens when a record arrives in a workflow state.

A state can carry `on_state_actions` — work a background worker performs once the record gets
there — and `sla_seconds`, a deadline that raises a signal if the record is still sitting there
when it passes. This service writes those instructions; it never executes them.

Two rules shape everything here:

**Scheduling can never fail the caller.** By the time this runs, the state change is already
committed. Raising would report failure for a record that has moved, and would skip the
succeeded audit event written afterwards, leaving the move with no audit trail. So each step is
logged and stepped over, and the steps are independent — one failing must not cancel the other.

**The instruction is a contract.** A worker in another process reads `config_json` and the
idempotency key. Their shapes are relied on outside this module, so they are built in one place
here rather than assembled at each call site.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from background_jobs.models.interface import ActionRunIdempotencyKey
from common.logger import logger
from exceptions import ConflictError, ValidationError
from workflow.models.interface import (
    SLA_BREACH_NOTIFY_BODY,
    SLA_BREACH_NOTIFY_RECIPIENT,
    SLA_BREACH_NOTIFY_TITLE,
    SLA_BREACH_SIGNAL_TYPE,
    SLA_BREACH_STEP_TYPE,
    SLA_SIGNAL_ACTION_KIND,
    StateActionConfigKey,
)

if TYPE_CHECKING:
    from workflow.db_models import WorkflowModelService
    from workflow.models.interface import State, StateAction, StateMachineDefinition


class StateActionSchedulingService:
    """Owns state-entry action scheduling, SLA signals, and manual reruns."""

    def __init__(self, workflow_db: WorkflowModelService) -> None:
        """Store the workflow persistence adapter that records and queries action runs."""
        self.workflow_db = workflow_db

    # ── deadlines ────────────────────────────────────────────────────────────

    @staticmethod
    def calculate_sla_due(
        transitioned_at: datetime, sla_seconds: int | None
    ) -> datetime | None:
        """The deadline for the destination state, or None when it has no SLA."""
        if sla_seconds is None:
            return None
        return transitioned_at + timedelta(seconds=sla_seconds)

    # ── arriving in a state ──────────────────────────────────────────────────

    def apply_entry_effects(
        self,
        *,
        organization_id: str,
        entity_id: str,
        state: str,
        machine_definition: StateMachineDefinition,
        entry_key: str,
        state_version: int,
        entered_at: datetime,
        workflow_id: str | None,
    ) -> None:
        """Schedule the state's first action and its SLA signal. Never raises.

        `entry_key` distinguishes what caused the arrival — a transition key, or the enrollment
        sentinel — and becomes part of the action's idempotency key.
        """
        self._schedule_entry_action(
            organization_id=organization_id,
            entity_id=entity_id,
            state=state,
            machine_definition=machine_definition,
            entry_key=entry_key,
            state_version=state_version,
        )
        self._schedule_sla_signal(
            organization_id=organization_id,
            entity_id=entity_id,
            state=state,
            machine_definition=machine_definition,
            entered_at=entered_at,
            workflow_id=workflow_id,
        )

    def _schedule_entry_action(
        self,
        *,
        organization_id: str,
        entity_id: str,
        state: str,
        machine_definition: StateMachineDefinition,
        entry_key: str,
        state_version: int,
    ) -> None:
        """Schedule the state's first action, stepping over a failure.

        A `ConflictError` is not a failure: another arrival won the race and the row already
        exists, which is the outcome wanted. Anything else means a configured action will
        silently never run, so it is logged as an error.
        """
        context = {
            "organization_id": organization_id,
            "entity_id": entity_id,
            "state": state,
            "state_version": state_version,
        }
        try:
            self.create_entry_action(
                organization_id,
                entity_id,
                state,
                machine_definition,
                entry_key,
                state_version,
            )
        except ConflictError:
            logger.info(
                "state entry action already scheduled by a concurrent arrival", extra=context
            )
        except Exception as exc:
            logger.error(
                "state entry action scheduling failed; the transition still stands: %s",
                exc,
                extra={**context, "entry_key": entry_key},
                exc_info=True,
            )

    def _schedule_sla_signal(
        self,
        *,
        organization_id: str,
        entity_id: str,
        state: str,
        machine_definition: StateMachineDefinition,
        entered_at: datetime,
        workflow_id: str | None,
    ) -> None:
        """Schedule the state's SLA breach signal, stepping over a failure."""
        try:
            self._replace_sla_signal(
                organization_id=organization_id,
                entity_id=entity_id,
                state=state,
                machine_definition=machine_definition,
                entered_at=entered_at,
                workflow_id=workflow_id,
            )
        except Exception as exc:
            logger.error(
                "state SLA signal scheduling failed; the transition still stands: %s",
                exc,
                extra={
                    "organization_id": organization_id,
                    "entity_id": entity_id,
                    "state": state,
                    "workflow_id": workflow_id,
                },
                exc_info=True,
            )

    def _replace_sla_signal(
        self,
        *,
        organization_id: str,
        entity_id: str,
        state: str,
        machine_definition: StateMachineDefinition,
        entered_at: datetime,
        workflow_id: str | None,
    ) -> None:
        """Retire the previous SLA signal and schedule one for the state just entered.

        The clock starts on arrival, so the pending signal is always cancelled first: the record
        has left wherever that deadline applied to. A state without an SLA simply leaves nothing
        scheduled, which is how leaving a timed state clears its deadline.
        """
        self.workflow_db.cancel_pending_signal(
            entity_id=entity_id, organization_id=organization_id
        )
        sla_seconds = self._state_sla_seconds(machine_definition, state)
        if not sla_seconds:
            return
        self._create_sla_signal_run(
            organization_id=organization_id,
            entity_id=entity_id,
            state=state,
            entered_at=entered_at,
            sla_seconds=sla_seconds,
            workflow_id=workflow_id,
        )

    def _state_sla_seconds(
        self, machine_definition: StateMachineDefinition, state: str
    ) -> int | None:
        """The state's SLA in seconds, or None when it has none or a non-positive one."""
        state_def = self._state(machine_definition, state)
        sla_seconds = getattr(state_def, "sla_seconds", None) if state_def else None
        return sla_seconds if sla_seconds and sla_seconds > 0 else None

    def _create_sla_signal_run(
        self,
        *,
        organization_id: str,
        entity_id: str,
        state: str,
        entered_at: datetime,
        sla_seconds: int,
        workflow_id: str | None,
    ) -> None:
        """Schedule the breach signal for the moment the deadline passes.

        Keyed on the arrival time, so re-entering the same state later schedules a new signal
        rather than colliding with the old one.
        """
        self.workflow_db.create_action_run(
            run_id=str(uuid4()),
            organization_id=organization_id,
            entity_id=entity_id,
            definition_id=None,
            action_kind=SLA_SIGNAL_ACTION_KIND,
            scheduled_at=entered_at + timedelta(seconds=sla_seconds),
            idempotency_key=ActionRunIdempotencyKey.sla_breach_signal(
                entity_id=entity_id, state=state, entered_at_epoch=int(entered_at.timestamp())
            ),
            config_json=json.dumps(
                {
                    "signal_type": SLA_BREACH_SIGNAL_TYPE,
                    "steps": [
                        {
                            "type": SLA_BREACH_STEP_TYPE,
                            "recipient": SLA_BREACH_NOTIFY_RECIPIENT,
                            "notification_type": SLA_BREACH_SIGNAL_TYPE,
                            "title": SLA_BREACH_NOTIFY_TITLE,
                            "body": SLA_BREACH_NOTIFY_BODY.format(state=state),
                            "workflow_id": workflow_id,
                        },
                    ],
                }
            ),
        )

    def create_entry_action(
        self,
        organization_id: str,
        entity_id: str,
        to_state: str,
        machine_definition: StateMachineDefinition,
        entry_key: str,
        state_version: int,
    ) -> None:
        """Create the first action_run in the destination state's chain, if it has one.

        Raises on failure; `_schedule_entry_action` owns the decision to step over that. Only
        the first action is created — the worker creates the next as each one finishes.
        """
        state_def = self._state(machine_definition, to_state)
        if state_def is None or not state_def.on_state_actions:
            return
        actions = state_def.on_state_actions
        action = actions[0]
        idempotency_key = ActionRunIdempotencyKey.state_entry(
            entity_id=entity_id, state=to_state,
            transition_key=entry_key, state_version=state_version,
        )
        if self.workflow_db.action_run_exists_by_idempotency_key(
            organization_id=organization_id, idempotency_key=idempotency_key
        ):
            return

        run_id = str(uuid4())
        config = self.action_config(
            action=action,
            action_total=len(actions),
            run_id=run_id,
            state=to_state,
            state_version=state_version,
        )
        self.workflow_db.create_action_run(
            run_id=run_id,
            organization_id=organization_id,
            entity_id=entity_id,
            definition_id=None,
            action_kind=action.kind,
            config_json=json.dumps(config),
            idempotency_key=idempotency_key,
        )
        logger.info(
            "state entry action scheduled",
            extra={"entity_id": entity_id, "state": to_state, "action_kind": action.kind},
        )

    # ── manual rerun ─────────────────────────────────────────────────────────

    def rerun_actions_for_state(
        self,
        machine_definition: StateMachineDefinition,
        state: str,
        *,
        entity_id: str,
        machine_name: str,
    ) -> list[StateAction]:
        """The action chain a manual rerun would replay, or raise if there is none.

        Whether a state has anything to re-run is a scheduling question, so it is answered here
        rather than by the caller re-walking the definition. The caller still owns resolving
        which entity and which workflow version it is asking about.
        """
        state_def = self._state(machine_definition, state)
        if state_def is None or not state_def.on_state_actions:
            logger.warning(
                "action rerun rejected: the state has no configured action",
                extra={"entity_id": entity_id, "state": state, "machine_name": machine_name},
            )
            raise ValidationError(f"state '{state}' has no action configured to re-run")
        return state_def.on_state_actions

    def ensure_rerun_allowed(self, organization_id: str, entity_id: str, state: str) -> None:
        """Raise `ConflictError` when a run for this state is already pending or running.

        Two runs of the same state's action must not overlap, so a rerun is only available once
        the previous one has finished.
        """
        if self.workflow_db.has_in_flight_state_action_run(
            organization_id=organization_id, entity_id=entity_id, state=state
        ):
            logger.warning(
                "action rerun rejected: a run is already in flight",
                extra={
                    "organization_id": organization_id,
                    "entity_id": entity_id,
                    "state": state,
                },
            )
            raise ConflictError(
                f"an action for state '{state}' is already pending or running"
            )

    def enqueue_rerun(
        self,
        *,
        organization_id: str,
        entity_id: str,
        current_state: str,
        state_version: int,
        action: StateAction,
        action_index: int,
        action_total: int,
        isolated: bool,
        actor_id: str | None,
    ) -> str:
        """Create and queue a fresh run for a manual rerun, returning its run id.

        A rerun is deliberately a new attempt rather than a replay, so its idempotency key
        carries the new run id instead of the arrival that first scheduled the action.
        """
        run_id = str(uuid4())
        config = self._rerun_config(
            action=action, action_total=action_total, run_id=run_id, state=current_state,
            state_version=state_version, action_index=action_index, isolated=isolated,
            actor_id=actor_id,
        )
        self.workflow_db.create_action_run(
            run_id=run_id,
            organization_id=organization_id,
            entity_id=entity_id,
            definition_id=None,
            action_kind=action.kind,
            config_json=json.dumps(config),
            idempotency_key=ActionRunIdempotencyKey.manual_rerun(
                entity_id=entity_id, state=current_state, run_id=run_id
            ),
        )
        logger.info(
            "action rerun requested",
            extra={
                "organization_id": organization_id,
                "entity_id": entity_id,
                "state": current_state,
                "action_kind": action.kind,
                "run_id": run_id,
                "actor_id": actor_id,
            },
        )
        return run_id

    # ── the instruction a worker reads ───────────────────────────────────────

    def _rerun_config(
        self,
        *,
        action: StateAction,
        action_total: int,
        run_id: str,
        state: str,
        state_version: int,
        action_index: int,
        isolated: bool,
        actor_id: str | None,
    ) -> dict[str, Any]:
        """A rerun's config: the standard one, plus who asked for it and why."""
        config = self.action_config(
            action=action,
            action_total=action_total,
            run_id=run_id,
            state=state,
            state_version=state_version,
            action_index=action_index,
            isolated=isolated,
        )
        config[StateActionConfigKey.TRIGGER_SOURCE] = StateActionConfigKey.MANUAL_RERUN_SOURCE
        if actor_id:
            config[StateActionConfigKey.TRIGGERED_BY] = actor_id
        return config


    def action_config(
        self,
        *,
        action: StateAction,
        action_total: int,
        run_id: str,
        state: str,
        state_version: int,
        action_index: int = 0,
        isolated: bool = False,
    ) -> dict[str, Any]:
        """The config a worker reads: the action's own settings plus its place in the chain."""
        return {
            **action.config,
            StateActionConfigKey.OUTCOME_TRIGGERS: action.outcome_triggers,
            StateActionConfigKey.FAILURE_POLICY: action.failure_policy,
            **self._chain_context(
                run_id=run_id,
                total=action_total,
                state=state,
                state_version=state_version,
                index=action_index,
                isolated=isolated,
            ),
        }

    @staticmethod
    def _chain_context(
        *,
        run_id: str,
        total: int,
        state: str,
        state_version: int,
        index: int = 0,
        isolated: bool = False,
    ) -> dict[str, Any]:
        """Where this run sits in its state's action chain.

        Read by `background_jobs` to decide what to run next, so these keys are a cross-module
        contract, not internal bookkeeping.
        """
        return {
            StateActionConfigKey.CHAIN_ID: run_id,
            StateActionConfigKey.STATE_ACTION_INDEX: index,
            StateActionConfigKey.STATE_ACTION_TOTAL: total,
            StateActionConfigKey.ISOLATED_RERUN: isolated,
            StateActionConfigKey.ORIGIN_STATE: state,
            StateActionConfigKey.ORIGIN_STATE_VERSION: state_version,
        }

    @staticmethod
    def _state(machine_definition: StateMachineDefinition, name: str) -> State | None:
        """The named state in this definition, or None when it has no such state."""
        return next(
            (state for state in machine_definition.states if state.name == name), None
        )

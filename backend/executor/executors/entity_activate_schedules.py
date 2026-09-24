"""Workflow action that subscribes the current entity to recurring schedules."""

from __future__ import annotations

import json
from typing import Any

from common.auth import build_system_actor
from executor.executors.base import fail, get_field
from executor.models.interface import (
    BaseExecutor,
    ExecutorData,
    ExecutorDefinition,
    ExecutorInput,
    ExecutorResponse,
)
from schedules.models.interface import ScheduleActivationPolicy


class EntityActivateSchedulesExecutor(BaseExecutor):
    """Activate explicitly configured schedules for the entity entering a state."""

    run_once = False
    action_name = "entity.activate_schedules"
    action_description = "Subscribe the current entity to selected recurring schedules."
    success_outcome = "activated"
    success_message = "Recurring schedules activated"
    empty_outcome: str | None = None
    empty_message: str | None = None

    def __init__(self, **_: Any) -> None:
        self.schedules_service: Any = None

    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name=self.action_name,
            description=self.action_description,
            supported_outcomes=[self.success_outcome, "failed"],
        )

    def bind_service(self, schedules_service: Any) -> None:
        self.schedules_service = schedules_service

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        if self.schedules_service is None:
            return fail("schedules service is not configured")
        try:
            config = json.loads(get_field(input_payload.fields, "_raw_config") or "{}")
            organization_id = str(
                config.get("org_id") or get_field(input_payload.fields, "org_id") or ""
            )
            schedule_ids = config.get("schedule_ids")
            if not isinstance(schedule_ids, list):
                return fail("schedule_ids must be a list")
            policy = ScheduleActivationPolicy(
                str(config.get("activation_policy") or ScheduleActivationPolicy.CURRENT_PERIOD)
            )
            result = self.schedules_service.activate_schedules_for_actor(
                build_system_actor(organization_id, source="workflow_action"),
                anchor_entity_id=input_payload.entity_id,
                schedule_ids=[str(item) for item in schedule_ids],
                policy=policy,
                run_once=self.run_once,
            )
            outcome = self.success_outcome
            message = self.success_message
            if self.empty_outcome and not result.get("activated"):
                outcome = (
                    self.empty_outcome
                    if result.get("already_active_schedule_ids")
                    else "skipped"
                )
                message = self.empty_message or self.success_message
            return ExecutorResponse(
                success=True,
                message=message,
                data=ExecutorData(outcome=outcome, fields={}, meta=result),
            )
        except Exception as exc:
            return fail(str(exc))


class EntityRunSchedulesOnceExecutor(EntityActivateSchedulesExecutor):
    """Queue one configured occurrence batch for the entity entering a state."""

    run_once = True
    action_name = "entity.run_schedules_once"
    action_description = "Run selected automations once for the current entity."
    success_outcome = "queued"
    success_message = "Automation batch queued"
    empty_outcome = "already_invoked"
    empty_message = "Automation batch was already invoked"

    @property
    def definition(self) -> ExecutorDefinition:
        definition = super().definition
        definition.supported_outcomes.extend(["already_invoked", "skipped"])
        return definition

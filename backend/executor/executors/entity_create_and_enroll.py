"""Executor that creates a related entity and enrolls it in a workflow."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from common.auth import build_system_actor
from exceptions import ConflictError
from executor.executors.base import fail, get_field
from executor.models.interface import BaseExecutor, ExecutorData, ExecutorDefinition, ExecutorInput, ExecutorResponse
from entities.models.request import EntityRecordCreateRequest


class EntityCreateAndEnrollExecutor(BaseExecutor):
    """Create one scheduled entity, with retry-safe create/enroll behavior."""

    def __init__(self, **_: Any) -> None:
        self.entities_service: Any = None
        self.workflow_service: Any = None
        self.schedules_service: Any = None

    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="entity.create_and_enroll",
            description="Create an entity related to an anchor and enroll it in a workflow.",
            supported_outcomes=["created", "cancelled", "failed"],
        )

    def bind_services(self, entities_service: Any, workflow_service: Any) -> None:
        self.entities_service = entities_service
        self.workflow_service = workflow_service

    def bind_schedules_service(self, schedules_service: Any) -> None:
        self.schedules_service = schedules_service

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        if self.entities_service is None or self.workflow_service is None:
            return fail("entity/workflow services are not configured")
        try:
            config = json.loads(get_field(input_payload.fields, "_raw_config") or "{}")
            organization_id = str(config.get("org_id") or get_field(input_payload.fields, "org_id") or "")
            entity_type_id = str(config.get("target_entity_type_id") or "")
            machine_name = str(config.get("machine_name") or "")
            anchor_entity_id = str(config.get("anchor_entity_id") or input_payload.entity_id)
            schedule_id = str(config.get("schedule_id") or "")
            schedule_target_id = str(config.get("schedule_target_id") or "")
            if self.schedules_service is None:
                return fail("schedules service is not configured")
            if not self.schedules_service.is_occurrence_active(
                organization_id, schedule_id, schedule_target_id
            ):
                return ExecutorResponse(
                    success=True,
                    message="Scheduled occurrence was cancelled",
                    data=ExecutorData(outcome="cancelled", fields={}, meta={}),
                )
            entity_data = dict(config.get("entity_data") or {})
            identifier = str(entity_data.get("identifier") or "")
            actor = build_system_actor(organization_id, source="scheduler")

            entity = next(
                (
                    item
                    for item in self.entities_service.list_entity_records(
                        organization_id=organization_id,
                        entity_type_id=entity_type_id,
                    )
                    if str((item.data or {}).get("identifier") or "") == identifier
                ),
                None,
            )
            if entity is None:
                entity = self.entities_service.create_entity_record_for_actor(
                    actor,
                    EntityRecordCreateRequest(
                        organization_id=organization_id,
                        entity_type_id=entity_type_id,
                        data=entity_data,
                        owner_id=config.get("owner_id") or None,
                        assignee_id=config.get("assignee_id") or None,
                        due_date=date.fromisoformat(str(config["due_date"])),
                        source_entity_ids=[anchor_entity_id],
                    ),
                )
            try:
                self.workflow_service.enroll_entity_for_actor(actor, machine_name, entity.entity_id)
            except ConflictError:
                pass
            if config.get("complete_after_run") is True:
                self.schedules_service.complete_once_occurrence(
                    organization_id,
                    schedule_id,
                    schedule_target_id,
                )
            return ExecutorResponse(
                success=True,
                message="Scheduled entity created and enrolled",
                data=ExecutorData(
                    outcome="created",
                    fields={},
                    meta={"created_entity_id": entity.entity_id, "schedule_id": schedule_id},
                ),
            )
        except Exception as exc:
            return fail(str(exc))

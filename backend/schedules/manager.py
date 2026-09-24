"""Business orchestration for recurring entity schedules."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from common.auth import actor_str
from common.enums import AuditMetadataType, ModuleStatus
from common.logger import logger
from exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from schedules.db_models import SchedulesModelService
from schedules.models.interface import (
    RecurrenceRule,
    ScheduleActivationPolicy,
    ScheduleCondition,
    ScheduleConditionOperator,
    ScheduleFrequency,
    ScheduleRecord,
    ScheduleTargetRecord,
    ScheduleTargetScope,
)
from schedules.models.request import (
    ScheduleCreateRequest,
    ScheduleRunNowRequest,
    ScheduleTargetCreateRequest,
    ScheduleUpdateRequest,
)
from schedules.models.response import (
    ScheduleListResponse,
    SchedulePreviewItem,
    SchedulePreviewResponse,
    ScheduleRunNowResponse,
    ScheduleRunPreviewItem,
    ScheduleRunPreviewResponse,
    ScheduleTargetListResponse,
    SchedulesStatusResponse,
)


def _clamped_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_due_date(rule: RecurrenceRule, on_or_after: date) -> date:
    """Return the first recurrence date on or after ``on_or_after``."""
    if rule.frequency == ScheduleFrequency.ONCE:
        if rule.occurs_on is not None and rule.occurs_on >= on_or_after:
            return rule.occurs_on
        raise ValidationError("one-time schedule has no remaining occurrence")
    months = (
        list(range(1, 13))
        if rule.frequency == ScheduleFrequency.MONTHLY
        else list(rule.months)
    )
    for year in range(on_or_after.year, on_or_after.year + 20):
        for month in months:
            candidate = _clamped_date(year, month, rule.day_of_month or 1)
            if candidate >= on_or_after:
                return candidate
    raise ValidationError("unable to calculate the next schedule occurrence")


def following_due_date(rule: RecurrenceRule, current: date) -> date:
    if rule.frequency == ScheduleFrequency.ONCE:
        raise ValidationError("one-time schedule has no following occurrence")
    return next_due_date(rule, current + timedelta(days=1))


def activation_due_date(
    rule: RecurrenceRule,
    activated_on: date,
    policy: ScheduleActivationPolicy,
) -> date:
    """Choose the first occurrence without backfilling earlier periods."""
    if policy == ScheduleActivationPolicy.NEXT_OCCURRENCE:
        return next_due_date(rule, activated_on)
    if rule.frequency == ScheduleFrequency.ONCE:
        return next_due_date(rule, activated_on)
    if rule.frequency == ScheduleFrequency.MONTHLY:
        period_start = activated_on.replace(day=1)
    elif rule.frequency == ScheduleFrequency.QUARTERLY:
        quarter_month = ((activated_on.month - 1) // 3) * 3 + 1
        period_start = date(activated_on.year, quarter_month, 1)
    else:
        period_start = date(activated_on.year, 1, 1)
    return next_due_date(rule, period_start)


def condition_matches(condition: ScheduleCondition, data: dict[str, Any]) -> bool:
    value = data.get(condition.field)
    operator = condition.operator
    if operator == ScheduleConditionOperator.EXISTS:
        return value is not None and value != ""
    if operator == ScheduleConditionOperator.NOT_EXISTS:
        return value is None or value == ""
    if operator == ScheduleConditionOperator.EQUALS:
        return value == condition.value
    if operator == ScheduleConditionOperator.NOT_EQUALS:
        return value != condition.value
    if operator == ScheduleConditionOperator.IN:
        return value in condition.value
    if operator == ScheduleConditionOperator.NOT_IN:
        return value not in condition.value
    return False


class _TemplateValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


class SchedulesServiceManager:
    """Own schedule definitions, targets, recurrence, and action-run creation."""

    def __init__(
        self,
        db: SchedulesModelService,
        *,
        entities_service_manager: Any,
        workflow_service_manager: Any,
        background_jobs_service_manager: Any,
        audit_events_service: Any = None,
    ) -> None:
        self.db = db
        self.entities = entities_service_manager
        self.workflow = workflow_service_manager
        self.background_jobs = background_jobs_service_manager
        self.audit_events = audit_events_service
        self.module_name = "schedules"
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> SchedulesStatusResponse:
        return SchedulesStatusResponse(module=self.module_name, status=ModuleStatus.READY.value, started=self._started)

    @staticmethod
    def _organization_id(actor: dict[str, object]) -> str:
        organization_id = actor_str(actor, "organization_id")
        if not organization_id:
            raise AuthorizationError("organization_id is required")
        return organization_id

    def create_schedule_for_actor(self, actor: dict[str, object], request: ScheduleCreateRequest) -> ScheduleRecord:
        organization_id = self._organization_id(actor)
        try:
            ZoneInfo(request.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError(f"unknown timezone '{request.timezone}'") from exc
        machine = self.workflow.get_state_machine_by_name(organization_id, request.machine_name)
        if machine is None or not machine.is_active:
            raise ValidationError(f"active workflow '{request.machine_name}' was not found")
        entity_type = self.entities.get_entity_type_record(organization_id=organization_id, name=machine.entity_type)
        if entity_type is None or not entity_type.is_active:
            raise ValidationError(f"workflow entity type '{machine.entity_type}' was not found")
        declarations = self.entities.db_model_service.list_entity_relation_declarations(
            organization_id=organization_id,
            entity_type_id=request.anchor_entity_type_id,
            direction="from",
        )
        relation = next((item for item in declarations if item.relation_def_id == request.relation_def_id), None)
        if relation is None or relation.to_entity_type_id != entity_type.entity_type_id:
            raise ValidationError("relation_def_id must connect the anchor type to the workflow entity type")
        values = request.model_dump(exclude={"recurrence", "conditions", "anchor_entity_ids"})
        values["target_scope"] = request.target_scope.value
        values["entity_data_json"] = values.pop("entity_data")
        values.update(
            organization_id=organization_id,
            target_entity_type_id=entity_type.entity_type_id,
            recurrence_json=request.recurrence.model_dump(mode="json"),
            conditions_json=[item.model_dump(mode="json") for item in request.conditions],
        )
        local_today = datetime.now(ZoneInfo(request.timezone)).date()
        if request.recurrence.frequency == ScheduleFrequency.ONCE:
            if request.recurrence.occurs_on is None or request.recurrence.occurs_on < local_today:
                raise ValidationError("one-time due date cannot be in the past")
        start = max(local_today, request.starts_on or local_today)
        due = next_due_date(request.recurrence, start)
        anchor_entity_ids = request.anchor_entity_ids
        if request.target_scope == ScheduleTargetScope.ALL:
            anchor_entity_ids = [
                record.entity_id
                for record in self.entities.list_entity_records(
                    organization_id=organization_id,
                    entity_type_id=request.anchor_entity_type_id,
                )
            ]
        target_values: list[dict[str, Any]] = []
        for anchor_entity_id in anchor_entity_ids:
            anchor = self.entities.get_entity_record(
                organization_id=organization_id,
                entity_id=anchor_entity_id,
                include_archived=False,
            )
            if anchor is None:
                raise ValidationError(f"anchor entity '{anchor_entity_id}' was not found or is archived")
            if anchor.entity_type_id != request.anchor_entity_type_id:
                raise ValidationError(f"anchor entity '{anchor_entity_id}' does not match the schedule type")
            target_values.append(
                {
                    "organization_id": organization_id,
                    "anchor_entity_id": anchor_entity_id,
                    "next_due_date": due,
                    "next_materialization_date": due - timedelta(days=request.lead_days),
                    "assignee_id": request.assignee_id,
                    "is_enabled": True,
                }
            )
        schedule, targets = self.db.create_schedule_with_targets(values, target_values)
        self._emit_schedule_audit(
            actor,
            schedule,
            "SCHEDULE_CREATED",
            idempotency_key=f"schedule:{schedule.schedule_id}:created",
            metadata={"machine_name": schedule.machine_name, "target_count": len(targets)},
        )
        return schedule

    def _sync_all_scope_targets(self, schedule: ScheduleRecord) -> int:
        """Create missing cursors for every active entity in an all-scope schedule."""
        if schedule.target_scope != ScheduleTargetScope.ALL:
            return 0
        existing_targets = self.db.list_targets(schedule.organization_id, schedule.schedule_id)
        if schedule.recurrence.frequency == ScheduleFrequency.ONCE and any(
            target.last_result is not None for target in existing_targets
        ):
            return 0
        existing_ids = {
            target.anchor_entity_id
            for target in existing_targets
        }
        local_today = datetime.now(ZoneInfo(schedule.timezone)).date()
        start = max(local_today, schedule.starts_on or local_today)
        due = next_due_date(schedule.recurrence, start)
        if schedule.ends_on is not None and due > schedule.ends_on:
            return 0
        created = 0
        for anchor in self.entities.list_entity_records(
            organization_id=schedule.organization_id,
            entity_type_id=schedule.anchor_entity_type_id,
        ):
            if anchor.entity_id in existing_ids:
                continue
            try:
                self.db.create_target(
                    {
                        "organization_id": schedule.organization_id,
                        "schedule_id": schedule.schedule_id,
                        "anchor_entity_id": anchor.entity_id,
                        "next_due_date": due,
                        "next_materialization_date": due - timedelta(days=schedule.lead_days),
                        "assignee_id": schedule.assignee_id,
                        "is_enabled": True,
                    }
                )
                created += 1
            except ConflictError:
                continue
        return created

    def list_schedules_for_actor(self, actor: dict[str, object], machine_name: str | None = None) -> ScheduleListResponse:
        items = self.db.list_schedules(self._organization_id(actor), machine_name)
        return ScheduleListResponse(items=items, total=len(items))

    def get_schedule_for_actor(self, actor: dict[str, object], schedule_id: str) -> ScheduleRecord:
        record = self.db.get_schedule(self._organization_id(actor), schedule_id)
        if record is None:
            raise NotFoundError("schedule not found")
        return record

    def _workflow_references(self, organization_id: str, schedule_id: str) -> list[str]:
        """Return active/draft workflow states that reference a schedule."""
        workflow_db = getattr(self.workflow, "workflow_db", None)
        if workflow_db is None:
            return []
        references: list[str] = []
        rows = workflow_db.list_state_machines(
            organization_id=organization_id,
            scope="all",
        )
        for row in rows:
            if row.version != 0 and not row.is_active:
                continue
            definition = row.definition
            states = definition.get("states", []) if isinstance(definition, dict) else definition.states
            for state in states:
                state_name = state.get("name", "unknown") if isinstance(state, dict) else state.name
                action = state.get("on_state_action") if isinstance(state, dict) else state.on_state_action
                if action is None:
                    continue
                kind = action.get("kind") if isinstance(action, dict) else action.kind
                config = action.get("config", {}) if isinstance(action, dict) else action.config
                configured_ids = config.get("schedule_ids", [])
                if (
                    kind in {"entity.activate_schedules", "entity.run_schedules_once"}
                    and isinstance(configured_ids, list)
                    and schedule_id in configured_ids
                ):
                    references.append(f"{row.machine_name} / {state_name}")
        return sorted(set(references))

    def delete_schedule_for_actor(self, actor: dict[str, object], schedule_id: str) -> None:
        organization_id = self._organization_id(actor)
        schedule = self.get_schedule_for_actor(actor, schedule_id)
        references = self._workflow_references(organization_id, schedule_id)
        if references:
            raise ConflictError(
                "Remove this schedule from the following workflow actions before deleting it: "
                + ", ".join(references)
            )
        if not self.db.delete_schedule(organization_id, schedule_id):
            raise NotFoundError("schedule not found")
        self._emit_schedule_audit(
            actor,
            schedule,
            "SCHEDULE_DELETED",
            metadata={"machine_name": schedule.machine_name},
        )

    def is_occurrence_active(
        self, organization_id: str, schedule_id: str, target_id: str
    ) -> bool:
        """Check whether a queued occurrence is still allowed to materialize."""
        schedule = self.db.get_schedule(organization_id, schedule_id)
        if schedule is None:
            return False
        target = self.db.get_target_by_id(organization_id, schedule_id, target_id)
        if target is None:
            return False
        if target.last_result in {
            "one_batch_pending",
            "queued_one_batch",
        }:
            return True
        if not schedule.is_enabled:
            return False
        return target.is_enabled or target.last_result == "queued_once"

    def complete_once_occurrence(
        self,
        organization_id: str,
        schedule_id: str,
        target_id: str,
        run_id: str | None = None,
    ) -> None:
        """Mark a successfully materialized one-time occurrence as complete."""
        schedule = self.db.get_schedule(organization_id, schedule_id)
        if schedule is None or schedule.recurrence.frequency != ScheduleFrequency.ONCE:
            return
        self.db.finish_once_target(
            organization_id,
            schedule_id,
            target_id,
            run_id=run_id,
            result="completed_once",
        )

    def update_schedule_for_actor(self, actor: dict[str, object], schedule_id: str, request: ScheduleUpdateRequest) -> ScheduleRecord:
        organization_id = self._organization_id(actor)
        existing = self.get_schedule_for_actor(actor, schedule_id)
        if request.is_enabled is True and existing.completed_at is not None:
            raise ValidationError("a completed one-time automation cannot be enabled again")
        if (
            request.is_enabled is False
            and existing.recurrence.frequency == ScheduleFrequency.ONCE
            and any(
                target.last_result == "queued_once"
                for target in self.db.list_targets(organization_id, schedule_id)
            )
        ):
            raise ValidationError("a one-time automation cannot be paused while it is running")
        values = request.model_dump(exclude_unset=True, exclude={"recurrence", "conditions"})
        if "entity_data" in values:
            values["entity_data_json"] = values.pop("entity_data")
        if request.recurrence is not None:
            values["recurrence_json"] = request.recurrence.model_dump(mode="json")
        if request.conditions is not None:
            values["conditions_json"] = [item.model_dump(mode="json") for item in request.conditions]
        if request.timezone is not None:
            try:
                ZoneInfo(request.timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValidationError(f"unknown timezone '{request.timezone}'") from exc
        updated = self.db.update_schedule(organization_id, schedule_id, values)
        if updated is None:
            raise NotFoundError("schedule not found")
        if request.recurrence is not None or request.lead_days is not None or request.starts_on is not None:
            local_today = datetime.now(ZoneInfo(updated.timezone)).date()
            for target in self.db.list_targets(organization_id, schedule_id):
                if request.recurrence is not None or request.starts_on is not None:
                    progress_floor = max(
                        target.next_due_date,
                        updated.starts_on or date.min,
                        local_today,
                    )
                    due = next_due_date(updated.recurrence, progress_floor)
                else:
                    # Changing lead time affects when work appears, not which
                    # occurrence this target is currently progressing toward.
                    due = target.next_due_date
                self.db.advance_target(
                    organization_id,
                    target.target_id,
                    due_date=due,
                    materialization_date=due - timedelta(days=updated.lead_days),
                    run_id=target.last_action_run_id,
                    result="recalculated",
                )
        self._emit_schedule_audit(
            actor,
            updated,
            "SCHEDULE_UPDATED",
            metadata={"changed_fields": sorted(values), "was_enabled": existing.is_enabled},
        )
        return updated

    def add_target_for_actor(self, actor: dict[str, object], schedule_id: str, request: ScheduleTargetCreateRequest) -> ScheduleTargetRecord:
        organization_id = self._organization_id(actor)
        schedule = self.get_schedule_for_actor(actor, schedule_id)
        anchor = self.entities.get_entity_record(organization_id=organization_id, entity_id=request.anchor_entity_id)
        if anchor is None or anchor.archived_at is not None:
            raise ValidationError("anchor entity was not found or is archived")
        if anchor.entity_type_id != schedule.anchor_entity_type_id:
            raise ValidationError("anchor entity type does not match the schedule")
        local_today = datetime.now(ZoneInfo(schedule.timezone)).date()
        start = max(local_today, schedule.starts_on or local_today)
        due = next_due_date(schedule.recurrence, start)
        target = self.db.create_target(
            {
                "organization_id": organization_id,
                "schedule_id": schedule_id,
                "anchor_entity_id": request.anchor_entity_id,
                "next_due_date": due,
                "next_materialization_date": due - timedelta(days=schedule.lead_days),
                "assignee_id": request.assignee_id,
                "is_enabled": request.is_enabled,
            }
        )
        self._emit_schedule_audit(
            actor,
            schedule,
            "SCHEDULE_TARGET_ADDED",
            metadata={"target_id": target.target_id, "anchor_entity_id": target.anchor_entity_id},
        )
        return target

    def activate_schedules_for_actor(
        self,
        actor: dict[str, object],
        *,
        anchor_entity_id: str,
        schedule_ids: list[str],
        policy: ScheduleActivationPolicy = ScheduleActivationPolicy.CURRENT_PERIOD,
        run_once: bool = False,
    ) -> dict[str, Any]:
        """Subscribe one entity, or queue one batch for it, idempotently."""
        organization_id = self._organization_id(actor)
        normalized_ids = list(dict.fromkeys(item.strip() for item in schedule_ids if item.strip()))
        if not normalized_ids:
            raise ValidationError("at least one schedule_id is required")
        anchor = self.entities.get_entity_record(
            organization_id=organization_id,
            entity_id=anchor_entity_id,
            include_archived=False,
        )
        if anchor is None:
            raise ValidationError("anchor entity was not found or is archived")

        schedules: list[ScheduleRecord] = []
        for schedule_id in normalized_ids:
            schedule = self.db.get_schedule(organization_id, schedule_id)
            if schedule is None:
                raise ValidationError(f"schedule '{schedule_id}' was not found")
            if schedule.completed_at is not None or (not run_once and not schedule.is_enabled):
                raise ValidationError(f"schedule '{schedule.name}' is not active")
            if schedule.anchor_entity_type_id != anchor.entity_type_id:
                raise ValidationError(
                    f"schedule '{schedule.name}' does not apply to this entity type"
                )
            schedules.append(schedule)

        activated: list[dict[str, Any]] = []
        existing: list[str] = []
        skipped: list[str] = []
        plans: list[tuple[ScheduleRecord, date, ScheduleTargetRecord | None]] = []
        for schedule in schedules:
            current = self.db.get_target(organization_id, schedule.schedule_id, anchor_entity_id)
            if current is not None:
                if run_once:
                    retrying = current.last_result == "one_batch_pending"
                    never_run = current.last_action_run_id is None and current.last_result in {
                        None, "activated_current_period"
                    }
                    if retrying or never_run:
                        if retrying or self._conditions_match(schedule, dict(anchor.data or {})):
                            plans.append((schedule, current.next_due_date, current))
                        else:
                            skipped.append(schedule.schedule_id)
                        continue
                existing.append(schedule.schedule_id)
                continue
            if run_once and not self._conditions_match(schedule, dict(anchor.data or {})):
                skipped.append(schedule.schedule_id)
                continue
            local_today = datetime.now(ZoneInfo(schedule.timezone)).date()
            activated_on = max(local_today, schedule.starts_on or local_today)
            due = activation_due_date(schedule.recurrence, activated_on, policy)
            if schedule.starts_on and due < schedule.starts_on:
                due = next_due_date(schedule.recurrence, schedule.starts_on)
            if schedule.ends_on and due > schedule.ends_on:
                raise ValidationError(f"schedule '{schedule.name}' has no remaining occurrences")
            plans.append((schedule, due, None))

        for schedule, due, target in plans:
            if target is None:
                try:
                    target = self.db.create_target(
                        {
                            "organization_id": organization_id,
                            "schedule_id": schedule.schedule_id,
                            "anchor_entity_id": anchor_entity_id,
                            "next_due_date": due,
                            "next_materialization_date": due
                            - timedelta(days=schedule.lead_days),
                            "assignee_id": schedule.assignee_id,
                            "is_enabled": not run_once,
                            "last_result": (
                                "one_batch_pending"
                                if run_once
                                else "activated_current_period"
                                if policy == ScheduleActivationPolicy.CURRENT_PERIOD
                                else None
                            ),
                        }
                    )
                except ConflictError:
                    # A concurrent/retried action may have inserted the same unique target.
                    target = self.db.get_target(organization_id, schedule.schedule_id, anchor_entity_id)
                    if not run_once or target is None or not (
                        target.last_result == "one_batch_pending"
                        or (
                            target.last_action_run_id is None
                            and target.last_result in {None, "activated_current_period"}
                        )
                    ):
                        existing.append(schedule.schedule_id)
                        continue
            run_ids: list[str] = []
            if run_once:
                self.db.prepare_one_batch_target(organization_id, target.target_id)
                for occurrence_due in self._batch_due_dates(schedule, due):
                    run_ids.append(
                        self._create_occurrence_run(
                            schedule,
                            target,
                            dict(anchor.data or {}),
                            trigger_source="workflow",
                            occurrence_due=occurrence_due,
                        )
                    )
                self.db.finish_one_batch_target(
                    organization_id,
                    target.target_id,
                    run_id=run_ids[-1] if run_ids else None,
                )
            activated.append(
                {
                    "schedule_id": schedule.schedule_id,
                    "target_id": target.target_id,
                    "next_due_date": due.isoformat(),
                    **({"run_ids": run_ids} if run_once else {}),
                }
            )
            self._emit_schedule_audit(
                actor,
                schedule,
                "SCHEDULE_TARGET_ACTIVATED",
                idempotency_key=(
                    f"schedule:{schedule.schedule_id}:target:{anchor_entity_id}:activated"
                ),
                metadata={
                    "target_id": target.target_id,
                    "activation_policy": policy.value,
                    "run_once": run_once,
                },
            )
        return {
            "anchor_entity_id": anchor_entity_id,
            "activated": activated,
            "already_active_schedule_ids": existing,
            "skipped_schedule_ids": skipped,
        }

    def list_targets_for_actor(self, actor: dict[str, object], schedule_id: str) -> ScheduleTargetListResponse:
        schedule = self.get_schedule_for_actor(actor, schedule_id)
        self._sync_all_scope_targets(schedule)
        items = self.db.list_targets(self._organization_id(actor), schedule_id)
        return ScheduleTargetListResponse(items=items, total=len(items))

    def preview_for_actor(self, actor: dict[str, object], schedule_id: str, count: int = 6) -> SchedulePreviewResponse:
        schedule = self.get_schedule_for_actor(actor, schedule_id)
        cursor = max(datetime.now(ZoneInfo(schedule.timezone)).date(), schedule.starts_on or date.min)
        items: list[SchedulePreviewItem] = []
        for _ in range(max(1, min(count, 24))):
            due = next_due_date(schedule.recurrence, cursor)
            if schedule.ends_on and due > schedule.ends_on:
                break
            items.append(SchedulePreviewItem(due_date=due, materialization_date=due - timedelta(days=schedule.lead_days)))
            cursor = due + timedelta(days=1)
        return SchedulePreviewResponse(items=items)

    @staticmethod
    def _conditions_match(schedule: ScheduleRecord, data: dict[str, Any]) -> bool:
        if not schedule.conditions:
            return True
        results = [condition_matches(condition, data) for condition in schedule.conditions]
        return any(results) if schedule.condition_mode == "any" else all(results)

    def _evaluate_target(
        self,
        schedule: ScheduleRecord,
        target: ScheduleTargetRecord,
        occurrence_due: date | None = None,
    ) -> tuple[str, str | None, Any | None, dict[str, Any]]:
        """Return status, reason, anchor record, and anchor data for one occurrence."""
        due = occurrence_due or target.next_due_date
        if not target.is_enabled:
            return "skipped", "Target is disabled", None, {}
        if schedule.ends_on and due > schedule.ends_on:
            return "skipped", "Schedule has ended", None, {}
        anchor = self.entities.get_entity_record(
            organization_id=target.organization_id,
            entity_id=target.anchor_entity_id,
            include_archived=False,
        )
        if anchor is None:
            return "skipped", "Related record is missing or archived", None, {}
        anchor_data = dict(anchor.data or {})
        if not self._conditions_match(schedule, anchor_data):
            return "skipped", "Condition does not match", anchor, anchor_data
        return "eligible", None, anchor, anchor_data

    def _create_occurrence_run(
        self,
        schedule: ScheduleRecord,
        target: ScheduleTargetRecord,
        anchor_data: dict[str, Any],
        *,
        trigger_source: str,
        triggered_by: str | None = None,
        run_invocation_id: str | None = None,
        occurrence_due: date | None = None,
    ) -> str:
        due = occurrence_due or target.next_due_date
        template_values = _TemplateValues(
            schedule_name=schedule.name,
            anchor_identifier=str(anchor_data.get("identifier") or target.anchor_entity_id),
            due_date=due.isoformat(),
        )
        entity_data = dict(schedule.entity_data)
        entity_data["identifier"] = schedule.identifier_template.format_map(template_values)
        return self.background_jobs.create_scheduled_action_run(
            organization_id=target.organization_id,
            entity_id=target.anchor_entity_id,
            action_kind="entity.create_and_enroll",
            config_json={
                "schedule_id": schedule.schedule_id,
                "schedule_target_id": target.target_id,
                "machine_name": schedule.machine_name,
                "target_entity_type_id": schedule.target_entity_type_id,
                "anchor_entity_id": target.anchor_entity_id,
                "due_date": due.isoformat(),
                "entity_data": entity_data,
                "owner_id": schedule.owner_id,
                "assignee_id": target.assignee_id or schedule.assignee_id,
                "trigger_source": trigger_source,
                "triggered_by": triggered_by,
                "run_invocation_id": run_invocation_id,
                "complete_after_run": schedule.recurrence.frequency == ScheduleFrequency.ONCE,
                "failure_policy": {
                    "on_failure": "retry",
                    "max_attempts": 3,
                    "delay_seconds": 60,
                    "backoff": "exponential",
                },
            },
            idempotency_key=(
                f"schedule:{target.organization_id}:{target.target_id}:{due.isoformat()}"
            ),
        )

    def _queue_occurrence_batch(
        self,
        schedule: ScheduleRecord,
        target: ScheduleTargetRecord,
        anchor_data: dict[str, Any],
        *,
        trigger_source: str,
        triggered_by: str | None = None,
        run_invocation_id: str | None = None,
        occurrence_due: date | None = None,
    ) -> list[str]:
        """Queue one bounded occurrence batch and advance the target once."""
        due = occurrence_due or target.next_due_date
        if schedule.recurrence.frequency == ScheduleFrequency.ONCE:
            run_id = self._create_occurrence_run(
                schedule,
                target,
                anchor_data,
                trigger_source=trigger_source,
                triggered_by=triggered_by,
                run_invocation_id=run_invocation_id,
                occurrence_due=due,
            )
            self.db.finish_once_target(
                target.organization_id,
                schedule.schedule_id,
                target.target_id,
                run_id=run_id,
                result="queued_once",
            )
            return [run_id]
        run_ids: list[str] = []
        last_due: date | None = None
        for _ in range(schedule.occurrences_per_batch):
            if schedule.ends_on and due > schedule.ends_on:
                break
            run_ids.append(
                self._create_occurrence_run(
                    schedule,
                    target,
                    anchor_data,
                    trigger_source=trigger_source,
                    triggered_by=triggered_by,
                    run_invocation_id=run_invocation_id,
                    occurrence_due=due,
                )
            )
            last_due = due
            due = following_due_date(schedule.recurrence, due)
        if last_due is None:
            return []
        self.db.advance_target(
            target.organization_id,
            target.target_id,
            due_date=due,
            materialization_date=due - timedelta(days=schedule.lead_days),
            run_id=run_ids[-1],
            result="manual_scheduled" if trigger_source == "manual" else "scheduled",
        )
        return run_ids

    @staticmethod
    def _batch_due_dates(schedule: ScheduleRecord, first_due: date) -> list[date]:
        if schedule.recurrence.frequency == ScheduleFrequency.ONCE:
            return [first_due]
        due = first_due
        dates: list[date] = []
        for _ in range(schedule.occurrences_per_batch):
            if schedule.ends_on and due > schedule.ends_on:
                break
            dates.append(due)
            due = following_due_date(schedule.recurrence, due)
        return dates

    def preview_run_now_for_actor(
        self, actor: dict[str, object], schedule_id: str
    ) -> ScheduleRunPreviewResponse:
        organization_id = self._organization_id(actor)
        schedule = self.get_schedule_for_actor(actor, schedule_id)
        self._sync_all_scope_targets(schedule)
        items: list[ScheduleRunPreviewItem] = []
        eligible = 0
        for target in self.db.list_targets(organization_id, schedule_id):
            status, reason, _anchor, anchor_data = self._evaluate_target(schedule, target)
            if status == "eligible":
                eligible += 1
            items.append(
                ScheduleRunPreviewItem(
                    target_id=target.target_id,
                    anchor_entity_id=target.anchor_entity_id,
                    anchor_identifier=str(
                        anchor_data.get("identifier") or target.anchor_entity_id
                    ),
                    due_date=target.next_due_date,
                    due_dates=self._batch_due_dates(schedule, target.next_due_date),
                    status=status,
                    reason=reason,
                )
            )
        return ScheduleRunPreviewResponse(
            schedule_id=schedule.schedule_id,
            schedule_name=schedule.name,
            invocation_id=str(uuid4()),
            eligible=eligible,
            skipped=len(items) - eligible,
            items=items,
        )

    def run_now_for_actor(
        self,
        actor: dict[str, object],
        schedule_id: str,
        request: ScheduleRunNowRequest,
    ) -> ScheduleRunNowResponse:
        organization_id = self._organization_id(actor)
        schedule = self.get_schedule_for_actor(actor, schedule_id)
        self._sync_all_scope_targets(schedule)
        if not schedule.is_enabled:
            raise ValidationError("Enable the schedule before running it")
        run_ids: list[str] = []
        skipped = 0
        triggered_by = actor_str(actor, "user_id")
        self._emit_schedule_audit(
            actor,
            schedule,
            "SCHEDULE_RUN_REQUESTED",
            correlation_id=request.invocation_id,
            idempotency_key=f"schedule:{schedule_id}:run-request:{request.invocation_id}",
        )
        for target in self.db.list_targets(organization_id, schedule_id):
            existing_run = self.background_jobs.find_scheduled_action_run(
                organization_id=organization_id,
                invocation_id=request.invocation_id,
                schedule_target_id=target.target_id,
            )
            if existing_run is not None:
                existing_run_ids = existing_run.get("run_ids") or [existing_run["run_id"]]
                existing_config = dict(existing_run.get("config_json") or {})
                existing_due = date.fromisoformat(str(existing_config["due_date"]))
                if (
                    target.next_due_date == existing_due
                    and schedule.recurrence.frequency != ScheduleFrequency.ONCE
                ):
                    # Replaying the original batch is safe because each due date has
                    # its own idempotency key. It repairs partially committed batches
                    # and advances the target only after every occurrence exists.
                    anchor = self.entities.get_entity_record(
                        organization_id=organization_id,
                        entity_id=target.anchor_entity_id,
                        include_archived=False,
                    )
                    if anchor is None:
                        skipped += 1
                        continue
                    run_ids.extend(
                        self._queue_occurrence_batch(
                            schedule,
                            target,
                            dict(anchor.data or {}),
                            trigger_source="manual",
                            triggered_by=triggered_by,
                            run_invocation_id=request.invocation_id,
                            occurrence_due=existing_due,
                        )
                    )
                else:
                    run_ids.extend(str(run_id) for run_id in existing_run_ids)
                continue
            status, _reason, _anchor, anchor_data = self._evaluate_target(schedule, target)
            if status != "eligible":
                skipped += 1
                continue
            run_ids.extend(
                self._queue_occurrence_batch(
                    schedule,
                    target,
                    anchor_data,
                    trigger_source="manual",
                    triggered_by=triggered_by,
                    run_invocation_id=request.invocation_id,
                )
            )
        response = ScheduleRunNowResponse(
            schedule_id=schedule.schedule_id,
            invocation_id=request.invocation_id,
            queued=len(run_ids),
            skipped=skipped,
            run_ids=run_ids,
        )
        self._emit_schedule_audit(
            actor,
            schedule,
            "SCHEDULE_RUN_QUEUED",
            correlation_id=request.invocation_id,
            idempotency_key=f"schedule:{schedule_id}:run-queued:{request.invocation_id}",
            metadata={"queued": response.queued, "skipped": response.skipped, "run_ids": response.run_ids},
        )
        return response

    def _emit_schedule_audit(
        self,
        actor: dict[str, object],
        schedule: ScheduleRecord,
        event_type: str,
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Best-effort append-only audit record for schedule mutations."""
        if self.audit_events is None:
            return
        try:
            actor_id = actor_str(actor, "user_id") or None
            self.audit_events.emit_audit_event(
                organization_id=schedule.organization_id,
                metadata_type=AuditMetadataType.SCHEDULE,
                event_type=event_type,
                actor_type=str(actor.get("actor_type") or ("user" if actor_id else "system")),
                actor_id=actor_id,
                user_id=actor_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                source=str(actor.get("source") or "api"),
                event_metadata={
                    "schedule_id": schedule.schedule_id,
                    "schedule_name": schedule.name,
                    **(metadata or {}),
                },
            )
        except Exception as exc:
            logger.warning("schedule audit emit failed event=%s schedule=%s: %s", event_type, schedule.schedule_id, exc)

    def process_due_targets(self, *, limit: int = 100) -> int:
        """Create action runs for due targets and advance them without historical backfill."""
        processed = 0
        for schedule in self.db.list_enabled_all_scope_schedules():
            self._sync_all_scope_targets(schedule)
            if (
                schedule.recurrence.frequency == ScheduleFrequency.ONCE
                and schedule.recurrence.occurs_on is not None
                and schedule.recurrence.occurs_on - timedelta(days=schedule.lead_days)
                <= datetime.now(ZoneInfo(schedule.timezone)).date()
                and not self.db.list_targets(schedule.organization_id, schedule.schedule_id)
            ):
                self.db.complete_empty_once_schedule(
                    schedule.organization_id, schedule.schedule_id
                )
        for target in self.db.list_due_targets(date.today() + timedelta(days=1), limit=limit):
            schedule = self.db.get_schedule(target.organization_id, target.schedule_id)
            if schedule is None or not schedule.is_enabled:
                continue
            local_today = datetime.now(ZoneInfo(schedule.timezone)).date()
            due = target.next_due_date
            # Normal targets collapse missed periods. A newly activated target
            # preserves its explicitly selected current period exactly once.
            if (
                schedule.recurrence.frequency != ScheduleFrequency.ONCE
                and target.last_result != "activated_current_period"
            ):
                while True:
                    following = following_due_date(schedule.recurrence, due)
                    if following - timedelta(days=schedule.lead_days) > local_today:
                        break
                    due = following
            if due - timedelta(days=schedule.lead_days) > local_today:
                continue
            status, reason, _anchor, anchor_data = self._evaluate_target(
                schedule, target, occurrence_due=due
            )
            if status != "eligible":
                if schedule.recurrence.frequency == ScheduleFrequency.ONCE:
                    self.db.finish_once_target(
                        target.organization_id,
                        schedule.schedule_id,
                        target.target_id,
                        run_id=None,
                        result=(reason or "skipped").lower().replace(" ", "_")[:64],
                    )
                    processed += 1
                    continue
                next_due = following_due_date(schedule.recurrence, due)
                self.db.advance_target(
                    target.organization_id,
                    target.target_id,
                    due_date=next_due,
                    materialization_date=next_due - timedelta(days=schedule.lead_days),
                    run_id=None,
                    result=(reason or "skipped").lower().replace(" ", "_")[:64],
                )
                processed += 1
                continue
            self._queue_occurrence_batch(
                schedule,
                target,
                anchor_data,
                trigger_source="schedule",
                occurrence_due=due,
            )
            processed += 1
        return processed

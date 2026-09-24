from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from exceptions import ConflictError
from executor.executors.entity_activate_schedules import (
    EntityActivateSchedulesExecutor,
    EntityRunSchedulesOnceExecutor,
)
from executor.executors.entity_create_and_enroll import EntityCreateAndEnrollExecutor
from executor.models.interface import ExecutorInput, ExecutorValue, ValueKind
from schedules.manager import SchedulesServiceManager, activation_due_date
from schedules.models.interface import (
    RecurrenceRule,
    ScheduleActivationPolicy,
    ScheduleFrequency,
    ScheduleRecord,
    ScheduleTargetRecord,
    ScheduleTargetScope,
)
from schedules.models.request import ScheduleCreateRequest


def test_current_period_selects_month_quarter_and_year_without_backfill() -> None:
    activated_on = date(2027, 8, 20)
    assert activation_due_date(
        RecurrenceRule(frequency=ScheduleFrequency.MONTHLY, day_of_month=1),
        activated_on,
        ScheduleActivationPolicy.CURRENT_PERIOD,
    ) == date(2027, 8, 1)
    assert activation_due_date(
        RecurrenceRule(
            frequency=ScheduleFrequency.QUARTERLY,
            day_of_month=30,
            months=[3, 6, 9, 12],
        ),
        activated_on,
        ScheduleActivationPolicy.CURRENT_PERIOD,
    ) == date(2027, 9, 30)
    assert activation_due_date(
        RecurrenceRule(
            frequency=ScheduleFrequency.ANNUAL,
            day_of_month=31,
            months=[3],
        ),
        activated_on,
        ScheduleActivationPolicy.CURRENT_PERIOD,
    ) == date(2027, 3, 31)


def _schedule(schedule_id: str = "schedule-1") -> ScheduleRecord:
    return ScheduleRecord(
        schedule_id=schedule_id,
        organization_id="org-1",
        machine_name="Filings",
        name=f"Filing {schedule_id}",
        anchor_entity_type_id="customer-type",
        target_entity_type_id="filing-type",
        relation_def_id="relation-1",
        target_scope=ScheduleTargetScope.SELECTED,
        recurrence=RecurrenceRule(frequency=ScheduleFrequency.MONTHLY, day_of_month=31),
        lead_days=30,
        timezone="UTC",
        identifier_template="{due_date}",
    )


def test_create_request_defaults_to_all_but_preserves_legacy_selected_ids() -> None:
    common = {
        "machine_name": "Filings",
        "name": "Monthly filings",
        "anchor_entity_type_id": "customer-type",
        "relation_def_id": "relation-1",
        "recurrence": RecurrenceRule(frequency=ScheduleFrequency.MONTHLY, day_of_month=1),
    }

    assert ScheduleCreateRequest(**common).target_scope == ScheduleTargetScope.ALL
    assert ScheduleCreateRequest(
        **common, anchor_entity_ids=["customer-1"]
    ).target_scope == ScheduleTargetScope.SELECTED


def test_activation_is_scoped_to_one_entity_and_idempotent() -> None:
    class Database:
        def __init__(self) -> None:
            self.targets: dict[tuple[str, str], ScheduleTargetRecord] = {}

        def get_schedule(self, _org_id, schedule_id):
            return _schedule(schedule_id)

        def get_target(self, _org_id, schedule_id, anchor_id):
            return self.targets.get((schedule_id, anchor_id))

        def create_target(self, values):
            target = ScheduleTargetRecord(target_id="target-1", **values)
            self.targets[(target.schedule_id, target.anchor_entity_id)] = target
            return target

    database = Database()
    entities = SimpleNamespace(
        get_entity_record=lambda **kwargs: SimpleNamespace(
            entity_id=kwargs["entity_id"], entity_type_id="customer-type"
        )
    )
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=entities,
        workflow_service_manager=object(),
        background_jobs_service_manager=object(),
    )
    actor = {"organization_id": "org-1", "user_id": "system"}

    first = manager.activate_schedules_for_actor(
        actor, anchor_entity_id="customer-new", schedule_ids=["schedule-1"]
    )
    second = manager.activate_schedules_for_actor(
        actor, anchor_entity_id="customer-new", schedule_ids=["schedule-1"]
    )

    assert len(first["activated"]) == 1
    assert second["activated"] == []
    assert second["already_active_schedule_ids"] == ["schedule-1"]
    assert set(database.targets) == {("schedule-1", "customer-new")}
    assert next(iter(database.targets.values())).last_result == "activated_current_period"


def test_workflow_executor_delegates_current_entity_and_selected_schedules() -> None:
    class Schedules:
        request = None

        def activate_schedules_for_actor(self, actor, **kwargs):
            self.request = (actor, kwargs)
            return {"activated": [{"schedule_id": "schedule-1"}]}

    schedules = Schedules()
    executor = EntityActivateSchedulesExecutor()
    executor.bind_service(schedules)
    result = executor.execute(
        ExecutorInput(
            entity_id="customer-new",
            entity_type="Customer",
            current_state="ONBOARDED",
            fields={
                "org_id": ExecutorValue(kind=ValueKind.TEXT, value="org-1"),
                "_raw_config": ExecutorValue(
                    kind=ValueKind.TEXT,
                    value=json.dumps(
                        {
                            "schedule_ids": ["schedule-1", "schedule-2"],
                            "activation_policy": "current_period",
                        }
                    ),
                ),
            },
        )
    )

    assert result.success is True
    assert schedules.request[1]["anchor_entity_id"] == "customer-new"
    assert schedules.request[1]["schedule_ids"] == ["schedule-1", "schedule-2"]
    assert schedules.request[1]["run_once"] is False


def test_workflow_executor_can_run_one_automation_batch() -> None:
    class Schedules:
        request = None

        def activate_schedules_for_actor(self, actor, **kwargs):
            self.request = (actor, kwargs)
            return {"activated": [{"schedule_id": "schedule-1", "run_ids": ["run-1"]}]}

    schedules = Schedules()
    executor = EntityRunSchedulesOnceExecutor()
    executor.bind_service(schedules)
    result = executor.execute(
        ExecutorInput(
            entity_id="customer-new",
            entity_type="Customer",
            current_state="ONBOARDED",
            fields={
                "org_id": ExecutorValue(kind=ValueKind.TEXT, value="org-1"),
                "_raw_config": ExecutorValue(
                    kind=ValueKind.TEXT,
                    value=json.dumps(
                        {
                            "schedule_ids": ["schedule-1"],
                            "activation_policy": "current_period",
                        }
                    ),
                ),
            },
        )
    )

    assert result.success is True
    assert result.data.outcome == "queued"
    assert schedules.request[1]["anchor_entity_id"] == "customer-new"
    assert schedules.request[1]["run_once"] is True


def test_workflow_executor_reports_already_invoked_when_no_batch_is_queued() -> None:
    class Schedules:
        def activate_schedules_for_actor(self, _actor, **_kwargs):
            return {
                "activated": [],
                "already_active_schedule_ids": ["schedule-1"],
                "skipped_schedule_ids": [],
            }

    executor = EntityRunSchedulesOnceExecutor()
    executor.bind_service(Schedules())
    result = executor.execute(
        ExecutorInput(
            entity_id="customer-existing",
            entity_type="Customer",
            current_state="ONBOARDED",
            fields={
                "org_id": ExecutorValue(kind=ValueKind.TEXT, value="org-1"),
                "_raw_config": ExecutorValue(
                    kind=ValueKind.TEXT,
                    value=json.dumps({"schedule_ids": ["schedule-1"]}),
                ),
            },
        )
    )

    assert result.success is True
    assert result.data.outcome == "already_invoked"


def test_run_once_queues_one_quarterly_batch_without_recurring_subscription() -> None:
    schedule = _schedule().model_copy(
        update={
            "recurrence": RecurrenceRule(
                frequency=ScheduleFrequency.QUARTERLY,
                day_of_month=31,
                months=[3, 6, 9, 12],
            ),
            "occurrences_per_batch": 3,
            "starts_on": date(2027, 7, 1),
            "identifier_template": "{anchor_identifier} - {due_date}",
        }
    )
    existing_target = ScheduleTargetRecord(
        target_id="target-1",
        organization_id="org-1",
        schedule_id=schedule.schedule_id,
        anchor_entity_id="customer-new",
        next_due_date=date(2027, 9, 30),
        next_materialization_date=date(2027, 8, 31),
    )

    class Database:
        target = existing_target
        finished = None
        prepared = None

        def get_schedule(self, *_args):
            return schedule

        def get_target(self, *_args):
            return self.target

        def create_target(self, values):
            raise AssertionError("the existing unprocessed target must be reused")

        def finish_one_batch_target(self, *args, **kwargs):
            self.finished = (args, kwargs)

        def prepare_one_batch_target(self, *args):
            self.prepared = args
            self.target = self.target.model_copy(
                update={"is_enabled": False, "last_result": "one_batch_pending"}
            )

    class Background:
        def __init__(self) -> None:
            self.calls = []

        def create_scheduled_action_run(self, **kwargs):
            self.calls.append(kwargs)
            return f"run-{len(self.calls)}"

    database = Database()
    background = Background()
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=SimpleNamespace(
            get_entity_record=lambda **_kwargs: SimpleNamespace(
                entity_type_id="customer-type",
                data={"identifier": "ABC"},
            )
        ),
        workflow_service_manager=object(),
        background_jobs_service_manager=background,
    )

    result = manager.activate_schedules_for_actor(
        {"organization_id": "org-1", "user_id": "system"},
        anchor_entity_id="customer-new",
        schedule_ids=[schedule.schedule_id],
        run_once=True,
    )

    assert database.target.is_enabled is False
    assert database.target.last_result == "one_batch_pending"
    assert database.prepared == ("org-1", "target-1")
    assert [call["config_json"]["due_date"] for call in background.calls] == [
        "2027-09-30",
        "2027-12-31",
        "2028-03-31",
    ]
    assert database.finished == (("org-1", "target-1"), {"run_id": "run-3"})
    assert result["activated"][0]["run_ids"] == ["run-1", "run-2", "run-3"]


def test_paused_automation_allows_explicit_batch_jobs_but_not_normal_targets() -> None:
    schedule = _schedule().model_copy(update={"is_enabled": False})
    target = ScheduleTargetRecord(
        target_id="target-1",
        organization_id="org-1",
        schedule_id=schedule.schedule_id,
        anchor_entity_id="customer-new",
        next_due_date=date(2027, 9, 30),
        next_materialization_date=date(2027, 8, 31),
        is_enabled=False,
        last_result="one_batch_pending",
    )

    class Database:
        def get_schedule(self, *_args):
            return schedule

        def get_target_by_id(self, *_args):
            return target

    manager = SchedulesServiceManager(
        Database(),
        entities_service_manager=object(),
        workflow_service_manager=object(),
        background_jobs_service_manager=object(),
    )

    assert manager.is_occurrence_active("org-1", schedule.schedule_id, target.target_id)
    target.last_result = None
    assert not manager.is_occurrence_active("org-1", schedule.schedule_id, target.target_id)


def test_due_worker_preserves_activated_current_period_once() -> None:
    today = datetime.now(UTC).date()
    due = today.replace(day=1)
    schedule = _schedule().model_copy(
        update={
            "recurrence": RecurrenceRule(
                frequency=ScheduleFrequency.MONTHLY, day_of_month=1
            )
        }
    )
    target = ScheduleTargetRecord(
        target_id="target-1",
        organization_id="org-1",
        schedule_id=schedule.schedule_id,
        anchor_entity_id="customer-new",
        next_due_date=due,
        next_materialization_date=due,
        last_result="activated_current_period",
    )

    class Database:
        advance = None

        def list_enabled_all_scope_schedules(self):
            return []

        def list_due_targets(self, *_args, **_kwargs):
            return [target]

        def get_schedule(self, *_args):
            return schedule

        def advance_target(self, *args, **kwargs):
            self.advance = (args, kwargs)

    class Background:
        config = None

        def create_scheduled_action_run(self, **kwargs):
            self.config = kwargs["config_json"]
            return "run-1"

    database = Database()
    background = Background()
    entities = SimpleNamespace(
        get_entity_record=lambda **_kwargs: SimpleNamespace(data={"identifier": "ABC"})
    )
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=entities,
        workflow_service_manager=object(),
        background_jobs_service_manager=background,
    )

    assert manager.process_due_targets() == 1
    assert background.config["due_date"] == due.isoformat()
    assert database.advance[1]["result"] == "scheduled"


def test_all_scope_sync_adds_only_missing_active_entities() -> None:
    schedule = _schedule().model_copy(update={"target_scope": ScheduleTargetScope.ALL})
    existing = ScheduleTargetRecord(
        target_id="target-1",
        organization_id="org-1",
        schedule_id=schedule.schedule_id,
        anchor_entity_id="customer-1",
        next_due_date=date(2027, 1, 31),
        next_materialization_date=date(2027, 1, 1),
    )

    class Database:
        created: list[dict] = []

        def list_targets(self, *_args):
            return [existing]

        def create_target(self, values):
            self.created.append(values)
            return ScheduleTargetRecord(target_id="target-2", **values)

    database = Database()
    entities = SimpleNamespace(
        list_entity_records=lambda **_kwargs: [
            SimpleNamespace(entity_id="customer-1"),
            SimpleNamespace(entity_id="customer-2"),
        ]
    )
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=entities,
        workflow_service_manager=object(),
        background_jobs_service_manager=object(),
    )

    assert manager._sync_all_scope_targets(schedule) == 1
    assert [values["anchor_entity_id"] for values in database.created] == ["customer-2"]


def test_occurrence_batch_queues_three_quarters_and_advances_once() -> None:
    schedule = _schedule().model_copy(
        update={
            "recurrence": RecurrenceRule(
                frequency=ScheduleFrequency.QUARTERLY,
                day_of_month=31,
                months=[3, 6, 9, 12],
            ),
            "occurrences_per_batch": 3,
        }
    )
    target = ScheduleTargetRecord(
        target_id="target-1",
        organization_id="org-1",
        schedule_id=schedule.schedule_id,
        anchor_entity_id="customer-1",
        next_due_date=date(2027, 9, 30),
        next_materialization_date=date(2027, 8, 31),
    )

    class Database:
        advance = None

        def advance_target(self, *args, **kwargs):
            self.advance = (args, kwargs)

    class Background:
        calls: list[dict] = []

        def create_scheduled_action_run(self, **kwargs):
            self.calls.append(kwargs)
            return f"run-{len(self.calls)}"

    database = Database()
    background = Background()
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=object(),
        workflow_service_manager=object(),
        background_jobs_service_manager=background,
    )

    run_ids = manager._queue_occurrence_batch(
        schedule,
        target,
        {"identifier": "ABC"},
        trigger_source="schedule",
    )

    assert run_ids == ["run-1", "run-2", "run-3"]
    assert [call["config_json"]["due_date"] for call in background.calls] == [
        "2027-09-30",
        "2027-12-31",
        "2028-03-31",
    ]
    assert len({call["idempotency_key"] for call in background.calls}) == 3
    assert database.advance[1]["due_date"] == date(2028, 6, 30)
    assert database.advance[1]["run_id"] == "run-3"


def test_one_time_batch_queues_once_and_waits_for_executor_completion() -> None:
    due = date(2027, 9, 30)
    schedule = _schedule().model_copy(
        update={
            "recurrence": RecurrenceRule(
                frequency=ScheduleFrequency.ONCE,
                occurs_on=due,
            ),
            "occurrences_per_batch": 1,
        }
    )
    target = ScheduleTargetRecord(
        target_id="target-once",
        organization_id="org-1",
        schedule_id=schedule.schedule_id,
        anchor_entity_id="customer-1",
        next_due_date=due,
        next_materialization_date=date(2027, 8, 31),
    )

    class Database:
        finished = None

        def finish_once_target(self, *args, **kwargs):
            self.finished = (args, kwargs)

    class Background:
        config = None

        def create_scheduled_action_run(self, **kwargs):
            self.config = kwargs["config_json"]
            return "run-once"

    database = Database()
    background = Background()
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=object(),
        workflow_service_manager=object(),
        background_jobs_service_manager=background,
    )

    assert manager._queue_occurrence_batch(
        schedule, target, {"identifier": "ABC"}, trigger_source="schedule"
    ) == ["run-once"]
    assert background.config["complete_after_run"] is True
    assert database.finished[1] == {"run_id": "run-once", "result": "queued_once"}


def test_schedule_delete_is_blocked_while_workflow_action_references_it() -> None:
    schedule = _schedule()

    class Database:
        deleted = False

        def get_schedule(self, *_args):
            return schedule

        def delete_schedule(self, *_args):
            self.deleted = True
            return True

    workflow_row = SimpleNamespace(
        version=1,
        is_active=True,
        machine_name="Client onboarding",
        definition={
            "states": [
                {
                    "name": "COMPLETED",
                    "on_state_action": {
                        "kind": "entity.activate_schedules",
                        "config": {"schedule_ids": [schedule.schedule_id]},
                    },
                }
            ]
        },
    )
    database = Database()
    workflow = SimpleNamespace(
        workflow_db=SimpleNamespace(list_state_machines=lambda **_kwargs: [workflow_row])
    )
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=object(),
        workflow_service_manager=workflow,
        background_jobs_service_manager=object(),
    )

    with pytest.raises(ConflictError, match="Client onboarding / COMPLETED"):
        manager.delete_schedule_for_actor(
            {"organization_id": "org-1", "user_id": "user-1"}, schedule.schedule_id
        )
    assert database.deleted is False


def test_queued_occurrence_cancels_after_schedule_or_target_is_removed() -> None:
    executor = EntityCreateAndEnrollExecutor()
    executor.bind_services(object(), object())
    executor.bind_schedules_service(
        SimpleNamespace(is_occurrence_active=lambda *_args: False)
    )
    result = executor.execute(
        ExecutorInput(
            entity_id="customer-1",
            entity_type="Customer",
            current_state="SCHEDULE_ANCHOR",
            fields={
                "org_id": ExecutorValue(kind=ValueKind.TEXT, value="org-1"),
                "_raw_config": ExecutorValue(
                    kind=ValueKind.TEXT,
                    value=json.dumps(
                        {
                            "schedule_id": "schedule-1",
                            "schedule_target_id": "target-1",
                            "anchor_entity_id": "customer-1",
                        }
                    ),
                ),
            },
        )
    )

    assert result.success is True
    assert result.data.outcome == "cancelled"

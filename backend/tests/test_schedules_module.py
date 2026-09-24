from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from exceptions import PersistenceError, ValidationError
from schedules.db_models import SchedulesModelService
from schedules.manager import SchedulesServiceManager, condition_matches, following_due_date, next_due_date
from executor.executors.entity_create_and_enroll import EntityCreateAndEnrollExecutor
from executor.models.interface import ExecutorInput, ExecutorValue, ValueKind
from schedules.models.interface import (
    RecurrenceRule,
    ScheduleCondition,
    ScheduleConditionOperator,
    ScheduleFrequency,
    ScheduleRecord,
    ScheduleTargetRecord,
    ScheduleTargetScope,
)
from schedules.models.request import ScheduleRunNowRequest, ScheduleUpdateRequest


def test_schedule_and_initial_targets_roll_back_together() -> None:
    class Session:
        rolled_back = False
        committed = False

        def add(self, row):
            self.schedule = row

        def flush(self):
            self.schedule.schedule_id = "schedule-1"

        def add_all(self, _rows):
            raise RuntimeError("target insert failed")

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            pass

    session = Session()
    database_manager = SimpleNamespace(
        postgres_db_service=lambda: SimpleNamespace(get_db_session=lambda: session)
    )
    service = SchedulesModelService(database_manager)

    with pytest.raises(PersistenceError, match="Unable to create schedule"):
        service.create_schedule_with_targets(
            {
                "organization_id": "org-1",
                "machine_name": "Filings",
                "name": "Monthly filings",
                "anchor_entity_type_id": "customer-type",
                "target_entity_type_id": "filing-type",
                "relation_def_id": "relation-1",
                "recurrence_json": {"frequency": "monthly", "day_of_month": 1, "months": []},
                "identifier_template": "{due_date}",
            },
            [
                {
                    "organization_id": "org-1",
                    "anchor_entity_id": "customer-1",
                    "next_due_date": date(2027, 9, 1),
                    "next_materialization_date": date(2027, 8, 1),
                }
            ],
        )

    assert session.rolled_back is True
    assert session.committed is False


def test_monthly_schedule_clamps_to_month_end() -> None:
    rule = RecurrenceRule(frequency=ScheduleFrequency.MONTHLY, day_of_month=31)
    assert next_due_date(rule, date(2027, 2, 1)) == date(2027, 2, 28)
    assert following_due_date(rule, date(2028, 1, 31)) == date(2028, 2, 29)


def test_quarterly_schedule_uses_configured_months() -> None:
    rule = RecurrenceRule(
        frequency=ScheduleFrequency.QUARTERLY,
        day_of_month=15,
        months=[1, 4, 7, 10],
    )
    assert next_due_date(rule, date(2027, 4, 16)) == date(2027, 7, 15)


def test_annual_schedule_rolls_to_next_year() -> None:
    rule = RecurrenceRule(
        frequency=ScheduleFrequency.ANNUAL,
        day_of_month=31,
        months=[3],
    )
    assert next_due_date(rule, date(2027, 4, 1)) == date(2028, 3, 31)


def test_one_time_schedule_has_exactly_one_occurrence() -> None:
    rule = RecurrenceRule(
        frequency=ScheduleFrequency.ONCE,
        occurs_on=date(2027, 5, 20),
    )
    assert next_due_date(rule, date(2027, 5, 1)) == date(2027, 5, 20)
    with pytest.raises(ValidationError, match="no remaining occurrence"):
        next_due_date(rule, date(2027, 5, 21))
    with pytest.raises(ValidationError, match="no following occurrence"):
        following_due_date(rule, date(2027, 5, 20))


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        (ScheduleConditionOperator.EQUALS, True),
        (ScheduleConditionOperator.NOT_EQUALS, False),
        (ScheduleConditionOperator.IN, True),
        (ScheduleConditionOperator.NOT_IN, False),
    ],
)
def test_schedule_conditions(operator: ScheduleConditionOperator, expected: bool) -> None:
    value = ["ABC", "XYZ"] if operator in {ScheduleConditionOperator.IN, ScheduleConditionOperator.NOT_IN} else "ABC"
    condition = ScheduleCondition(field="name", operator=operator, value=value)
    assert condition_matches(condition, {"name": "ABC"}) is expected


def test_quarterly_requires_four_months() -> None:
    with pytest.raises(ValueError, match="exactly four months"):
        RecurrenceRule(frequency=ScheduleFrequency.QUARTERLY, day_of_month=1, months=[3, 6, 9])


def test_lead_day_update_preserves_target_due_date() -> None:
    existing = ScheduleRecord(
        schedule_id="schedule-1",
        organization_id="org-1",
        machine_name="Filings",
        name="Monthly filings",
        anchor_entity_type_id="customer-type",
        target_entity_type_id="filing-type",
        relation_def_id="relation-1",
        target_scope=ScheduleTargetScope.SELECTED,
        recurrence=RecurrenceRule(frequency=ScheduleFrequency.MONTHLY, day_of_month=15),
        lead_days=30,
        timezone="UTC",
        identifier_template="{due_date}",
    )
    updated = existing.model_copy(update={"lead_days": 10})
    target = ScheduleTargetRecord(
        target_id="target-1",
        organization_id="org-1",
        schedule_id="schedule-1",
        anchor_entity_id="customer-1",
        next_due_date=date(2027, 12, 15),
        next_materialization_date=date(2027, 11, 15),
    )

    class Database:
        advances = []

        def get_schedule(self, *_args):
            return existing

        def update_schedule(self, *_args):
            return updated

        def list_targets(self, *_args):
            return [target]

        def advance_target(self, *args, **kwargs):
            self.advances.append((args, kwargs))

    database = Database()
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=object(),
        workflow_service_manager=object(),
        background_jobs_service_manager=object(),
    )

    manager.update_schedule_for_actor(
        {"organization_id": "org-1", "user_id": "user-1"},
        "schedule-1",
        ScheduleUpdateRequest(lead_days=10),
    )

    assert database.advances[0][1]["due_date"] == target.next_due_date
    assert database.advances[0][1]["materialization_date"] == date(2027, 12, 5)


def test_recurrence_update_never_moves_target_progress_backward() -> None:
    existing = ScheduleRecord(
        schedule_id="schedule-1",
        organization_id="org-1",
        machine_name="Filings",
        name="Monthly filings",
        anchor_entity_type_id="customer-type",
        target_entity_type_id="filing-type",
        relation_def_id="relation-1",
        target_scope=ScheduleTargetScope.SELECTED,
        recurrence=RecurrenceRule(frequency=ScheduleFrequency.MONTHLY, day_of_month=15),
        lead_days=30,
        timezone="UTC",
        identifier_template="{due_date}",
    )
    new_recurrence = RecurrenceRule(
        frequency=ScheduleFrequency.QUARTERLY,
        day_of_month=1,
        months=[1, 4, 7, 10],
    )
    updated = existing.model_copy(update={"recurrence": new_recurrence})
    targets = [
        ScheduleTargetRecord(
            target_id=f"target-{index}",
            organization_id="org-1",
            schedule_id="schedule-1",
            anchor_entity_id=f"customer-{index}",
            next_due_date=due,
            next_materialization_date=due - timedelta(days=30),
        )
        for index, due in enumerate((date(2027, 10, 15), date(2028, 4, 15)), start=1)
    ]

    class Database:
        advances = []

        def get_schedule(self, *_args):
            return existing

        def update_schedule(self, *_args):
            return updated

        def list_targets(self, *_args):
            return targets

        def advance_target(self, *args, **kwargs):
            self.advances.append((args, kwargs))

    database = Database()
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=object(),
        workflow_service_manager=object(),
        background_jobs_service_manager=object(),
    )

    manager.update_schedule_for_actor(
        {"organization_id": "org-1", "user_id": "user-1"},
        "schedule-1",
        ScheduleUpdateRequest(recurrence=new_recurrence),
    )

    recalculated_due_dates = [advance[1]["due_date"] for advance in database.advances]
    assert recalculated_due_dates == [date(2028, 1, 1), date(2028, 7, 1)]
    assert all(
        recalculated >= target.next_due_date
        for recalculated, target in zip(recalculated_due_dates, targets, strict=True)
    )


def test_create_and_enroll_executor_preserves_due_date_and_relation() -> None:
    class Entities:
        def __init__(self) -> None:
            self.request = None

        def list_entity_records(self, **_kwargs):
            return []

        def create_entity_record_for_actor(self, _actor, request):
            self.request = request
            return SimpleNamespace(entity_id="filing-1")

    class Workflow:
        def __init__(self) -> None:
            self.enrolled = None

        def enroll_entity_for_actor(self, _actor, machine_name, entity_id):
            self.enrolled = (machine_name, entity_id)

    entities = Entities()
    workflow = Workflow()
    completed: list[tuple[str, str, str]] = []
    executor = EntityCreateAndEnrollExecutor()
    executor.bind_services(entities, workflow)
    executor.bind_schedules_service(
        SimpleNamespace(
            is_occurrence_active=lambda *_args: True,
            complete_once_occurrence=lambda *args: completed.append(args),
        )
    )
    config = {
        "org_id": "org-1",
        "machine_name": "Filings",
        "target_entity_type_id": "filing-type",
        "anchor_entity_id": "customer-1",
        "schedule_id": "schedule-once",
        "schedule_target_id": "target-once",
        "complete_after_run": True,
        "due_date": "2027-03-31",
        "entity_data": {"identifier": "Q1 filing - ABC"},
    }

    result = executor.execute(
        ExecutorInput(
            entity_id="customer-1",
            entity_type="Customer",
            current_state="SCHEDULE_ANCHOR",
            fields={
                "_raw_config": ExecutorValue(kind=ValueKind.TEXT, value=json.dumps(config)),
            },
        )
    )

    assert result.success is True
    assert entities.request.due_date == date(2027, 3, 31)
    assert entities.request.source_entity_ids == ["customer-1"]
    assert workflow.enrolled == ("Filings", "filing-1")
    assert completed == [("org-1", "schedule-once", "target-once")]


def test_run_now_previews_conditions_and_queues_only_eligible_targets() -> None:
    schedule = ScheduleRecord(
        schedule_id="schedule-1",
        organization_id="org-1",
        machine_name="Filings",
        name="Monthly filings",
        anchor_entity_type_id="customer-type",
        target_entity_type_id="filing-type",
        relation_def_id="relation-1",
        target_scope=ScheduleTargetScope.SELECTED,
        recurrence=RecurrenceRule(frequency=ScheduleFrequency.MONTHLY, day_of_month=30),
        lead_days=30,
        timezone="UTC",
        identifier_template="{schedule_name} - {anchor_identifier} - {due_date}",
        conditions=[
            ScheduleCondition(
                field="name",
                operator=ScheduleConditionOperator.EQUALS,
                value="ABC",
            )
        ],
    )
    targets = [
        ScheduleTargetRecord(
            target_id="target-1",
            organization_id="org-1",
            schedule_id="schedule-1",
            anchor_entity_id="customer-1",
            next_due_date=date(2027, 9, 30),
            next_materialization_date=date(2027, 8, 31),
        ),
        ScheduleTargetRecord(
            target_id="target-2",
            organization_id="org-1",
            schedule_id="schedule-1",
            anchor_entity_id="customer-2",
            next_due_date=date(2027, 9, 30),
            next_materialization_date=date(2027, 8, 31),
        ),
    ]

    class Database:
        def __init__(self) -> None:
            self.advances = []

        def get_schedule(self, organization_id, schedule_id):
            return schedule if (organization_id, schedule_id) == ("org-1", "schedule-1") else None

        def list_targets(self, organization_id, schedule_id):
            assert (organization_id, schedule_id) == ("org-1", "schedule-1")
            return targets

        def advance_target(self, *args, **kwargs):
            self.advances.append((args, kwargs))

    class Entities:
        def get_entity_record(self, *, entity_id, **_kwargs):
            names = {"customer-1": "ABC", "customer-2": "XYZ"}
            return SimpleNamespace(data={"identifier": entity_id, "name": names[entity_id]})

    class BackgroundJobs:
        def __init__(self) -> None:
            self.calls = []

        def create_scheduled_action_run(self, **kwargs):
            self.calls.append(kwargs)
            return "run-1"

        def find_scheduled_action_run(self, **_kwargs):
            return None

    class AuditEvents:
        def __init__(self) -> None:
            self.events = []

        def emit_audit_event(self, **kwargs):
            self.events.append(kwargs)

    database = Database()
    background_jobs = BackgroundJobs()
    audit_events = AuditEvents()
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=Entities(),
        workflow_service_manager=object(),
        background_jobs_service_manager=background_jobs,
        audit_events_service=audit_events,
    )
    actor = {"organization_id": "org-1", "user_id": "user-1"}

    preview = manager.preview_run_now_for_actor(actor, "schedule-1")
    result = manager.run_now_for_actor(
        actor,
        "schedule-1",
        ScheduleRunNowRequest(invocation_id=preview.invocation_id),
    )

    assert preview.eligible == 1
    assert preview.skipped == 1
    assert preview.items[1].reason == "Condition does not match"
    assert result.queued == 1
    assert result.skipped == 1
    assert background_jobs.calls[0]["config_json"]["trigger_source"] == "manual"
    assert background_jobs.calls[0]["config_json"]["triggered_by"] == "user-1"
    assert background_jobs.calls[0]["config_json"]["run_invocation_id"] == preview.invocation_id
    assert background_jobs.calls[0]["idempotency_key"] == (
        "schedule:org-1:target-1:2027-09-30"
    )
    assert database.advances[0][1]["due_date"] == date(2027, 10, 30)
    assert database.advances[0][1]["result"] == "manual_scheduled"
    assert [event["event_type"] for event in audit_events.events] == [
        "SCHEDULE_RUN_REQUESTED",
        "SCHEDULE_RUN_QUEUED",
    ]
    assert all(event["actor_id"] == "user-1" for event in audit_events.events)
    assert all(event["correlation_id"] == preview.invocation_id for event in audit_events.events)


def test_run_now_retry_reuses_invocation_without_queuing_next_occurrence() -> None:
    schedule = ScheduleRecord(
        schedule_id="schedule-1",
        organization_id="org-1",
        machine_name="Filings",
        name="Monthly filings",
        anchor_entity_type_id="customer-type",
        target_entity_type_id="filing-type",
        relation_def_id="relation-1",
        target_scope=ScheduleTargetScope.SELECTED,
        recurrence=RecurrenceRule(frequency=ScheduleFrequency.MONTHLY, day_of_month=30),
        lead_days=30,
        timezone="UTC",
        identifier_template="{due_date}",
    )
    target = ScheduleTargetRecord(
        target_id="target-1",
        organization_id="org-1",
        schedule_id="schedule-1",
        anchor_entity_id="customer-1",
        next_due_date=date(2027, 10, 30),
        next_materialization_date=date(2027, 9, 30),
    )

    class Database:
        def get_schedule(self, *_args):
            return schedule

        def list_targets(self, *_args):
            return [target]

        def advance_target(self, *_args, **_kwargs):
            raise AssertionError("an already advanced invocation must not advance again")

    class BackgroundJobs:
        def find_scheduled_action_run(self, **_kwargs):
            return {
                "run_id": "run-1",
                "config_json": {"due_date": "2027-09-30"},
            }

        def create_scheduled_action_run(self, **_kwargs):
            raise AssertionError("an invocation retry must not create another run")

    manager = SchedulesServiceManager(
        Database(),
        entities_service_manager=object(),
        workflow_service_manager=object(),
        background_jobs_service_manager=BackgroundJobs(),
    )
    result = manager.run_now_for_actor(
        {"organization_id": "org-1", "user_id": "user-1"},
        "schedule-1",
        ScheduleRunNowRequest(invocation_id="invocation-1"),
    )

    assert result.run_ids == ["run-1"]
    assert result.invocation_id == "invocation-1"


def test_run_now_retry_repairs_partial_occurrence_batch_before_advancing() -> None:
    schedule = ScheduleRecord(
        schedule_id="schedule-1",
        organization_id="org-1",
        machine_name="Filings",
        name="Quarterly filings",
        anchor_entity_type_id="customer-type",
        target_entity_type_id="filing-type",
        relation_def_id="relation-1",
        target_scope=ScheduleTargetScope.SELECTED,
        recurrence=RecurrenceRule(
            frequency=ScheduleFrequency.QUARTERLY,
            day_of_month=31,
            months=[3, 6, 9, 12],
        ),
        occurrences_per_batch=3,
        lead_days=30,
        timezone="UTC",
        identifier_template="{anchor_identifier} - {due_date}",
    )
    target = ScheduleTargetRecord(
        target_id="target-1",
        organization_id="org-1",
        schedule_id="schedule-1",
        anchor_entity_id="customer-1",
        next_due_date=date(2027, 9, 30),
        next_materialization_date=date(2027, 8, 31),
    )

    class Database:
        advance = None

        def get_schedule(self, *_args):
            return schedule

        def list_targets(self, *_args):
            return [target]

        def advance_target(self, *args, **kwargs):
            self.advance = (args, kwargs)

    class Entities:
        def get_entity_record(self, **_kwargs):
            return SimpleNamespace(data={"identifier": "ABC"})

    class BackgroundJobs:
        calls = []

        def find_scheduled_action_run(self, **_kwargs):
            return {
                "run_id": "run-q3",
                "run_ids": ["run-q3"],
                "config_json": {"due_date": "2027-09-30"},
            }

        def create_scheduled_action_run(self, **kwargs):
            self.calls.append(kwargs)
            due = kwargs["config_json"]["due_date"]
            return {
                "2027-09-30": "run-q3",
                "2027-12-31": "run-q4",
                "2028-03-31": "run-q1",
            }[due]

    database = Database()
    background_jobs = BackgroundJobs()
    manager = SchedulesServiceManager(
        database,
        entities_service_manager=Entities(),
        workflow_service_manager=object(),
        background_jobs_service_manager=background_jobs,
    )

    result = manager.run_now_for_actor(
        {"organization_id": "org-1", "user_id": "user-1"},
        "schedule-1",
        ScheduleRunNowRequest(invocation_id="invocation-1"),
    )

    assert result.run_ids == ["run-q3", "run-q4", "run-q1"]
    assert [call["config_json"]["due_date"] for call in background_jobs.calls] == [
        "2027-09-30",
        "2027-12-31",
        "2028-03-31",
    ]
    assert database.advance[1]["due_date"] == date(2028, 6, 30)
    assert database.advance[1]["run_id"] == "run-q1"

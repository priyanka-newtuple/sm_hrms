"""Tests for the batched run-facts capability (`workflow/manager.py::run_facts_for_actor`).

Exercises `RunFactsRequest` validation and `WorkflowServiceManager._run_facts_item`'s state-tag,
terminal-transition, and due_at mapping directly. Both are pure functions over an already-loaded
row, so these run without Postgres — the row-fetch itself (`list_enrollment_summary_rows`, with
its existing `entity_ids` filter) is exercised indirectly via the enrollment-summary test suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from exceptions import ValidationError
from workflow.db_models import WorkflowEnrollmentSummaryRow
from workflow.manager import WorkflowServiceManager
from workflow.models.interface import (
    RUN_FACTS_DEVIATION_HISTORY_PAGE_SIZE,
    RUN_FACTS_ENTITY_ID_CAP,
    EntitySchema,
    State,
    StateMachineDefinition,
)
from workflow.models.request import RunFactsRequest


def _definition(done_state_tags: list[str]) -> StateMachineDefinition:
    return StateMachineDefinition(
        machine_key="wf_run_facts_test",
        name="wf_run_facts_test",
        description="",
        entity_type="run_facts_test_type",
        entity_schema=EntitySchema(entity_type="run_facts_test_type", fields=[]),
        states=[
            State(name="in_progress", tags=[], order=1),
            State(name="done", tags=done_state_tags, order=2),
        ],
        initial_state="in_progress",
        transitions=[],
    )


def _row(
    current_state: str,
    done_state_tags: list[str],
    *,
    definition: StateMachineDefinition | None = None,
    workflow_id: str = "wf-1",
) -> WorkflowEnrollmentSummaryRow:
    return WorkflowEnrollmentSummaryRow(
        state_id="state-1",
        organization_id="org-1",
        entity_id="entity-1",
        entity_type_id="type-1",
        entity_type="Widget",
        entity_data={},
        owner_id=None,
        assignee_id="user-1",
        due_date=None,
        entity_created_at=datetime(2026, 9, 1, tzinfo=UTC),
        entity_updated_at=None,
        archived_at=None,
        workflow_id=workflow_id,
        machine_name="qa_equipment_inspection",
        machine_display_name="QA Equipment Inspection",
        machine_version=1,
        machine_definition=definition or _definition(done_state_tags),
        current_state=current_state,
        state_version=1,
        enrollment_created_at=None,
        state_entered_at=datetime(2026, 9, 2, tzinfo=UTC),
        last_transition_at=datetime(2026, 9, 3, tzinfo=UTC),
        sla_due_at=datetime(2026, 9, 5, tzinfo=UTC),
    )


def _deviation_definition(initial_state: str = "in_progress") -> StateMachineDefinition:
    """A three-state machine with one state carrying the `deviation` tag."""
    return StateMachineDefinition(
        machine_key="wf_run_facts_test",
        name="wf_run_facts_test",
        description="",
        entity_type="run_facts_test_type",
        entity_schema=EntitySchema(entity_type="run_facts_test_type", fields=[]),
        states=[
            State(name="in_progress", tags=[], order=1),
            State(name="flagged", tags=["deviation"], order=2),
            State(name="done", tags=["terminal"], order=3),
        ],
        initial_state=initial_state,
        transitions=[],
    )


def test_terminal_state_reports_terminal_transition_at() -> None:
    row = _row("done", ["terminal"])
    item = WorkflowServiceManager._run_facts_item(row)
    assert item.machine_display_name == "QA Equipment Inspection"
    assert item.current_state_tags == ["terminal"]
    assert item.terminal_transition_at == row.last_transition_at
    assert item.due_at == row.sla_due_at
    assert item.assignee_id == "user-1"


def test_non_terminal_state_has_no_terminal_transition_at() -> None:
    row = _row("in_progress", ["terminal"])
    item = WorkflowServiceManager._run_facts_item(row)
    assert item.current_state_tags == []
    assert item.terminal_transition_at is None


def test_unknown_current_state_degrades_to_empty_tags() -> None:
    """A current_state absent from the definition (stale snapshot, renamed state)
    yields empty tags rather than raising."""
    row = _row("some_removed_state", ["terminal"])
    item = WorkflowServiceManager._run_facts_item(row)
    assert item.current_state_tags == []
    assert item.terminal_transition_at is None


def test_has_deviation_true_when_a_visited_state_carries_the_deviation_tag() -> None:
    row = _row("done", [], definition=_deviation_definition())
    item = WorkflowServiceManager._run_facts_item(row, {"flagged"})
    assert item.has_deviation is True


def test_has_deviation_true_for_the_current_state_with_no_transition_history() -> None:
    row = _row("flagged", [], definition=_deviation_definition())
    item = WorkflowServiceManager._run_facts_item(row, set())
    assert item.has_deviation is True


def test_has_deviation_false_when_no_visited_state_is_tagged_deviation() -> None:
    row = _row("done", [], definition=_deviation_definition())
    item = WorkflowServiceManager._run_facts_item(row, {"in_progress"})
    assert item.has_deviation is False


def test_has_deviation_defaults_false_with_no_visited_states_argument() -> None:
    row = _row("done", ["terminal"])
    item = WorkflowServiceManager._run_facts_item(row)
    assert item.has_deviation is False


def _run_facts_manager(rows, events):
    class FakeWorkflowDB:
        def list_enrollment_summary_rows(self, **_kwargs):
            return rows

    class FakeRolesManager:
        def get_workflow_access_scope(self, _actor):
            return None

    class FakeAuditEventsService:
        def __init__(self) -> None:
            self.calls = []

        def list_for_org_paginated(self, **kwargs):
            self.calls.append(kwargs)
            offset, limit = kwargs["offset"], kwargs["limit"]
            return events[offset : offset + limit], len(events)

    class FakeTransitionAudit:
        def __init__(self) -> None:
            self.audit_events_service = FakeAuditEventsService()

    manager = WorkflowServiceManager.__new__(WorkflowServiceManager)
    manager.workflow_db = FakeWorkflowDB()
    manager.roles_manager = FakeRolesManager()
    manager.transition_audit = FakeTransitionAudit()
    return manager


def _transition_event(
    entity_id: str,
    workflow_id: str,
    *,
    before_state: str | None = None,
    after_state: str | None = None,
):
    return SimpleNamespace(
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        metadata={"workflow_id": workflow_id},
    )


def test_run_facts_keeps_deviation_history_scoped_to_the_workflow_enrollment() -> None:
    """A state visited in workflow A must not mark workflow B as deviated."""
    row_a = _row("done", [], workflow_id="wf-a")
    row_b = _row("done", [], definition=_deviation_definition(), workflow_id="wf-b")
    manager = _run_facts_manager(
        [row_a, row_b],
        [_transition_event("entity-1", "wf-a", after_state="flagged")],
    )

    response = manager.run_facts_for_actor(
        {"organization_id": "org-1"}, RunFactsRequest(entity_ids=["entity-1"])
    )

    assert response.items[1].has_deviation is False


def test_run_facts_counts_a_deviation_tagged_initial_state_after_it_is_left() -> None:
    row = _row("done", [], definition=_deviation_definition(initial_state="flagged"))
    manager = _run_facts_manager([row], [])

    response = manager.run_facts_for_actor(
        {"organization_id": "org-1"}, RunFactsRequest(entity_ids=["entity-1"])
    )

    assert response.items[0].has_deviation is True
    assert manager.transition_audit.audit_events_service.calls == []


def test_run_facts_pages_past_a_full_batch_before_reporting_deviation_false() -> None:
    row = _row("done", [], definition=_deviation_definition())
    older_target_event = _transition_event("entity-1", "wf-1", after_state="flagged")
    events = [
        _transition_event("entity-1", "another-workflow", after_state="done")
        for _ in range(RUN_FACTS_DEVIATION_HISTORY_PAGE_SIZE)
    ] + [older_target_event]
    manager = _run_facts_manager([row], events)

    response = manager.run_facts_for_actor(
        {"organization_id": "org-1"}, RunFactsRequest(entity_ids=["entity-1"])
    )

    assert response.items[0].has_deviation is True
    assert [call["offset"] for call in manager.transition_audit.audit_events_service.calls] == [
        0,
        RUN_FACTS_DEVIATION_HISTORY_PAGE_SIZE,
    ]


def test_run_facts_request_dedupes_and_trims() -> None:
    payload = RunFactsRequest(entity_ids=["a", "b", "a", " c "])
    assert payload.entity_ids == ["a", "b", "c"]


def test_run_facts_request_rejects_empty_batch() -> None:
    with pytest.raises(Exception):
        RunFactsRequest(entity_ids=[])


def test_run_facts_request_rejects_batches_over_the_cap() -> None:
    with pytest.raises(Exception):
        RunFactsRequest(entity_ids=[f"id-{i}" for i in range(RUN_FACTS_ENTITY_ID_CAP + 1)])


def test_run_facts_for_actor_scopes_by_org_and_role_and_maps_every_row() -> None:
    """End-to-end through run_facts_for_actor: org derivation, access-scope pass-through,
    the exact limit passed, and the row -> RunFactsItem mapping, all in one call."""
    calls: dict[str, object] = {}

    class FakeWorkflowDB:
        def list_enrollment_summary_rows(self, **kwargs):
            calls.update(kwargs)
            return [_row("done", ["terminal"]), _row("in_progress", [])]

    class FakeRolesManager:
        def get_workflow_access_scope(self, actor):
            return {"qa_equipment_inspection"}

    class FakeAuditEventsService:
        def list_for_org_paginated(self, **kwargs):
            return [], 0

    class FakeTransitionAudit:
        def __init__(self) -> None:
            self.audit_events_service = FakeAuditEventsService()

    manager = WorkflowServiceManager.__new__(WorkflowServiceManager)
    manager.workflow_db = FakeWorkflowDB()
    manager.roles_manager = FakeRolesManager()
    manager.transition_audit = FakeTransitionAudit()

    actor = {"user_id": "u1", "organization_id": "org-1"}
    payload = RunFactsRequest(entity_ids=["entity-1", "entity-2", "entity-1"])
    response = manager.run_facts_for_actor(actor, payload)

    assert calls["organization_id"] == "org-1"
    assert calls["entity_ids"] == {"entity-1", "entity-2"}
    assert calls["machine_names"] == {"qa_equipment_inspection"}
    assert calls["limit"] == 2  # deduped payload, not the raw 3 the caller sent
    assert [item.current_state for item in response.items] == ["done", "in_progress"]
    assert response.items[0].terminal_transition_at is not None


def test_run_facts_for_actor_rejects_a_missing_organization_id() -> None:
    manager = WorkflowServiceManager.__new__(WorkflowServiceManager)
    payload = RunFactsRequest(entity_ids=["entity-1"])
    with pytest.raises(ValidationError):
        manager.run_facts_for_actor({"user_id": "u1"}, payload)

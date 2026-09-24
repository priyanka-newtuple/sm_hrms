"""Owner/assignee names filled in on enrollment summaries.

Rows only carried user ids and the UI looked the names up itself, so Agent Mode
had no way to resolve them and failed when asked for an assignee's name.
"""

from __future__ import annotations

from typing import Any

from workflow_manager_factory import make_workflow_manager

from workflow.models.response import WorkflowEnrollmentSummary


class _UserServiceFake:
    """Returns display info the way the real one does: a (name, ...) tuple."""

    def __init__(self, names: dict[str, str], *, raises: bool = False) -> None:
        self.names = names
        self.raises = raises
        self.lookups: list[str] = []

    def get_user_display_info(self, user_id: str) -> tuple[str | None, Any]:
        if self.raises:
            raise RuntimeError("user service unavailable")
        self.lookups.append(user_id)
        return self.names.get(user_id), None


def _summary(entity_id: str, *, owner_id: str | None, assignee_id: str | None):
    return WorkflowEnrollmentSummary(
        state_id=f"state-{entity_id}",
        entity_id=entity_id,
        entity_type_id="type-1",
        entity_type="ticket",
        organization_id="org-1",
        workflow_id="wf-1",
        machine_name="wf",
        machine_display_name="Workflow",
        machine_version=1,
        current_state="INPROGRESS",
        display_name=entity_id,
        owner_id=owner_id,
        assignee_id=assignee_id,
    )


def test_owner_and_assignee_names_are_resolved() -> None:
    users = _UserServiceFake({"u-1": "Vinay Kumar", "u-2": "Priya Sharma"})
    manager = make_workflow_manager(user_service_manager=users)
    items = [
        _summary("e-1", owner_id="u-1", assignee_id="u-2"),
        _summary("e-2", owner_id="u-2", assignee_id=None),
    ]

    manager._attach_assignee_owner_names(items)

    assert items[0].owner_name == "Vinay Kumar"
    assert items[0].assignee_name == "Priya Sharma"
    assert items[1].owner_name == "Priya Sharma"
    assert items[1].assignee_name is None
    # Distinct ids only: u-2 appears three times across the page, looked up once.
    assert sorted(users.lookups) == ["u-1", "u-2"]


def test_unknown_user_leaves_the_name_unset_rather_than_guessing() -> None:
    users = _UserServiceFake({})
    manager = make_workflow_manager(user_service_manager=users)
    items = [_summary("e-1", owner_id="ghost", assignee_id=None)]

    manager._attach_assignee_owner_names(items)

    assert items[0].owner_name is None


def test_user_service_failure_degrades_instead_of_breaking_the_listing() -> None:
    # Names are a convenience; a lookup failure must never fail the board.
    users = _UserServiceFake({"u-1": "Vinay Kumar"}, raises=True)
    manager = make_workflow_manager(user_service_manager=users)
    items = [_summary("e-1", owner_id="u-1", assignee_id="u-1")]

    manager._attach_assignee_owner_names(items)

    assert items[0].owner_name is None
    assert items[0].assignee_name is None


def test_no_user_service_configured_is_a_no_op() -> None:
    manager = make_workflow_manager(user_service_manager=None)
    items = [_summary("e-1", owner_id="u-1", assignee_id="u-1")]

    manager._attach_assignee_owner_names(items)

    assert items[0].owner_name is None


def test_rows_without_ids_skip_the_lookup_entirely() -> None:
    users = _UserServiceFake({"u-1": "Vinay Kumar"})
    manager = make_workflow_manager(user_service_manager=users)
    items = [_summary("e-1", owner_id=None, assignee_id=None)]

    manager._attach_assignee_owner_names(items)

    assert users.lookups == []

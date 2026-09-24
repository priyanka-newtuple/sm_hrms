"""Tests for the per-workflow Kanban "board display fields" feature.

Covers the three gaps flagged on PR #493: the model service's get/upsert
round-trip, the manager's actor-facing existence/scope checks, and the
request validator's field-count/blank/dedupe rules.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from exceptions import NotFoundError
from workflow.db_models import WorkflowModelService
from workflow.models.request import (
    MAX_BOARD_DISPLAY_FIELDS,
    WorkflowBoardDisplayFieldsUpdateRequest,
)
from workflow_manager_factory import UnrestrictedRolesManager, make_workflow_manager

_ORG_ID = "test-org-board-fields"


class _FakeWorkflowDb:
    """Minimal double for the manager-level tests: only `get_active_state_machine`
    is faked (`_assert_workflow_exists`'s one dependency, and not memory-mode
    capable on the real service — see `create_state_machine_published`).
    The board-display-fields methods delegate to a real `WorkflowModelService`
    in memory mode, since those already work standalone.
    """

    def __init__(self) -> None:
        self._real = WorkflowModelService(None)
        self._published: set[tuple[str, str]] = set()

    def publish(self, organization_id: str, machine_name: str) -> None:
        self._published.add((organization_id, machine_name))

    def get_active_state_machine(self, *, organization_id: str, machine_name: str):
        if (organization_id, machine_name) in self._published:
            return SimpleNamespace(machine_name=machine_name)
        return None

    def get_board_display_fields(self, **kwargs: object):
        return self._real.get_board_display_fields(**kwargs)

    def upsert_board_display_fields(self, **kwargs: object):
        return self._real.upsert_board_display_fields(**kwargs)


def _actor(user_id: str = "u1") -> dict[str, object]:
    return {"organization_id": _ORG_ID, "user_id": user_id, "roles": ["admin"]}


# --- WorkflowBoardDisplayFieldsUpdateRequest validation -----------------------


def test_update_request_rejects_more_than_max_fields() -> None:
    with pytest.raises(PydanticValidationError, match=f"more than {MAX_BOARD_DISPLAY_FIELDS}"):
        WorkflowBoardDisplayFieldsUpdateRequest(
            machine_name="wf1",
            fields=["a", "b", "c", "d"],
        )


def test_update_request_rejects_blank_field_id() -> None:
    with pytest.raises(PydanticValidationError, match="fields must be a non-empty string"):
        WorkflowBoardDisplayFieldsUpdateRequest(machine_name="wf1", fields=["priority", "   "])


def test_update_request_dedupes_fields_preserving_first_occurrence_order() -> None:
    request = WorkflowBoardDisplayFieldsUpdateRequest(
        machine_name="wf1",
        fields=["priority", "sprint", "priority"],
    )
    assert request.fields == ["priority", "sprint"]


def test_update_request_rejects_blank_machine_name() -> None:
    with pytest.raises(PydanticValidationError, match="machine_name must be a non-empty string"):
        WorkflowBoardDisplayFieldsUpdateRequest(machine_name="  ", fields=[])


# --- WorkflowModelService.get_board_display_fields / upsert_board_display_fields ---


def test_get_board_display_fields_returns_empty_record_when_unconfigured() -> None:
    db = WorkflowModelService(None)
    record = db.get_board_display_fields(organization_id=_ORG_ID, machine_name="wf1")
    assert record.machine_name == "wf1"
    assert record.fields == []
    assert record.updated_at is None
    assert record.updated_by is None


def test_upsert_and_get_board_display_fields_round_trip() -> None:
    db = WorkflowModelService(None)
    saved = db.upsert_board_display_fields(
        organization_id=_ORG_ID,
        machine_name="wf1",
        fields=["priority", "story_points"],
        updated_by="user-1",
    )
    assert saved.fields == ["priority", "story_points"]
    assert saved.updated_by == "user-1"

    fetched = db.get_board_display_fields(organization_id=_ORG_ID, machine_name="wf1")
    assert fetched.fields == ["priority", "story_points"]
    assert fetched.updated_by == "user-1"


def test_upsert_board_display_fields_replaces_previous_selection() -> None:
    db = WorkflowModelService(None)
    db.upsert_board_display_fields(
        organization_id=_ORG_ID, machine_name="wf1", fields=["priority"], updated_by="user-1"
    )
    replaced = db.upsert_board_display_fields(
        organization_id=_ORG_ID, machine_name="wf1", fields=["sprint"], updated_by="user-2"
    )
    assert replaced.fields == ["sprint"]
    assert replaced.updated_by == "user-2"


def test_board_display_fields_are_independent_per_workflow() -> None:
    """The whole point of this feature: two workflows never share a selection,
    even when configured back-to-back against the same model service."""
    db = WorkflowModelService(None)
    db.upsert_board_display_fields(
        organization_id=_ORG_ID, machine_name="workflow_a", fields=["priority"], updated_by="u1"
    )
    db.upsert_board_display_fields(
        organization_id=_ORG_ID, machine_name="workflow_b", fields=["labels", "is_blocked"], updated_by="u1"
    )
    assert db.get_board_display_fields(organization_id=_ORG_ID, machine_name="workflow_a").fields == ["priority"]
    assert db.get_board_display_fields(organization_id=_ORG_ID, machine_name="workflow_b").fields == [
        "labels",
        "is_blocked",
    ]


# --- WorkflowServiceManager.get_board_display_fields_for_actor / update_... ---


def test_get_board_display_fields_for_actor_returns_empty_when_unconfigured() -> None:
    db = _FakeWorkflowDb()
    db.publish(_ORG_ID, "wf1")
    manager = make_workflow_manager(db)

    record = manager.get_board_display_fields_for_actor(_actor(), "wf1")
    assert record.fields == []


def test_update_board_display_fields_for_actor_persists_and_stamps_actor() -> None:
    db = _FakeWorkflowDb()
    db.publish(_ORG_ID, "wf1")
    manager = make_workflow_manager(db)

    updated = manager.update_board_display_fields_for_actor(
        _actor("user-42"),
        WorkflowBoardDisplayFieldsUpdateRequest(machine_name="wf1", fields=["priority", "sprint"]),
    )
    assert updated.fields == ["priority", "sprint"]
    assert updated.updated_by == "user-42"

    refetched = manager.get_board_display_fields_for_actor(_actor(), "wf1")
    assert refetched.fields == ["priority", "sprint"]


def test_get_board_display_fields_for_unknown_workflow_raises_not_found() -> None:
    db = _FakeWorkflowDb()
    manager = make_workflow_manager(db)

    with pytest.raises(NotFoundError, match="unknown_workflow"):
        manager.get_board_display_fields_for_actor(_actor(), "unknown_workflow")


def test_update_board_display_fields_for_unknown_workflow_raises_not_found() -> None:
    db = _FakeWorkflowDb()
    manager = make_workflow_manager(db)

    with pytest.raises(NotFoundError, match="unknown_workflow"):
        manager.update_board_display_fields_for_actor(
            _actor(),
            WorkflowBoardDisplayFieldsUpdateRequest(machine_name="unknown_workflow", fields=["priority"]),
        )


def test_board_display_fields_denied_for_out_of_scope_workflow() -> None:
    """A workflow that exists but isn't in the actor's RBAC scope 404s rather
    than 403s, matching every other actor-facing workflow lookup."""
    db = _FakeWorkflowDb()
    db.publish(_ORG_ID, "wf_visible")
    db.publish(_ORG_ID, "wf_hidden")

    class _RestrictedRoles(UnrestrictedRolesManager):
        def get_workflow_access_scope(self, _actor: object) -> set[str] | None:
            return {"wf_visible"}

    manager = make_workflow_manager(db, roles_manager=_RestrictedRoles())

    with pytest.raises(NotFoundError, match="wf_hidden"):
        manager.get_board_display_fields_for_actor(_actor(), "wf_hidden")
    with pytest.raises(NotFoundError, match="wf_hidden"):
        manager.update_board_display_fields_for_actor(
            _actor(),
            WorkflowBoardDisplayFieldsUpdateRequest(machine_name="wf_hidden", fields=["priority"]),
        )

    # The in-scope workflow is unaffected.
    assert manager.get_board_display_fields_for_actor(_actor(), "wf_visible").fields == []

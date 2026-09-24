"""Unit tests for the entity.assign_user workflow action.

Covers the executor's own decisions — config reading, configured-user
validation, outcome classification and idempotency — with the entities and user
managers as doubles. The assignment behaviour those managers provide (audit
metadata, originator resolution, real membership rules) is covered against real
Postgres in `test_entity_assignee_originator.py`.

Also covers the publish-time validation that stops a broken action from
reaching the worker at all.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from workflow_manager_factory import make_workflow_manager

from entities.models.interface import AssignmentRejection, AssignmentSource
from exceptions import ValidationError
from executor.executors.entity_assign_user import VERDICT_REASONS, EntityAssignUserExecutor
from executor.manager import ExecutorServiceManager
from executor.models.interface import (
    ENTITY_ASSIGN_USER_ACTION_KIND,
    ROUTABLE_ASSIGN_USER_OUTCOMES,
    AssignUserOutcome,
    ExecutorInput,
    ExecutorValue,
    ValueKind,
    assign_user_config_problem,
)
from user.models.interface import OrgMemberAssignability, OrgMembershipVerdict
from workflow.models.interface import (
    StateAction,
    StateMachineDefinition,
    ValidationIssueCode,
)
from workflow.services.definition_analysis import DefinitionAnalysisService

ORG = "org-1"
ENTITY = "entity-1"
RUN = "run-9"


class _FakeRecord:
    """Only the attribute the executor reads off an entity response."""

    def __init__(self, assignee_id: str | None) -> None:
        self.assignee_id = assignee_id


class _FakeEntities:
    """Records the assignment call and replays a scripted before/after."""

    def __init__(
        self,
        *,
        before: str | None = None,
        after: str | None = "user-target",
        raises: Exception | None = None,
    ) -> None:
        self.before = before
        self.after = after
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def get_entity_record_for_actor(
        self, actor: dict[str, Any], entity_id: str, organization_id: str | None = None
    ) -> _FakeRecord:
        return _FakeRecord(self.before)

    def set_entity_assignee_for_actor(
        self,
        actor: dict[str, Any],
        entity_id: str,
        assignee_id: str | None,
        organization_id: str | None = None,
        **kwargs: Any,
    ) -> _FakeRecord:
        if self.raises is not None:
            raise self.raises
        self.calls.append(
            {
                "actor": actor,
                "entity_id": entity_id,
                "assignee_id": assignee_id,
                "organization_id": organization_id,
                **kwargs,
            }
        )
        return _FakeRecord(self.after)


class _FakeUsers:
    """Returns a fixed assignability verdict for any user."""

    def __init__(
        self,
        verdict: OrgMembershipVerdict = OrgMembershipVerdict.ASSIGNABLE,
        full_name: str = "Mohit Rana",
    ) -> None:
        self.verdict = verdict
        self.full_name = full_name
        self.asked: list[tuple[str | None, str]] = []

    def get_org_member_assignability(
        self, user_id: str | None, organization_id: str
    ) -> OrgMemberAssignability:
        self.asked.append((user_id, organization_id))
        return OrgMemberAssignability(
            user_id=user_id or "", full_name=self.full_name, verdict=self.verdict
        )


def _input(config: dict[str, Any], *, org_id: str = ORG) -> ExecutorInput:
    return ExecutorInput(
        entity_id=ENTITY,
        entity_type="Patient",
        current_state="INTAKE",
        fields={
            "org_id": ExecutorValue(kind=ValueKind.TEXT, value=org_id),
            "run_id": ExecutorValue(kind=ValueKind.TEXT, value=RUN),
            "_raw_config": ExecutorValue(kind=ValueKind.TEXT, value=json.dumps(config)),
        },
    )


def _executor(entities: Any, users: Any) -> EntityAssignUserExecutor:
    executor = EntityAssignUserExecutor()
    executor.bind_services(entities, users)
    return executor


# ── Registration ────────────────────────────────────────────────────────────


def test_executor_is_registered_and_reported_as_runnable() -> None:
    """The action must be executable, or publish validation would reject it."""
    manager = ExecutorServiceManager(
        _database_service_manager=object(), _mail_service=object()
    )
    assert ENTITY_ASSIGN_USER_ACTION_KIND in manager.registered_action_kinds()
    assert manager.get_executor(ENTITY_ASSIGN_USER_ACTION_KIND) is not None


def test_binding_hands_the_managers_to_the_executor() -> None:
    """The action is useless unless main.py's late binding actually reaches it."""
    manager = ExecutorServiceManager(
        _database_service_manager=object(), _mail_service=object()
    )
    entities, users = object(), object()

    manager.bind_assign_user_services(entities, users)

    executor = manager.get_executor(ENTITY_ASSIGN_USER_ACTION_KIND)
    assert executor.entities_service is entities
    assert executor.user_service is users


def test_only_routable_outcomes_are_declared() -> None:
    """`failed` is the engine's failure policy's business, not a routable outcome.

    Declaring it would put a dropdown in the builder that the failure policy
    overrides anyway.
    """
    declared = set(EntityAssignUserExecutor().definition.supported_outcomes)

    assert declared == {str(outcome) for outcome in ROUTABLE_ASSIGN_USER_OUTCOMES}
    assert str(AssignUserOutcome.FAILED) not in declared
    assert declared == {str(o) for o in AssignUserOutcome} - {str(AssignUserOutcome.FAILED)}


# ── Configured user ─────────────────────────────────────────────────────────


def test_configured_user_is_assigned() -> None:
    entities = _FakeEntities(before=None, after="user-target")
    executor = _executor(entities, _FakeUsers())

    result = executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    assert result.success is True
    assert result.data.outcome == str(AssignUserOutcome.ASSIGNED)
    assert entities.calls[0]["assignee_id"] == "user-target"
    assert entities.calls[0]["assign_to_originator"] is False


def test_configured_user_assignment_records_workflow_context() -> None:
    """Audit metadata must show a workflow action made the change, and which run."""
    entities = _FakeEntities(before=None, after="user-target")
    executor = _executor(entities, _FakeUsers())

    executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    call = entities.calls[0]
    assert call["assignment_source"] is AssignmentSource.WORKFLOW_ACTION
    assert call["action_run_id"] == RUN


def test_worker_assigns_as_a_system_actor_not_as_a_human() -> None:
    entities = _FakeEntities(before=None, after="user-target")
    executor = _executor(entities, _FakeUsers())

    executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    actor = entities.calls[0]["actor"]
    assert actor["actor_type"] == "system"
    assert actor["user_id"] is None
    assert actor["organization_id"] == ORG


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (OrgMembershipVerdict.NOT_FOUND, AssignUserOutcome.USER_NOT_FOUND),
        (OrgMembershipVerdict.NOT_A_MEMBER, AssignUserOutcome.USER_NOT_FOUND),
        (OrgMembershipVerdict.SUSPENDED, AssignUserOutcome.USER_SUSPENDED),
        (OrgMembershipVerdict.INACTIVE_ACCOUNT, AssignUserOutcome.USER_SUSPENDED),
    ],
)
def test_unassignable_configured_user_is_refused_without_writing(
    verdict: OrgMembershipVerdict, expected: AssignUserOutcome
) -> None:
    entities = _FakeEntities()
    executor = _executor(entities, _FakeUsers(verdict=verdict))

    result = executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    # Reported as a completed run so the engine reads the outcome and can fire
    # the transition the author mapped to it; it only routes successful results.
    assert result.success is True
    assert result.data.outcome == str(expected)
    assert entities.calls == []
    # Drawn as "made no change" — true for every verdict, not just suspension.
    assert result.data.meta["refused"] is True


def test_refusal_reason_is_one_short_line_naming_nobody() -> None:
    """The reason lands on the record's activity timeline, which anyone with
    read access sees. It must not carry the person's name (the timeline
    resolves that from the id, so it stays current) nor their id, and it must
    not leak the raw verdict enum."""
    executor = _executor(
        _FakeEntities(), _FakeUsers(verdict=OrgMembershipVerdict.SUSPENDED)
    )

    result = executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    assert result.message == "User is suspended."
    assert result.data.meta["reason"] == "User is suspended."
    assert "Mohit Rana" not in result.message
    assert "user-target" not in result.message
    assert "suspended)" not in result.message


@pytest.mark.parametrize(
    "verdict",
    [
        OrgMembershipVerdict.NOT_FOUND,
        OrgMembershipVerdict.NOT_A_MEMBER,
        OrgMembershipVerdict.SUSPENDED,
        OrgMembershipVerdict.INACTIVE_ACCOUNT,
    ],
)
def test_every_refusal_verdict_has_its_own_readable_reason(
    verdict: OrgMembershipVerdict,
) -> None:
    """A verdict without an entry would fall back to printing the enum."""
    executor = _executor(_FakeEntities(), _FakeUsers(verdict=verdict))

    message = executor.execute(
        _input({"assignment_type": "user", "user_id": "user-target"})
    ).message

    assert message == VERDICT_REASONS[verdict]
    assert message[0].isupper() and message.endswith(".")
    # The old text appended the raw verdict as "(suspended)". A bracket here
    # means an enum leaked back into the sentence.
    assert "(" not in message


def test_a_refusal_is_flagged_for_the_timeline_but_stays_a_successful_run() -> None:
    """`refused` changes how the timeline draws the event, nothing else.

    The run must stay successful: outcome routing only happens for successful
    responses, so failing it here would break routing on a refusal and hand the
    record to the failure policy instead.
    """
    executor = _executor(_FakeEntities(), _FakeUsers(verdict=OrgMembershipVerdict.SUSPENDED))

    result = executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    assert result.data.meta["refused"] is True
    assert result.success is True


def test_a_real_assignment_is_not_flagged_as_refused() -> None:
    executor = _executor(_FakeEntities(before=None, after="user-target"), _FakeUsers())

    result = executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    assert result.data.meta.get("refused") is None
    assert result.data.outcome == str(AssignUserOutcome.ASSIGNED)


def test_configured_user_is_checked_against_the_records_organization() -> None:
    users = _FakeUsers()
    executor = _executor(_FakeEntities(), users)

    executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    assert users.asked == [("user-target", ORG)]


# ── Originator ──────────────────────────────────────────────────────────────


def test_originator_mode_delegates_resolution_to_the_entities_manager() -> None:
    """The executor must not resolve the creator itself, nor pre-check them."""
    entities = _FakeEntities(before=None, after="creator-1")
    users = _FakeUsers()
    executor = _executor(entities, users)

    result = executor.execute(_input({"assignment_type": "originator"}))

    assert result.data.outcome == str(AssignUserOutcome.ASSIGNED)
    assert entities.calls[0]["assign_to_originator"] is True
    assert entities.calls[0]["assignee_id"] is None
    assert users.asked == []


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (AssignmentRejection.ORIGINATOR_NOT_FOUND, AssignUserOutcome.ORIGINATOR_NOT_FOUND),
        (AssignmentRejection.ORIGINATOR_USER_MISSING, AssignUserOutcome.ORIGINATOR_NOT_FOUND),
        (AssignmentRejection.ORIGINATOR_NOT_A_MEMBER, AssignUserOutcome.USER_NOT_FOUND),
        (AssignmentRejection.ORIGINATOR_SUSPENDED, AssignUserOutcome.USER_SUSPENDED),
        (
            AssignmentRejection.ORIGINATOR_INACTIVE_ACCOUNT,
            AssignUserOutcome.USER_SUSPENDED,
        ),
    ],
)
def test_originator_rejection_maps_to_its_own_outcome(
    code: str, expected: AssignUserOutcome
) -> None:
    """Routing keys off the error code, so each refusal stays distinguishable."""
    entities = _FakeEntities(raises=ValidationError("nope", code=code))
    executor = _executor(entities, _FakeUsers())

    result = executor.execute(_input({"assignment_type": "originator"}))

    assert result.success is True
    assert result.data.outcome == str(expected)
    # Every refusal, originator ones included, is drawn as "made no change".
    assert result.data.meta["refused"] is True


def test_refusals_are_routable_but_real_failures_are_not() -> None:
    """The success flag decides whether the engine reads the outcome at all.

    A target who cannot take work is an answer the author can route on, so it
    must come back successful. A genuine breakage must not, so the failure
    policy still governs it.
    """
    suspended = _executor(
        _FakeEntities(), _FakeUsers(verdict=OrgMembershipVerdict.SUSPENDED)
    ).execute(_input({"assignment_type": "user", "user_id": "u1"}))
    broken = _executor(
        _FakeEntities(raises=RuntimeError("database on fire")), _FakeUsers()
    ).execute(_input({"assignment_type": "originator"}))

    assert (suspended.success, suspended.data.outcome) == (
        True,
        str(AssignUserOutcome.USER_SUSPENDED),
    )
    assert (broken.success, broken.data.outcome) == (False, str(AssignUserOutcome.FAILED))


def test_unrecognized_rejection_code_degrades_to_failed() -> None:
    entities = _FakeEntities(raises=ValidationError("nope", code="something_new"))
    executor = _executor(entities, _FakeUsers())

    result = executor.execute(_input({"assignment_type": "originator"}))

    assert result.data.outcome == str(AssignUserOutcome.FAILED)


# ── Idempotency and failure ─────────────────────────────────────────────────


def test_assigning_the_current_holder_reports_already_assigned() -> None:
    """A retried worker run must not look like a fresh assignment."""
    entities = _FakeEntities(before="user-target", after="user-target")
    executor = _executor(entities, _FakeUsers())

    result = executor.execute(_input({"assignment_type": "user", "user_id": "user-target"}))

    assert result.success is True
    assert result.data.outcome == str(AssignUserOutcome.ALREADY_ASSIGNED)


def test_unexpected_error_is_reported_as_failed() -> None:
    entities = _FakeEntities(raises=RuntimeError("database on fire"))
    executor = _executor(entities, _FakeUsers())

    result = executor.execute(_input({"assignment_type": "originator"}))

    assert result.success is False
    assert result.data.outcome == str(AssignUserOutcome.FAILED)
    # A crash must stay a crash: red in the timeline, not the amber "made no
    # change" a refusal gets. Flagging it here would hide a real fault behind a
    # business-finding style.
    assert result.data.meta.get("refused") is None


def test_unbound_services_fail_rather_than_crash() -> None:
    result = EntityAssignUserExecutor().execute(_input({"assignment_type": "originator"}))
    assert result.data.outcome == str(AssignUserOutcome.FAILED)


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"assignment_type": ""},
        {"assignment_type": "nonsense"},
        {"assignment_type": "user"},
        {"assignment_type": "user", "user_id": "   "},
    ],
)
def test_malformed_config_fails_without_assigning(config: dict[str, Any]) -> None:
    entities = _FakeEntities()
    executor = _executor(entities, _FakeUsers())

    result = executor.execute(_input(config))

    assert result.success is False
    assert result.data.outcome == str(AssignUserOutcome.FAILED)
    assert entities.calls == []


# ── Config validation rule ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "config",
    [
        {"assignment_type": "originator"},
        {"assignment_type": "user", "user_id": "u1"},
    ],
)
def test_valid_configs_report_no_problem(config: dict[str, Any]) -> None:
    assert assign_user_config_problem(config) is None


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"assignment_type": "nonsense"},
        {"assignment_type": "user"},
        {"assignment_type": "originator", "user_id": "u1"},
    ],
)
def test_invalid_configs_report_a_problem(config: dict[str, Any]) -> None:
    problem = assign_user_config_problem(config)
    assert problem is not None and problem.strip() != ""


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"assignment_type": "nonsense"},
        {"assignment_type": "user"},
        {"assignment_type": "originator", "user_id": "u1"},
    ],
)
def test_setup_problems_read_as_sentences_not_as_config_keys(
    config: dict[str, Any],
) -> None:
    """A workflow author sees these in the builder and on a failed run.

    They are embedded as `State 'X': {problem}`, so each must stand on its own
    as a sentence and must never name an internal config key.
    """
    problem = assign_user_config_problem(config)

    assert problem is not None
    assert problem[0].isupper() and problem.endswith(".")
    assert "assignment_type" not in problem
    assert "user_id" not in problem


# ── Publish-time validation ─────────────────────────────────────────────────


def _definition(action: StateAction) -> StateMachineDefinition:
    """Smallest definition that passes the unrelated structural rules.

    Those rules must stay satisfied so a failure here can only come from the
    action checks under test.
    """
    return StateMachineDefinition.model_validate(
        {
            "machine_key": "patient_intake",
            "name": "Patient Intake",
            "entity_type": "Patient",
            "entity_schema": {"entity_type": "Patient", "fields": []},
            "initial_state": "INTAKE",
            "states": [
                {
                    "name": "INTAKE",
                    "tags": ["initial"],
                    "on_state_actions": [action.model_dump()],
                },
                {"name": "DONE", "tags": ["terminal"]},
            ],
            "transitions": [
                {
                    "key": "finish",
                    "trigger": "finish",
                    "label": "Finish",
                    "from": "INTAKE",
                    "to_state": "DONE",
                }
            ],
        }
    )


def _codes(
    definition: StateMachineDefinition, known: frozenset[str] | None = None
) -> list[str]:
    issues = DefinitionAnalysisService().validate_states(definition, known_action_kinds=known)
    return [issue.code for issue in issues]


def test_publish_validation_accepts_a_well_configured_action() -> None:
    definition = _definition(
        StateAction(
            kind=ENTITY_ASSIGN_USER_ACTION_KIND,
            config={"assignment_type": "user", "user_id": "u1"},
        )
    )
    assert _codes(definition, frozenset({ENTITY_ASSIGN_USER_ACTION_KIND})) == []


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"assignment_type": "nonsense"},
        {"assignment_type": "user"},
        {"assignment_type": "originator", "user_id": "u1"},
    ],
)
def test_publish_validation_rejects_a_broken_action_config(config: dict[str, Any]) -> None:
    definition = _definition(
        StateAction(kind=ENTITY_ASSIGN_USER_ACTION_KIND, config=config)
    )
    assert ValidationIssueCode.INVALID_ACTION_CONFIG in _codes(
        definition, frozenset({ENTITY_ASSIGN_USER_ACTION_KIND})
    )


def test_publish_validation_rejects_an_action_the_runtime_cannot_run() -> None:
    definition = _definition(StateAction(kind="entity.does_not_exist", config={}))
    assert ValidationIssueCode.UNKNOWN_ACTION_KIND in _codes(
        definition, frozenset({ENTITY_ASSIGN_USER_ACTION_KIND})
    )


def test_unknown_kind_check_is_skipped_when_no_registry_is_supplied() -> None:
    """A caller with no runtime to ask must not declare every action unknown."""
    definition = _definition(StateAction(kind="entity.does_not_exist", config={}))
    assert ValidationIssueCode.UNKNOWN_ACTION_KIND not in _codes(definition, None)


# ── Publish validation through the manager the builder actually calls ───────


class _FakeRegistry:
    """Stands in for the executor runtime's view of what it can run."""

    def __init__(self, kinds: set[str]) -> None:
        self._kinds = kinds

    def registered_action_kinds(self) -> frozenset[str]:
        return frozenset(self._kinds)


def _manager_issue_codes(action: StateAction, registry: Any) -> list[str]:
    """Publish-path issue codes for a definition carrying one action.

    Goes through `_definition_issues` — the manager entry point the draft,
    publish and version flows all share — rather than the analysis service, so
    the wiring between the two is exercised too.
    """
    manager = make_workflow_manager(None, None, executor_service_manager=registry)
    return [issue.code for issue in manager._definition_issues(_definition(action))]


def test_publish_through_the_manager_rejects_an_unrunnable_action_kind() -> None:
    codes = _manager_issue_codes(
        StateAction(kind="entity.does_not_exist", config={}),
        _FakeRegistry({ENTITY_ASSIGN_USER_ACTION_KIND}),
    )
    assert ValidationIssueCode.UNKNOWN_ACTION_KIND in codes


def test_publish_through_the_manager_rejects_a_half_configured_action() -> None:
    """The PR's headline claim, asserted where the builder actually enters."""
    codes = _manager_issue_codes(
        StateAction(kind=ENTITY_ASSIGN_USER_ACTION_KIND, config={"assignment_type": "user"}),
        _FakeRegistry({ENTITY_ASSIGN_USER_ACTION_KIND}),
    )
    assert ValidationIssueCode.INVALID_ACTION_CONFIG in codes


def test_publish_through_the_manager_accepts_a_valid_action() -> None:
    codes = _manager_issue_codes(
        StateAction(
            kind=ENTITY_ASSIGN_USER_ACTION_KIND,
            config={"assignment_type": "user", "user_id": "u1"},
        ),
        _FakeRegistry({ENTITY_ASSIGN_USER_ACTION_KIND}),
    )
    assert codes == []


def test_without_an_executor_runtime_the_kind_check_is_skipped_not_failed() -> None:
    """A validator must not turn its own missing dependency into a broken workflow."""
    codes = _manager_issue_codes(
        StateAction(kind="entity.does_not_exist", config={}), None
    )
    assert ValidationIssueCode.UNKNOWN_ACTION_KIND not in codes


def test_other_action_kinds_are_not_config_validated_here() -> None:
    """Only kinds with a declared contract are inspected."""
    definition = _definition(StateAction(kind="mail.send_email", config={}))
    assert _codes(definition, frozenset({"mail.send_email"})) == []

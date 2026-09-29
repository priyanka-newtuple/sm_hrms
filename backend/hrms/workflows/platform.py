"""Validate migrated HRMS lifecycles with the shared platform evaluator.

The compatibility services still own authorization, related writes, and audit. This
adapter gives their existing ORM mutations a versioned transition definition,
so bypassing a route cannot move a record along an undeclared edge.
"""
from sqlalchemy import event
from sqlalchemy.orm.attributes import NO_VALUE, NEVER_SET

from hrms.core.exceptions import ValidationFailed
from workflow.models.interface import StateMachineDefinition
from workflow.services.transition_evaluation import TransitionEvaluationService

# Current legacy states and edges, checked against the source services and tests.
# The workflow definition version is pinned here until records gain an explicit pin.
EDGES = {
    "timesheet": [
        ("draft", "submitted"), ("submitted", "approved"), ("submitted", "rejected"),
        ("rejected", "draft"), ("rejected", "submitted"),
    ],
    "onboarding": [("not_started", "in_progress"), ("in_progress", "completed")],
    "onboarding_task": [
        ("pending", "ready"), ("ready", "done"), ("ready", "skipped"),
        ("pending", "skipped"), ("ready", "pending"),
    ],
    "project_approval": [
        ("draft", "pending"), ("pending", "approved"), ("pending", "rejected"),
        ("pending", "changes_requested"), ("pending", "draft"),
        ("changes_requested", "draft"), ("changes_requested", "pending"),
        ("rejected", "draft"),
    ],
    "published_content": [
        ("draft", "pending_approval"), ("pending_approval", "published"),
        ("pending_approval", "approved"), ("approved", "published"),
        ("pending_approval", "draft"), ("published", "draft"),
        ("published", "archived"),
    ],
    "helpdesk": [
        ("open", "assigned"), ("open", "in_progress"), ("assigned", "in_progress"),
        ("in_progress", "resolved"), ("resolved", "closed"),
        ("resolved", "in_progress"), ("assigned", "resolved"),
    ],
    "leave": [("pending", "approved"), ("pending", "rejected")],
}
INITIAL = {
    "timesheet": "draft", "onboarding": "not_started", "onboarding_task": "pending",
    "project_approval": "draft", "published_content": "draft", "helpdesk": "open", "leave": "pending",
}


def _definition(name, edges):
    states = sorted({state for pair in edges for state in pair})
    entity_type = f"HRMS.{name}"
    return StateMachineDefinition.model_validate({
        "machine_key": f"hrms_{name}_v1", "name": f"HRMS {name}",
        "entity_type": entity_type, "entity_schema": {"entity_type": entity_type, "fields": []},
        "initial_state": INITIAL[name], "states": [{"name": state} for state in states],
        "transitions": [
            {"key": f"{source}_to_{target}", "trigger": f"to_{target}",
             "label": f"Move to {target}", "from": source, "to_state": target}
            for source, target in edges
        ],
    })


DEFINITIONS = {name: _definition(name, edges) for name, edges in EDGES.items()}
_evaluator = TransitionEvaluationService()
_installed = False


def validate_transition(kind: str, from_state: str, to_state: str):
    if from_state == to_state:
        return
    definition = DEFINITIONS[kind]
    transition = next((item for item in _evaluator.transitions_from(definition, from_state)
                       if item.to_state == to_state), None)
    if transition is None:
        raise ValidationFailed(f"{kind} cannot move from {from_state} to {to_state}")
    blocked, _, _ = _evaluator.evaluate(transition, {}, {})
    if blocked:
        raise ValidationFailed("; ".join(blocked))


def install_workflow_checks():
    global _installed
    if _installed:
        return
    from hrms.models.helpdesk import HelpdeskTicket
    from hrms.models.hr_content import JobOpening, LearningEvent, OrganizationPolicy
    from hrms.models.onboarding import OnboardingRecord, OnboardingTask
    from hrms.models.project import ProjectApprovalRequest
    from hrms.models.timesheet import Holiday, LeaveRequest, Timesheet

    registry = {
        "timesheet": [Timesheet], "onboarding": [OnboardingRecord],
        "onboarding_task": [OnboardingTask], "project_approval": [ProjectApprovalRequest],
        "published_content": [OrganizationPolicy, LearningEvent, JobOpening, Holiday],
        "helpdesk": [HelpdeskTicket], "leave": [LeaveRequest],
    }
    for kind, models in registry.items():
        for model in models:
            def check(target, value, previous, initiator, workflow_kind=kind):
                if previous not in (NO_VALUE, NEVER_SET, None):
                    old = previous.value if hasattr(previous, "value") else str(previous)
                    new = value.value if hasattr(value, "value") else str(value)
                    validate_transition(workflow_kind, old, new)
                return value
            event.listen(model.status, "set", check, retval=True, active_history=True)
    _installed = True

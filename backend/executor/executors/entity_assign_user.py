"""Executor that assigns an entity record to a chosen user or to its creator."""

from __future__ import annotations

import json
from typing import Any

from common.auth import build_system_actor
from common.logger import logger
from entities.models.interface import AssignmentRejection, AssignmentSource
from exceptions import ValidationError
from executor.executors.base import fail, get_field
from executor.models.interface import (
    ENTITY_ASSIGN_USER_ACTION_KIND,
    ROUTABLE_ASSIGN_USER_OUTCOMES,
    AssignUserAssignmentType,
    AssignUserConfigKey,
    AssignUserOutcome,
    BaseExecutor,
    ExecutorData,
    ExecutorDefinition,
    ExecutorInput,
    ExecutorResponse,
    assign_user_config_problem,
)
from user.models.interface import OrgMembershipVerdict

# `source` recorded on the audit actor, distinguishing a workflow action from the
# scheduler and from an agent acting for a human.
ASSIGN_USER_ACTOR_SOURCE = "worker"

# Worker-supplied field names, set by `background_jobs/manager.py` on every run.
FIELD_RAW_CONFIG = "_raw_config"
FIELD_ORG_ID = "org_id"
FIELD_RUN_ID = "run_id"

# Which of the entities module's assignment rejections maps to which routable
# outcome. "No creation event" and "creator no longer exists" mean the same thing
# to a workflow author — there is no originator to assign — so they share one
# outcome instead of exposing a distinction nobody can act on differently.
REJECTION_OUTCOMES: dict[str, AssignUserOutcome] = {
    AssignmentRejection.ORIGINATOR_NOT_FOUND: AssignUserOutcome.ORIGINATOR_NOT_FOUND,
    AssignmentRejection.ORIGINATOR_USER_MISSING: AssignUserOutcome.ORIGINATOR_NOT_FOUND,
    AssignmentRejection.ORIGINATOR_NOT_A_MEMBER: AssignUserOutcome.USER_NOT_FOUND,
    AssignmentRejection.ORIGINATOR_SUSPENDED: AssignUserOutcome.USER_SUSPENDED,
    # A pending or rejected account is reported as suspended to the workflow:
    # the action's published outcomes carry no separate value for it, and both
    # mean the same thing to an author — this person cannot take work.
    AssignmentRejection.ORIGINATOR_INACTIVE_ACCOUNT: AssignUserOutcome.USER_SUSPENDED,
}

# Why a configured user cannot be assigned. A user who exists but was never added
# to this organization is reported as not found rather than as suspended: from the
# workflow's point of view there is no such member to assign.
VERDICT_OUTCOMES: dict[OrgMembershipVerdict, AssignUserOutcome] = {
    OrgMembershipVerdict.NOT_FOUND: AssignUserOutcome.USER_NOT_FOUND,
    OrgMembershipVerdict.NOT_A_MEMBER: AssignUserOutcome.USER_NOT_FOUND,
    OrgMembershipVerdict.SUSPENDED: AssignUserOutcome.USER_SUSPENDED,
    OrgMembershipVerdict.INACTIVE_ACCOUNT: AssignUserOutcome.USER_SUSPENDED,
}

# Shown on the record's activity timeline, so: one short line, and no name or id.
# The timeline resolves the person from the id it already holds, which keeps the
# name current and keeps an account's status out of the stored text.
VERDICT_REASONS: dict[OrgMembershipVerdict, str] = {
    OrgMembershipVerdict.NOT_FOUND: "User no longer exists.",
    OrgMembershipVerdict.NOT_A_MEMBER: "User is not in this organization.",
    OrgMembershipVerdict.SUSPENDED: "User is suspended.",
    OrgMembershipVerdict.INACTIVE_ACCOUNT: "User's account is not active.",
}


class EntityAssignUserExecutor(BaseExecutor):
    """Assign a record to a configured user, or to the person who created it.

    Runs the assignment through the entities manager as a system actor, so it
    produces the same write, notification and history as a manual assignment.
    A configured user is checked for assignability here; an originator is
    resolved and checked by the entities manager.
    """

    def __init__(self, **_: Any) -> None:
        """Accept the shared executor kwargs; domain managers are late-bound."""
        self.entities_service: Any = None
        self.user_service: Any = None

    @property
    def definition(self) -> ExecutorDefinition:
        """Describe this executor for the registry and the action catalogue."""
        return ExecutorDefinition(
            name=ENTITY_ASSIGN_USER_ACTION_KIND,
            description="Assign the record to a selected user or to its original creator.",
            supported_outcomes=[str(outcome) for outcome in ROUTABLE_ASSIGN_USER_OUTCOMES],
        )

    def bind_services(self, entities_service: Any, user_service: Any) -> None:
        """Late-bind the entities and user managers (built after the registry)."""
        self.entities_service = entities_service
        self.user_service = user_service

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        """Resolve the target user and assign the record to them."""
        if self.entities_service is None or self.user_service is None:
            return fail("entities/user services are not configured")
        organization_id = get_field(input_payload.fields, FIELD_ORG_ID) or ""
        entity_id = input_payload.entity_id
        try:
            raw_config = get_field(input_payload.fields, FIELD_RAW_CONFIG) or "{}"
            to_originator, target_user_id = self._target_from_config(json.loads(raw_config))
        except (ValidationError, ValueError) as exc:
            return fail(str(exc))
        if not to_originator:
            refusal = self._refuse_unassignable_user(
                user_id=target_user_id, organization_id=organization_id, entity_id=entity_id
            )
            if refusal is not None:
                return refusal
        return self._assign(
            organization_id=organization_id,
            entity_id=entity_id,
            target_user_id=target_user_id,
            to_originator=to_originator,
            run_id=get_field(input_payload.fields, FIELD_RUN_ID),
        )

    @staticmethod
    def _target_from_config(config: dict[str, Any]) -> tuple[bool, str | None]:
        """Return (assign_to_originator, explicit_user_id) from the action's config.

        Validates through the same rule publish validation applies, so the
        builder and the worker cannot disagree about what a valid config is.
        Raises `ValidationError` for a shape publish would have rejected —
        reaching here means the workflow was published before that check.
        """
        problem = assign_user_config_problem(config)
        if problem:
            raise ValidationError(problem)
        assignment_type = str(config.get(AssignUserConfigKey.ASSIGNMENT_TYPE)).strip()
        if assignment_type == AssignUserAssignmentType.ORIGINATOR:
            return True, None
        return False, str(config.get(AssignUserConfigKey.USER_ID)).strip()

    def _refuse_unassignable_user(
        self, *, user_id: str | None, organization_id: str, entity_id: str
    ) -> ExecutorResponse | None:
        """Return a refusal when the configured user cannot be assigned, else None."""
        candidate = self.user_service.get_org_member_assignability(user_id, organization_id)
        if candidate.is_assignable:
            return None
        outcome = VERDICT_OUTCOMES.get(candidate.verdict)
        reason = VERDICT_REASONS.get(
            candidate.verdict, f"User cannot be assigned ({candidate.verdict})."
        )
        if outcome is None:
            # A verdict nobody mapped is our own gap, not a finding about the
            # user, so it must reach the failure policy rather than pose as a
            # routable outcome the engine would then reject as undeclared.
            return fail(reason)
        logger.warning(
            "entity.assign_user refused configured user: %s",
            reason,
            extra={
                "entity_id": entity_id,
                "organization_id": organization_id,
                "outcome": str(outcome),
            },
        )
        return self._refusal_response(outcome, reason)

    @staticmethod
    def _refusal_response(outcome: AssignUserOutcome, reason: str) -> ExecutorResponse:
        """Report a refusal as a completed run carrying a routable outcome.

        `success` marks whether the action ran, not whether it assigned anyone.
        A target who cannot take work is a real answer, so the engine must read
        the outcome and fire whatever transition the author mapped to it — it
        only resolves outcome triggers for successful responses. `failed` stays
        unsuccessful, and is the only case the failure policy should govern.

        `refused` asks the timeline to show this in the failure style rather
        than as a plain success — the run completed, but nobody was assigned,
        and a green tick reads identically to an assignment that worked. It is
        presentation only: the run stays successful, so outcome routing and the
        failure policy behave exactly as they do for any other outcome.
        """
        return ExecutorResponse(
            success=True,
            message=reason,
            data=ExecutorData(
                outcome=str(outcome), fields={}, meta={"reason": reason, "refused": True}
            ),
        )

    def _assign(
        self,
        *,
        organization_id: str,
        entity_id: str,
        target_user_id: str | None,
        to_originator: bool,
        run_id: str | None,
    ) -> ExecutorResponse:
        """Perform the assignment and classify the result into an outcome."""
        actor = build_system_actor(organization_id, source=ASSIGN_USER_ACTOR_SOURCE)
        try:
            before = self.entities_service.get_entity_record_for_actor(
                actor, entity_id, organization_id
            )
            record = self.entities_service.set_entity_assignee_for_actor(
                actor,
                entity_id,
                target_user_id,
                organization_id,
                assign_to_originator=to_originator,
                assignment_source=AssignmentSource.WORKFLOW_ACTION,
                action_run_id=run_id,
            )
        except ValidationError as exc:
            return self._rejection_response(entity_id=entity_id, error=exc)
        except Exception as exc:
            logger.exception(
                "entity.assign_user failed: %s",
                exc,
                extra={"entity_id": entity_id, "organization_id": organization_id},
            )
            return fail(str(exc))
        unchanged = before.assignee_id == record.assignee_id
        logger.info(
            "entity.assign_user completed",
            extra={
                "entity_id": entity_id,
                "organization_id": organization_id,
                "unchanged": unchanged,
                "assignee_id": record.assignee_id,
            },
        )
        return self._success_response(unchanged=unchanged, assignee_id=record.assignee_id)

    @staticmethod
    def _success_response(*, unchanged: bool, assignee_id: str | None) -> ExecutorResponse:
        """Report a completed assignment as `assigned`, or `already_assigned` if unchanged."""
        outcome = AssignUserOutcome.ALREADY_ASSIGNED if unchanged else AssignUserOutcome.ASSIGNED
        return ExecutorResponse(
            success=True,
            message=(
                "Record was already assigned to that user" if unchanged else "Record assigned"
            ),
            data=ExecutorData(outcome=str(outcome), fields={}, meta={"assignee_id": assignee_id}),
        )

    @staticmethod
    def _rejection_response(*, entity_id: str, error: ValidationError) -> ExecutorResponse:
        """Map an originator rejection onto this action's outcomes by error code.

        An unrecognized code reports `failed`.
        """
        reason = str(error)
        outcome = REJECTION_OUTCOMES.get(error.code, AssignUserOutcome.FAILED)
        logger.warning(
            "entity.assign_user rejected: %s",
            reason,
            extra={
                "entity_id": entity_id,
                "outcome": str(outcome),
                "rejection_code": error.code,
            },
        )
        if outcome is AssignUserOutcome.FAILED:
            return fail(reason)
        return EntityAssignUserExecutor._refusal_response(outcome, reason)

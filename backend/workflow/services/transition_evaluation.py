"""Pure transition lookup, eligibility and option projection.

The single authority on whether a workflow move is allowed: transition lookup by state and
trigger, required-field presence and typing, guard evaluation, the fields that influence a
transition's readiness, and the option shapes the API returns.

Every function here is pure. No database, roles, entity manager, audit, configuration or other
workflow service. Authorization is deliberately absent — workflow scope, catalog permission,
entity visibility and exact transition permission all remain the manager's concern. This module
consumes an already-resolved visible/masked field set and nothing more.
"""

from __future__ import annotations

from datetime import datetime

from common.logger import logger
from common.protocols import EntityReadPolicy
from entities.models.interface import IDENTIFIER_FIELD_KEY
from exceptions import NotFoundError
from workflow.models.interface import (
    GUARD_TYPE_ALL,
    AvailableTransition,
    Guard,
    GuardEvaluation,
    GuardType,
    PreflightFieldRequirement,
    StateMachineDefinition,
    Transition,
    matches_workflow_value,
)


class TransitionEvaluationService:
    """Decide whether a workflow transition is allowed, and describe the options.

    Pure: no database, no roles, no audit. Every input arrives as an argument and every
    answer is returned, so the manager keeps ownership of persistence and authorization.
    """

    def transitions_from(
        self, definition: StateMachineDefinition, current_state: str
    ) -> list[Transition]:
        """List transitions from a state."""
        return [item for item in definition.transitions if current_state in item.source_states]

    def transition_field_names(self, transition: Transition) -> set[str]:
        """Fields whose values can affect one transition's readiness."""
        fields = {item.field for item in transition.required_fields if item.field}
        for guard in transition.guards:
            if guard.field:
                fields.add(guard.field)
            other_field = (
                guard.config.get("other_field") if isinstance(guard.config, dict) else None
            )
            if isinstance(other_field, str) and other_field:
                fields.add(other_field)
        return fields

    def _eval_guard_field_checks(
        self, value: object, guard: Guard, _merged: dict[str, object]
    ) -> tuple[bool, str | None]:
        """Evaluate field-level guards: presence check and exact-value match."""
        if guard.type == GuardType.FIELD_PRESENT:
            if isinstance(value, list):
                return len(value) > 0, None
            return value is not None and value != "", None
        # FIELD_EXACT_MATCH
        if isinstance(value, list):
            return guard.value in value, None
        return value == guard.value, None

    def _eval_guard_numerical(
        self, value: object, guard: Guard, _merged: dict[str, object]
    ) -> tuple[bool, str | None]:
        """Evaluate numeric comparison guards: GTE, LTE, and set-membership."""
        if guard.type == GuardType.NUMERICAL_VALUE_GTE:
            return value is not None and guard.value is not None and value >= guard.value, None
        if guard.type == GuardType.NUMERICAL_VALUE_LTE:
            return value is not None and guard.value is not None and value <= guard.value, None
        # NUMERICAL_VALUE_IN_SET
        candidates = guard.value if isinstance(guard.value, (list, tuple, set)) else [guard.value]
        return value in candidates, None

    def _eval_guard_compare_dates(
        self, value: object, guard: Guard, merged: dict[str, object]
    ) -> tuple[bool, str | None]:
        """Evaluate a datetime comparison guard against two ISO datetime fields."""
        other_field = guard.config.get("other_field")
        operator = str(guard.config.get("operator", "lte")).strip().lower()
        other_value = merged.get(other_field) if isinstance(other_field, str) else None
        if not isinstance(value, str) or not isinstance(other_value, str):
            label = guard.field.replace("_", " ").title() if guard.field else "A date field"
            other_label = (
                other_field.replace("_", " ").title()
                if isinstance(other_field, str)
                else "the comparison date"
            )
            return False, f"Both {label} and {other_label} must be valid dates to compare"
        left = datetime.fromisoformat(value.replace("Z", "+00:00"))
        right = datetime.fromisoformat(other_value.replace("Z", "+00:00"))
        date_ops: dict[str, object] = {
            "lt": left < right,
            "lte": left <= right,
            "gt": left > right,
            "gte": left >= right,
            "eq": left == right,
            "ne": left != right,
        }
        if operator not in date_ops:
            return False, f"guard '{guard.type}' has unsupported operator '{operator}'"
        return bool(date_ops[operator]), None

    def _evaluate_guards(
        self, guards: list[Guard], merged: dict[str, object]
    ) -> list[GuardEvaluation]:
        """Run each guard against the entity's merged data + transition inputs.

        Dispatches to a per-domain evaluator. Unknown types pass by default so a
        definition isn't bricked by a forward-compat rule."""
        evaluators = {
            GuardType.FIELD_PRESENT: self._eval_guard_field_checks,
            GuardType.FIELD_EXACT_MATCH: self._eval_guard_field_checks,
            GuardType.NUMERICAL_VALUE_GTE: self._eval_guard_numerical,
            GuardType.NUMERICAL_VALUE_LTE: self._eval_guard_numerical,
            GuardType.NUMERICAL_VALUE_IN_SET: self._eval_guard_numerical,
            GuardType.COMPARE_DATES: self._eval_guard_compare_dates,
        }
        results: list[GuardEvaluation] = []
        for guard in guards:
            value = merged.get(guard.field) if guard.field else None
            passed, message = True, None
            if guard.type in GUARD_TYPE_ALL and not guard.field:
                passed = False
                message = guard.message or f"guard '{guard.type}' is missing a field reference"
                results.append(
                    GuardEvaluation(
                        type=guard.type, field=guard.field, passed=passed, message=message
                    )
                )
                continue
            evaluator = evaluators.get(guard.type)
            if evaluator is not None:
                try:
                    passed, message = evaluator(value, guard, merged)
                except (TypeError, ValueError) as exc:
                    # The guard is treated as failed so one malformed rule cannot take a
                    # workflow down, but the transition then looks legitimately blocked and
                    # the caller only ever sees the guard's own message. Log the real cause,
                    # or a bad guard config is indistinguishable from a real block.
                    passed = False
                    message = guard.message
                    logger.warning(
                        "guard evaluation raised, treating the guard as failed: %s",
                        exc,
                        exc_info=True,
                        extra={
                            "guard_type": str(guard.type),
                            "guard_field": guard.field,
                            "value_type": type(value).__name__,
                        },
                    )
            if not passed and message is None:
                message = guard.message
            results.append(
                GuardEvaluation(type=guard.type, field=guard.field, passed=passed, message=message)
            )
        return results

    def evaluate(
        self, transition: Transition, data: dict[str, object], inputs: dict[str, object]
    ) -> tuple[list[str], list[GuardEvaluation], list[PreflightFieldRequirement]]:
        """Evaluate required fields and guards."""
        merged = {**data, **inputs}
        missing = [
            PreflightFieldRequirement(
                field=item.field,
                type=item.type,
                required=item.required,
                provided=(
                    merged.get(item.field) is not None
                    and matches_workflow_value(item.type, merged.get(item.field))
                )
                or not item.required,
            )
            for item in transition.required_fields
        ]
        missing = [item for item in missing if item.required and not item.provided]
        guards = self._evaluate_guards(transition.guards, merged)
        blocked = []
        blocked.extend(f"required field '{item.field}' is missing or invalid" for item in missing)
        for item in guards:
            if not item.passed:
                if item.message:
                    blocked.append(item.message)
                else:
                    field_label = (
                        item.field.replace("_", " ").title() if item.field else "A condition"
                    )
                    blocked.append(f"{field_label} did not meet the required condition")
        return blocked, guards, missing

    def require_transition(
        self, definition: StateMachineDefinition, current_state: str, trigger: str
    ) -> Transition:
        """Find one runtime transition."""
        for transition in self.transitions_from(definition, current_state):
            if transition.trigger == trigger:
                return transition
        raise NotFoundError(f"transition '{trigger}' is not allowed from state '{current_state}'")

    def _available_option(
        self,
        transition: Transition,
        data: dict[str, object],
        inputs: dict[str, object],
    ) -> AvailableTransition:
        blocked, guards, _ = self.evaluate(transition, data, inputs)
        return AvailableTransition(
            trigger=transition.trigger,
            label=transition.label,
            to_state=transition.to_state,
            allowed=not blocked,
            availability_known=True,
            guards=[item.model_dump() for item in guards],
            blocked_reasons=blocked,
        )

    def available_options(
        self,
        definition: StateMachineDefinition,
        current_state: str,
        data: dict[str, object],
        inputs: dict[str, object],
    ) -> list[AvailableTransition]:
        """Evaluate compact transition previews without additional entity reads."""
        options: list[AvailableTransition] = []
        for transition in self.transitions_from(definition, current_state):
            options.append(self._available_option(transition, data, inputs))
        return options

    def summary_options(
        self,
        definition: StateMachineDefinition,
        current_state: str,
        data: dict[str, object],
        policy: EntityReadPolicy,
    ) -> list[AvailableTransition]:
        """Return readiness only when every influencing field is actor-visible."""
        options: list[AvailableTransition] = []
        for transition in self.transitions_from(definition, current_state):
            fields = self.transition_field_names(transition)
            hidden = fields & policy.masked_fields
            if policy.visible_fields is not None:
                hidden |= {
                    field
                    for field in fields
                    if field != IDENTIFIER_FIELD_KEY and field not in policy.visible_fields
                }
            if hidden:
                options.append(
                    AvailableTransition(
                        trigger=transition.trigger,
                        label=transition.label,
                        to_state=transition.to_state,
                        allowed=True,
                        availability_known=False,
                    )
                )
                continue
            options.append(self._available_option(transition, data, {}))
        return options

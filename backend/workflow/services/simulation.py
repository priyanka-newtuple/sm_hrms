"""Bounded dry-run simulation over a workflow definition.

Pure functions: no database, no roles, no audit, no persistence. Given a definition and an
optional starting state and data snapshot, they explore reachable transition paths within
fixed bounds and report what would happen. Callers own authorization and persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from common.logger import logger
from workflow.models import (
    DryRunPath,
    DryRunStep,
    DryRunTransitionCheck,
    EntityField,
    EntityFieldType,
    Guard,
    GuardType,
    StateMachineDefinition,
    StateTag,
    Transition,
    ValidationIssue,
    ValidationIssueCode,
    WorkflowDryRunSummary,
    WorkflowPathLine,
)
from workflow.models.interface import (
    DRY_RUN_BOOLEAN,
    DRY_RUN_DATE,
    DRY_RUN_DATE_OFFSET_DAYS,
    DRY_RUN_DATETIME,
    DRY_RUN_EMAIL_DOMAIN,
    DRY_RUN_FLOAT,
    DRY_RUN_INTEGER,
    DRY_RUN_PHONE,
    DRY_RUN_STRING_PREFIX,
    DRY_RUN_TIMER_DURATION_SECONDS,
    DRY_RUN_URL_BASE,
    matches_workflow_value,
    transition_identity,
)

if TYPE_CHECKING:
    from workflow.services.definition_analysis import DefinitionAnalysisService
    from workflow.services.transition_evaluation import TransitionEvaluationService



@dataclass(frozen=True)
class _Exploration:
    """Everything a bounded path walk needs that does not change as it descends.

    The three collections are accumulators shared by every walk in one simulation: the dataclass
    is frozen so the fields cannot be rebound, but their contents are appended to.
    """

    definition: StateMachineDefinition
    graph: dict[str, list[Transition]]
    max_depth: int
    state_visit_cap: int
    start_state: str
    explored_paths: list[DryRunPath]
    transition_checks: list[DryRunTransitionCheck]
    terminal_states_reached: set[str]


class SimulationService:
    """Bounded dry-run simulation over a workflow definition.

    Pure: no database, no roles, no audit, no persistence. Given a definition and an
    optional starting state and data snapshot, it explores reachable transition paths
    within fixed bounds and reports what would happen. Callers own authorization and
    persistence.
    """

    def __init__(
        self,
        transition_evaluation: TransitionEvaluationService,
        definition_analysis: DefinitionAnalysisService,
    ) -> None:
        """Take the guard evaluator and the structural analyser from the caller.

        Stage 3.5 §9: a workflow service must not hold, inject or orchestrate another workflow
        service. Both are supplied by `workflow/manager.py`, which owns the wiring, so this
        module has no runtime import of another capability and no cycle is possible.
        """
        self.transition_evaluation = transition_evaluation
        self.definition_analysis = definition_analysis

    def _check_state_reachability(
        self,
        definition: StateMachineDefinition, reachable: set[str], outgoing: dict[str, list[Transition]]
    ) -> list[ValidationIssue]:
        """Report states no initial state can reach, and non-terminal states with no way out."""
        issues: list[ValidationIssue] = []
        for state in definition.states:
            if state.name not in reachable:
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.UNREACHABLE_STATE,
                        message=f"State '{state.name}' cannot be reached from any initial state.",
                    )
                )
            if not state.terminal and not outgoing.get(state.name):
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.DEAD_END_STATE,
                        message=f"State '{state.name}' is not terminal but has no outgoing transitions.",
                    )
                )
        return issues

    def _check_terminal_reachable(
        self,
        graph: dict[str, list[str]], initial_states: list[str], terminal_states: list[str]
    ) -> list[ValidationIssue]:
        """Report initial states from which no terminal state is reachable."""
        issues: list[ValidationIssue] = []
        for initial_state in initial_states:
            if terminal_states and not any(
                self.definition_analysis.has_path(graph, initial_state, terminal_state)
                for terminal_state in terminal_states
            ):
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.NO_TERMINAL_PATH,
                        message=f"Initial state '{initial_state}' cannot reach any terminal state.",
                    )
                )
        return issues

    def _check_unsatisfied_transitions(
        self,
        definition: StateMachineDefinition, summary: WorkflowDryRunSummary
    ) -> list[ValidationIssue]:
        """Report transitions the simulation never managed to satisfy."""
        issues: list[ValidationIssue] = []
        successful_transitions = {
            item.transition_key for item in summary.transition_checks if item.satisfiable
        }
        for transition in definition.transitions:
            transition_key = transition.key or transition_identity(transition)
            blocked = next(
                (item for item in summary.transition_checks if item.transition_key == transition_key),
                None,
            )
            if blocked is None:
                continue
            if transition_key not in successful_transitions:
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.UNSATISFIED_TRANSITION,
                        message=f"Transition '{transition.trigger}' from '{transition.from_state}' cannot be satisfied."
                        + (
                            f": {'; '.join(blocked.blocked_reasons)}"
                            if blocked and blocked.blocked_reasons
                            else ""
                        ),
                    )
                )
        return issues

    def _check_loop_without_terminal(self, summary: WorkflowDryRunSummary) -> list[ValidationIssue]:
        """Report a definition whose only explored paths loop and never complete."""
        if summary.loop_paths_count > 0 and summary.successful_paths_count == 0:
            return [
                ValidationIssue(
                    code=ValidationIssueCode.LOOP_WITHOUT_TERMINAL,
                    message="Dry run detected looping paths without any successful terminal completion.",
                    severity="error",
                )
            ]
        return []

    def dry_run_issues(
        self,
        definition: StateMachineDefinition, summary: WorkflowDryRunSummary
    ) -> list[ValidationIssue]:
        """Convert dry-run simulation results into publish-gating issues."""
        initial_states = [state.name for state in definition.states if StateTag.INITIAL in state.tags]
        terminal_states = [state.name for state in definition.states if state.terminal]
        graph = self.definition_analysis.build_graph(definition.transitions)
        reachable = self.definition_analysis.reachable_states(graph, initial_states)
        outgoing = self.definition_analysis.outgoing_map(definition)
        return [
            *self._check_state_reachability(definition, reachable, outgoing),
            *self._check_terminal_reachable(graph, initial_states, terminal_states),
            *self._check_unsatisfied_transitions(definition, summary),
            *self._check_loop_without_terminal(summary),
        ]

    def simulate_definition(
        self,
        definition: StateMachineDefinition,
        *,
        start_states: list[str] | None = None,
        seed_data: dict[str, object] | None = None,
    ) -> WorkflowDryRunSummary:
        """Simulate all bounded workflow paths for a definition."""
        initial_states = start_states or [
            state.name for state in definition.states if StateTag.INITIAL in state.tags
        ]
        transition_checks: list[DryRunTransitionCheck] = []
        explored_paths: list[DryRunPath] = []
        terminal_states_reached: set[str] = set()
        graph = self.definition_analysis.outgoing_map(definition)
        max_depth = max(len(definition.transitions) * 2, len(definition.states) * 3, 4)
        state_visit_cap = 2

        for state_name in initial_states:
            self._explore_dry_run_paths(
                _Exploration(
                    definition=definition,
                    graph=graph,
                    max_depth=max_depth,
                    state_visit_cap=state_visit_cap,
                    start_state=state_name,
                    explored_paths=explored_paths,
                    transition_checks=transition_checks,
                    terminal_states_reached=terminal_states_reached,
                ),
                current_state=state_name,
                current_data=dict(seed_data or {}),
                steps=[],
                visit_counts={state_name: 1},
            )

        return WorkflowDryRunSummary(
            initial_states_checked=list(initial_states),
            terminal_states_reached=sorted(terminal_states_reached),
            successful_paths_count=sum(1 for item in explored_paths if item.terminal_reached),
            blocked_paths_count=sum(
                1 for item in explored_paths if item.blocked and not item.loop_detected
            ),
            loop_paths_count=sum(1 for item in explored_paths if item.loop_detected),
            explored_paths=explored_paths,
            transition_checks=transition_checks,
        )

    def _record_block(
        self,
        ctx: _Exploration,
        *,
        end_state: str,
        steps: list[DryRunStep],
        reason: str,
        loop_detected: bool = False,
    ) -> None:
        """Record one path that stopped early, with the reason it stopped."""
        ctx.explored_paths.append(
            self._blocked_dry_run_path(
                start_state=ctx.start_state,
                end_state=end_state,
                steps=steps,
                blocked_reasons=[reason],
                loop_detected=loop_detected,
            )
        )

    def _bounds_exceeded(
        self,
        ctx: _Exploration, current_state: str, steps: list[DryRunStep], visit_counts: dict[str, int]
    ) -> bool:
        """Stop the walk if it has gone too deep or revisited one state too often."""
        if len(steps) >= ctx.max_depth:
            self._record_block(
                ctx,
                end_state=current_state,
                steps=steps,
                reason="maximum dry-run depth reached",
                loop_detected=True,
            )
            return True
        if visit_counts.get(current_state, 0) > ctx.state_visit_cap:
            self._record_block(
                ctx,
                end_state=current_state,
                steps=steps,
                reason=f"state '{current_state}' exceeded loop visit limit",
                loop_detected=True,
            )
            return True
        return False

    def _explore_dry_run_paths(
        self,
        ctx: _Exploration,
        *,
        current_state: str,
        current_data: dict[str, object],
        steps: list[DryRunStep],
        visit_counts: dict[str, int],
    ) -> None:
        """Recursively explore bounded dry-run paths from one state."""
        if self._bounds_exceeded(ctx, current_state, steps, visit_counts):
            return
        state = next(item for item in ctx.definition.states if item.name == current_state)
        outgoing = ctx.graph.get(current_state, [])
        if state.terminal:
            ctx.terminal_states_reached.add(current_state)
            ctx.explored_paths.append(
                DryRunPath(
                    path_id=str(uuid4()),
                    start_state=ctx.start_state,
                    end_state=current_state,
                    terminal_reached=True,
                    steps=list(steps),
                )
            )
            return
        if not outgoing:
            self._record_block(
                ctx,
                end_state=current_state,
                steps=steps,
                reason=f"state '{current_state}' has no outgoing transitions",
            )
            return
        for transition in outgoing:
            self._explore_dry_run_transition(
                ctx,
                transition=transition,
                current_data=current_data,
                steps=steps,
                visit_counts=visit_counts,
            )

    def _explore_dry_run_transition(
        self,
        ctx: _Exploration,
        *,
        transition: Transition,
        current_data: dict[str, object],
        steps: list[DryRunStep],
        visit_counts: dict[str, int],
    ) -> None:
        """Evaluate one transition during dry-run exploration."""
        check = self._simulate_transition_check(ctx.definition, transition, current_data)
        ctx.transition_checks.append(check)
        if not check.satisfiable:
            ctx.explored_paths.append(
                self._blocked_dry_run_path(
                    start_state=ctx.start_state,
                    end_state=transition.from_state,
                    steps=steps,
                    blocked_reasons=list(check.blocked_reasons),
                )
            )
            return
        next_steps = list(steps)
        next_steps.append(
            DryRunStep(
                from_state=transition.from_state,
                trigger=transition.trigger,
                to_state=transition.to_state,
                actor_role=check.actor_role,
                synthesized_inputs=dict(check.synthesized_inputs),
            )
        )
        next_visits = dict(visit_counts)
        next_visits[transition.to_state] = next_visits.get(transition.to_state, 0) + 1
        if transition.to_state in visit_counts:
            self._record_block(
                ctx,
                end_state=transition.to_state,
                steps=next_steps,
                reason=f"loop detected on state '{transition.to_state}'",
                loop_detected=True,
            )
            return
        self._explore_dry_run_paths(
            ctx,
            current_state=transition.to_state,
            current_data={**current_data, **check.synthesized_inputs},
            steps=next_steps,
            visit_counts=next_visits,
        )

    def _blocked_dry_run_path(
        self,
        *,
        start_state: str,
        end_state: str,
        steps: list[DryRunStep],
        blocked_reasons: list[str],
        loop_detected: bool = False,
    ) -> DryRunPath:
        """Build one blocked dry-run path record."""
        return DryRunPath(
            path_id=str(uuid4()),
            start_state=start_state,
            end_state=end_state,
            blocked=True,
            loop_detected=loop_detected,
            blocked_reasons=blocked_reasons,
            steps=list(steps),
        )

    def render_workflow_paths(self, summary: WorkflowDryRunSummary) -> list[WorkflowPathLine]:
        """Render explored dry-run paths into readable arrow strings."""
        return [self._render_workflow_path(path) for path in summary.explored_paths]

    def _render_workflow_path(self, path: DryRunPath) -> WorkflowPathLine:
        """Render one dry-run path as a linear workflow string."""
        parts = [f"(STARTING){path.start_state}"]
        current_state = path.start_state
        for step in path.steps:
            if current_state != step.from_state:
                current_state = step.from_state
            parts.append(f"-> ({step.trigger}) -> {step.to_state}")
            current_state = step.to_state
        suffix = ""
        path_type = "terminal"
        if path.loop_detected:
            path_type = "loop"
            suffix = " (LOOP)"
        elif path.blocked:
            path_type = "blocked"
            details = f": {'; '.join(path.blocked_reasons)}" if path.blocked_reasons else ""
            suffix = f" (BLOCKED{details})"
        elif path.terminal_reached:
            suffix = " (END)"
        rendered = " ".join(parts) + suffix
        return WorkflowPathLine(
            path_type=path_type,
            rendered=rendered,
            start_state=path.start_state,
            end_state=path.end_state,
            blocked_reasons=list(path.blocked_reasons),
        )

    def _blocked_check(self, transition: Transition, reason: str) -> DryRunTransitionCheck:
        """Build the unsatisfiable result for one transition, carrying a single reason."""
        return DryRunTransitionCheck(
            transition_key=transition.key or transition_identity(transition),
            trigger=transition.trigger,
            from_state=transition.from_state,
            to_state=transition.to_state,
            blocked_reasons=[reason],
        )

    def _synthesize_required_fields(
        self,
        transition: Transition,
        schema_fields: dict[str, EntityField],
        current_data: dict[str, object],
    ) -> tuple[dict[str, object], DryRunTransitionCheck | None]:
        """Invent values for the transition's required fields the data does not already supply."""
        synthesized_inputs: dict[str, object] = {}
        for required_field in transition.required_fields:
            field = schema_fields.get(required_field.field)
            if field is None:
                return synthesized_inputs, self._blocked_check(
                    transition,
                    f"required field '{required_field.field}' is missing from entity schema",
                )
            if required_field.field in current_data and current_data[required_field.field] is not None:
                continue
            synthesized = self.default_value_for_field(field, prefer_concrete=required_field.required)
            if synthesized is None and required_field.required:
                return synthesized_inputs, self._blocked_check(
                    transition,
                    f"required field '{required_field.field}' has no synthesizable value",
                )
            if synthesized is not None:
                synthesized_inputs[required_field.field] = synthesized
        return synthesized_inputs, None

    def _synthesize_compare_dates_pair(
        self,
        guard: Guard,
        schema_fields: dict[str, EntityField],
        merged: dict[str, object],
        synthesized_inputs: dict[str, object],
    ) -> None:
        """Fill in the counterpart date a compare-dates guard needs, when it is absent."""
        if guard.type != GuardType.COMPARE_DATES or not isinstance(guard.config, dict):
            return
        other_field_name = guard.config.get("other_field")
        operator = str(guard.config.get("operator", "lte")).strip().lower()
        if not isinstance(other_field_name, str) or merged.get(other_field_name) is not None:
            return
        other_field_def = schema_fields.get(other_field_name)
        if other_field_def is None:
            return
        other_synth = self._synthesize_compare_dates_other(
            merged.get(guard.field), operator, other_field_def
        )
        if other_synth is not None:
            synthesized_inputs[other_field_name] = other_synth
            merged[other_field_name] = other_synth

    def _resolve_guard_values(
        self,
        transition: Transition,
        schema_fields: dict[str, EntityField],
        merged: dict[str, object],
        synthesized_inputs: dict[str, object],
    ) -> DryRunTransitionCheck | None:
        """Invent values the guards need; return a blocked result if one cannot be met."""
        for guard in transition.guards:
            if guard.field is None:
                continue
            field = schema_fields.get(guard.field)
            if field is None:
                return self._blocked_check(
                    transition, f"guard field '{guard.field}' is missing from entity schema"
                )
            candidate_value, reason = self._value_for_guard(field, guard, merged.get(guard.field))
            if reason is not None:
                return self._blocked_check(transition, reason)
            if candidate_value is not None:
                synthesized_inputs[guard.field] = candidate_value
                merged[guard.field] = candidate_value
            self._synthesize_compare_dates_pair(guard, schema_fields, merged, synthesized_inputs)
        return None

    def _simulate_transition_check(
        self,
        definition: StateMachineDefinition,
        transition: Transition,
        current_data: dict[str, object],
    ) -> DryRunTransitionCheck:
        """Determine whether one transition can be satisfied and synthesized."""
        schema_fields = {field.field: field for field in definition.entity_schema.fields}
        synthesized_inputs, blocked_check = self._synthesize_required_fields(
            transition, schema_fields, current_data
        )
        if blocked_check is not None:
            return blocked_check
        merged = {**current_data, **synthesized_inputs}
        blocked_check = self._resolve_guard_values(transition, schema_fields, merged, synthesized_inputs)
        if blocked_check is not None:
            return blocked_check
        blocked, _, _ = self.transition_evaluation.evaluate(
            transition, current_data, synthesized_inputs
        )
        return DryRunTransitionCheck(
            transition_key=transition.key or transition_identity(transition),
            trigger=transition.trigger,
            from_state=transition.from_state,
            to_state=transition.to_state,
            satisfiable=not blocked,
            actor_role=None,
            synthesized_inputs=synthesized_inputs,
            blocked_reasons=blocked,
        )

    def default_value_for_field(self, field: EntityField, *, prefer_concrete: bool = False) -> object | None:
        """Return a deterministic synthetic value for a schema field."""
        if (
            field.default is not None
            and field.default != ""
            and matches_workflow_value(field.type, field.default, enum_values=field.enum_values or None)
        ):
            return field.default
        if field.nullable and not prefer_concrete:
            if field.type == EntityFieldType.ENUM and field.enum_values:
                return field.enum_values[0]
            return None
        if field.type in {EntityFieldType.STRING, EntityFieldType.TEXT}:
            return f"{DRY_RUN_STRING_PREFIX}{field.field}"
        if field.type == EntityFieldType.EMAIL:
            return f"{DRY_RUN_STRING_PREFIX}{field.field}@{DRY_RUN_EMAIL_DOMAIN}"
        if field.type == EntityFieldType.PHONE:
            return DRY_RUN_PHONE
        if field.type == EntityFieldType.URL:
            return f"{DRY_RUN_URL_BASE}/{field.field}"
        if field.type == EntityFieldType.INTEGER:
            return DRY_RUN_INTEGER
        if field.type == EntityFieldType.FLOAT:
            return DRY_RUN_FLOAT
        if field.type == EntityFieldType.BOOLEAN:
            return DRY_RUN_BOOLEAN
        if field.type == EntityFieldType.DATE:
            return DRY_RUN_DATE
        if field.type == EntityFieldType.DATETIME:
            return DRY_RUN_DATETIME
        if field.type == EntityFieldType.ENUM:
            return field.enum_values[0] if field.enum_values else None
        if field.type == EntityFieldType.JSON:
            return {}
        if field.type == EntityFieldType.MULTI_SELECT:
            return field.enum_values[:1] if field.enum_values else []
        if field.type == EntityFieldType.TIMER_DURATION:
            # A plausible run, so a transition requiring the field can be
            # simulated. Nothing typed it: only completing a timer ever does.
            return DRY_RUN_TIMER_DURATION_SECONDS
        if field.type == EntityFieldType.DOCUMENT:
            # No file exists to point at in a dry run, and inventing an id would
            # fail the same existence check publishing applies.
            return []
        return None

    def _value_for_guard(
        self,
        field: EntityField, guard: Guard, current_value: object | None
    ) -> tuple[object | None, str | None]:
        """Generate a value that can satisfy one guard when possible."""
        if guard.type == GuardType.FIELD_PRESENT:
            if current_value is not None and current_value != "":
                return current_value, None
            value = self.default_value_for_field(field, prefer_concrete=True)
            return (
                (value, None)
                if value is not None
                else (None, f"guard field '{field.field}' cannot be synthesized")
            )
        if guard.type == GuardType.FIELD_EXACT_MATCH:
            return guard.value, None
        if guard.type == GuardType.NUMERICAL_VALUE_GTE:
            if field.type == EntityFieldType.INTEGER:
                return self._coerce_guard_numeric_value(field.field, guard.type, guard.value, int)
            if field.type == EntityFieldType.FLOAT:
                return self._coerce_guard_numeric_value(field.field, guard.type, guard.value, float)
            return (
                None,
                f"guard '{guard.type}' cannot be satisfied for field '{field.field}' of type '{field.type}'",
            )
        if guard.type == GuardType.NUMERICAL_VALUE_LTE:
            if field.type == EntityFieldType.INTEGER:
                return self._coerce_guard_numeric_value(field.field, guard.type, guard.value, int)
            if field.type == EntityFieldType.FLOAT:
                return self._coerce_guard_numeric_value(field.field, guard.type, guard.value, float)
            return (
                None,
                f"guard '{guard.type}' cannot be satisfied for field '{field.field}' of type '{field.type}'",
            )
        if guard.type == GuardType.NUMERICAL_VALUE_IN_SET:
            if not isinstance(guard.value, (list, tuple, set)) or not guard.value:
                return None, f"guard '{guard.type}' requires a non-empty list-like value"
            return next(iter(guard.value)), None
        if guard.type == GuardType.COMPARE_DATES:
            if current_value is not None:
                return current_value, None
            return self.default_value_for_field(field, prefer_concrete=True), None
        return current_value, None

    def _coerce_guard_numeric_value(
        self,
        field_name: str,
        guard_type: str,
        raw_value: object | None,
        caster: type[int] | type[float],
    ) -> tuple[object | None, str | None]:
        """Safely coerce a numeric guard value for simulation."""
        if raw_value is None:
            return None, f"guard '{guard_type}' for field '{field_name}' requires a numeric value"
        try:
            return caster(raw_value), None
        except (TypeError, ValueError):
            return (
                None,
                f"guard '{guard_type}' for field '{field_name}' has an incompatible numeric value",
            )

    def _synthesize_compare_dates_other(
        self, primary: object | None, operator: str, field: EntityField
    ) -> object | None:
        """Return a synthetic other_field value that satisfies the compare_dates operator.

        The record's own date is the base when it has one, otherwise the shared dry-run
        constant. `ne` has to move off the base like the ordering operators do: returning the
        base unchanged made `other != primary` false, so a "these dates must differ" rule
        reported its transition as unreachable in every dry run.
        """
        base_str = (
            primary
            if isinstance(primary, str)
            else (DRY_RUN_DATETIME if field.type == EntityFieldType.DATETIME else DRY_RUN_DATE)
        )
        offset = timedelta(days=DRY_RUN_DATE_OFFSET_DAYS)
        try:
            dt = datetime.fromisoformat(str(base_str).replace("Z", "+00:00"))
            if operator in {"lt", "lte", "ne"}:
                return (dt + offset).isoformat()
            if operator in {"gt", "gte"}:
                return (dt - offset).isoformat()
            return base_str
        except (TypeError, ValueError) as exc:
            # No usable date means no synthesized counterpart, so the guard simply fails and
            # the path reports as blocked. Without this the reason never says the date could
            # not be parsed, and a bad value looks identical to a legitimately blocked path.
            logger.warning(
                "compare_dates synthesis could not parse the base date, skipping the "
                "counterpart value: %s",
                exc,
                extra={"field": field.field, "operator": operator, "base": str(base_str)[:64]},
            )
            return None

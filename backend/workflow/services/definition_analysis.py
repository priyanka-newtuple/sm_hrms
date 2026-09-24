"""Deterministic structural analysis of workflow definitions.

Owns state/transition/graph rules, issue normalization, bucket and next-action
classification, transient report shaping, and definition-to-definition comparison.

Every function here is pure: inputs are immutable definitions or issue lists, outputs are
model values. There is no persistence, no forms or entity access, no authorization, no
configuration and no I/O. The manager decides which issue sources apply to a given
lifecycle flow and whether a report is persisted.

Deliberately outside this capability: entity-schema field rules, active-form
compatibility, dry-run traversal, version selection, and report persistence.

The issue-classification *catalog* (bucket names, per-code next actions, the graph-code
set) lives in `workflow.models.interface` per the fiesta rule that domain values do not
sit in logic files. This module owns the *rules* that consume it.

Validating an action's settings needs that action's config contract, which the executor
module owns because it defines the action. So this module imports from
`executor.models.interface` — a deliberate consumer-to-owner dependency, the same
direction every other module takes to a contract it does not own. It stays safe because
the import is contract-only (a constant, enums and one pure function), executor never
imports workflow, and the executable-kind *set* is still passed in as a plain value
rather than reached for. If the action catalogue grows past a couple of kinds, move the
per-kind rules behind one registry lookup instead of importing each contract here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from executor.models.interface import (
    ENTITY_ASSIGN_USER_ACTION_KIND,
    assign_user_config_problem,
)
from workflow.models.interface import (
    DEFAULT_ISSUE_ACTION,
    DEFAULT_ISSUE_BUCKET,
    GRAPH_ISSUE_CODES,
    ISSUE_ACTIONS,
    DefinitionReport,
    Guard,
    IssueBucket,
    IssueBuckets,
    ReportType,
    StateMachineDefinition,
    StateTag,
    Transition,
    TransitionGuardChange,
    TransitionRequiredFieldChange,
    ValidationIssue,
    ValidationIssueCode,
    VersionCompareSummary,
    transition_identity,
)
from workflow.models.response import StateMachineVersionCompareResponse


class DefinitionAnalysisService:
    """Deterministic structural analysis of workflow definitions.

    Holds no state and takes no dependencies: every method is pure, turning definitions or
    issue lists into model values. It is a class rather than a module of functions so that it
    is constructed and injected like every other workflow capability service, and so callers
    depend on one named collaborator instead of a module import.
    """

    # -----------------------------------------------------------------------
    # Graph primitives
    # -----------------------------------------------------------------------

    def outgoing_map(self, definition: StateMachineDefinition) -> dict[str, list[Transition]]:
        """Map each state name to the transitions leaving it."""
        return {
            state.name: [
                transition
                for transition in definition.transitions
                if state.name in transition.source_states
            ]
            for state in definition.states
        }

    def build_graph(self, transitions: list[Transition]) -> dict[str, set[str]]:
        """Build a state adjacency graph from transitions."""
        graph: dict[str, set[str]] = {}
        for transition in transitions:
            for source in transition.source_states:
                graph.setdefault(source, set()).add(transition.to_state)
        return graph

    def has_path(self, graph: dict[str, set[str]], start: str, target: str) -> bool:
        """Return whether a path exists between two states."""
        pending, visited = [start], set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(sorted(graph.get(current, set()) - visited))
        return False

    def reachable_states(self, graph: dict[str, set[str]], start_states: list[str]) -> set[str]:
        """Return every state reachable from the provided start states."""
        pending = list(start_states)
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(sorted(graph.get(current, set()) - visited))
        return visited

    # ---------------------------------------------------------------------------
    # Structural validation
    # ---------------------------------------------------------------------------

    def _initial_state_names(self, definition: StateMachineDefinition) -> set[str]:
        """Names of states tagged 'initial'."""
        return {state.name for state in definition.states if StateTag.INITIAL in state.tags}

    def _terminal_state_names(self, definition: StateMachineDefinition) -> set[str]:
        """Names of states tagged 'terminal'."""
        return {state.name for state in definition.states if StateTag.TERMINAL in state.tags}

    def _schema_guaranteed_fields(self, definition: StateMachineDefinition) -> set[str]:
        """Field names the schema guarantees on every record, by being required or defaulted."""
        return {
            field.field
            for field in definition.entity_schema.fields
            if field.required or field.default is not None
        }

    def _check_initial_state(self, definition: StateMachineDefinition) -> list[ValidationIssue]:
        """Require an initial state, and require it to carry the 'initial' tag."""
        if definition.initial_state is None:
            return [
                ValidationIssue(
                    code=ValidationIssueCode.MISSING_INITIAL_STATE,
                    message=(
                        "State machine definition requires at least one state tagged "
                        "'initial'."
                    ),
                )
            ]
        if definition.initial_state not in self._initial_state_names(definition):
            return [
                ValidationIssue(
                    code=ValidationIssueCode.INITIAL_STATE_MISSING_TAG,
                    message=(
                        f"State '{definition.initial_state}' is set as initial_state "
                        f"but is not tagged 'initial'."
                    ),
                )
            ]
        return []

    def _check_terminal_state(self, definition: StateMachineDefinition) -> list[ValidationIssue]:
        """Require at least one terminal state, so work can finish."""
        if any(state.terminal for state in definition.states):
            return []
        return [
            ValidationIssue(
                code=ValidationIssueCode.MISSING_TERMINAL_STATE,
                message="State machine definition requires at least one state tagged 'terminal'.",
            )
        ]

    def _check_transitions_present(
        self, definition: StateMachineDefinition
    ) -> list[ValidationIssue]:
        """Require at least one transition, so the process can move."""
        if definition.transitions:
            return []
        return [
            ValidationIssue(
                code=ValidationIssueCode.MISSING_TRANSITIONS,
                message="State machine definition requires at least one transition.",
            )
        ]

    def _check_action_chains(self, definition: StateMachineDefinition) -> list[ValidationIssue]:
        """Only the last action in a state's chain may declare outcome triggers."""
        issues: list[ValidationIssue] = []
        for state in definition.states:
            for action in state.on_state_actions[:-1]:
                if action.outcome_triggers:
                    issues.append(
                        ValidationIssue(
                            code=ValidationIssueCode.NON_LAST_ACTION_HAS_OUTCOME_TRIGGERS,
                            message=(
                                f"State '{state.name}': only the last action in a chain "
                                f"may define outcome triggers ('{action.kind}' is not last)."
                            ),
                        )
                    )
        return issues

    def _check_action_kinds(
        self, definition: StateMachineDefinition, known_action_kinds: frozenset[str]
    ) -> list[ValidationIssue]:
        """Report any action naming a kind the runtime cannot execute.

        Skipped entirely when `known_action_kinds` is empty.
        """
        if not known_action_kinds:
            return []
        return [
            ValidationIssue(
                code=ValidationIssueCode.UNKNOWN_ACTION_KIND,
                message=(
                    f"State '{state.name}': '{action.kind}' is not an action this "
                    f"platform can run."
                ),
            )
            for state in definition.states
            for action in state.on_state_actions
            if action.kind not in known_action_kinds
        ]

    def _check_action_configs(
        self, definition: StateMachineDefinition
    ) -> list[ValidationIssue]:
        """Report any action whose settings are invalid for its kind.

        Only kinds that declare a config contract are inspected.
        """
        issues: list[ValidationIssue] = []
        for state in definition.states:
            for action in state.on_state_actions:
                if action.kind != ENTITY_ASSIGN_USER_ACTION_KIND:
                    continue
                problem = assign_user_config_problem(action.config)
                if problem:
                    issues.append(
                        ValidationIssue(
                            code=ValidationIssueCode.INVALID_ACTION_CONFIG,
                            message=f"State '{state.name}': {problem}",
                        )
                    )
        return issues

    def validate_states(
        self,
        definition: StateMachineDefinition,
        known_action_kinds: frozenset[str] | None = None,
    ) -> list[ValidationIssue]:
        """Check initial-state tagging, terminal presence, transitions presence, and action chains.

        Check order is part of the response contract - the builder renders issues in sequence.

        `known_action_kinds` is the set of action kinds the runtime can execute,
        passed in as a plain value so this service stays free of dependencies;
        omitting it skips the action-kind existence check only.
        """
        issues: list[ValidationIssue] = []
        issues.extend(self._check_initial_state(definition))
        issues.extend(self._check_terminal_state(definition))
        issues.extend(self._check_transitions_present(definition))
        issues.extend(self._check_action_chains(definition))
        issues.extend(self._check_action_kinds(definition, known_action_kinds or frozenset()))
        issues.extend(self._check_action_configs(definition))
        return issues

    def _check_task_orders(self, transition: Transition) -> list[ValidationIssue]:
        """Task order numbers must be unique within a transition, pre and post independently."""
        issues: list[ValidationIssue] = []
        pre_orders = [task.order for task in transition.pre_transition_tasks]
        post_orders = [task.order for task in transition.post_transition_tasks]
        if len(set(pre_orders)) != len(pre_orders):
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.DUPLICATE_PRE_TRANSITION_TASK_ORDER,
                    message=(
                        f"Transition '{transition.trigger}' has duplicate "
                        f"pre-transition task order values."
                    ),
                )
            )
        if len(set(post_orders)) != len(post_orders):
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.DUPLICATE_POST_TRANSITION_TASK_ORDER,
                    message=(
                        f"Transition '{transition.trigger}' has duplicate "
                        f"post-transition task order values."
                    ),
                )
            )
        return issues

    def _check_terminal_outgoing(
        self,
        transition: Transition, terminal_state_names: set[str]
    ) -> list[ValidationIssue]:
        """A terminal state ends the process, so it may not have outgoing transitions."""
        if transition.from_state not in terminal_state_names:
            return []
        return [
            ValidationIssue(
                code=ValidationIssueCode.TERMINAL_STATE_HAS_OUTGOING_TRANSITION,
                message=(
                    f"'{transition.from_state}' is marked as a terminal state but has an "
                    f"outgoing transition '{transition.trigger}'. A terminal state ends the "
                    f"workflow — either remove this transition or unmark "
                    f"'{transition.from_state}' as terminal."
                ),
            )
        ]

    def _check_guard_reachability(
        self,
        transition: Transition,
        initial_state_names: set[str],
        schema_guaranteed: set[str],
        outgoing: dict[str, list[Transition]],
    ) -> list[ValidationIssue]:
        """Collect reachability warnings for every guard on one transition."""
        issues: list[ValidationIssue] = []
        for guard in transition.guards:
            issue = self._validate_guard_field_reachability(
                guard, transition, initial_state_names, schema_guaranteed, outgoing
            )
            if issue is not None:
                issues.append(issue)
        return issues

    def validate_transitions(self, definition: StateMachineDefinition) -> list[ValidationIssue]:
        """Check per-transition task orders, terminal outgoing transitions, and guard reachability.

        Issues are emitted in definition order, and within each transition in check order.
        """
        terminal_state_names = self._terminal_state_names(definition)
        initial_state_names = self._initial_state_names(definition)
        schema_guaranteed = self._schema_guaranteed_fields(definition)
        outgoing = self.outgoing_map(definition)

        issues: list[ValidationIssue] = []
        for transition in definition.transitions:
            issues.extend(self._check_task_orders(transition))
            issues.extend(self._check_terminal_outgoing(transition, terminal_state_names))
            issues.extend(
                self._check_guard_reachability(
                    transition, initial_state_names, schema_guaranteed, outgoing
                )
            )
        return issues

    def _validate_guard_field_reachability(
        self,
        guard: Guard,
        transition: Transition,
        initial_state_names: set[str],
        schema_required_or_defaulted: set[str],
        outgoing: dict[str, list[Transition]],
    ) -> ValidationIssue | None:
        """Warn when a guarded field is not guaranteed on every path to the transition."""
        if guard.field is None or guard.field in schema_required_or_defaulted:
            return None
        if any(rf.field == guard.field and rf.required for rf in transition.required_fields):
            return None
        pending: list[tuple[str, bool]] = [(s, False) for s in initial_state_names]
        visited: set[tuple[str, bool]] = set(pending)
        field_guaranteed = True
        while pending:
            state, field_set = pending.pop()
            if state == transition.from_state and not field_set:
                field_guaranteed = False
                break
            for candidate in outgoing.get(state, []):
                new_field_set = field_set or any(
                    rf.field == guard.field and rf.required for rf in candidate.required_fields
                )
                key = (candidate.to_state, new_field_set)
                if key not in visited:
                    visited.add(key)
                    pending.append(key)
        if field_guaranteed:
            return None
        return ValidationIssue(
            code=ValidationIssueCode.UNREACHABLE_GUARD_FIELD,
            message=(
                f"Transition '{transition.trigger}' guards on field '{guard.field}', but this "
                f"field may not be filled in when the transition fires — no prior step "
                f"guarantees it is "
                f"collected. Entities that arrive at '{transition.from_state}' without "
                f"'{guard.field}' set could get permanently stuck."
            ),
            severity="warning",
        )

    # ---------------------------------------------------------------------------
    # Issue classification and report shaping
    # ---------------------------------------------------------------------------

    def has_blocking_issues(self, issues: list[ValidationIssue]) -> bool:
        """Return whether any issue blocks the next lifecycle stage."""
        return any((issue.severity or "error") == "error" for issue in issues)

    def normalize_issues(
        self, issues: list[ValidationIssue], report_type: str
    ) -> list[ValidationIssue]:
        """Attach buckets and next-step actions to issues that do not already carry them."""
        return [
            ValidationIssue(
                code=issue.code,
                message=issue.message,
                severity=issue.severity,
                bucket=issue.bucket or self._issue_bucket(issue, report_type),
                action=issue.action or self._issue_action(issue),
            )
            for issue in issues
        ]

    def _issue_bucket(self, issue: ValidationIssue, report_type: str) -> str:
        """Map one issue into a builder-facing report bucket."""
        if report_type == ReportType.VALIDATION:
            return DEFAULT_ISSUE_BUCKET
        if issue.code in GRAPH_ISSUE_CODES:
            return IssueBucket.GRAPH_ERRORS
        if issue.code == ValidationIssueCode.LOOP_WITHOUT_TERMINAL:
            return IssueBucket.WORKFLOW_OBSERVATIONS
        return IssueBucket.SIMULATION_ERRORS

    def _issue_action(self, issue: ValidationIssue) -> str:
        """Return the one directive next action for a validation issue."""
        return ISSUE_ACTIONS.get(issue.code, DEFAULT_ISSUE_ACTION)

    def bucket_issues(self, issues: list[ValidationIssue]) -> IssueBuckets:
        """Group issues into reusable builder buckets."""
        buckets = IssueBuckets()
        for issue in issues:
            bucket_name = issue.bucket or DEFAULT_ISSUE_BUCKET
            if not hasattr(buckets, bucket_name):
                bucket_name = DEFAULT_ISSUE_BUCKET
            getattr(buckets, bucket_name).append(issue)
        return buckets

    def next_actions(self, issues: list[ValidationIssue]) -> list[str]:
        """Return ordered distinct next actions for the user."""
        actions: list[str] = []
        seen: set[str] = set()
        for issue in issues:
            if not issue.action or issue.action in seen:
                continue
            seen.add(issue.action)
            actions.append(issue.action)
        return actions

    def build_preview_report(
        self,
        machine_name: str, version: int, report_type: str, issues: list[ValidationIssue]
    ) -> DefinitionReport:
        """Build one normalized, non-persisted definition report."""
        normalized = self.normalize_issues(issues, report_type)
        return DefinitionReport(
            report_id=str(uuid4()),
            report_type=report_type,
            machine_name=machine_name,
            version=version,
            valid=not self.has_blocking_issues(normalized),
            issues=normalized,
            buckets=self.bucket_issues(normalized),
            next_actions=self.next_actions(normalized),
            created_at=datetime.now(UTC),
        )

    # ---------------------------------------------------------------------------
    # Version comparison
    # ---------------------------------------------------------------------------

    def _compare_state_names(
        self,
        left: StateMachineDefinition, right: StateMachineDefinition
    ) -> tuple[list[str], list[str]]:
        """Sorted state names added and removed between two definitions."""
        left_states = {item.name for item in left.states}
        right_states = {item.name for item in right.states}
        return sorted(right_states - left_states), sorted(left_states - right_states)

    def _index_transitions(self, definition: StateMachineDefinition) -> dict[str, Transition]:
        """Index a definition's transitions by canonical identity."""
        return {transition_identity(item): item for item in definition.transitions}

    def _compare_transition_keys(
        self,
        left_transitions: dict[str, Transition], right_transitions: dict[str, Transition]
    ) -> tuple[list[str], list[str], list[str]]:
        """Sorted added, removed and shared transition identity keys."""
        return (
            sorted(set(right_transitions) - set(left_transitions)),
            sorted(set(left_transitions) - set(right_transitions)),
            sorted(set(left_transitions) & set(right_transitions)),
        )

    def _detect_transition_changes(
        self,
        shared: list[str],
        left_transitions: dict[str, Transition],
        right_transitions: dict[str, Transition],
    ) -> tuple[list[TransitionRequiredFieldChange], list[TransitionGuardChange]]:
        """Required-field and guard changes for transitions present in both versions."""
        changed_fields: list[TransitionRequiredFieldChange] = []
        changed_guards: list[TransitionGuardChange] = []
        for key in shared:
            before, after = left_transitions[key], right_transitions[key]
            before_fields = {item.field for item in before.required_fields}
            after_fields = {item.field for item in after.required_fields}
            if before_fields != after_fields:
                changed_fields.append(
                    TransitionRequiredFieldChange(
                        trigger=after.trigger,
                        from_states=after.source_states,
                        to_state=after.to_state,
                        added_fields=sorted(after_fields - before_fields),
                        removed_fields=sorted(before_fields - after_fields),
                    )
                )
            if self._normalize_guards(before.guards) != self._normalize_guards(after.guards):
                changed_guards.append(
                    TransitionGuardChange(
                        trigger=after.trigger,
                        from_states=after.source_states,
                        to_state=after.to_state,
                        from_guards=before.guards,
                        to_guards=after.guards,
                    )
                )
        return changed_fields, changed_guards

    def compare_definitions(
        self,
        machine_name: str,
        from_version: int,
        to_version: int,
        left: StateMachineDefinition,
        right: StateMachineDefinition,
    ) -> StateMachineVersionCompareResponse:
        """Build a version comparison response for two definitions of one workflow."""
        added_states, removed_states = self._compare_state_names(left, right)
        left_transitions = self._index_transitions(left)
        right_transitions = self._index_transitions(right)
        added_keys, removed_keys, shared = self._compare_transition_keys(
            left_transitions, right_transitions
        )
        changed_fields, changed_guards = self._detect_transition_changes(
            shared, left_transitions, right_transitions
        )
        summary = VersionCompareSummary(
            changed=bool(
                added_states
                or removed_states
                or added_keys
                or removed_keys
                or changed_fields
                or changed_guards
            ),
            added_states_count=len(added_states),
            removed_states_count=len(removed_states),
            added_transitions_count=len(added_keys),
            removed_transitions_count=len(removed_keys),
            changed_roles_count=0,
            changed_required_fields_count=len(changed_fields),
            changed_guards_count=len(changed_guards),
        )
        return StateMachineVersionCompareResponse(
            machine_name=machine_name,
            from_version=from_version,
            to_version=to_version,
            summary=summary,
            added_states=added_states,
            removed_states=removed_states,
            added_transitions=[right_transitions[key] for key in added_keys],
            removed_transitions=[left_transitions[key] for key in removed_keys],
            changed_required_fields=changed_fields,
            changed_guards=changed_guards,
        )

    def _normalize_guards(
        self,
        guards: list[Guard],
    ) -> list[tuple[str, str | None, object | None, str | None]]:
        """Normalize guards into an order-independent comparable form."""
        return sorted(
            [(item.type, item.field, item.value, item.message) for item in guards],
            key=lambda value: (value[0], value[1] or "", str(value[2]), value[3] or ""),
        )

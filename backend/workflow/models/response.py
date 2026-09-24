"""workflow response models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from background_jobs.models.interface import ActionRunStatus
from common.data_model import BaseModel as PydanticBaseModel
from entities.models.response import EntityRecordResponse, EntityStateResponse
from workflow.models.interface import (
    ActivityRecord,
    AvailableTransition,
    DefinitionReport,
    DryRunPath,
    DryRunStep,
    DryRunTransitionCheck,
    EntitySchemaPicklist,
    EntityState,
    FieldTotalErrorCode,
    Guard,
    GuardEvaluation,
    PreflightFieldRequirement,
    StateMachineDefinition,
    StateMachineRecord,
    Transition,
    TransitionGuardChange,
    TransitionRequiredFieldChange,
    ValidationIssue,
    VersionCompareSummary,
    WorkflowDraftRecord,
    WorkflowDryRunSummary,
    WorkflowService,
    WorkflowServiceWithWorkflows,
)


class EntityWithStatesResponse(PydanticBaseModel):
    """An entity record with its workflow enrollments.

    Future replacement for the legacy combined `EntityState` shape. `entity`
    carries the canonical runtime record (data, identity, owner); `states`
    carries one row per workflow enrollment so a single entity can sit in
    multiple workflows. The workflow REST surface still returns `EntityState`
    today; switching this in is a follow-up.
    """

    entity: EntityRecordResponse
    states: list[EntityStateResponse] = Field(default_factory=list)

class WorkflowStatusResponse(PydanticBaseModel):
    """Workflow module status."""

    module: str
    status: str
    started: bool


class StateMachineListResponse(PydanticBaseModel):
    """State machine list response."""

    items: list[StateMachineRecord] = Field(default_factory=list)


class StateMachineValidationResponse(PydanticBaseModel):
    """Validation and compatibility response for a candidate definition."""

    machine_name: str
    base_version: int | None = None
    candidate_version: int
    can_dry_run: bool = False
    can_publish: bool
    validation_report_id: str
    validation_report: DefinitionReport
    dry_run_report: DefinitionReport | None = None
    dry_run_summary: WorkflowDryRunSummary | None = None


class WorkflowValidationIssueMessage(PydanticBaseModel):
    """Simple validation issue returned to workflow editing clients."""

    message: str


class WorkflowDraftSaveResponse(PydanticBaseModel):
    """Response for saving an in-progress workflow definition."""

    record: WorkflowDraftRecord
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    is_valid: bool
    deactivated: bool = False


class WorkflowDraftListResponse(PydanticBaseModel):
    """Draft state machine list response."""

    items: list[WorkflowDraftRecord] = Field(default_factory=list)


class WorkflowServiceWithWorkflowsListResponse(PydanticBaseModel):
    """A page of services, each with the workflows filed under it.

    Paginated over services, not workflows: `total` counts every service in the
    organization so the caller can build page controls, while each item carries
    its own complete workflow list.
    """

    organization_id: str
    items: list[WorkflowServiceWithWorkflows] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class WorkflowServiceListResponse(PydanticBaseModel):
    """Every service in the organization, ordered by name.

    Not paginated: this is the lookup list behind a service picker, and an
    organization has a handful of services rather than a growing history.
    """

    organization_id: str
    items: list[WorkflowService] = Field(default_factory=list)


class WorkflowListResponse(PydanticBaseModel):
    """Scoped workflow list response."""

    scope: str
    published_items: list[StateMachineRecord] = Field(default_factory=list)
    draft_items: list[WorkflowDraftRecord] = Field(default_factory=list)


class StateMachinePublishResponse(PydanticBaseModel):
    """Publish response for a successfully persisted workflow version."""

    state_machine: StateMachineRecord
    validation_report_id: str
    validation_report: DefinitionReport
    dry_run_report: DefinitionReport
    dry_run_summary: WorkflowDryRunSummary
    # True when the version published but its role transition permissions could not be
    # updated. The publish itself succeeded, so this is a warning for the caller to surface,
    # not a failure. Republishing will not repair it: the key change is no longer detectable.
    permission_sync_failed: bool = False


class TransitionPreflightResponse(PydanticBaseModel):
    """Transition preflight response."""

    entity_id: str
    trigger: str
    to_state: str
    label: str | None = None
    allowed: bool = False
    missing_required_fields: list[PreflightFieldRequirement] = Field(default_factory=list)
    guard_results: list[GuardEvaluation] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    needs_dialog: bool = False


class AvailableTransitionsResponse(PydanticBaseModel):
    """Available transitions response."""

    entity_id: str
    current_state: str
    available_transitions: list[AvailableTransition] = Field(default_factory=list)


class TransitionExecutionResponse(PydanticBaseModel):
    """Transition execution response."""

    transition_id: str
    event_id: str
    entity_id: str
    from_state: str
    to_state: str
    state_version: int
    executed_tasks: list[str] = Field(default_factory=list)
    idempotent: bool = False
    sla_due_at: datetime | None = None
    state_duration_seconds: int | None = None


class TransitionHistoryResponse(PydanticBaseModel):
    """Transition history response."""

    total: int = 0
    items: list[ActivityRecord] = Field(default_factory=list)


class EventRecord(PydanticBaseModel):
    """Projected event record."""

    event_id: str
    entity_id: str
    machine_name: str
    machine_version: int
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class EventHistoryResponse(PydanticBaseModel):
    """Event history response."""

    items: list[EventRecord] = Field(default_factory=list)


class StateMachineVersionCompareResponse(PydanticBaseModel):
    """State machine compare response."""

    machine_name: str
    from_version: int
    to_version: int
    summary: VersionCompareSummary
    added_states: list[str] = Field(default_factory=list)
    removed_states: list[str] = Field(default_factory=list)
    added_transitions: list[Transition] = Field(default_factory=list)
    removed_transitions: list[Transition] = Field(default_factory=list)
    changed_required_fields: list[TransitionRequiredFieldChange] = Field(default_factory=list)
    changed_guards: list[TransitionGuardChange] = Field(default_factory=list)


class EntityDryRunResponse(PydanticBaseModel):
    """Entity dry-run response."""

    machine_name: str
    version: int
    definition: StateMachineDefinition
    validation_report: DefinitionReport
    dry_run_summary: WorkflowDryRunSummary


class WorkflowPathLine(PydanticBaseModel):
    """Human-readable linear workflow path."""

    path_type: str
    rendered: str
    start_state: str
    end_state: str
    blocked_reasons: list[str] = Field(default_factory=list)


class WorkflowPathsResponse(PydanticBaseModel):
    """Rendered workflow path analysis for one candidate definition."""

    machine_name: str
    candidate_version: int
    validation_report: DefinitionReport
    dry_run_report: DefinitionReport | None = None
    paths: list[WorkflowPathLine] = Field(default_factory=list)


class EntityListResponse(PydanticBaseModel):
    """Paginated entity list response."""

    items: list[EntityState] = Field(default_factory=list)
    total: int = 0


class WorkflowEnrollmentSummary(PydanticBaseModel):
    """Compact, permission-filtered row for workflow boards and lists."""

    state_id: str
    entity_id: str
    entity_type_id: str
    entity_type: str
    organization_id: str
    workflow_id: str
    machine_name: str
    machine_display_name: str
    machine_version: int
    current_state: str
    state_version: int = 0
    display_name: str
    summary_fields: dict[str, object] = Field(default_factory=dict)
    transition_options: list[AvailableTransition] = Field(default_factory=list)
    owner_id: str | None = None
    assignee_id: str | None = None
    # Filled in server-side so callers see a person, not a user id. None when
    # the user can't be looked up.
    owner_name: str | None = None
    assignee_name: str | None = None
    due_date: date | None = None
    state_entered_at: datetime | None = None
    last_transition_at: datetime | None = None
    sla_due_at: datetime | None = None
    entity_created_at: datetime | None = None
    entity_updated_at: datetime | None = None
    archived_at: datetime | None = None
    preview_thumbnail_url: str | None = None


class FieldTotalValue(PydanticBaseModel):
    """A column's total, with the currency it is denominated in.

    `currency_code` is set only for a currency column, and only because the
    aggregate confirmed every contributing row shared that one code — the
    client must not have to re-derive it from whichever rows it happens to
    be showing.
    """

    total: float
    currency_code: str | None = None


class FieldTotalError(PydanticBaseModel):
    """Why one requested column has no single total, in place of a number.

    `message` is user-facing and names what to fix, since the only resolution
    is a data change (normalizing the records to one currency).
    """

    error: FieldTotalErrorCode
    currency_codes: list[str] = Field(default_factory=list)
    message: str


class WorkflowEnrollmentSummaryPage(PydanticBaseModel):
    """Offset-paged result of the canonical workflow-enrollment read API."""

    items: list[WorkflowEnrollmentSummary] = Field(default_factory=list)
    has_more: bool = False
    state_counts: dict[str, int] | None = None
    total_count: int | None = None
    identifier_options: list[str] | None = None
    field_totals: dict[str, FieldTotalValue | FieldTotalError] | None = None
    """Sum of each requested numeric column across the whole filtered set.

    Only the fields the actor may actually read are present: a column their
    role cannot view, or masks, is omitted entirely rather than summed. A
    column whose values span several currencies carries a `FieldTotalError`
    instead of a number."""
    scan_truncated: bool = False
    """True when a bounded row scan stopped at its cap instead of at the data.

    Only reachable for callers whose read policy carries a condition that has
    to be evaluated on a loaded row. When set, `state_counts`/`total_count`
    understate and `has_more` may be `False` while more rows exist — the
    response is a prefix, not the whole answer."""


class EntitySchemaPicklistListResponse(PydanticBaseModel):
    """Reusable entity-schema picklist list response."""

    items: list[EntitySchemaPicklist] = Field(default_factory=list)
    total: int = 0


class StateActionRerunResponse(PydanticBaseModel):
    """Result of manually re-running the current state's on-state action chain."""

    run_id: str
    entity_id: str
    state: str
    action_kinds: list[str] = Field(default_factory=list)
    status: str = ActionRunStatus.PENDING.value


class RunFactsItem(PydanticBaseModel):
    """One entity's state facts, for analytics — no entity_data, no read-policy projection."""

    entity_id: str
    machine_name: str
    machine_display_name: str
    current_state: str
    current_state_tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    state_entered_at: datetime | None = None
    terminal_transition_at: datetime | None = None
    assignee_id: str | None = None
    due_at: datetime | None = None
    has_deviation: bool = False


class RunFactsResponse(PydanticBaseModel):
    """Batched run-facts result — one item per resolvable entity id, in no particular order."""

    items: list[RunFactsItem] = Field(default_factory=list)

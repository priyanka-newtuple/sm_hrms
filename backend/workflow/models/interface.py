"""workflow typed contracts and shared in-memory records."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic import AnyHttpUrl, EmailStr, Field, TypeAdapter, model_validator

from common.auto_number import AUTO_NUMBER_MAX_AFFIX_LENGTH
from common.data_model import BaseModel as PydanticBaseModel
from common.data_model import ExtendedStrEnum
from common.logger import logger
from common.protocols import EntityConditionSpec, EntityReadPolicy

if TYPE_CHECKING:
    from workflow.db_models import WorkflowEnrollmentSummaryRow

_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


def _non_empty(value: object, field_name: str) -> str:
    """Normalize a string field."""
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _optional_non_empty(value: object | None) -> str | None:
    """Normalize optional text fields, treating blank values as None."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _is_json_compatible(value: object | None) -> bool:
    """Return whether a value can be represented as plain JSON data."""
    if value is None:
        return True
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_compatible(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_compatible(item) for key, item in value.items())
    return False


def _matches_entity_field_type(
    value: object | None, field_type: str, enum_values: list[str] | None = None
) -> bool:
    """Return whether a raw value is compatible with a declared entity field type."""
    if value is None:
        return True
    normalized = str(field_type).strip().lower()
    if normalized in {EntityFieldType.NUMBER, EntityFieldType.INTEGER_ALIAS}:
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
    if normalized in {EntityFieldType.STRING, EntityFieldType.TEXT, EntityFieldType.PHONE}:
        return isinstance(value, str)
    if normalized == EntityFieldType.EMAIL:
        if not isinstance(value, str):
            return False
        try:
            _EMAIL_ADAPTER.validate_python(value)
        except Exception:
            return False
        return True
    if normalized == EntityFieldType.URL:
        if not isinstance(value, str):
            return False
        try:
            _URL_ADAPTER.validate_python(value)
        except Exception:
            return False
        return True
    if normalized == EntityFieldType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if normalized == EntityFieldType.FLOAT:
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
    if normalized == EntityFieldType.BOOLEAN:
        return isinstance(value, bool)
    if normalized in {EntityFieldType.DATE, EntityFieldType.DATETIME}:
        return isinstance(value, str)
    if normalized == EntityFieldType.ENUM:
        return isinstance(value, str) and (not enum_values or value in enum_values)
    if normalized == EntityFieldType.JSON:
        return _is_json_compatible(value)
    if normalized == EntityFieldType.MULTI_SELECT:
        return isinstance(value, list)
    if normalized == EntityFieldType.AUTO_NUMBER:
        return isinstance(value, str)
    if normalized == EntityFieldType.TIMER_DURATION:
        return isinstance(value, int) and not isinstance(value, bool)
    return False


def not_enrolled_message(entity_id: str, machine_name: str) -> str:
    """Message for a transition request against an entity that has no workflow enrollment.

    Kept in one place because three endpoints raise it, and it is text a client reads.
    """
    if machine_name:
        return f"entity '{entity_id}' is not enrolled in workflow '{machine_name}'"
    return f"entity '{entity_id}' is not enrolled in any workflow"


def matches_workflow_value(type_name: str, value: object, enum_values: list | None = None) -> bool:
    """Check a workflow value against a declared type name.

    Deliberately separate from `_matches_entity_field_type`, which the two disagree with on
    several inputs — `None` (rejected here, accepted there), `float` given an int, `number` given
    a float, `dict`/`list`, and unrecognised type names (permissive here, strict there). They serve
    different contracts and must not be merged without deciding, per caller, which semantic is
    wanted.
    """
    normalized = str(type_name).strip().lower()
    if normalized in {"string", "str", "text", "phone"}:
        return isinstance(value, str)
    if normalized == "email":
        return _matches_entity_field_type(value, "email")
    if normalized == "url":
        return _matches_entity_field_type(value, "url")
    if normalized in {"integer", "int"}:
        return isinstance(value, int) and not isinstance(value, bool)
    if normalized == "float":
        return isinstance(value, float)
    if normalized == "number":
        return isinstance(value, int) and not isinstance(value, bool)
    if normalized in {"boolean", "bool"}:
        return isinstance(value, bool)
    if normalized in {"object", "dict"}:
        return isinstance(value, dict)
    if normalized in {"array", "list"}:
        return isinstance(value, list)
    if normalized == "json":
        return _is_json_compatible(value)
    if normalized == "enum":
        if enum_values is not None:
            return isinstance(value, str) and value in enum_values
        return isinstance(value, str)
    if normalized == "date":
        return isinstance(value, str)
    if normalized == "datetime":
        return isinstance(value, str)
    if normalized == "timer_duration":
        return isinstance(value, int) and not isinstance(value, bool)
    if normalized == "document":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return value is not None


# Values the dry-run simulator invents for fields a definition leaves empty. Fixed rather than
# derived from the clock: a dry run has to give the same answer for the same definition every
# time, and `_synthesize_compare_dates_other` derives a counterpart date from these by offsetting
# a day, so only their relative order matters, never the absolute value.
DRY_RUN_DATE = "2026-01-01"
DRY_RUN_DATETIME = "2026-01-01T00:00:00Z"
DRY_RUN_DATE_OFFSET_DAYS = 1

# Synthetic values for the remaining field types. `mock_` is prefixed to the field's own name so a
# value that escapes into real data is obvious at a glance.
DRY_RUN_STRING_PREFIX = "mock_"
DRY_RUN_EMAIL_DOMAIN = "example.com"
DRY_RUN_URL_BASE = "https://example.com"
DRY_RUN_PHONE = "+15551234567"
DRY_RUN_INTEGER = 1
DRY_RUN_FLOAT = 1.0
DRY_RUN_BOOLEAN = True
DRY_RUN_TIMER_DURATION_SECONDS = 0


class GuardType(ExtendedStrEnum):
    """Supported guard types."""

    FIELD_PRESENT = "field_present"
    FIELD_EXACT_MATCH = "field_exact_match"
    NUMERICAL_VALUE_GTE = "numerical_value_gte"
    NUMERICAL_VALUE_LTE = "numerical_value_lte"
    NUMERICAL_VALUE_IN_SET = "numerical_value_in_set"
    COMPARE_DATES = "compare_dates"


GUARD_TYPE_ALL: set[str] = {
    GuardType.FIELD_PRESENT,
    GuardType.FIELD_EXACT_MATCH,
    GuardType.NUMERICAL_VALUE_GTE,
    GuardType.NUMERICAL_VALUE_LTE,
    GuardType.NUMERICAL_VALUE_IN_SET,
    GuardType.COMPARE_DATES,
}

GUARD_TYPE_LEGACY_ALIASES: dict[str, str] = {
    "value_equals": GuardType.FIELD_EXACT_MATCH,
    "value_gte": GuardType.NUMERICAL_VALUE_GTE,
    "value_lte": GuardType.NUMERICAL_VALUE_LTE,
    "value_in_set": GuardType.NUMERICAL_VALUE_IN_SET,
}


class EntityFieldType(ExtendedStrEnum):
    """Supported entity field types for workflow definitions."""

    STRING = "string"
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    NUMBER = "number"
    INTEGER = "int"
    INTEGER_ALIAS = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ENUM = "enum"
    JSON = "json"
    MULTI_SELECT = "multi_select"
    AUTO_NUMBER = "auto_number"
    CURRENCY = "currency"
    # Elapsed seconds recorded by the timer control rather than typed directly.
    # Matches the `timer_duration` catalogue code.
    TIMER_DURATION = "timer_duration"
    # Holds a list of filehandler file ids, not one value: a form field can carry
    # several attached documents.
    DOCUMENT = "document"


class FormFieldType(ExtendedStrEnum):
    """The form-builder field types this module knows how to translate.

    A separate vocabulary from `EntityFieldType`: these are the types a form field is saved as,
    and several of them collapse onto one workflow type. Only the ones the translation handles
    are listed — a form type absent from here is compared as itself.
    """

    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    PHONE = "phone"
    URL = "url"
    DATE = "date"
    DATETIME = "datetime"
    EMAIL = "email"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    MULTI_SELECT = "multi_select"
    JSON_ARRAY = "json_array"


class TableColumnType(ExtendedStrEnum):
    """The cell types a table or grid column can declare.

    A third vocabulary, distinct from both `EntityFieldType` and `FormFieldType`: a column
    describes one cell inside a JSON table value, so it carries presentation types such as
    `percent` that no stored field type has. `int` and `float` are the engine spellings of
    `integer` and `number`, accepted because a column can be described by its stored type
    rather than its builder type.

    Not exhaustive by design. A column type missing from here is accepted rather than rejected
    (see `_matches_table_cell_type`), so a table the form builder permitted is never blocked by
    this list being out of date.
    """

    TEXT = "text"
    TEXTAREA = "textarea"
    EMAIL = "email"
    PHONE = "phone"
    SELECT = "select"
    DATE = "date"
    DATETIME = "datetime"
    URL = "url"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    INT = "int"
    NUMBER = "number"
    FLOAT = "float"
    CURRENCY = "currency"
    PERCENT = "percent"
    MULTI_SELECT = "multi_select"


# The state reported for an entity that exists but is enrolled in no workflow. No definition
# declares it — it exists so a tracked-but-unenrolled entity still has a state to show.
UNENROLLED_PLACEHOLDER_STATE = "CREATED"

class TableRowMode(ExtendedStrEnum):
    """How a table field decides what rows it has.

    FIXED means the rows are part of the definition, so every one of them counts and can carry
    per-cell calculations. DYNAMIC means the user adds rows as they go, so blank ones are not
    counted and there are no stable row ids to address. A config that omits `row_mode`, or names
    a mode not listed here, is treated as DYNAMIC.
    """

    FIXED = "fixed"
    DYNAMIC = "dynamic"


class StateTag(ExtendedStrEnum):
    """Supported built-in state tags."""

    INITIAL = "initial"
    TERMINAL = "terminal"
    DEVIATION = "deviation"


class EntityTypeSentinel(ExtendedStrEnum):
    """Placeholder `entity_type` value on a workflow definition that hasn't
    had a real entity type configured yet (see `_blank_draft_definition`) —
    a workflow can be saved and viewed in this state without crashing."""

    UNASSIGNED = "entity"


class TaskName(ExtendedStrEnum):
    """Built-in task names."""

    RECORD_TRANSITION = "task_record_transition"
    EMIT_NOTIFICATION = "task_emit_notification"
    UPDATE_SUMMARY = "task_update_summary"


ENTITY_FIELD_TYPE_ALL: set[str] = {
    EntityFieldType.STRING,
    EntityFieldType.TEXT,
    EntityFieldType.EMAIL,
    EntityFieldType.PHONE,
    EntityFieldType.URL,
    EntityFieldType.NUMBER,
    EntityFieldType.INTEGER,
    EntityFieldType.INTEGER_ALIAS,
    EntityFieldType.FLOAT,
    EntityFieldType.BOOLEAN,
    EntityFieldType.DATE,
    EntityFieldType.DATETIME,
    EntityFieldType.ENUM,
    EntityFieldType.JSON,
    EntityFieldType.MULTI_SELECT,
    EntityFieldType.AUTO_NUMBER,
    EntityFieldType.CURRENCY,
    EntityFieldType.TIMER_DURATION,
}

STATE_TAG_ALL: set[str] = {StateTag.INITIAL, StateTag.TERMINAL, StateTag.DEVIATION}

TASK_NAME_ALL: set[str] = {
    TaskName.RECORD_TRANSITION,
    TaskName.EMIT_NOTIFICATION,
    TaskName.UPDATE_SUMMARY,
}


class FieldOwnership(ExtendedStrEnum):
    """Supported field ownership types."""

    OWNED = "owned"
    INHERITED = "inherited"


class TransitionStatus(ExtendedStrEnum):
    """Transition statuses."""

    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    CONFLICT = "conflict"


class ReportType(ExtendedStrEnum):
    """Definition report types."""

    VALIDATION = "validation"
    COMPATIBILITY = "compatibility"
    DRY_RUN = "dry_run"


class ActivityType(ExtendedStrEnum):
    """Activity log types."""

    TRANSITION_ATTEMPT = "transition_attempt"
    TASK_EXECUTED = "task_executed"


class EventType(ExtendedStrEnum):
    """Projected event types."""

    TRANSITION_COMMITTED = "transition_committed"
    TASK_EXECUTED = "task_executed"


class WorkflowEventType(ExtendedStrEnum):
    """Entity event types emitted during workflow execution."""

    STATE_TRANSITIONED = "STATE_TRANSITIONED"
    ENTITY_ENROLLED = "ENTITY_ENROLLED"
    TASK_EXECUTED = "TASK_EXECUTED"


class ActorType(ExtendedStrEnum):
    """Actor type values recorded in workflow events and transition logs."""

    USER = "user"
    SYSTEM = "system"


class TransitionAuditEventType(ExtendedStrEnum):
    """Event type values written to `audit_events` for transition attempts.

    Values must match the catalog registered in audit/models/interface.py
    under AuditMetadataType.TRANSITION.
    """

    SUCCEEDED = "TRANSITION_SUCCEEDED"
    BLOCKED = "TRANSITION_BLOCKED"
    CONFLICT = "TRANSITION_CONFLICT"


# What a transition audit row records for an attempt the platform made on its own behalf. The
# triggering user's id is still stored separately, so a system label does not lose who caused it.
# Reported to the client and recorded on the audit row when the optimistic lock rejects a
# transition. One name so the message a user reads and the message stored cannot drift apart.
STATE_VERSION_CONFLICT_REASON = "workflow entity state version conflict"

# The SLA breach signal. These values leave this module: `dashboard/metrics.py` counts breaches
# by matching both the action kind and the signal type, and `executor/executors/signal_fire.py`
# executes the steps. Changing one means changing those too, so they are named here rather than
# repeated as literals at the point of writing.
# `assignee_ids` may name this instead of a user id, to mean "rows with nobody assigned".
# It reaches the API as a query value, so it is fixed rather than free-form.
UNASSIGNED_FILTER_SENTINEL = "__unassigned__"

# How many identifier options the board will offer. A bound rather than a page size: the list
# populates a filter dropdown, and a caller asking for every identifier in a large organization
# would scan far more than the dropdown could usefully show.
IDENTIFIER_OPTION_CAP = 200

# The largest page the enrollment board will return, however large a `limit` the caller asks for.
# The route declares it as its `le=` bound and the read clamps to it again, so a caller reaching
# the manager directly cannot ask for more than the API allows.
ENROLLMENT_PAGE_SIZE_CAP = 200

# The most entity ids a single run-facts batch read will accept. Kept in step with
# ENROLLMENT_PAGE_SIZE_CAP above, since both bound one caller-supplied id set to one query.
RUN_FACTS_ENTITY_ID_CAP = 200

# Page size for succeeded-transition audit rows scanned while deriving run-fact
# deviation history. This bounds an individual query, not the total history:
# the reader continues paging until each enrollment is classified.
RUN_FACTS_DEVIATION_HISTORY_PAGE_SIZE = 2000


SLA_SIGNAL_ACTION_KIND = "signal.fire"
SLA_BREACH_SIGNAL_TYPE = "sla_breach"
SLA_BREACH_STEP_TYPE = "notify"
SLA_BREACH_NOTIFY_RECIPIENT = "entity_creator"
SLA_BREACH_NOTIFY_TITLE = "SLA Deadline Missed"
SLA_BREACH_NOTIFY_BODY = "An entity has been stuck in '{state}' past its SLA deadline."


class StateActionConfigKey(ExtendedStrEnum):
    """Keys inside an action run's `config_json`.

    A cross-module contract, not internal bookkeeping: `background_jobs` reads these to decide
    what to run next and whether a run is stale. Renaming one breaks the worker, and the worker
    still refers to them as plain strings, so both sides must be changed together.
    """

    # what the action itself was configured with
    OUTCOME_TRIGGERS = "outcome_triggers"
    FAILURE_POLICY = "failure_policy"

    # where this run sits in its state's chain
    CHAIN_ID = "chain_id"
    STATE_ACTION_INDEX = "state_action_index"
    STATE_ACTION_TOTAL = "state_action_total"
    ORIGIN_STATE = "origin_state"
    ORIGIN_STATE_VERSION = "origin_state_version"
    ISOLATED_RERUN = "isolated_rerun"

    # only present on a manual rerun
    TRIGGER_SOURCE = "trigger_source"
    TRIGGERED_BY = "triggered_by"

    # the one value, rather than key, this enum carries: what `trigger_source` is set to
    MANUAL_RERUN_SOURCE = "manual_rerun"


# Stands in for a transition key when a state is entered by enrolling rather than by a
# transition. It becomes part of the action's idempotency key, so it must stay stable: changing
# it would make an already-scheduled enrollment action look unscheduled.
ENROLLMENT_TRANSITION_KEY = "enrollment"

SYSTEM_ACTOR_NAME = "System"
SYSTEM_ACTOR_ROLE = "SYSTEM"

# `source` on a transition audit row. Every transition reaches the engine through the API, so
# this is constant today; it exists as a name so a second entry point does not add a bare string.
TRANSITION_AUDIT_SOURCE = "api"

TRANSITION_STATUS_TO_AUDIT_EVENT_TYPE: dict[str, str] = {
    TransitionStatus.SUCCEEDED: TransitionAuditEventType.SUCCEEDED,
    TransitionStatus.BLOCKED: TransitionAuditEventType.BLOCKED,
    TransitionStatus.CONFLICT: TransitionAuditEventType.CONFLICT,
}


class TransitionAuditMetadataKey(ExtendedStrEnum):
    """Well-known keys inside the `metadata` JSONB payload for transition audit events."""

    WORKFLOW_ID = "workflow_id"
    TRIGGER = "trigger"
    STATUS = "status"
    FAILURE_CODE = "failure_code"
    INPUTS = "inputs"
    OUTPUTS = "outputs"
    GUARD_EVALUATIONS = "guard_evaluations"
    MACHINE_NAME = "machine_name"
    MACHINE_VERSION = "machine_version"
    BLOCKED_REASONS = "blocked_reasons"


class ValidationIssueCode(ExtendedStrEnum):
    """All issue codes produced by workflow definition validation."""

    # Definition-level structural issues
    INVALID_DEFINITION = "invalid_definition"
    MISSING_INITIAL_STATE = "missing_initial_state"
    INITIAL_STATE_MISSING_TAG = "initial_state_missing_tag"
    MISSING_TERMINAL_STATE = "missing_terminal_state"
    MISSING_TRANSITIONS = "missing_transitions"
    INVALID_ENUM_DEFAULT = "invalid_enum_default"
    CALC_CYCLE = "calc_cycle"
    CALC_INVALID_REF = "calc_invalid_ref"
    ORPHANED_ENTITY_SCHEMA_FIELD = "orphaned_entity_schema_field"
    ENTITY_SCHEMA_FIELD_DRIFTED = "entity_schema_field_drifted"
    DUPLICATE_PRE_TRANSITION_TASK_ORDER = "duplicate_pre_transition_task_order"
    DUPLICATE_POST_TRANSITION_TASK_ORDER = "duplicate_post_transition_task_order"
    TERMINAL_STATE_HAS_OUTGOING_TRANSITION = "terminal_state_has_outgoing_transition"
    UNREACHABLE_GUARD_FIELD = "unreachable_guard_field"
    NON_LAST_ACTION_HAS_OUTCOME_TRIGGERS = "non_last_action_has_outcome_triggers"
    UNKNOWN_ACTION_KIND = "unknown_action_kind"
    INVALID_ACTION_CONFIG = "invalid_action_config"
    PINNED_METHOD_FIELD_CONFLICT = "pinned_method_field_conflict"
    UNKNOWN_DOCUMENT_FILE = "unknown_document_file"
    PINNED_METHOD_FIELD_UNRELATED_SOURCE = "pinned_method_field_unrelated_source"
    PINNED_METHOD_FIELD_UNKNOWN_SOURCE_FIELD = "pinned_method_field_unknown_source_field"
    PINNED_METHOD_FIELD_SOURCE_REMAPPED = "pinned_method_field_source_remapped"
    # Dry-run graph / simulation issues
    UNREACHABLE_STATE = "unreachable_state"
    DEAD_END_STATE = "dead_end_state"
    NO_TERMINAL_PATH = "no_terminal_path"
    UNSATISFIED_TRANSITION = "unsatisfied_transition"
    LOOP_WITHOUT_TERMINAL = "loop_without_terminal"


class FieldTotalErrorCode(ExtendedStrEnum):
    """Why a requested numeric column has no single total to report."""

    MIXED_CURRENCY = "mixed_currency"


class CurrencyValueKey(ExtendedStrEnum):
    """Keys of a currency value as stored in an entity record's `data` JSON."""

    AMOUNT = "amount"
    CURRENCY_CODE = "currency_code"


class JsonbType(ExtendedStrEnum):
    """`jsonb_typeof()` results the enrollment queries branch on."""

    OBJECT = "object"
    BOOLEAN = "boolean"


class EnrollmentInclude(ExtendedStrEnum):
    """Opt-in facets of the enrollment summary API's `include=` parameter.

    Each costs an extra aggregate, so none is computed unless asked for.
    """

    STATE_COUNTS = "state_counts"
    TOTAL_COUNT = "total_count"
    IDENTIFIER_OPTIONS = "identifier_options"


# Bounds on the `field_filters` JSON object accepted by the enrollment summary
# API — it reaches SQL as exact-match predicates, so it is validated as
# untrusted input rather than trusted for being well-formed JSON.
FIELD_FILTERS_MAX_KEYS = 20
FIELD_FILTERS_MAX_KEY_LENGTH = 128
FIELD_FILTERS_MAX_VALUE_LENGTH = 500
# A filter value may be a list (match any of); this bounds how many entries.
FIELD_FILTERS_MAX_VALUES = 50


# Values eligible to be summed: entity data is free-form JSON, so anything
# that isn't plainly numeric is skipped rather than allowed to fail a query.
NUMERIC_TEXT_PATTERN = r"^[+-]?[0-9]+(\.[0-9]+)?$"
# How much of an unparseable value to keep when logging it — enough to
# recognise the offending record, not enough to dump a field into the logs.
UNSUMMABLE_VALUE_LOG_LIMIT = 100


@dataclass(frozen=True)
class EnrollmentAggregateFilters:
    """The row set an enrollment aggregate runs over, as one passable value.

    Field names deliberately mirror `_enrollment_summary_base_query`'s
    parameters so a query method can forward them with `asdict(...)` instead
    of restating sixteen arguments. Excludes `current_state`: the counts must
    span every state to fill a board's column badges, while a total describes
    only the rows on screen, so that one stays each caller's own decision.
    """

    organization_id: str
    machine_name: str | None
    machine_names: set[str] | None
    exclude_states: frozenset[str] | None
    entity_type_name: str | None
    entity_type_id: str | None
    entity_type_ids: set[str] | None
    include_archived: bool
    entity_ids: set[str] | None
    assignee_ids: frozenset[str] | None
    include_unassigned: bool
    search: str | None
    field_filters: dict[str, str | list[str]] | None
    searchable_fields_by_type: dict[str, set[str] | None] | None
    read_conditions_by_type: dict[str, list[EntityConditionSpec]] | None
    identifier: str | None


@dataclass(frozen=True)
class FieldNumericAggregate:
    """One summed field's aggregate over the rows of a single query.

    `currency_codes` is empty for a plain numeric field; a currency field
    carries every distinct code found, so the caller can refuse to add
    amounts denominated differently instead of reporting a meaningless total.
    """

    total: Decimal
    currency_codes: frozenset[str]


class EnrollmentSortField(ExtendedStrEnum):
    """What `sort_by` may name on the enrollment board.

    A caller-supplied value reaches SQL, so this is a whitelist rather than a hint: anything
    outside it is refused instead of being passed through.
    """

    IDENTIFIER = "identifier"
    DISPLAY_NAME = "display_name"
    STATE = "state"
    CREATED = "created"
    DUE_DATE = "due_date"


class EnrollmentSortDirection(ExtendedStrEnum):
    """Which way the enrollment board sorts. Also caller-supplied, also a whitelist."""

    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True)
class EnrollmentSummaryRequest:
    """One enrollment-board read, with every caller-supplied value already parsed and checked.

    Built once from the endpoint's query parameters and then passed around whole, so the parts
    that answer different sections of the response cannot disagree about what was asked for.
    """

    machine_name: str | None
    machine_names: set[str] | None
    current_state: str | None
    exclude_states: frozenset[str] | None
    entity_type_name: str | None
    entity_type_id: str | None
    include_archived: bool
    anchor_entity_id: str | None
    requested_fields: set[str]
    thumbnail_field: str | None
    assignee_ids: frozenset[str] | None
    include_unassigned: bool
    search: str | None
    field_filters: dict[str, str | list[str]] | None
    identifier: str | None
    sort_by: str | None
    sort_dir: str
    offset: int | None
    include_total_count: bool
    include_identifier_options: bool
    page_size: int


@dataclass(frozen=True)
class EntityReadAccess:
    """What an actor may read, split by where each half can be enforced.

    `policies` is the authority — `apply_read_policy_to_data` runs on every row
    that reaches a response regardless of what SQL did. `sql_conditions` is the
    subset of row-level conditions expressible as a predicate on the entity
    row itself, and `needs_row_scan` says whether anything is left over that
    only a loaded row can answer.
    """

    policies: dict[str, EntityReadPolicy]
    sql_conditions: dict[str, list[EntityConditionSpec]]
    scan_type_ids: frozenset[str]
    needs_row_scan: bool

    @property
    def type_ids(self) -> set[str]:
        return set(self.policies)


@dataclass
class ScanLimit:
    """Set when a bounded scan stopped at its configured cap, not at the data.

    Mutable and passed down deliberately: the scans are generators, so there is
    no return value to carry this back, and a caller that stops early never
    resumes them. A response built from an exhausted scan understates its
    counts and can report `has_more=False` while more rows exist — which the
    caller has no other way to detect.
    """

    exhausted: bool = False


@dataclass
class FieldTotalAccumulator:
    """Running sum of one field's values across the rows of a scan.

    Mirrors the SQL path's semantics exactly, so the fast and scan paths cannot
    disagree: a null, a missing key or an unparseable value is skipped rather
    than counted as zero, and an all-null column still totals zero.
    """

    field: str
    total: Decimal = Decimal(0)
    currency_codes: set[str] = dataclass_field(default_factory=set)

    def add(self, value: object, *, entity_id: str) -> None:
        """Fold one row's raw value in, ignoring anything non-numeric."""
        amount = value
        if isinstance(value, dict):
            code = value.get(CurrencyValueKey.CURRENCY_CODE)
            if isinstance(code, str) and code.strip():
                self.currency_codes.add(code.strip())
            amount = value.get(CurrencyValueKey.AMOUNT)
        if isinstance(amount, bool) or amount is None:
            return
        try:
            self.total += Decimal(str(amount))
        except (ArithmeticError, ValueError) as exc:
            logger.warning(
                "skipping unsummable entity field value: %s",
                exc,
                extra={
                    "field": self.field,
                    "entity_id": entity_id,
                    "value": str(amount)[:UNSUMMABLE_VALUE_LOG_LIMIT],
                },
            )

    def to_aggregate(self) -> FieldNumericAggregate:
        return FieldNumericAggregate(
            total=self.total, currency_codes=frozenset(self.currency_codes)
        )


@dataclass(frozen=True)
class EnrollmentAggregates:
    """Per-state row counts, plus one total for each summed field."""

    state_counts: dict[str, int]
    field_totals: dict[str, FieldNumericAggregate]


@dataclass(frozen=True)
class EnrollmentSummaryPageData:
    """One page of enrollment rows, and whether anything follows it."""

    rows: list[WorkflowEnrollmentSummaryRow]
    has_more: bool


@dataclass(frozen=True)
class EnrollmentSummaryContext:
    """Everything a page of rows needs resolved once, rather than per row."""

    policies: dict[str, EntityReadPolicy]
    inherited: dict[str, dict[str, object]]
    preview_urls: dict[str, str]


class RequiredField(PydanticBaseModel):
    """Transition required field."""

    field: str
    required: bool = True
    type: str | None = None

    @model_validator(mode="after")
    def validate_model(self) -> RequiredField:
        """Normalize field values."""
        self.field = _non_empty(self.field, "field")
        if self.type is not None:
            self.type = _non_empty(self.type, "type").lower()
        return self


def _document_file_ids(field_name: str, value: Any) -> list[str] | None:
    """Normalise a document field's value into a list of file ids.

    A document field holds several attached files, so its value is a list even
    when there is one of them. Shape only: whether those ids exist, and belong to
    the reading organization, is checked at publish time, where the organization
    and the filehandler are both in scope. See
    `WorkflowServiceManager._validate_document_fields`.
    """
    if value is None or value == "":
        return None
    if not isinstance(value, list):
        raise ValueError(
            f"document field '{field_name}' must hold a list of file ids, not "
            f"{type(value).__name__}"
        )
    file_ids: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"document field '{field_name}' has a file id that is not a string")
        file_ids.append(item.strip())
    duplicates = sorted({item for item in file_ids if file_ids.count(item) > 1})
    if duplicates:
        raise ValueError(
            f"document field '{field_name}' lists the same file twice: " + ", ".join(duplicates)
        )
    return file_ids


# The admin-supplied wording a picklist_multi field carries: what its extension
# fields collect, plus a heading and a description for each wizard step. One
# tuple so validation cannot cover some and miss others.
PICKLIST_MULTI_COPY_FIELDS = (
    "extension_label",
    "step1_label",
    "step1_description",
    "step2_label",
    "step2_description",
    "step3_label",
    "step3_description",
)

# Long enough for a sentence of description, short enough to stay readable in
# the one line each of these renders on.
PICKLIST_MULTI_COPY_MAX_LENGTH = 200


class EntityField(PydanticBaseModel):
    """Entity schema field."""

    field: str
    type: str
    required: bool = False
    nullable: bool = True
    default: Any | None = None
    enum_values: list[str] = Field(default_factory=list)
    picklist_id: str | None = None
    # The second picklist of a "Picklist Multi (Dropdown Add)" field, whose
    # options are toggled per option of the first, plus the Field Library fields
    # each of those options reveals ("Extend Field"). The engine stores such a
    # field as `multi_select`, so these are what tell a renderer it is the
    # two-picklist kind rather than a flat multi-select.
    picklist_id_2: str | None = None
    enum_values_2: list[str] = Field(default_factory=list)
    enum_labels_2: list[str] = Field(default_factory=list)
    extensions: dict[str, dict[str, Any]] | None = None
    # Names what the extension fields collect, so a form can say "Certificate
    # required" where the generic wording would say "Details required". Absent
    # means the generic wording, which is what every field configured before
    # this had.
    extension_label: str | None = None
    # Headings for the first two steps of the picklist_multi wizard, so a form
    # can say "Choose jurisdictions" rather than the generic wording. Unlike
    # `extension_label` these apply whether or not Extend Field is configured.
    step1_label: str | None = None
    step1_description: str | None = None
    step2_label: str | None = None
    step2_description: str | None = None
    step3_label: str | None = None
    step3_description: str | None = None
    description: str | None = None
    ownership: str | None = None
    source: dict[str, str] | None = None
    editable: bool | None = None
    col_span: str | None = None
    auto_number_config: dict[str, Any] | None = None
    currency_config: dict[str, Any] | None = None
    # Which file type a document field uploads against, and whether it accepts
    # more than one file. The file type is what decides the storage provider and
    # the accepted extensions, so a document field is not usable without it.
    document_config: dict[str, Any] | None = None
    placeholder: str | None = None
    table_config: dict[str, Any] | None = None
    calc: dict[str, Any] | None = None
    # Generic per-type appearance override (e.g. a textarea's background/text
    # color) and a value-level read-only lock independent of RBAC field
    # permissions. Both opaque to the engine, consumed only by the renderer.
    style_config: dict[str, Any] | None = None
    read_only: bool | None = None
    # Workflow states whose pinned Method contributed this field, so a display
    # surface can show a state's own fields rather than every field the
    # workflow collects anywhere. Empty for a field the workflow declares
    # itself, which belongs to every state. Plural because one Method can be
    # pinned to several states. Deliberately excluded from the pinned-field
    # conflict comparison — see `_merge_pinned_field`.
    source_states: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_model(self) -> EntityField:
        """Normalize field values."""
        self.field = _non_empty(self.field, "field")
        self.type = _non_empty(self.type, "type").lower()
        if self.type not in {field_type.value for field_type in EntityFieldType}:
            raise ValueError(f"unsupported entity field type '{self.type}'")
        if self.type in {EntityFieldType.NUMBER, EntityFieldType.INTEGER_ALIAS}:
            self.type = EntityFieldType.INTEGER
        self.enum_values = [_non_empty(item, "enum_values") for item in self.enum_values]
        if self.type == EntityFieldType.ENUM and not self.enum_values:
            raise ValueError(f"entity field '{self.field}' of type 'enum' requires enum_values")
        if self.type == EntityFieldType.MULTI_SELECT and not self.enum_values:
            raise ValueError(
                f"entity field '{self.field}' of type 'multi_select' requires enum_values"
            )
        if (
            self.type not in {EntityFieldType.ENUM, EntityFieldType.MULTI_SELECT}
            and self.enum_values
            and not self.picklist_id
        ):
            raise ValueError(
                f"entity field '{self.field}' may only declare enum_values when type is 'enum' or 'multi_select'"
            )
        self.enum_values_2 = [_non_empty(item, "enum_values_2") for item in self.enum_values_2]
        self.picklist_id_2 = _optional_non_empty(self.picklist_id_2)
        for copy_name in PICKLIST_MULTI_COPY_FIELDS:
            setattr(self, copy_name, _optional_non_empty(getattr(self, copy_name)))
        if (
            self.picklist_id_2
            or self.enum_values_2
            or self.extensions
            or any(getattr(self, name) for name in PICKLIST_MULTI_COPY_FIELDS)
        ) and (self.type != EntityFieldType.MULTI_SELECT):
            raise ValueError(
                f"entity field '{self.field}' may only declare a second picklist, "
                "extensions or wizard copy when type is 'multi_select'"
            )
        for copy_name in PICKLIST_MULTI_COPY_FIELDS:
            copy_value = getattr(self, copy_name)
            if copy_value and len(copy_value) > PICKLIST_MULTI_COPY_MAX_LENGTH:
                raise ValueError(
                    f"entity field '{self.field}' {copy_name} max "
                    f"{PICKLIST_MULTI_COPY_MAX_LENGTH} chars"
                )
        if self.extensions is not None:
            # Keyed by an option of the second picklist; each entry lists the
            # snapshotted Field Library fields that option reveals. Options that
            # reveal nothing are dropped rather than stored empty.
            cleaned: dict[str, dict[str, Any]] = {}
            for option, entry in self.extensions.items():
                fields = entry.get("fields") if isinstance(entry, dict) else None
                if not isinstance(fields, list):
                    raise ValueError(
                        f"entity field '{self.field}' extension '{option}' must declare a "
                        "list of fields"
                    )
                if any(not isinstance(item, dict) for item in fields):
                    raise ValueError(
                        f"entity field '{self.field}' extension '{option}' has a field that "
                        "is not an object"
                    )
                if fields:
                    cleaned[option] = {**entry, "fields": fields}
            self.extensions = cleaned or None
        if self.type == EntityFieldType.TIMER_DURATION:
            # Never typed in: the frontend timer control records the value, the
            # same reason calc and auto_number are locked.
            self.editable = False
            if self.default is not None:
                raise ValueError(
                    f"timer field '{self.field}' cannot declare a default; its value "
                    "comes from stopping the timer"
                )
        if self.type == EntityFieldType.DOCUMENT:
            self.default = _document_file_ids(self.field, self.default)
        self.picklist_id = _optional_non_empty(self.picklist_id)
        self.description = _optional_non_empty(self.description)
        if self.ownership is not None:
            self.ownership = _non_empty(self.ownership, "ownership").lower()
            if self.ownership not in FieldOwnership:
                raise ValueError(
                    f"unsupported ownership '{self.ownership}' for field '{self.field}'"
                )
            if self.ownership == FieldOwnership.INHERITED:
                if not isinstance(self.source, dict):
                    raise ValueError(f"inherited field '{self.field}' must define source mapping")
                source_entity_type = _non_empty(
                    self.source.get("context_entity_type", ""), "source.context_entity_type"
                )
                source_field = _non_empty(
                    self.source.get("context_field", ""), "source.context_field"
                )
                self.source = {
                    "context_entity_type": source_entity_type,
                    "context_field": source_field,
                }
                if self.editable not in {None, False}:
                    raise ValueError(f"inherited field '{self.field}' must be editable=false")
                self.editable = False
            else:
                if self.source is not None:
                    raise ValueError(f"owned field '{self.field}' must not define source mapping")
                if self.editable is None:
                    self.editable = True
        elif self.source is not None:
            raise ValueError(
                f"field '{self.field}' defines source mapping without ownership='inherited'"
            )
        if self.type == EntityFieldType.AUTO_NUMBER:
            cfg = dict(self.auto_number_config or {})
            allowed = {"affix_mode", "affix"}
            mode = str(cfg.get("affix_mode", "none")).strip().lower()
            if mode not in {"none", "prefix", "suffix"}:
                raise ValueError(
                    f"entity field '{self.field}' auto_number_config affix_mode must be none/prefix/suffix"
                )
            affix = str(cfg.get("affix", "")).strip()
            if len(affix) > AUTO_NUMBER_MAX_AFFIX_LENGTH:
                raise ValueError(
                    f"entity field '{self.field}' auto_number_config affix max "
                    f"{AUTO_NUMBER_MAX_AFFIX_LENGTH} chars"
                )
            self.auto_number_config = {"affix_mode": mode, "affix": affix}
            self.editable = False
        if self.table_config is not None and self.type != EntityFieldType.JSON:
            raise ValueError(f"table_config is only supported for json field '{self.field}'")
        if self.type == EntityFieldType.CURRENCY:
            cfg = dict(self.currency_config or {})
            currency_code = str(cfg.get("currency_code", "USD")).strip().upper()
            self.currency_config = {"currency_code": currency_code}
        elif self.currency_config is not None:
            raise ValueError(f"currency_config is only supported for currency field '{self.field}'")
        # TODO(calc, P1): this only checks a top-level calc has a numeric type.
        # Full calc validation — unknown-reference checks, field/column/cell cycle
        # detection, and table_config column/cell calc checks — lives in
        # EntitySchemaService._validate_calc_fields and is NOT invoked by the
        # Forms schema create/update managers (EntityTypeSchemaCreate/UpdateRequest
        # just construct EntityField). So schemas saved via the Forms API can
        # persist unknown references and cyclic column/cell formulas (later yielding
        # null / order-dependent stored values). Run full-schema calc validation
        # before persisting a form schema.
        # [issue](https://dev.flowtuple.com/pipeline/00240677-cdac-4d68-8e57-b2ce1cddc9b9/entity/546bc86c-6191-41f6-83f6-e3c85d566b85)
        if self.calc is not None:
            numeric = {
                EntityFieldType.INTEGER,
                EntityFieldType.FLOAT,
                EntityFieldType.NUMBER,
            }
            if self.type not in numeric:
                raise ValueError(
                    f"calc is only supported on numeric fields, not '{self.type}' (field '{self.field}')"
                )
            # A computed field is never user-required and always nullable.
            self.required = False
            self.nullable = True
        return self


class EntitySchema(PydanticBaseModel):
    """Embedded entity schema."""

    entity_type: str
    fields: list[EntityField] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_model(self) -> EntitySchema:
        """Validate uniqueness."""
        self.entity_type = _non_empty(self.entity_type, "entity_type")
        names = [item.field for item in self.fields]
        if len(set(names)) != len(names):
            raise ValueError("entity schema contains duplicate field names")
        return self


class Guard(PydanticBaseModel):
    """Transition guard."""

    type: str
    field: str | None = None
    value: object | None = None
    message: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model(self) -> Guard:
        """Normalize guard values and set a default message if none provided."""
        self.type = _non_empty(self.type, "type").lower()
        self.type = GUARD_TYPE_LEGACY_ALIASES.get(self.type, self.type)
        if self.type not in GuardType:
            raise ValueError(f"unsupported guard type '{self.type}'")
        if self.field is not None:
            self.field = _non_empty(self.field, "field")
        self.message = _optional_non_empty(self.message)
        if not self.message or self.message.strip().lower() == "guard":
            self.message = self._default_message()
        return self

    def _default_message(self) -> str:
        """Generate a plain-language failure message from the guard definition."""
        label = self.field.replace("_", " ").title() if self.field else "A required field"
        if self.type == GuardType.FIELD_PRESENT:
            return f"{label} is required"
        if self.type == GuardType.FIELD_EXACT_MATCH:
            return f"{label} must be '{self.value}'"
        if self.type == GuardType.NUMERICAL_VALUE_GTE:
            return f"{label} must be at least {self.value}"
        if self.type == GuardType.NUMERICAL_VALUE_LTE:
            return f"{label} must be at most {self.value}"
        if self.type == GuardType.NUMERICAL_VALUE_IN_SET:
            candidates = self.value if isinstance(self.value, (list, tuple)) else [self.value]
            return f"{label} must be one of: {', '.join(str(c) for c in candidates)}"
        if self.type == GuardType.COMPARE_DATES:
            other = self.config.get("other_field", "another date")
            other_label = other.replace("_", " ").title() if isinstance(other, str) else "another date"
            op = str(self.config.get("operator", "lte")).strip().lower()
            op_labels = {
                "lt": "before", "lte": "on or before",
                "gt": "after", "gte": "on or after",
                "eq": "the same as", "ne": "different from",
            }
            return f"{label} must be {op_labels.get(op, op)} {other_label}"
        return f"{label} did not meet the required condition"


class TransitionTask(PydanticBaseModel):
    """Transition task definition."""

    task: str
    label: str | None = None
    order: int = Field(..., ge=1)
    required: bool = True
    on_failure: str = "stop"
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model(self) -> TransitionTask:
        """Normalize task values."""
        self.task = _non_empty(self.task, "task")
        self.label = _optional_non_empty(self.label)
        self.on_failure = _non_empty(self.on_failure, "on_failure").lower()
        return self

    @property
    def task_key(self) -> str:
        """Compatibility alias for generic task identity."""
        return self.task


class PostTask(PydanticBaseModel):
    """Post-transition task."""

    task: str
    order: int = Field(..., ge=1)
    required: bool = True
    on_failure: str = "stop"

    @model_validator(mode="after")
    def validate_model(self) -> PostTask:
        """Normalize task values."""
        self.task = _non_empty(self.task, "task")
        if self.task not in TaskName:
            raise ValueError(f"unsupported post-transition task '{self.task}'")
        self.on_failure = _non_empty(self.on_failure, "on_failure").lower()
        return self


class StateAction(PydanticBaseModel):
    """Action attached to a workflow state, executed on state entry."""

    kind: str
    config: dict[str, Any] = Field(default_factory=dict)
    outcome_triggers: dict[str, str] = Field(default_factory=dict)
    failure_policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model(self) -> StateAction:
        self.kind = _non_empty(self.kind, "kind")
        return self


class MethodRef(PydanticBaseModel):
    """A method library method referenced by a workflow state.

    `version_id` None means "resolve to whatever is current at the moment this is
    published". From that point on the pin is a real version id and is never
    re-checked on its own: a method moving on to a newer version leaves an already
    published workflow resolving the version it captured.
    """

    method_id: str
    version_id: str | None = None

    @model_validator(mode="after")
    def validate_model(self) -> MethodRef:
        """Normalize reference values."""
        self.method_id = _non_empty(self.method_id, "method_id")
        self.version_id = _optional_non_empty(self.version_id)
        return self


class ResolvedMethodSchema(PydanticBaseModel):
    """Immutable presentation snapshot for one Method pinned to one state.

    ``entity_schema`` remains the workflow engine's flattened field contract.
    This snapshot preserves the Method boundary that form-driven clients need
    in order to render one form/step per pinned Method without trying to infer
    provenance from that flattened schema.
    """

    method_id: str
    method_name: str
    version_id: str
    version: int = Field(..., ge=1)
    state_name: str
    state_order: int | None = Field(default=None, ge=1)
    method_order: int = Field(..., ge=0)
    fields: list[EntityField] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_model(self) -> ResolvedMethodSchema:
        """Normalize the identifiers and labels captured at publish time."""
        self.method_id = _non_empty(self.method_id, "method_id")
        self.method_name = _non_empty(self.method_name, "method_name")
        self.version_id = _non_empty(self.version_id, "version_id")
        self.state_name = _non_empty(self.state_name, "state_name")
        return self


class State(PydanticBaseModel):
    """Workflow state."""

    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    order: int | None = Field(default=None, ge=1)
    on_state_actions: list[StateAction] = Field(default_factory=list)
    sla_seconds: int | None = Field(default=None, ge=0)
    # Method library methods whose fields this state captures. Purely additive:
    # an empty list is the default and behaves exactly as before.
    method_refs: list[MethodRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_action(cls, data: Any) -> Any:
        """Fold the legacy singular `on_state_action` into `on_state_actions`."""
        if isinstance(data, dict):
            legacy = data.get("on_state_action")
            if legacy is not None and not data.get("on_state_actions"):
                data = {**data, "on_state_actions": [legacy]}
        return data

    @model_validator(mode="after")
    def validate_model(self) -> State:
        """Normalize state values."""
        self.name = _non_empty(self.name, "name")
        self.description = _optional_non_empty(self.description)
        self.tags = [_non_empty(item, "tags").lower() for item in self.tags]
        unsupported = [item for item in self.tags if item not in StateTag.list()]
        if unsupported:
            raise ValueError(f"unsupported state tags: {', '.join(sorted(set(unsupported)))}")
        # One pin per method per state. Listing a method twice, especially at two
        # versions, would merge fields from both and leave the state describing a
        # shape no single version of that method ever had.
        method_ids = [ref.method_id for ref in self.method_refs]
        repeated = sorted({item for item in method_ids if method_ids.count(item) > 1})
        if repeated:
            raise ValueError(
                f"state '{self.name}' references these methods more than once: "
                + ", ".join(repeated)
            )
        return self

    @property
    def terminal(self) -> bool:
        """Compatibility helper for legacy runtime code."""
        return StateTag.TERMINAL in self.tags

    @property
    def deviation(self) -> bool:
        """Whether this state carries the `deviation` tag."""
        return StateTag.DEVIATION in self.tags


class Transition(PydanticBaseModel):
    """Workflow transition."""

    key: str
    trigger: str
    label: str
    from_state: str = Field(alias="from")
    to_state: str
    required_fields: list[RequiredField] = Field(default_factory=list)
    guards: list[Guard] = Field(default_factory=list)
    pre_transition_tasks: list[TransitionTask] = Field(default_factory=list)
    post_transition_tasks: list[TransitionTask] = Field(default_factory=list)
    auto_transition: dict[str, Any] | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_model(self) -> Transition:
        """Normalize transition values."""
        self.trigger = _non_empty(self.trigger, "trigger")
        self.to_state = _non_empty(self.to_state, "to_state")
        self.from_state = _non_empty(self.from_state, "from_state")
        self.label = _non_empty(self.label, "label")
        self.key = _non_empty(self.key, "key")
        self.description = _optional_non_empty(self.description)
        self.pre_transition_tasks = sorted(self.pre_transition_tasks, key=lambda item: item.order)
        self.post_transition_tasks = sorted(self.post_transition_tasks, key=lambda item: item.order)
        return self

    @property
    def source_states(self) -> list[str]:
        """Source state as a list for iteration compatibility."""
        return [self.from_state]


class StateMachineDefinition(PydanticBaseModel):
    """Workflow definition."""

    machine_key: str
    name: str
    description: str | None = None
    entity_type: str
    # Optional grouping onto a WorkflowService, mirroring how a Method Block
    # carries category_id: a single value on the definition, not something
    # re-captured per published version. Never required to publish.
    service_id: str | None = None
    entity_schema: EntitySchema
    states: list[State] = Field(default_factory=list)
    # Publish-time snapshots of each state's pinned Methods. Additive and empty
    # on drafts/legacy definitions; entity_schema remains the runtime contract.
    method_schemas: list[ResolvedMethodSchema] = Field(default_factory=list)
    initial_state: str | None = None
    transitions: list[Transition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_model(self) -> StateMachineDefinition:
        """Validate internal coherence."""
        self.machine_key = _non_empty(self.machine_key, "machine_key")
        self.name = _non_empty(self.name, "name")
        self.description = _optional_non_empty(self.description)
        self.entity_type = _non_empty(self.entity_type, "entity_type")
        self.service_id = _optional_non_empty(self.service_id)
        if self.entity_schema.entity_type != self.entity_type:
            raise ValueError("state machine entity_type must match entity_schema.entity_type")
        states = {item.name: item for item in self.states}
        if not states:
            raise ValueError("state machine definition requires at least one state")
        if len(states) != len(self.states):
            raise ValueError("state machine definition contains duplicate state names")
        initial_states = [item.name for item in self.states if StateTag.INITIAL in item.tags]
        if self.initial_state is not None:
            self.initial_state = self.initial_state.strip() or None
        if self.initial_state is not None:
            if self.initial_state not in states:
                raise ValueError("initial_state must be declared in states")
        elif len(initial_states) == 1:
            self.initial_state = initial_states[0]
        fields = {item.field: item for item in self.entity_schema.fields}
        transition_keys = [item.key for item in self.transitions if item.key]
        if len(set(transition_keys)) != len(transition_keys):
            raise ValueError("state machine definition contains duplicate transition keys")
        transition_identities: set[tuple[str, str]] = set()
        for transition in self.transitions:
            for source in transition.source_states:
                if source not in states:
                    raise ValueError(f"transition source state '{source}' is not declared")
            if transition.to_state not in states:
                raise ValueError(f"transition target state '{transition.to_state}' is not declared")
            identity = (transition.from_state, transition.trigger)
            if identity in transition_identities:
                raise ValueError(
                    f"transition '{transition.trigger}' from state '{transition.from_state}' is duplicated"
                )
            transition_identities.add(identity)
            # A transition may reference a field contributed by a Method
            # attached to the state it leaves, not just one declared on the
            # entity schema — both as a `required_field` and as a guard field.
            # Which fields a Method contributes is only knowable by resolving
            # its pinned version against the database, which this contract has
            # no access to. So when the source state pins any method, an
            # unrecognised field is left for the service layer to settle (see
            # `_validate_transition_field_references` in workflow/manager.py).
            # Everything else below still applies to fields the schema declares.
            source_pins_methods = any(
                states[source].method_refs
                for source in transition.source_states
                if source in states
            )
            for required_field in transition.required_fields:
                schema_field = fields.get(required_field.field)
                if schema_field is None:
                    if source_pins_methods:
                        # Type is left as sent; the merged schema is what the
                        # service layer type-checks against.
                        continue
                    raise ValueError(
                        f"transition '{transition.trigger}' references undefined entity field '{required_field.field}'"
                    )
                if required_field.type is None:
                    required_field.type = schema_field.type
                if required_field.type is not None and schema_field.type != required_field.type:
                    raise ValueError(
                        f"transition '{transition.trigger}' field '{required_field.field}' type does not match entity schema"
                    )
            for guard in transition.guards:
                if guard.field is not None and guard.field not in fields:
                    if source_pins_methods:
                        continue
                    raise ValueError(
                        f"transition '{transition.trigger}' guard references undefined entity field '{guard.field}'"
                    )
                if guard.field is None:
                    continue
                schema_field = fields[guard.field]
                if guard.type in {
                    GuardType.NUMERICAL_VALUE_GTE,
                    GuardType.NUMERICAL_VALUE_LTE,
                } and schema_field.type not in {
                    EntityFieldType.INTEGER,
                    EntityFieldType.FLOAT,
                }:
                    raise ValueError(
                        f"transition '{transition.trigger}' guard '{guard.type}' requires numeric field '{guard.field}'"
                    )
                if guard.type == GuardType.NUMERICAL_VALUE_IN_SET:
                    if schema_field.type not in {EntityFieldType.INTEGER, EntityFieldType.FLOAT}:
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' requires numeric field '{guard.field}'"
                        )
                    if not isinstance(guard.value, (list, tuple, set)) or not guard.value:
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' requires a non-empty list value"
                        )
                    invalid_candidates = [
                        candidate
                        for candidate in guard.value
                        if not _matches_entity_field_type(
                            candidate, schema_field.type, schema_field.enum_values
                        )
                    ]
                    if invalid_candidates:
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' has values incompatible with field '{guard.field}'"
                        )
                elif guard.type in {
                    GuardType.FIELD_EXACT_MATCH,
                    GuardType.NUMERICAL_VALUE_GTE,
                    GuardType.NUMERICAL_VALUE_LTE,
                }:
                    if guard.value is None:
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' requires a non-null value"
                        )
                    if not _matches_entity_field_type(
                        guard.value, schema_field.type, schema_field.enum_values
                    ):
                        raise ValueError(
                            f"transition '{transition.trigger}' guard value type does not match field '{guard.field}'"
                        )
                elif guard.type == GuardType.COMPARE_DATES:
                    if schema_field.type != EntityFieldType.DATETIME:
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' requires datetime field '{guard.field}'"
                        )
                    other_field = guard.config.get("other_field")
                    operator = str(guard.config.get("operator", "lte")).strip().lower()
                    supported_operators = {"lt", "lte", "gt", "gte", "eq", "ne"}
                    if not isinstance(other_field, str) or not other_field.strip():
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' requires config.other_field"
                        )
                    if other_field not in fields:
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' references undefined datetime field '{other_field}'"
                        )
                    if fields[other_field].type != EntityFieldType.DATETIME:
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' requires datetime config.other_field"
                        )
                    if operator not in supported_operators:
                        raise ValueError(
                            f"transition '{transition.trigger}' guard '{guard.type}' has unsupported operator '{operator}'"
                        )
        return self


SERVICE_NAME_MAX_LENGTH = 256


class WorkflowService(PydanticBaseModel):
    """A grouping for workflows, unique by name within an organization.

    Mirrors MethodCategory (method_library/models/interface.py) exactly.
    Uniqueness is case insensitive, so "Cell Supply" and "cell supply" are the
    same service to one organization and unrelated across two.
    """

    service_id: str
    organization_id: str
    name: str
    created_at: datetime | None = None


class WorkflowServiceWorkflow(PydanticBaseModel):
    """One workflow filed under a service, summarised.

    Deliberately not a StateMachineRecord: that carries the whole definition,
    and this list exists to answer "which workflows are in this service", not
    to hand back every definition on the page.
    """

    id: str
    machine_key: str
    machine_name: str
    name: str
    description: str | None = None
    entity_type: str
    version: int
    is_active: bool
    created_at: datetime | None = None


class WorkflowServiceWithWorkflows(WorkflowService):
    """A service together with the workflows currently filed under it.

    `workflows` holds one entry per machine name — its highest non-archived
    version — so a workflow published five times appears once rather than five
    times. `workflow_count` counts those entries, not the underlying rows.
    """

    workflow_count: int = 0
    workflows: list[WorkflowServiceWorkflow] = Field(default_factory=list)


class StateMachineRecord(PydanticBaseModel):
    """Persisted workflow record."""

    id: str | None = None
    machine_key: str
    machine_name: str
    name: str
    description: str | None = None
    entity_type: str
    service_id: str | None = None
    version: int
    is_active: bool
    definition: StateMachineDefinition
    canvas_metadata: dict[str, Any] | None = None
    organization_id: str
    created_by: str | None = None
    created_by_name: str | None = None
    created_at: datetime | None = None


class WorkflowDraftRecord(PydanticBaseModel):
    """Persisted workflow draft record with permissive definition shape."""

    id: str | None = None
    machine_key: str
    machine_name: str
    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    service_id: str | None = None
    version: int
    is_active: bool
    definition: dict[str, Any] = Field(default_factory=dict)
    canvas_metadata: dict[str, Any] | None = None
    organization_id: str
    created_by: str | None = None
    created_by_name: str | None = None
    created_at: datetime | None = None


class WorkflowBoardDisplayFieldsRecord(PydanticBaseModel):
    """Up to 3 extra entity fields shown on one workflow's Kanban cards."""

    machine_name: str
    fields: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None
    updated_by: str | None = None


class EntitySchemaPicklist(PydanticBaseModel):
    """Persisted reusable entity-schema template for the builder."""

    schema_key: str
    name: str
    description: str | None = None
    entity_type: str
    fields: list[EntityField] = Field(default_factory=list)
    is_active: bool = True
    content_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_model(self) -> EntitySchemaPicklist:
        """Normalize schema picklist fields."""
        self.schema_key = _non_empty(self.schema_key, "schema_key")
        self.name = _non_empty(self.name, "name")
        self.description = _optional_non_empty(self.description)
        self.entity_type = _non_empty(self.entity_type, "entity_type")
        return self


def transition_identity(transition: Transition) -> str:
    """Build the canonical identity key for one transition."""
    return (
        f"{transition.trigger}|{','.join(sorted(transition.source_states))}|{transition.to_state}"
    )


class ValidationIssue(PydanticBaseModel):
    """Definition validation issue."""

    code: str
    message: str
    severity: str = "error"
    bucket: str | None = None
    action: str | None = None


class IssueBuckets(PydanticBaseModel):
    """Grouped issue buckets for builder-oriented reporting."""

    form_errors: list[ValidationIssue] = Field(default_factory=list)
    graph_errors: list[ValidationIssue] = Field(default_factory=list)
    simulation_errors: list[ValidationIssue] = Field(default_factory=list)
    workflow_observations: list[ValidationIssue] = Field(default_factory=list)


class IssueBucket(ExtendedStrEnum):
    """Builder-facing report buckets a validation issue can be filed under.

    Values must stay identical to `IssueBuckets`' field names — both `bucket_issues` and
    `db_models._report` resolve the target list with `getattr(buckets, bucket_name)`.
    """

    FORM_ERRORS = "form_errors"
    GRAPH_ERRORS = "graph_errors"
    SIMULATION_ERRORS = "simulation_errors"
    WORKFLOW_OBSERVATIONS = "workflow_observations"


DEFAULT_ISSUE_BUCKET: str = IssueBucket.FORM_ERRORS

GRAPH_ISSUE_CODES: frozenset[str] = frozenset(
    {
        ValidationIssueCode.UNREACHABLE_STATE,
        ValidationIssueCode.DEAD_END_STATE,
        ValidationIssueCode.NO_TERMINAL_PATH,
        ValidationIssueCode.TERMINAL_STATE_HAS_OUTGOING_TRANSITION,
        ValidationIssueCode.UNREACHABLE_GUARD_FIELD,
    }
)

DEFAULT_ISSUE_ACTION: str = "Fix the reported issue and validate again."

ISSUE_ACTIONS: dict[str, str] = {
    ValidationIssueCode.INVALID_DEFINITION: (
        "Fix the malformed definition fields reported in the message before validating again."
    ),
    ValidationIssueCode.MISSING_INITIAL_STATE: "Tag at least one state as 'initial'.",
    ValidationIssueCode.MISSING_TERMINAL_STATE: "Tag at least one state as 'terminal'.",
    ValidationIssueCode.MISSING_TRANSITIONS: (
        "Add at least one transition between two declared states."
    ),
    ValidationIssueCode.DUPLICATE_PRE_TRANSITION_TASK_ORDER: (
        "Make each pre-transition task order unique for this transition."
    ),
    ValidationIssueCode.DUPLICATE_POST_TRANSITION_TASK_ORDER: (
        "Make each post-transition task order unique for this transition."
    ),
    ValidationIssueCode.UNREACHABLE_STATE: (
        "Add an incoming transition to the state or remove the state if it is not needed."
    ),
    ValidationIssueCode.DEAD_END_STATE: (
        "Mark the state as terminal or add at least one outgoing transition."
    ),
    ValidationIssueCode.NO_TERMINAL_PATH: (
        "Add transitions so this initial state can eventually reach a terminal state."
    ),
    ValidationIssueCode.UNSATISFIED_TRANSITION: (
        "Fix the listed transition so it can be executed during dry run."
    ),
    ValidationIssueCode.LOOP_WITHOUT_TERMINAL: (
        "Add an exit path from the loop to a terminal state, or remove the loop."
    ),
    ValidationIssueCode.INITIAL_STATE_MISSING_TAG: (
        "Add the 'initial' tag to the state set as initial_state."
    ),
    ValidationIssueCode.INVALID_ENUM_DEFAULT: (
        "Set the default value to one of the declared enum_values, or remove the default."
    ),
    ValidationIssueCode.ORPHANED_ENTITY_SCHEMA_FIELD: (
        "Refresh the workflow entity type selection so its schema fields match the active forms."
    ),
    ValidationIssueCode.ENTITY_SCHEMA_FIELD_DRIFTED: (
        "Review the workflow's entity type field selection against the active form and re-save "
        "if any changes should be picked up here."
    ),
    ValidationIssueCode.UNKNOWN_ACTION_KIND: (
        "Pick an action the platform can run, or remove it from the state."
    ),
    ValidationIssueCode.INVALID_ACTION_CONFIG: (
        "Complete the action's settings as described in the message before publishing."
    ),
    ValidationIssueCode.TERMINAL_STATE_HAS_OUTGOING_TRANSITION: (
        "Remove the outgoing transition from the terminal state, or remove the 'terminal' tag "
        "if the state is not truly terminal."
    ),
    ValidationIssueCode.UNREACHABLE_GUARD_FIELD: (
        "Mark the field as required=True in the entity schema, or ensure every path from an "
        "initial state to this transition collects the field as a required_field on at least "
        "one step along the way."
    ),
}


class DefinitionReport(PydanticBaseModel):
    """Unified definition report."""

    report_id: str
    report_type: str
    machine_name: str
    version: int | None = None
    valid: bool | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    buckets: IssueBuckets = Field(default_factory=IssueBuckets)
    next_actions: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class EntityState(PydanticBaseModel):
    """Runtime entity state."""

    entity_id: str
    entity_type: str
    organization_id: str
    machine_name: str
    machine_version: int
    workflow_id: str | None = None
    current_state: str
    # Human-readable description of the current state (when the workflow
    # definition declares one); lets list views show prose instead of a code.
    current_state_description: str | None = None
    state_version: int = 0
    owner_id: str | None = None
    assignee_id: str | None = None
    due_date: date | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    state_entered_at: datetime | None = None
    last_transition_at: datetime | None = None
    sla_due_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None
    preview_thumbnail_url: str | None = None


class TransitionAttemptRecord(PydanticBaseModel):
    """Internal data transfer object for one row in `audit.transition_attempts`."""

    transition_attempt_id: str
    organization_id: str
    entity_id: str
    workflow_id: str
    from_state: str | None = None
    to_state: str | None = None
    trigger: str | None = None
    actor_id: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    status: str
    failure_code: str | None = None
    idempotency_key: str | None = None
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    guard_evaluations: dict[str, Any] | None = None
    occurred_at: datetime | None = None


class ActivityRecord(PydanticBaseModel):
    """Unified activity log record."""

    activity_id: str
    activity_type: str
    entity_id: str
    machine_name: str
    machine_version: int
    trigger: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    actor_id: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    status: str | None = None
    idempotency_key: str | None = None
    blocked_reasons: list[str] = Field(default_factory=list)
    executed_tasks: list[str] = Field(default_factory=list)
    committed_response: dict[str, Any] | None = None
    state_duration_seconds: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AvailableTransition(PydanticBaseModel):
    """Available transition summary."""

    trigger: str
    label: str | None = None
    to_state: str
    allowed: bool = True
    availability_known: bool = True
    guards: list[dict[str, Any]] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)


class PreflightFieldRequirement(PydanticBaseModel):
    """Required field state during preflight."""

    field: str
    type: str
    required: bool = True
    provided: bool = False


class GuardEvaluation(PydanticBaseModel):
    """Guard evaluation result."""

    type: str
    field: str | None = None
    passed: bool
    message: str | None = None


class DryRunStep(PydanticBaseModel):
    """One simulated transition step."""

    from_state: str
    trigger: str
    to_state: str
    actor_role: str | None = None
    synthesized_inputs: dict[str, Any] = Field(default_factory=dict)


class DryRunPath(PydanticBaseModel):
    """One simulated workflow path."""

    path_id: str
    start_state: str
    end_state: str
    terminal_reached: bool = False
    blocked: bool = False
    loop_detected: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    steps: list[DryRunStep] = Field(default_factory=list)


class DryRunTransitionCheck(PydanticBaseModel):
    """Transition-level dry-run result."""

    transition_key: str
    trigger: str
    from_state: str
    to_state: str
    satisfiable: bool = False
    actor_role: str | None = None
    synthesized_inputs: dict[str, Any] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)


class WorkflowDryRunSummary(PydanticBaseModel):
    """Whole-definition dry-run simulation summary."""

    initial_states_checked: list[str] = Field(default_factory=list)
    terminal_states_reached: list[str] = Field(default_factory=list)
    successful_paths_count: int = 0
    blocked_paths_count: int = 0
    loop_paths_count: int = 0
    explored_paths: list[DryRunPath] = Field(default_factory=list)
    transition_checks: list[DryRunTransitionCheck] = Field(default_factory=list)


class TransitionRoleChange(PydanticBaseModel):
    """Role diff."""

    trigger: str
    from_states: list[str] = Field(default_factory=list)
    to_state: str
    from_roles: list[str] = Field(default_factory=list)
    to_roles: list[str] = Field(default_factory=list)


class TransitionRequiredFieldChange(PydanticBaseModel):
    """Required-field diff."""

    trigger: str
    from_states: list[str] = Field(default_factory=list)
    to_state: str
    added_fields: list[str] = Field(default_factory=list)
    removed_fields: list[str] = Field(default_factory=list)


class TransitionGuardChange(PydanticBaseModel):
    """Guard diff."""

    trigger: str
    from_states: list[str] = Field(default_factory=list)
    to_state: str
    from_guards: list[Guard] = Field(default_factory=list)
    to_guards: list[Guard] = Field(default_factory=list)


class VersionCompareSummary(PydanticBaseModel):
    """Version compare summary."""

    changed: bool
    added_states_count: int = 0
    removed_states_count: int = 0
    added_transitions_count: int = 0
    removed_transitions_count: int = 0
    changed_roles_count: int = 0
    changed_required_fields_count: int = 0
    changed_guards_count: int = 0


@dataclass
class MemoryStateMachine:
    """In-memory workflow record."""

    organization_id: str
    machine_key: str
    machine_name: str
    name: str
    description: str | None
    entity_type: str
    version: int
    is_active: bool
    definition: StateMachineDefinition
    canvas_metadata: dict | None = None
    created_by: str | None = None
    created_at: datetime | None = None


@dataclass
class MemoryDefinitionReport:
    """In-memory definition report."""

    report_id: str
    organization_id: str
    report_type: str
    machine_name: str
    version: int | None = None
    valid: bool | None = None
    issues: list[ValidationIssue] = dataclass_field(default_factory=list)
    created_at: datetime | None = None


@dataclass
class MemoryEntityState:
    """In-memory entity state."""

    entity_id: str
    entity_type: str
    organization_id: str
    machine_name: str
    machine_version: int
    current_state: str
    state_version: int = 0
    data: dict[str, Any] = dataclass_field(default_factory=dict)
    state_entered_at: datetime | None = None
    last_transition_at: datetime | None = None
    sla_due_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class MemoryActivity:
    """In-memory activity record."""

    activity_id: str
    organization_id: str
    activity_type: str
    entity_id: str
    machine_name: str
    machine_version: int
    trigger: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    actor_id: str | None = None
    actor_role: str | None = None
    status: str | None = None
    idempotency_key: str | None = None
    blocked_reasons: list[str] = dataclass_field(default_factory=list)
    executed_tasks: list[str] = dataclass_field(default_factory=list)
    committed_response: dict[str, Any] | None = None
    state_duration_seconds: int | None = None
    payload: dict[str, Any] = dataclass_field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class MemoryEntitySchemaPicklist:
    """In-memory reusable entity schema template."""

    organization_id: str
    schema_key: str
    name: str
    description: str | None
    entity_type: str
    fields: list[EntityField]
    is_active: bool = True
    content_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

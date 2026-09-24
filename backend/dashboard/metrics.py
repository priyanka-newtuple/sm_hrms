"""Metric registry and query execution for the customizable dashboard.

A *metric* is a named, parameterized server-side query. Widgets bind to a
metric key + filters; the dashboard data endpoint resolves them into data.
All queries are scoped to the caller's organization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable

from sqlalchemy import ColumnElement, and_, func, nullslast, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    # Annotation only. `from __future__ import annotations` keeps it lazy, so it
    # never has to be imported at runtime.
    from sqlalchemy.orm import Query

from audit.db_models import AuditEventModel
from background_jobs.db_models import ActionRunModel
from common.logger import logger
from common.protocols import MASKED_FIELD_VALUE
from dashboard.global_filters import global_entity_ids
from entities.db_models import (
    EntityEventAuditModel,
    EntityRecordModel,
    EntityStateRuntimeModel,
    EntityTypeModel,
)
from exceptions import ValidationError
from forms.db_models import EntityTypeSchemaModel, active_schema_fields_by_type_id
from workflow.db_models import WorkflowStateMachineModel

# Output kinds tell the frontend how to render the payload.
#   series → list[{label, value}]   (bar / pie / funnel / line)
#   scalar → {value, prevValue?}    (stat tile)
#   rows   → {columns[], rows[]}    (table)


@dataclass(frozen=True)
class MetricParam:
    key: str
    label: str
    type: str  # "string" | "date" | "number"
    source: str | None = None  # "workflows" | "entity_types" | "states" | "event_types"


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    description: str
    output: str  # "series" | "scalar" | "rows"
    default_visuals: tuple[str, ...]
    params: tuple[MetricParam, ...] = field(default_factory=tuple)
    # Selectable columns for "rows" metrics: (key, label). Empty for non-rows.
    fields: tuple[tuple[str, str], ...] = field(default_factory=tuple)


# Column catalogs for row-output metrics. The widget stores a chosen subset in
# filters["fields"]; an empty/missing selection shows every column.
EVENTS_RECENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("event_type", "Event"),
    ("entity_id", "Entity"),
    ("actor", "Actor"),
    ("actor_type", "Actor Type"),
    ("correlation_id", "Correlation"),
    ("occurred_at", "When"),
)

INSTANCES_LIST_FIELDS: tuple[tuple[str, str], ...] = (
    ("entity_id", "Entity"),
    ("current_state", "State"),
    ("workflow_id", "Workflow"),
    ("state_version", "Version"),
    ("state_entered_at", "Entered"),
    ("last_transition_at", "Last Transition"),
    ("sla_due_at", "SLA Due"),
)

REACHED_STATE_LIST_FIELDS: tuple[tuple[str, str], ...] = (
    ("identifier", "Ticket"),
    ("moved_at", "Moved On"),
    ("current_state", "State Now"),
    ("entity_id", "Entity"),
)

ACTIVITY_FIELDS: tuple[tuple[str, str], ...] = (
    ("event_type", "Event"),
    ("entity_type", "Type"),
    ("entity_id", "Entity"),
    ("actor_type", "Actor Type"),
    ("actor_id", "Actor"),
    ("before_state", "From"),
    ("after_state", "To"),
    ("occurred_at", "When"),
)


def _select_columns(
    catalog: tuple[tuple[str, str], ...],
    filters: dict[str, Any],
    extra_labels: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Return the column list narrowed to the widget's chosen fields.

    Honors the order of the selection and resolves both catalog keys and any
    `extra_labels` (e.g. dynamic entity-data columns). Falls back to the full
    catalog when nothing valid is selected.
    """
    label_map = {key: label for key, label in catalog}
    if extra_labels:
        label_map.update(extra_labels)
    selected = filters.get("fields")
    if isinstance(selected, list) and selected:
        cols = [
            {"key": str(k), "label": label_map[str(k)]}
            for k in selected
            if str(k) in label_map
        ]
        if cols:
            return cols
    return [{"key": key, "label": label} for key, label in catalog]


def _selected_data_fields(filters: dict[str, Any]) -> list[str]:
    """Entity-data field names chosen by the widget (keys like ``data.email``)."""
    selected = filters.get("fields")
    if not isinstance(selected, list):
        return []
    names: list[str] = []
    for raw in selected:
        text = str(raw)
        if text.startswith("data.") and len(text) > 5:
            names.append(text[5:])
    return names


# Cap on entity records sampled when discovering ad-hoc data keys, so the
# builder query stays cheap on large orgs.
_DATA_FIELD_SAMPLE_LIMIT = 1000


def _is_offerable_value(value: Any) -> bool:
    """True when a stored value is real. `0`/`False` count, blanks do not."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict, set, tuple)):
        return len(value) > 0
    return True


def _form_declared_fields(
    db: Session, organization_id: str, entity_type: str | None = None
) -> list[tuple[str, str]]:
    """(field name, label) declared in the org's active entity-type forms.

    Form-driven orgs keep their real field definitions here, not in
    `EntityTypeModel.schema`. Best-effort: returns nothing on failure and the
    caller falls back to sampled record keys.
    """
    raw: list[dict] = []
    try:
        if entity_type:
            raw = active_schema_fields_by_type_id(db, organization_id, entity_type) or []
        else:
            # "All workflows": every active form in the org, all entity types.
            rows = (
                db.query(EntityTypeSchemaModel.fields_json)
                .filter(
                    EntityTypeSchemaModel.organization_id == organization_id,
                    EntityTypeSchemaModel.is_active.is_(True),
                )
                .all()
            )
            for (fields_json,) in rows:
                raw.extend(fields_json or [])
    except SQLAlchemyError as exc:
        logger.warning(
            "Failed to load declared form fields, falling back to sampled record keys: %s",
            exc,
            extra={"organization_id": organization_id, "entity_type": entity_type},
        )
        return []

    declared: list[tuple[str, str]] = []
    for field_def in raw:
        if not isinstance(field_def, dict):
            continue
        name = str(
            field_def.get("field") or field_def.get("name") or field_def.get("id") or ""
        )
        declared.append((name, str(field_def.get("label") or "")))
    return declared


def entity_data_fields(
    db: Session, organization_id: str, entity_type: str | None = None
) -> list[tuple[str, str]]:
    """Selectable entity-data columns for the org. Keys are prefixed ``data.<name>``.

    A field is offered if it is declared (entity type schema or active form)
    or if some record holds a real value for it. Keys left empty on every
    record are skipped, since editing a form leaves its removed keys behind
    on old records and they would only render blank columns.
    """
    seen: set[str] = set()
    fields: list[tuple[str, str]] = []

    def _add(name: str, label: str | None = None) -> None:
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            fields.append((f"data.{name}", (label or "").strip() or _humanize(name)))

    schema_query = db.query(EntityTypeModel.schema).filter(
        EntityTypeModel.organization_id == organization_id,
        EntityTypeModel.archived_at.is_(None),
    )
    if entity_type:
        schema_query = schema_query.filter(EntityTypeModel.entity_type_id == entity_type)
    schemas = schema_query.all()
    for (schema,) in schemas:
        if not isinstance(schema, dict):
            continue
        for field_def in schema.get("fields", []) or []:
            if not isinstance(field_def, dict):
                continue
            # Field identifier is keyed as id / field / name across the codebase
            # (see entities/manager.py). Match that resolution order.
            name = str(
                field_def.get("id")
                or field_def.get("field")
                or field_def.get("name", "")
            )
            _add(name, str(field_def.get("label") or ""))

    for name, label in _form_declared_fields(db, organization_id, entity_type=entity_type):
        _add(name, label)

    data_query = db.query(EntityRecordModel.data).filter(
        EntityRecordModel.organization_id == organization_id,
        EntityRecordModel.archived_at.is_(None),
    )
    if entity_type:
        data_query = data_query.filter(EntityRecordModel.entity_type_id == entity_type)
    data_rows = (
        data_query.order_by(EntityRecordModel.updated_at.desc())
        .limit(_DATA_FIELD_SAMPLE_LIMIT)
        .all()
    )
    for (data,) in data_rows:
        if isinstance(data, dict):
            for key, value in data.items():
                if _is_offerable_value(value):
                    _add(str(key))

    return sorted(fields, key=lambda item: item[1].lower())


def _humanize(identifier: str) -> str:
    """Turn a field identifier like ``first_name`` into ``First Name``."""
    cleaned = identifier.replace("_", " ").replace("-", " ").strip()
    return cleaned.title() if cleaned else identifier


def _filter_str(filters: dict[str, Any], key: str) -> str | None:
    value = filters.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _filter_int(filters: dict[str, Any], key: str, default: int, lo: int, hi: int) -> int:
    """Parse a bounded integer filter, falling back to ``default`` on bad input."""
    try:
        return max(lo, min(int(filters.get(key, default)), hi))
    except (TypeError, ValueError):
        return default


def _parse_iso_date(value: str | None) -> datetime | None:
    """Parse a 'YYYY-MM-DD' filter value into a UTC midnight datetime."""
    if not value:
        return None
    try:
        d = datetime.strptime(value.strip(), "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    return d.replace(tzinfo=timezone.utc)


_LAST_N_DAYS = {"last_7d": 7, "last_30d": 30, "last_90d": 90, "last_180d": 180}

# Every named value `time_range` accepts. "" and "all" both mean no lower bound.
# `last_<N>d` is also accepted for any N from 1 to 365: callers ask for windows
# the named presets do not cover ("the last 5 days"), and without this they
# either error or, worse, substitute a preset that does not match the question.
TIME_RANGE_VALUES = ("all", "today", "this_week", "this_month", "last_month", *_LAST_N_DAYS)
_LAST_N_DAYS_PATTERN = re.compile(r"^last_(\d{1,3})d$")
_MAX_RANGE_DAYS = 365


def _last_n_days(value: str) -> int | None:
    """Day count for a `last_<N>d` window, or None if it is not one."""
    match = _LAST_N_DAYS_PATTERN.match(value)
    if match is None:
        return None
    days = int(match.group(1))
    return days if 1 <= days <= _MAX_RANGE_DAYS else None


# Committed state changes now land in the unified `audit_events` table. The old
# `audit.transition_attempts` table stopped being written when the workflow
# manager moved to that writer, so every metric sourced from it silently
# returned zero. These helpers keep the live source in one place.
def _succeeded_transitions(db: Session, organization_id: str) -> Query:
    """Base query over committed transitions for one organization."""
    from workflow.models.interface import TransitionAuditEventType

    return db.query(AuditEventModel).filter(
        AuditEventModel.organization_id == organization_id,
        AuditEventModel.event_type == TransitionAuditEventType.SUCCEEDED.value,
    )


def _transition_workflow_column() -> ColumnElement[str]:
    """The workflow a transition belongs to, read out of the event metadata."""
    return AuditEventModel.event_metadata["workflow_id"].astext


def _apply_global_entity_filter(query, column, filters: dict[str, Any]):  # noqa: ANN001, ANN202
    entity_ids = global_entity_ids(filters)
    if entity_ids is None:
        return query
    return query.filter(column.in_(entity_ids))


def _range_since(filters: dict[str, Any]) -> datetime | None:
    """Resolve the universal time filter into a lower-bound timestamp.

    ``time_range`` is an implicit universal filter present on every widget. It is
    not a declared MetricParam — each metric applies the returned cutoff to its
    own natural timestamp column. A custom ``date_from`` takes precedence. ``None``
    (also ``""`` / ``"all"``) means no lower bound, i.e. show everything.

    Raises ValidationError on an unrecognized value, so a bad window is never
    answered with an all-time number.
    """
    custom_from = _parse_iso_date(_filter_str(filters, "date_from"))
    if custom_from is not None:
        return custom_from
    value = _filter_str(filters, "time_range")
    if not value or value == "all":
        return None
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if value == "today":
        return midnight
    if value == "this_week":
        return midnight - timedelta(days=midnight.weekday())
    if value == "this_month":
        return midnight.replace(day=1)
    if value == "last_month":
        # A calendar month, not a trailing 30 days. Without it "last month" was
        # answered with last_30d, which starts mid-month and misses the rest.
        return (midnight.replace(day=1) - timedelta(days=1)).replace(day=1)
    days = _LAST_N_DAYS.get(value) or _last_n_days(value)
    if days is not None:
        return now - timedelta(days=days)
    # An unrecognized value used to fall through to "no lower bound", so a
    # mistyped window silently answered with an all-time number. The date is
    # named here because the caller's next move is to work out a real range,
    # and picking a preset that does not match the question is not it.
    raise ValidationError(
        f"Unsupported time_range {value!r}. Use one of: "
        f"{', '.join(TIME_RANGE_VALUES)}, or last_<N>d for any N up to "
        f"{_MAX_RANGE_DAYS} (e.g. last_5d). For anything else pass "
        f"date_from/date_to as YYYY-MM-DD; today is {now.date().isoformat()}. "
        "Do not substitute a different window."
    )


def _range_until(filters: dict[str, Any]) -> datetime | None:
    """Upper bound (exclusive) for the time filter.

    ``None`` for presets (the window ends "now"). For a custom range, the day
    after ``date_to`` at midnight so the end date is inclusive.
    """
    custom_to = _parse_iso_date(_filter_str(filters, "date_to"))
    if custom_to is not None:
        return custom_to + timedelta(days=1)
    # Every other preset runs up to now; a past calendar month has a real end.
    if _filter_str(filters, "time_range") == "last_month":
        now = datetime.now(UTC)
        return now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return None


def _previous_range(filters: dict[str, Any]) -> tuple[datetime, datetime] | None:
    """The [start, end) window immediately preceding the current range.

    Used for period-over-period deltas on scalar metrics. ``None`` when there is
    no current lower bound. The current window's lower bound is the previous
    window's upper bound.
    """
    current_start = _range_since(filters)
    if current_start is None:
        return None
    until = _range_until(filters)
    if until is not None:
        # Custom range: previous window is the same length, immediately before.
        span = until - current_start
        return current_start - span, current_start
    value = _filter_str(filters, "time_range")
    if value == "today":
        return current_start - timedelta(days=1), current_start
    if value == "this_week":
        return current_start - timedelta(days=7), current_start
    if value in ("this_month", "last_month"):
        last_day_prev = current_start - timedelta(days=1)
        return last_day_prev.replace(day=1), current_start
    days = _LAST_N_DAYS.get(value or "") or _last_n_days(value or "")
    if days is not None:
        return current_start - timedelta(days=days), current_start
    return None


def _daily_trend(
    db: Session, organization_id: str, filters: dict[str, Any], days: int = 14
) -> list[dict[str, Any]]:
    """Daily count of entities created over the trailing ``days`` window.

    Powers the KPI sparkline. Honors ``entity_type_id`` when present so the
    sparkline matches the headline ``entities.count`` value.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    bucket = func.date_trunc("day", EntityRecordModel.created_at)
    query = db.query(bucket.label("day"), func.count().label("count")).filter(
        EntityRecordModel.organization_id == organization_id,
        EntityRecordModel.archived_at.is_(None),
        EntityRecordModel.created_at >= since,
    )
    entity_type_id = _filter_str(filters, "entity_type_id")
    if entity_type_id:
        query = query.filter(EntityRecordModel.entity_type_id == entity_type_id)
    query = _apply_global_entity_filter(query, EntityRecordModel.entity_id, filters)
    rows = query.group_by(bucket).order_by(bucket.asc()).all()
    return [
        {"label": day.date().isoformat() if day else "", "value": int(count)}
        for day, count in rows
    ]


def order_series_by_states(
    series: list[dict[str, Any]], state_order: list[str]
) -> list[dict[str, Any]]:
    """Reorder a label/value series to follow a workflow's declared state order.

    States in ``state_order`` absent from ``series`` are appended with value 0 so
    the funnel shows the full pipeline. Labels not in ``state_order`` keep their
    original relative order at the end.
    """
    by_label = {str(point["label"]): point for point in series}
    ordered: list[dict[str, Any]] = []
    for state in state_order:
        point = by_label.pop(state, None)
        ordered.append(point if point is not None else {"label": state, "value": 0})
    ordered.extend(by_label.values())
    return ordered


def _workflow_family_filter(column, organization_id: str, workflow_id: str):
    """Match every version row of the workflow family ``workflow_id`` belongs to.

    An entity pins ``workflow_id`` to the version row it enrolled on and is never
    repointed when a newer version is published, so matching a single row id would
    silently drop every in-flight entity still running an earlier version. Filters
    therefore expand the picked version to all versions sharing its ``machine_name``.

    Yields no matches for an unknown id, same as the exact-id match it replaces.
    """
    machine_name = (
        select(WorkflowStateMachineModel.machine_name)
        .where(
            WorkflowStateMachineModel.organization_id == organization_id,
            WorkflowStateMachineModel.id == workflow_id,
        )
        .scalar_subquery()
    )
    family = (
        select(WorkflowStateMachineModel.id)
        .where(
            WorkflowStateMachineModel.organization_id == organization_id,
            WorkflowStateMachineModel.machine_name == machine_name,
        )
        .scalar_subquery()
    )
    return column.in_(family)


def resolve_workflow_entity_type(
    db: Session, organization_id: str, workflow_id: str
) -> str | None:
    """Entity type id bound to ``workflow_id``'s family, or None if unbound.

    Joins by name to drop placeholder/stale versions (e.g. blank drafts), and
    reads the active version first. Shared by every filter-options/metrics
    field that must be scoped to one workflow's own entity type rather than
    leaking every entity type's fields into the picker (see ``filter_options``
    and ``DashboardServiceManager.list_metrics``).
    """
    row = (
        db.query(EntityTypeModel.entity_type_id)
        .select_from(WorkflowStateMachineModel)
        .join(
            EntityTypeModel,
            and_(
                EntityTypeModel.organization_id == WorkflowStateMachineModel.organization_id,
                EntityTypeModel.name == WorkflowStateMachineModel.entity_type,
                EntityTypeModel.archived_at.is_(None),
            ),
        )
        .filter(
            WorkflowStateMachineModel.organization_id == organization_id,
            _workflow_family_filter(WorkflowStateMachineModel.id, organization_id, workflow_id),
        )
        .order_by(
            WorkflowStateMachineModel.is_active.desc(),
            WorkflowStateMachineModel.version.desc(),
        )
        .first()
    )
    return row[0] if row else None


def _active_workflow_state_order(
    db: Session, organization_id: str, workflow_id: str
) -> list[str]:
    """Ordered state names for a workflow's active definition.

    Reads the active ``WorkflowStateMachineModel`` row of ``workflow_id``'s family,
    parses ``definition_json``, and returns state names sorted by each state's
    ``order`` field (states without an explicit order sort last, by declared
    sequence). Returns [] when no active definition is found, so callers can fall
    back to count-desc ordering.
    """
    row = (
        db.query(WorkflowStateMachineModel.definition_json)
        .filter(
            WorkflowStateMachineModel.organization_id == organization_id,
            _workflow_family_filter(
                WorkflowStateMachineModel.id, organization_id, workflow_id
            ),
            WorkflowStateMachineModel.is_active.is_(True),
        )
        .first()
    )
    if row is None:
        return []
    try:
        definition = json.loads(row[0])
    except (TypeError, ValueError) as exc:
        logger.warning(
            "Malformed definition_json for workflow %s, treating as no active states: %s",
            workflow_id,
            exc,
            extra={"organization_id": organization_id, "workflow_id": workflow_id},
        )
        return []
    states = definition.get("states") if isinstance(definition, dict) else None
    if not isinstance(states, list):
        return []
    indexed = []
    for seq, state in enumerate(states):
        if not isinstance(state, dict):
            continue
        name = state.get("name")
        if not name:
            continue
        order = state.get("order")
        sort_key = (0, order, seq) if isinstance(order, int) else (1, 0, seq)
        indexed.append((sort_key, str(name)))
    indexed.sort(key=lambda item: item[0])
    return [name for _, name in indexed]


def _pipeline_by_state(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    query = (
        db.query(EntityStateRuntimeModel.current_state, func.count().label("count"))
        .filter(EntityStateRuntimeModel.organization_id == organization_id)
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        query = query.filter(
            _workflow_family_filter(
                EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
            )
        )
    query = _apply_global_entity_filter(query, EntityStateRuntimeModel.entity_id, filters)
    since = _range_since(filters)
    if since:
        query = query.filter(EntityStateRuntimeModel.state_entered_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityStateRuntimeModel.state_entered_at < until)
    query = query.group_by(EntityStateRuntimeModel.current_state).order_by(func.count().desc())
    series = [{"label": state, "value": int(count)} for state, count in query.all()]
    return {"kind": "series", "series": series}


def _pipeline_funnel(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Pipeline counts ordered by the workflow's declared state sequence.

    Like ``pipeline.by_state`` but ordered for funnel display. Falls back to
    count-descending when no active workflow definition is available.
    """
    query = (
        db.query(EntityStateRuntimeModel.current_state, func.count().label("count"))
        .filter(EntityStateRuntimeModel.organization_id == organization_id)
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        query = query.filter(
            _workflow_family_filter(
                EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
            )
        )
    query = _apply_global_entity_filter(query, EntityStateRuntimeModel.entity_id, filters)
    since = _range_since(filters)
    if since:
        query = query.filter(EntityStateRuntimeModel.state_entered_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityStateRuntimeModel.state_entered_at < until)
    query = query.group_by(EntityStateRuntimeModel.current_state).order_by(func.count().desc())
    series = [{"label": state, "value": int(count)} for state, count in query.all()]

    state_order = (
        _active_workflow_state_order(db, organization_id, workflow_id)
        if workflow_id
        else []
    )
    if state_order:
        series = order_series_by_states(series, state_order)
    return {"kind": "series", "series": series}


def _entities_count(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    query = (
        db.query(func.count())
        .select_from(EntityRecordModel)
        .filter(
            EntityRecordModel.organization_id == organization_id,
            EntityRecordModel.archived_at.is_(None),
        )
    )
    entity_type_id = _filter_str(filters, "entity_type_id")
    if entity_type_id:
        query = query.filter(EntityRecordModel.entity_type_id == entity_type_id)
    query = _apply_global_entity_filter(query, EntityRecordModel.entity_id, filters)
    since = _range_since(filters)
    if since:
        query = query.filter(EntityRecordModel.created_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityRecordModel.created_at < until)
    value = int(query.scalar() or 0)
    payload: dict[str, Any] = {"kind": "scalar", "value": value}
    prev_window = _previous_range(filters)
    if prev_window is not None:
        prev_start, prev_end = prev_window
        prev_query = (
            db.query(func.count())
            .select_from(EntityRecordModel)
            .filter(
                EntityRecordModel.organization_id == organization_id,
                EntityRecordModel.archived_at.is_(None),
                EntityRecordModel.created_at >= prev_start,
                EntityRecordModel.created_at < prev_end,
            )
        )
        if entity_type_id:
            prev_query = prev_query.filter(EntityRecordModel.entity_type_id == entity_type_id)
        prev_query = _apply_global_entity_filter(prev_query, EntityRecordModel.entity_id, filters)
        payload["prevValue"] = int(prev_query.scalar() or 0)
    payload["trend"] = _daily_trend(db, organization_id, filters)
    return payload


def _entities_in_state(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Count entity instances CURRENTLY in a chosen state (e.g. Open / Closed).

    A snapshot of current occupancy — entities whose ``current_state`` equals the
    requested state right now. Distinct from ``entities.reached_state``, which
    counts entities that *ever* passed through a state. Honors the universal time
    window via ``state_entered_at`` and exposes a trailing-14d entries sparkline.
    """
    state = _filter_str(filters, "state")
    if not state:
        return {"kind": "scalar", "value": 0}

    workflow_id = _filter_str(filters, "workflow_id")

    def _base():
        q = (
            db.query(func.count())
            .select_from(EntityStateRuntimeModel)
            .filter(
                EntityStateRuntimeModel.organization_id == organization_id,
                EntityStateRuntimeModel.current_state == state,
            )
        )
        if workflow_id:
            q = q.filter(
                _workflow_family_filter(
                    EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
                )
            )
        q = _apply_global_entity_filter(q, EntityStateRuntimeModel.entity_id, filters)
        return q

    query = _base()
    since = _range_since(filters)
    if since:
        query = query.filter(EntityStateRuntimeModel.state_entered_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityStateRuntimeModel.state_entered_at < until)
    value = int(query.scalar() or 0)

    payload: dict[str, Any] = {"kind": "scalar", "value": value}
    prev_window = _previous_range(filters)
    if prev_window is not None:
        prev_start, prev_end = prev_window
        payload["prevValue"] = int(
            _base()
            .filter(
                EntityStateRuntimeModel.state_entered_at >= prev_start,
                EntityStateRuntimeModel.state_entered_at < prev_end,
            )
            .scalar()
            or 0
        )

    # Sparkline: daily entries into the state over a trailing 14-day window.
    bucket = func.date_trunc("day", EntityStateRuntimeModel.state_entered_at)
    trend_since = datetime.now(timezone.utc) - timedelta(days=14)
    trend_rows = (
        _base()
        .with_entities(bucket.label("day"), func.count().label("count"))
        .filter(EntityStateRuntimeModel.state_entered_at >= trend_since)
        .group_by(bucket)
        .order_by(bucket.asc())
        .all()
    )
    payload["trend"] = [
        {"label": day.date().isoformat() if day else "", "value": int(count)}
        for day, count in trend_rows
    ]
    return payload


def _entities_by_field(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Count entity instances grouped by the value of a chosen form field.

    The form field is an entity ``data`` JSONB key (same field across instances,
    differing/recurring values). Returns a count per distinct value, sorted
    descending, optionally capped to the top ``limit`` (0/unset = all values).
    Renders as a bar / horizontal-bar / pie chart.
    """
    raw = _filter_str(filters, "field")
    if not raw:
        return {"kind": "series", "series": []}
    name = raw[5:] if raw.startswith("data.") else raw
    group_col = EntityRecordModel.data[name].astext
    count_col = func.count(EntityRecordModel.entity_id)
    query = db.query(group_col.label("value"), count_col.label("count")).filter(
        EntityRecordModel.organization_id == organization_id,
        EntityRecordModel.archived_at.is_(None),
        group_col.isnot(None),
    )
    query = _apply_global_entity_filter(query, EntityRecordModel.entity_id, filters)
    since = _range_since(filters)
    if since:
        query = query.filter(EntityRecordModel.created_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityRecordModel.created_at < until)
    query = query.group_by(group_col).order_by(count_col.desc())
    limit = _filter_int(filters, "limit", default=0, lo=0, hi=1000)
    if limit > 0:
        query = query.limit(limit)
    rows = query.all()
    series = [
        {"label": str(value), "value": int(count)}
        for value, count in rows
        if value is not None
    ]
    return {"kind": "series", "series": series}


def _sla_breaches(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Count SLA breaches that have actually fired.

    A breach is recorded as a ``signal.fire`` action_run with
    ``signal_type == 'sla_breach'`` (see WorkflowDefinitionService._create_sla_action_run).
    The notification the user receives is emitted when that run succeeds, so we
    count succeeded runs — this is what keeps the stat in sync with the alerts.
    Note: ``entity_state.sla_due_at`` is unrelated here (it tracks the next-step
    deadline and is often null), which is why the older query under-counted.
    """
    query = (
        db.query(func.count())
        .select_from(ActionRunModel)
        .filter(
            ActionRunModel.organization_id == organization_id,
            ActionRunModel.action_kind == "signal.fire",
            ActionRunModel.config_json["signal_type"].astext == "sla_breach",
            ActionRunModel.status == "succeeded",
        )
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        # The action_run isn't tagged with a workflow column, so scope by the
        # entities currently bound to the requested workflow.
        entity_ids = db.query(EntityStateRuntimeModel.entity_id).filter(
            EntityStateRuntimeModel.organization_id == organization_id,
            _workflow_family_filter(
                EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
            ),
        )
        query = query.filter(ActionRunModel.entity_id.in_(entity_ids))
    query = _apply_global_entity_filter(query, ActionRunModel.entity_id, filters)
    since = _range_since(filters)
    if since:
        query = query.filter(ActionRunModel.completed_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(ActionRunModel.completed_at < until)
    value = int(query.scalar() or 0)
    payload: dict[str, Any] = {"kind": "scalar", "value": value}
    prev_window = _previous_range(filters)
    if prev_window is not None:
        prev_start, prev_end = prev_window
        prev_query = (
            db.query(func.count())
            .select_from(ActionRunModel)
            .filter(
                ActionRunModel.organization_id == organization_id,
                ActionRunModel.action_kind == "signal.fire",
                ActionRunModel.config_json["signal_type"].astext == "sla_breach",
                ActionRunModel.status == "succeeded",
                ActionRunModel.completed_at >= prev_start,
                ActionRunModel.completed_at < prev_end,
            )
        )
        if workflow_id:
            entity_ids = db.query(EntityStateRuntimeModel.entity_id).filter(
                EntityStateRuntimeModel.organization_id == organization_id,
                _workflow_family_filter(
                    EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
                ),
            )
            prev_query = prev_query.filter(ActionRunModel.entity_id.in_(entity_ids))
        prev_query = _apply_global_entity_filter(prev_query, ActionRunModel.entity_id, filters)
        payload["prevValue"] = int(prev_query.scalar() or 0)
    return payload


def _sla_compliance(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """On-time percentage for instances that carry an SLA due time.

    Compliance = instances whose ``sla_due_at`` is still in the future over all
    instances with a due date. Returns a gauge payload (0-100). When no instance
    has an SLA, value is 100.
    """
    base = db.query(func.count()).select_from(EntityStateRuntimeModel).filter(
        EntityStateRuntimeModel.organization_id == organization_id,
        EntityStateRuntimeModel.sla_due_at.isnot(None),
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        base = base.filter(
            _workflow_family_filter(
                EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
            )
        )
    base = _apply_global_entity_filter(base, EntityStateRuntimeModel.entity_id, filters)
    total = int(base.scalar() or 0)
    if total == 0:
        return {"kind": "gauge", "value": 100.0, "max": 100, "label": "On-time %"}
    now = datetime.now(timezone.utc)
    on_time_query = db.query(func.count()).select_from(EntityStateRuntimeModel).filter(
        EntityStateRuntimeModel.organization_id == organization_id,
        EntityStateRuntimeModel.sla_due_at.isnot(None),
        EntityStateRuntimeModel.sla_due_at >= now,
    )
    if workflow_id:
        on_time_query = on_time_query.filter(
            _workflow_family_filter(
                EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
            )
        )
    on_time_query = _apply_global_entity_filter(
        on_time_query, EntityStateRuntimeModel.entity_id, filters
    )
    on_time = int(on_time_query.scalar() or 0)
    return {
        "kind": "gauge",
        "value": round(on_time / total * 100, 1),
        "max": 100,
        "label": "On-time %",
    }


def _events_recent(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    query = db.query(EntityEventAuditModel).filter(
        EntityEventAuditModel.organization_id == organization_id
    )
    event_type = _filter_str(filters, "event_type")
    if event_type:
        query = query.filter(EntityEventAuditModel.event_type == event_type)
    query = _apply_global_entity_filter(query, EntityEventAuditModel.entity_id, filters)
    since = _range_since(filters)
    if since:
        query = query.filter(EntityEventAuditModel.occurred_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityEventAuditModel.occurred_at < until)
    limit_raw = filters.get("limit", 20)
    try:
        limit = max(1, min(int(limit_raw), 100))
    except (TypeError, ValueError):
        limit = 20
    records = query.order_by(EntityEventAuditModel.occurred_at.desc()).limit(limit).all()
    rows = [
        {
            "event_type": r.event_type,
            "entity_id": r.entity_id,
            "actor": r.actor_id or r.actor_type,
            "actor_type": r.actor_type,
            "correlation_id": r.correlation_id,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
        }
        for r in records
    ]
    columns = _select_columns(EVENTS_RECENT_FIELDS, filters)
    return {"kind": "rows", "columns": columns, "rows": rows}


def _resolve_instances_field_visibility(
    present_types: set[str],
    field_policy_resolver: Callable[[str], tuple[list[str] | None, list[str]]] | None,
) -> tuple[dict[str, set[str] | None], dict[str, set[str]]]:
    """(visible_by_type, masked_by_type) for every entity type present in a
    batch — resolved once per type, never per row."""
    visible_by_type: dict[str, set[str] | None] = {}
    masked_by_type: dict[str, set[str]] = {}
    if field_policy_resolver is not None:
        for entity_type_id in present_types:
            visible, masked = field_policy_resolver(entity_type_id)
            visible_by_type[entity_type_id] = set(visible) if visible is not None else None
            masked_by_type[entity_type_id] = set(masked)
    return visible_by_type, masked_by_type


def _resolve_instances_data_field_names(
    db: Session,
    organization_id: str,
    filters: dict[str, Any],
    present_types: set[str],
    visible_by_type: dict[str, set[str] | None],
    has_policy: bool,
) -> tuple[list[str], dict[str, str]]:
    """Data field names + labels for `_instances_list`.

    This widget replays a saved dashboard config — a chosen field that this
    viewer can't see is dropped from the result silently (same as if it were
    never chosen), never an error that blanks the whole widget.
    """
    selected = filters.get("fields")
    if isinstance(selected, list) and selected:
        requested = _selected_data_fields(filters)
        if has_policy and present_types:
            data_field_names = [
                name
                for name in requested
                if not any(
                    visible_by_type[t] is not None and name not in visible_by_type[t]
                    for t in present_types
                )
            ]
        else:
            data_field_names = requested
        return data_field_names, {f"data.{name}": _humanize(name) for name in data_field_names}

    all_data = entity_data_fields(db, organization_id)
    discovered = [key[len("data."):] for key, _ in all_data]
    if has_policy and present_types:
        data_field_names = [
            name
            for name in discovered
            if any(visible_by_type[t] is None or name in visible_by_type[t] for t in present_types)
        ]
    else:
        data_field_names = discovered
    return data_field_names, dict(all_data)


def _resolve_workflow_display_names(
    db: Session, organization_id: str, workflow_ids: set[str]
) -> dict[str, str]:
    """Workflow id -> display name, so the table shows names, not UUIDs. The
    friendly name lives in definition_json.name; machine_name is a slug, so
    fall back slug -> id only when the name is missing."""
    workflow_names: dict[str, str] = {}
    if not workflow_ids:
        return workflow_names
    for wid, machine_name, definition_json in (
        db.query(
            WorkflowStateMachineModel.id,
            WorkflowStateMachineModel.machine_name,
            WorkflowStateMachineModel.definition_json,
        )
        .filter(
            WorkflowStateMachineModel.organization_id == organization_id,
            WorkflowStateMachineModel.id.in_(workflow_ids),
        )
        .all()
    ):
        display = machine_name
        try:
            parsed = (
                json.loads(definition_json) if isinstance(definition_json, str) else definition_json
            )
            if isinstance(parsed, dict) and parsed.get("name"):
                display = str(parsed["name"])
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Malformed definition_json for workflow %s, falling back to machine_name: %s",
                wid,
                exc,
                extra={"organization_id": organization_id, "workflow_id": wid},
            )
        workflow_names[wid] = display
    return workflow_names


def _build_instances_row(
    record: Any,
    *,
    data_by_entity: dict[str, dict[str, Any]],
    entity_type_by_id: dict[str, str],
    visible_by_type: dict[str, set[str] | None],
    masked_by_type: dict[str, set[str]],
    data_field_names: list[str],
    workflow_names: dict[str, str],
) -> dict[str, Any]:
    """One `instances.list` row, with `data.*` columns filtered/masked per the
    row's own entity type."""
    row: dict[str, Any] = {
        "entity_id": record.entity_id,
        "current_state": record.current_state,
        "workflow_id": workflow_names.get(record.workflow_id, record.workflow_id),
        "state_version": record.state_version,
        "state_entered_at": record.state_entered_at.isoformat() if record.state_entered_at else None,
        "last_transition_at": (
            record.last_transition_at.isoformat() if record.last_transition_at else None
        ),
        "sla_due_at": record.sla_due_at.isoformat() if record.sla_due_at else None,
    }
    entity_data = data_by_entity.get(record.entity_id, {})
    row_type = entity_type_by_id.get(record.entity_id)
    row_visible = visible_by_type.get(row_type) if row_type else None
    row_masked = masked_by_type.get(row_type, set()) if row_type else set()
    for name in data_field_names:
        if row_visible is not None and name not in row_visible:
            continue  # not visible for this row's own entity type — silently omitted
        if name in row_masked and name in entity_data:
            row[f"data.{name}"] = MASKED_FIELD_VALUE
        else:
            row[f"data.{name}"] = entity_data.get(name)
    return row


def _instances_list(
    db: Session,
    organization_id: str,
    filters: dict[str, Any],
    field_policy_resolver: Callable[[str], tuple[list[str] | None, list[str]]] | None = None,
) -> dict[str, Any]:
    """List of workflow instance rows.

    `field_policy_resolver`, when supplied, is `(entity_type_id) -> (visible_fields,
    masked_fields)` bound to the roles module by the caller (see
    `DashboardServiceManager._entity_field_policy_resolver` in `dashboard/manager.py`) —
    kept as a callable rather than an import so this file never depends on the roles
    module directly. `visible_fields=None` means unrestricted for that entity type.
    """
    query = db.query(EntityStateRuntimeModel).filter(
        EntityStateRuntimeModel.organization_id == organization_id
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        query = query.filter(
            _workflow_family_filter(
                EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
            )
        )
    current_state = _filter_str(filters, "current_state")
    if current_state:
        query = query.filter(EntityStateRuntimeModel.current_state == current_state)
    query = _apply_global_entity_filter(query, EntityStateRuntimeModel.entity_id, filters)
    since = _range_since(filters)
    if since:
        query = query.filter(EntityStateRuntimeModel.state_entered_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityStateRuntimeModel.state_entered_at < until)
    limit_raw = filters.get("limit", 50)
    try:
        limit = max(1, min(int(limit_raw), 200))
    except (TypeError, ValueError):
        limit = 50
    records = (
        query.order_by(nullslast(EntityStateRuntimeModel.last_transition_at.desc()))
        .limit(limit)
        .all()
    )

    entity_ids = [r.entity_id for r in records]
    data_by_entity: dict[str, dict[str, Any]] = {}
    entity_type_by_id: dict[str, str] = {}
    if entity_ids:
        data_rows = (
            db.query(
                EntityRecordModel.entity_id,
                EntityRecordModel.entity_type_id,
                EntityRecordModel.data,
            )
            .filter(
                EntityRecordModel.organization_id == organization_id,
                EntityRecordModel.entity_id.in_(entity_ids),
            )
            .all()
        )
        for eid, entity_type_id, data in data_rows:
            data_by_entity[eid] = data if isinstance(data, dict) else {}
            if entity_type_id:
                entity_type_by_id[eid] = entity_type_id

    present_types = {t for t in entity_type_by_id.values() if t}
    visible_by_type, masked_by_type = _resolve_instances_field_visibility(
        present_types, field_policy_resolver
    )
    data_field_names, data_labels = _resolve_instances_data_field_names(
        db, organization_id, filters, present_types, visible_by_type, field_policy_resolver is not None
    )
    workflow_names = _resolve_workflow_display_names(
        db, organization_id, {r.workflow_id for r in records if r.workflow_id}
    )

    rows = [
        _build_instances_row(
            r,
            data_by_entity=data_by_entity,
            entity_type_by_id=entity_type_by_id,
            visible_by_type=visible_by_type,
            masked_by_type=masked_by_type,
            data_field_names=data_field_names,
            workflow_names=workflow_names,
        )
        for r in records
    ]

    has_selection = isinstance(filters.get("fields"), list) and bool(filters.get("fields"))
    if has_selection:
        columns = _select_columns(INSTANCES_LIST_FIELDS, filters, data_labels)
    else:
        columns = [{"key": key, "label": label} for key, label in INSTANCES_LIST_FIELDS]
        columns += [
            {"key": f"data.{name}", "label": data_labels[f"data.{name}"]}
            for name in data_field_names
        ]
    return {"kind": "rows", "columns": columns, "rows": rows}


def _events_by_type(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    query = db.query(EntityEventAuditModel.event_type, func.count().label("count")).filter(
        EntityEventAuditModel.organization_id == organization_id
    )
    query = _apply_global_entity_filter(query, EntityEventAuditModel.entity_id, filters)
    since = _range_since(filters)
    if since:
        query = query.filter(EntityEventAuditModel.occurred_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityEventAuditModel.occurred_at < until)
    rows = (
        query.group_by(EntityEventAuditModel.event_type)
        .order_by(func.count().desc())
        .limit(20)
        .all()
    )
    series = [{"label": event_type, "value": int(count)} for event_type, count in rows]
    return {"kind": "series", "series": series}


def _entities_by_type(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    count_col = func.count(EntityRecordModel.entity_id)
    query = (
        db.query(EntityTypeModel.name, count_col.label("count"))
        .join(
            EntityRecordModel,
            EntityRecordModel.entity_type_id == EntityTypeModel.entity_type_id,
        )
        .filter(
            EntityRecordModel.organization_id == organization_id,
            EntityRecordModel.archived_at.is_(None),
            EntityTypeModel.organization_id == organization_id,
        )
    )
    since = _range_since(filters)
    if since:
        query = query.filter(EntityRecordModel.created_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityRecordModel.created_at < until)
    query = _apply_global_entity_filter(query, EntityRecordModel.entity_id, filters)
    rows = (
        query.group_by(EntityTypeModel.name)
        .order_by(count_col.desc())
        .all()
    )
    series = [{"label": name, "value": int(count)} for name, count in rows]
    return {"kind": "series", "series": series}


def _events_over_time(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    # A widget time_range, when set, takes precedence over the rolling days window.
    since = _range_since(filters)
    if since is None:
        days = _filter_int(filters, "days", default=30, lo=1, hi=365)
        since = datetime.now(timezone.utc) - timedelta(days=days)
    bucket = func.date_trunc("day", EntityEventAuditModel.occurred_at)
    query = db.query(bucket.label("day"), func.count().label("count")).filter(
        EntityEventAuditModel.organization_id == organization_id,
        EntityEventAuditModel.occurred_at >= since,
    )
    query = _apply_global_entity_filter(query, EntityEventAuditModel.entity_id, filters)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityEventAuditModel.occurred_at < until)
    event_type = _filter_str(filters, "event_type")
    if event_type:
        query = query.filter(EntityEventAuditModel.event_type == event_type)
    rows = query.group_by(bucket).order_by(bucket.asc()).all()
    series = [
        {"label": day.date().isoformat() if day else "", "value": int(count)}
        for day, count in rows
    ]
    return {"kind": "series", "series": series}


def _transitions_over_time(
    db: Session, organization_id: str, filters: dict[str, Any]
) -> dict[str, Any]:
    # A widget time_range, when set, takes precedence over the rolling days window.
    since = _range_since(filters)
    if since is None:
        days = _filter_int(filters, "days", default=30, lo=1, hi=365)
        since = datetime.now(timezone.utc) - timedelta(days=days)
    bucket = func.date_trunc("day", AuditEventModel.event_timestamp)
    query = (
        _succeeded_transitions(db, organization_id)
        .with_entities(bucket.label("day"), func.count().label("count"))
        .filter(AuditEventModel.event_timestamp >= since)
    )
    # Without this the chart counted every transition in the org, so "moved to
    # Done over time" plotted all movement regardless of destination.
    target_state = _filter_str(filters, "state")
    if target_state:
        query = query.filter(AuditEventModel.after_state == target_state)
    query = _apply_global_entity_filter(query, AuditEventModel.entity_id, filters)
    until = _range_until(filters)
    if until:
        query = query.filter(AuditEventModel.event_timestamp < until)
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        query = query.filter(
            _workflow_family_filter(_transition_workflow_column(), organization_id, workflow_id)
        )
    rows = query.group_by(bucket).order_by(bucket.asc()).all()
    series = [
        {"label": day.date().isoformat() if day else "", "value": int(count)}
        for day, count in rows
    ]
    return {"kind": "series", "series": series}


def _reached_state_base(db: Session, organization_id: str, filters: dict[str, Any]) -> Query:
    """Committed moves into `filters["state"]`, before any time window.

    The count and the list have to select the same transitions or they report
    different things about the same question, so they share this instead of
    each building the chain. The window is deliberately left off: the scalar
    reuses this for the preceding period to work out its delta, so each caller
    applies its own bounds.
    """
    query = _succeeded_transitions(db, organization_id).filter(
        AuditEventModel.after_state == _filter_str(filters, "state")
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        query = query.filter(
            _workflow_family_filter(_transition_workflow_column(), organization_id, workflow_id)
        )
    return _apply_global_entity_filter(query, AuditEventModel.entity_id, filters)


def _within_window(query: Query, filters: dict[str, Any]) -> Query:
    """Bound a transition query by the universal time filter."""
    since = _range_since(filters)
    if since:
        query = query.filter(AuditEventModel.event_timestamp >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(AuditEventModel.event_timestamp < until)
    return query


def _entities_reached_state(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Distinct entities that ever transitioned INTO a chosen state (committed).

    Answers "how many moved to X", counted from committed transitions in
    `audit_events`, so an entity that looped through the state counts once and
    still counts after it moves on. Honors the universal time window, which is
    what makes "moved to X in the last N days" work.
    """
    if not _filter_str(filters, "state"):
        return {"kind": "scalar", "value": 0}

    def _count(query: Query) -> int:
        return int(
            query.with_entities(func.count(func.distinct(AuditEventModel.entity_id))).scalar() or 0
        )

    base = _reached_state_base(db, organization_id, filters)
    payload: dict[str, Any] = {"kind": "scalar", "value": _count(_within_window(base, filters))}

    prev_window = _previous_range(filters)
    if prev_window is not None:
        prev_start, prev_end = prev_window
        payload["prevValue"] = _count(
            base.filter(
                AuditEventModel.event_timestamp >= prev_start,
                AuditEventModel.event_timestamp < prev_end,
            )
        )
    return payload


def _entities_reached_state_list(
    db: Session, organization_id: str, filters: dict[str, Any]
) -> dict[str, Any]:
    """The entities behind `entities.reached_state`, not just how many.

    Nothing could list them. Asked "which tickets moved to Done last week", the
    only listing tools filtered on the state an entity is in *now*, so the
    answer was every ticket sitting in Done - the count said 1 and the list
    showed 4.

    Selects over the same base as the scalar, so both answer the same question.
    The rows stop at `limit` while the scalar counts every match, so `total`
    carries the real figure and is what to quote when it exceeds the rows.
    """
    columns = [{"key": key, "label": label} for key, label in REACHED_STATE_LIST_FIELDS]
    if not _filter_str(filters, "state"):
        return {"kind": "rows", "columns": columns, "rows": [], "total": 0}

    query = _within_window(_reached_state_base(db, organization_id, filters), filters)
    limit = _filter_int(filters, "limit", default=50, lo=1, hi=200)

    # The scalar counts every match while these rows stop at `limit`, so report
    # the real figure too. Without it a page of 50 reads as the whole set and
    # the caller states it as the answer.
    total = int(
        query.with_entities(func.count(func.distinct(AuditEventModel.entity_id))).scalar() or 0
    )

    # One row per entity: an entity that entered the state twice in the window
    # is one ticket, matching how the scalar counts distinct entities.
    moved_at = func.max(AuditEventModel.event_timestamp).label("moved_at")
    records = (
        query.with_entities(AuditEventModel.entity_id, moved_at)
        .group_by(AuditEventModel.entity_id)
        .order_by(moved_at.desc())
        .limit(limit)
        .all()
    )
    entity_ids = [entity_id for entity_id, _ in records if entity_id]
    if not entity_ids:
        return {"kind": "rows", "columns": columns, "rows": [], "total": total}

    identifiers: dict[str, str] = {}
    for entity_id, data in (
        db.query(EntityRecordModel.entity_id, EntityRecordModel.data)
        .filter(
            EntityRecordModel.organization_id == organization_id,
            EntityRecordModel.entity_id.in_(entity_ids),
        )
        .all()
    ):
        if isinstance(data, dict):
            identifiers[entity_id] = str(data.get("identifier") or data.get("name") or "")

    current_states: dict[str, str] = dict(
        db.query(EntityStateRuntimeModel.entity_id, EntityStateRuntimeModel.current_state)
        .filter(
            EntityStateRuntimeModel.organization_id == organization_id,
            EntityStateRuntimeModel.entity_id.in_(entity_ids),
        )
        .all()
    )

    rows = [
        {
            "identifier": identifiers.get(entity_id) or entity_id,
            "moved_at": when.isoformat() if when else "",
            # Where it sits now, which is not always the state it moved into:
            # a ticket can pass through and move on inside the same window.
            "current_state": current_states.get(entity_id) or "",
            "entity_id": entity_id,
        }
        for entity_id, when in records
        if entity_id
    ]
    return {"kind": "rows", "columns": columns, "rows": rows, "total": total}


def _incidents_trend(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Example multiseries metric: weekly transition counts split by outcome.

    Demonstrates the 'multiseries' shape. Series keys are stable identifiers;
    labels are human-readable. Each point is { label, <key>: value, ... }.
    """
    from workflow.models.interface import TransitionAuditEventType

    since = _range_since(filters) or (datetime.now(timezone.utc) - timedelta(days=84))
    until = _range_until(filters)
    week = func.date_trunc("week", AuditEventModel.event_timestamp)
    outcomes = [t.value for t in TransitionAuditEventType]
    q = db.query(
        week.label("week"),
        AuditEventModel.event_type.label("status"),
        func.count().label("count"),
    ).filter(
        AuditEventModel.organization_id == organization_id,
        AuditEventModel.event_type.in_(outcomes),
        AuditEventModel.event_timestamp >= since,
    )
    if until:
        q = q.filter(AuditEventModel.event_timestamp < until)
    q = _apply_global_entity_filter(q, AuditEventModel.entity_id, filters)
    rows = q.group_by(week, AuditEventModel.event_type).order_by(week.asc()).all()

    statuses = sorted({status for _, status, _ in rows if status})
    by_week: dict[str, dict[str, int]] = {}
    for week_dt, status, count in rows:
        label = week_dt.date().isoformat() if week_dt else ""
        by_week.setdefault(label, {})[status] = int(count)
    points = [
        {"label": label, **{s: counts.get(s, 0) for s in statuses}}
        for label, counts in by_week.items()
    ]
    series = [{"key": s, "label": s.replace("_", " ").title()} for s in statuses]
    return {"kind": "multiseries", "points": points, "series": series}


# Whitelisted date_trunc units for the custom timeline. NEVER pass raw user
# input to date_trunc — only these literals.
_BUCKET_UNITS = {"day", "week", "month"}


def _transitions_by_state(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Multi-line trend: instances in each state over a custom timeline.

    One line per ``current_state``, bucketed by ``state_entered_at`` (day / week
    / month via the ``bucket`` param; default week). X = bucket date, Y = number
    of instances that entered that state in the bucket. Sourced from the
    entity-state runtime table (same source as ``pipeline.by_state``), so it
    plots whenever entities exist — no transition log required. Honors the
    global date range and an optional ``workflow_id``.
    """
    raw_bucket = (_filter_str(filters, "bucket") or "week").lower()
    bucket_unit = raw_bucket if raw_bucket in _BUCKET_UNITS else "week"

    bucket = func.date_trunc(bucket_unit, EntityStateRuntimeModel.state_entered_at)
    query = db.query(
        bucket.label("bucket"),
        EntityStateRuntimeModel.current_state.label("state"),
        func.count().label("count"),
    ).filter(
        EntityStateRuntimeModel.organization_id == organization_id,
        EntityStateRuntimeModel.current_state.isnot(None),
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        query = query.filter(
            _workflow_family_filter(
                EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
            )
        )
    query = _apply_global_entity_filter(query, EntityStateRuntimeModel.entity_id, filters)
    # Optional state whitelist — empty/absent plots every state.
    selected_states = filters.get("states")
    if isinstance(selected_states, list) and selected_states:
        query = query.filter(
            EntityStateRuntimeModel.current_state.in_([str(s) for s in selected_states])
        )
    since = _range_since(filters)
    if since:
        query = query.filter(EntityStateRuntimeModel.state_entered_at >= since)
    until = _range_until(filters)
    if until:
        query = query.filter(EntityStateRuntimeModel.state_entered_at < until)
    rows = (
        query.group_by(bucket, EntityStateRuntimeModel.current_state)
        .order_by(bucket.asc())
        .all()
    )

    states = sorted({state for _, state, _ in rows if state})
    by_bucket: dict[str, dict[str, int]] = {}
    for bucket_dt, state, count in rows:
        label = bucket_dt.date().isoformat() if bucket_dt else ""
        by_bucket.setdefault(label, {})[state] = int(count)
    points = [
        {"label": label, **{s: counts.get(s, 0) for s in states}}
        for label, counts in by_bucket.items()
    ]
    series = [{"key": s, "label": s.replace("_", " ").title()} for s in states]
    return {"kind": "multiseries", "points": points, "series": series}


_METRIC_FNS: dict[str, Callable[[Session, str, dict[str, Any]], dict[str, Any]]] = {
    "pipeline.by_state": _pipeline_by_state,
    "pipeline.funnel": _pipeline_funnel,
    "entities.count": _entities_count,
    "entities.by_type": _entities_by_type,
    "sla.breaches": _sla_breaches,
    "sla.compliance": _sla_compliance,
    "events.recent": _events_recent,
    "events.by_type": _events_by_type,
    "events.over_time": _events_over_time,
    "transitions.over_time": _transitions_over_time,
    "instances.list": _instances_list,
    "incidents.trend": _incidents_trend,
    "entities.reached_state": _entities_reached_state,
    "entities.reached_state_list": _entities_reached_state_list,
    "entities.in_state": _entities_in_state,
    "entities.by_field": _entities_by_field,
    "transitions.by_state": _transitions_by_state,
}

METRIC_REGISTRY: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="pipeline.by_state",
        label="Pipeline by State",
        description="Count of workflow instances grouped by their current state.",
        output="series",
        default_visuals=("bar", "pie", "funnel"),
        params=(MetricParam("workflow_id", "Workflow", "string", source="workflows"),),
    ),
    MetricSpec(
        key="pipeline.funnel",
        label="Pipeline Funnel",
        description="Workflow instances by state, ordered as a conversion funnel.",
        output="series",
        default_visuals=("funnel", "bar"),
        params=(MetricParam("workflow_id", "Workflow", "string", source="workflows"),),
    ),
    MetricSpec(
        key="entities.count",
        label="Entity Count",
        description="Total active entities, optionally filtered by entity type.",
        output="scalar",
        default_visuals=("number",),
        params=(
            MetricParam("entity_type_id", "Entity Type", "string", source="entity_types"),
        ),
    ),
    MetricSpec(
        key="entities.by_type",
        label="Entities by Type",
        description="Count of active entities grouped by entity type.",
        output="series",
        default_visuals=("bar", "pie"),
    ),
    MetricSpec(
        key="sla.breaches",
        label="SLA Breaches",
        description="Number of workflow instances past their SLA due time.",
        output="scalar",
        default_visuals=("number",),
        params=(MetricParam("workflow_id", "Workflow", "string", source="workflows"),),
    ),
    MetricSpec(
        key="sla.compliance",
        label="SLA Compliance",
        description="Percentage of SLA-bound instances still within their due time.",
        output="gauge",
        default_visuals=("gauge",),
        params=(MetricParam("workflow_id", "Workflow", "string", source="workflows"),),
    ),
    MetricSpec(
        key="events.recent",
        label="Recent Events",
        description="Most recent entity events from the audit log.",
        output="rows",
        default_visuals=("table",),
        params=(
            MetricParam("event_type", "Event Type", "string", source="event_types"),
            MetricParam("limit", "Row Limit", "number"),
        ),
        fields=EVENTS_RECENT_FIELDS,
    ),
    MetricSpec(
        key="events.activity",
        label="Activity Log",
        description="Recent audit-log events (state changes, enrollments, tasks) as a timeline.",
        output="rows",
        default_visuals=("table",),
        params=(MetricParam("limit", "Show", "number"),),
        fields=ACTIVITY_FIELDS,
    ),
    MetricSpec(
        key="events.by_type",
        label="Events by Type",
        description="Count of audit events grouped by event type (top 20).",
        output="series",
        default_visuals=("bar", "pie"),
    ),
    MetricSpec(
        key="events.over_time",
        label="Events Over Time",
        description="Daily count of audit events over a rolling window.",
        output="series",
        default_visuals=("line", "area", "bar"),
        params=(
            MetricParam("days", "Days", "number"),
            MetricParam("event_type", "Event Type", "string", source="event_types"),
        ),
    ),
    MetricSpec(
        key="transitions.over_time",
        label="Transitions Over Time",
        description=(
            "Daily count of committed state changes. Set a state to chart movement into "
            "just that state, e.g. tickets moved to Done per day."
        ),
        output="series",
        default_visuals=("line", "area", "bar"),
        params=(
            MetricParam("days", "Days", "number"),
            MetricParam("state", "State", "string", source="states"),
            MetricParam("workflow_id", "Workflow", "string", source="workflows"),
        ),
    ),
    MetricSpec(
        key="instances.list",
        label="Workflow Instances",
        description="List of workflow instances filterable by workflow and state.",
        output="rows",
        default_visuals=("table",),
        params=(
            MetricParam("workflow_id", "Workflow", "string", source="workflows"),
            MetricParam("current_state", "Current State", "string", source="states"),
            MetricParam("limit", "Row Limit", "number"),
        ),
        fields=INSTANCES_LIST_FIELDS,
    ),
    MetricSpec(
        key="incidents.trend",
        label="Trend by Week (multi-series)",
        description="Weekly transition counts split into one line per status.",
        output="multiseries",
        default_visuals=("line",),
    ),
    MetricSpec(
        key="entities.reached_state",
        label="Entities Reached State",
        description=(
            "Distinct entities that moved into a chosen state. Honors the date window, so "
            "it answers 'how many moved to X in the last N days'."
        ),
        output="scalar",
        default_visuals=("number",),
        params=(
            MetricParam("state", "State", "string", source="states"),
            MetricParam("workflow_id", "Workflow", "string", source="workflows"),
        ),
    ),
    MetricSpec(
        key="entities.reached_state_list",
        label="Entities That Reached State",
        description=(
            "The entities that moved into a chosen state during the window - the list "
            "behind entities.reached_state. Use this to show which tickets moved, since "
            "the pipeline and table views filter on the state an entity is in now. "
            "Returns at most `limit` rows (50 by default, 200 max) alongside `total`, "
            "the full count: quote `total`, not the number of rows."
        ),
        output="rows",
        default_visuals=("table",),
        params=(
            MetricParam("state", "State", "string", source="states"),
            MetricParam("workflow_id", "Workflow", "string", source="workflows"),
            MetricParam("limit", "Limit", "number"),
        ),
    ),
    MetricSpec(
        key="entities.in_state",
        label="Entities in State",
        description="Count of entity instances currently in a chosen state (e.g. Open, In Progress, Closed).",
        output="scalar",
        default_visuals=("number",),
        params=(
            MetricParam("state", "State", "string", source="states"),
            MetricParam("workflow_id", "Workflow", "string", source="workflows"),
        ),
    ),
    MetricSpec(
        key="entities.by_field",
        label="Count by Form Field",
        description="Count of entity instances grouped by a chosen form field's value (top N, or all).",
        output="series",
        default_visuals=("barh", "bar", "pie"),
        params=(
            MetricParam("field", "Form field", "string", source="entity_fields"),
            MetricParam("limit", "Top N", "number"),
        ),
    ),
    MetricSpec(
        key="transitions.by_state",
        label="Trend by State (multi-line)",
        description="Instances entering each state over time, one line per state. Custom timeline (day/week/month).",
        output="multiseries",
        default_visuals=("line",),
        params=(
            MetricParam("bucket", "Timeline", "string"),
            MetricParam("workflow_id", "Workflow", "string", source="workflows"),
        ),
    ),
)


def execute_metric(
    db: Session,
    organization_id: str,
    metric_key: str,
    filters: dict[str, Any] | None,
    field_policy_resolver: Callable[[str], tuple[list[str] | None, list[str]]] | None = None,
) -> dict[str, Any]:
    """Run a metric query and return its rendered payload.

    `field_policy_resolver` is only meaningful to `instances.list`, the one metric
    that reads raw entity `data` fields — every other metric ignores it.
    """
    fn = _METRIC_FNS.get(metric_key)
    if fn is None:
        raise KeyError(f"Unknown metric: {metric_key}")
    if metric_key == "instances.list":
        return _instances_list(db, organization_id, filters or {}, field_policy_resolver=field_policy_resolver)
    return fn(db, organization_id, filters or {})


def filter_options(
    db: Session, organization_id: str, workflow_id: str | None = None
) -> dict[str, list[dict[str, str]]]:
    """Org-scoped option lists that populate the builder's filter dropdowns.

    Keys match MetricParam.source values: "workflows", "entity_types",
    "states", "event_types". Each option is {"value", "label"}.
    """
    workflows = (
        db.query(
            WorkflowStateMachineModel.id,
            WorkflowStateMachineModel.machine_name,
            WorkflowStateMachineModel.definition_json,
        )
        .filter(
            WorkflowStateMachineModel.organization_id == organization_id,
            WorkflowStateMachineModel.archived_at.is_(None),
            # One option per workflow, carrying the active version's row id.
            # Listing every version bloated the picker, and metrics expand the id
            # to the whole family anyway (see `_workflow_family_filter`).
            WorkflowStateMachineModel.is_active.is_(True),
        )
        .order_by(WorkflowStateMachineModel.machine_name.asc())
        .all()
    )

    # Scoped to one workflow's own entity type when given a workflow maps to
    # exactly one entity type (see resolve_workflow_entity_type), so "columns
    # to show" / entity type pickers must not leak a sibling workflow's entity
    # type or fields
    scoped_entity_type_id = (
        resolve_workflow_entity_type(db, organization_id, workflow_id) if workflow_id else None
    )

    entity_types_query = db.query(EntityTypeModel.entity_type_id, EntityTypeModel.name).filter(
        EntityTypeModel.organization_id == organization_id,
        EntityTypeModel.archived_at.is_(None),
    )
    if scoped_entity_type_id:
        entity_types_query = entity_types_query.filter(
            EntityTypeModel.entity_type_id == scoped_entity_type_id
        )
    entity_types = entity_types_query.order_by(EntityTypeModel.name.asc()).all()

    state_names: set[str]
    if workflow_id:
        # Scoped to one workflow's family: states its entities currently occupy...
        scoped_states = (
            db.query(EntityStateRuntimeModel.current_state)
            .filter(
                EntityStateRuntimeModel.organization_id == organization_id,
                _workflow_family_filter(
                    EntityStateRuntimeModel.workflow_id, organization_id, workflow_id
                ),
            )
            .distinct()
            .all()
        )
        state_names = {s for (s,) in scoped_states if s}
        # ...unioned with every state DECLARED in the active definition, so
        # states no entity has reached yet (e.g. MID/END) still appear.
        state_names.update(_active_workflow_state_order(db, organization_id, workflow_id))
    else:
        states = (
            db.query(EntityStateRuntimeModel.current_state)
            .filter(EntityStateRuntimeModel.organization_id == organization_id)
            .distinct()
            .order_by(EntityStateRuntimeModel.current_state.asc())
            .all()
        )
        # Union runtime occupancy with the states DECLARED in active workflow
        # definitions, so states no entity has reached yet (e.g. MID/END) still
        # appear in the picker.
        state_names = {s for (s,) in states if s}
        definitions = (
            db.query(WorkflowStateMachineModel.definition_json)
            .filter(
                WorkflowStateMachineModel.organization_id == organization_id,
                WorkflowStateMachineModel.archived_at.is_(None),
            )
            .all()
        )
        for (definition_json,) in definitions:
            try:
                definition = (
                    json.loads(definition_json)
                    if isinstance(definition_json, str)
                    else definition_json
                )
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Malformed definition_json among org %s's active workflows, skipping it for the state picker: %s",
                    organization_id,
                    exc,
                    extra={"organization_id": organization_id},
                )
                continue
            if not isinstance(definition, dict):
                continue
            for state_def in definition.get("states") or []:
                if isinstance(state_def, dict) and state_def.get("name"):
                    state_names.add(str(state_def["name"]))

    event_types = (
        db.query(EntityEventAuditModel.event_type)
        .filter(EntityEventAuditModel.organization_id == organization_id)
        .distinct()
        .order_by(EntityEventAuditModel.event_type.asc())
        .all()
    )

    workflow_options = []
    for wf_id, machine_name, definition_json in workflows:
        try:
            definition = (
                json.loads(definition_json)
                if isinstance(definition_json, str)
                else definition_json
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Malformed definition_json for workflow %s, falling back to machine_name: %s",
                wf_id,
                exc,
                extra={"organization_id": organization_id, "workflow_id": wf_id},
            )
            definition = None
        name = (definition or {}).get("name") or machine_name
        # No version suffix: the value is the active version's row id, but metrics
        # expand it to the whole family, so the option means "this workflow".
        workflow_options.append({"value": wf_id, "label": name})

    return {
        "workflows": workflow_options,
        "entity_types": [
            {"value": et_id, "label": name} for et_id, name in entity_types
        ],
        "states": [
            {"value": s, "label": s} for s in sorted(state_names)
        ],
        "event_types": [
            {"value": et, "label": et} for (et,) in event_types if et
        ],
        "entity_fields": [
            {"value": key, "label": label}
            for key, label in entity_data_fields(db, organization_id, entity_type=scoped_entity_type_id)
        ],
    }

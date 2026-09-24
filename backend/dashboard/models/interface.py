"""Domain constants and shared internal contracts for dashboard query sources.

Moved out of `dashboard/manager.py` per fiesta convention — hardcoded domain
values belong here, not in the manager. `APPLICATION_PIPELINE_JOINS` and
`FALLBACK_FIELD_ENTITY_TYPES` are declared together because the latter is
derived from the former (see its own docstring below) — splitting them across
files would invert that dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.data_model import ExtendedStrEnum

# Discriminator on a widget result the dashboard could not compute. Shared so
# the producer (dashboard.manager) and the readers cannot drift apart: a reader
# that misses a rename silently stops noticing failed widgets.
WIDGET_RESULT_KIND_ERROR = "error"


@dataclass(frozen=True)
class QueryFieldSpec:
    key: str
    label: str
    field_type: str
    aggregatable: bool = False
    groupable: bool = True
    filterable: bool = True


@dataclass(frozen=True)
class QueryJoinSpec:
    alias: str
    label: str
    description: str
    fields: tuple[QueryFieldSpec, ...]


@dataclass(frozen=True)
class QuerySourceSpec:
    id: str
    label: str
    description: str
    fields: tuple[QueryFieldSpec, ...]
    joins: tuple[QueryJoinSpec, ...] = ()


class FallbackJoinAlias(ExtendedStrEnum):
    """Entity types joined into the `application_pipeline` source, by join alias."""

    CANDIDATE = "candidate"
    JOB = "job"


class ProjectionFixedColumn(ExtendedStrEnum):
    """Projection columns with no org-configurable field permission.

    Fixed workflow-runtime columns — always visible, never checked against a
    role's field permissions.
    """

    ENTITY_ID = "entity_id"
    CURRENT_STATE = "current_state"
    SLA_RISK = "sla_risk"
    MACHINE_NAME = "machine_name"
    MACHINE_VERSION = "machine_version"
    STATE_ENTERED_AT = "state_entered_at"
    SLA_DUE_AT = "sla_due_at"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class HeatmapFixedColumn(ExtendedStrEnum):
    """Heatmap columns with no org-configurable field permission.

    Aggregated, fixed columns — always visible, never checked against a
    role's field permissions.
    """

    STATE = "state"
    APPLICATION_COUNT = "application_count"
    BREACHED_COUNT = "breached_count"
    AVG_TIME_IN_STATE_SECONDS = "avg_time_in_state_seconds"
    UPDATED_AT = "updated_at"


APPLICATION_PIPELINE_FIELDS = (
    QueryFieldSpec("entity_id", "Application ID", "string"),
    QueryFieldSpec("current_state", "Current State", "string"),
    QueryFieldSpec("sla_risk", "SLA Risk", "string"),
    QueryFieldSpec("machine_name", "Machine Name", "string"),
    QueryFieldSpec("machine_version", "Machine Version", "number", aggregatable=True),
    QueryFieldSpec("state_entered_at", "State Entered At", "date"),
    QueryFieldSpec("sla_due_at", "SLA Due At", "date"),
    QueryFieldSpec("candidate_id", "Candidate ID", "string"),
    QueryFieldSpec("candidate_name", "Candidate Name", "string"),
    QueryFieldSpec("candidate_email", "Candidate Email", "string"),
    QueryFieldSpec("job_id", "Job ID", "string"),
    QueryFieldSpec("job_title", "Job Title", "string"),
    QueryFieldSpec("job_department", "Job Department", "string"),
    QueryFieldSpec("created_at", "Created At", "date"),
    QueryFieldSpec("updated_at", "Updated At", "date"),
)

APPLICATION_PIPELINE_JOINS = (
    QueryJoinSpec(
        alias=FallbackJoinAlias.CANDIDATE,
        label="Candidate",
        description="Join the related candidate entity by candidate_id.",
        fields=(
            QueryFieldSpec("candidate.name", "Candidate Name", "string"),
            QueryFieldSpec("candidate.email", "Candidate Email", "string"),
            QueryFieldSpec("candidate.phone", "Candidate Phone", "string"),
            QueryFieldSpec("candidate.source", "Candidate Source", "string"),
            QueryFieldSpec("candidate.current_company", "Candidate Current Company", "string"),
        ),
    ),
    QueryJoinSpec(
        alias=FallbackJoinAlias.JOB,
        label="Job",
        description="Join the related job entity by job_id.",
        fields=(
            QueryFieldSpec("job.title", "Job Title", "string"),
            QueryFieldSpec("job.department", "Job Department", "string"),
            QueryFieldSpec("job.location", "Job Location", "string"),
            QueryFieldSpec("job.status", "Job Status", "string"),
            QueryFieldSpec("job.hiring_manager", "Hiring Manager", "string"),
        ),
    ),
)

HEATMAP_FIELDS = (
    QueryFieldSpec("job_id", "Job ID", "string"),
    QueryFieldSpec("state", "State", "string"),
    QueryFieldSpec("application_count", "Application Count", "number", aggregatable=True),
    QueryFieldSpec("breached_count", "Breached Count", "number", aggregatable=True),
    QueryFieldSpec("avg_time_in_state_seconds", "Average Time In State (Seconds)", "number", aggregatable=True),
    QueryFieldSpec("updated_at", "Updated At", "date"),
)

SOURCE_CATALOG: dict[str, QuerySourceSpec] = {
    "application_pipeline": QuerySourceSpec(
        id="application_pipeline",
        label="Application Pipeline",
        description="Application workflow rows with current state, SLA risk, candidate, and job context.",
        fields=APPLICATION_PIPELINE_FIELDS,
        joins=APPLICATION_PIPELINE_JOINS,
    ),
    "heatmap": QuerySourceSpec(
        id="heatmap",
        label="Heatmap",
        description="Aggregated state-level heatmap rows grouped by job and state.",
        fields=HEATMAP_FIELDS,
    ),
}


# Field -> (owning entity type name, real field-permission name) for the fixed
# keys `preview_projection_query`'s own `base_field_map` resolves unconditionally
# for *every* projection view, not just the SOURCE_CATALOG fallback
# (`candidate_id`/`candidate_email`/`job_title`/etc. are hardcoded there
# regardless of a given view's declared `source_fields` — see Finding 1 in
# design_docs/tony_dashboard_field_rbac_fix.md) — so these must always be
# checked, real `ViewDefinition` row or not. A real view's own `source_fields`/
# `denormalized_fields` are layered on top of this base map, not instead of it
# (see `dashboard/manager.py`'s `_field_entity_type_map`). Fixed workflow-runtime
# columns (entity_id, current_state, timestamps, etc.) are deliberately absent —
# they carry no org-configurable field permission and are always visible, exactly
# like `entities/manager.py` never gates its own fixed columns, only `data` fields.
#
# The query field key (e.g. `candidate_email`) is a denormalized alias, not the
# name a role's field permission is actually configured under — permissions are
# configured against the entity's own schema field name (`email`), which is
# `candidate_email` with the `candidate_`/`job_` prefix stripped, or the part
# after the dot for a join field (`candidate.email` -> `email`). Confirmed live:
# checking the alias itself against `get_visible_fields` silently denied fields
# a role could legitimately see, since no permission is ever configured under
# the literal alias name.
FALLBACK_FIELD_ENTITY_TYPES: dict[str, tuple[str, str]] = {
    "candidate_id": (FallbackJoinAlias.CANDIDATE, "id"),
    "candidate_name": (FallbackJoinAlias.CANDIDATE, "name"),
    "candidate_email": (FallbackJoinAlias.CANDIDATE, "email"),
    "job_id": (FallbackJoinAlias.JOB, "id"),
    "job_title": (FallbackJoinAlias.JOB, "title"),
    "job_department": (FallbackJoinAlias.JOB, "department"),
    # Join fields derive their owner from the join alias, and their real field
    # name from the part after the dot — keeps this map from drifting out of
    # sync with APPLICATION_PIPELINE_JOINS.
    **{
        field.key: (join.alias, field.key.split(".", 1)[1])
        for join in APPLICATION_PIPELINE_JOINS
        for field in join.fields
    },
}

# Columns with no org-configurable field permission — always visible, never
# checked. Anything else requested from these sources that isn't in the maps
# above is unrecognized and denied by default (see
# `dashboard/manager.py`'s `_resolve_source_field_policy`).
PROJECTION_FIXED_COLUMNS: frozenset[str] = frozenset(ProjectionFixedColumn.list())
HEATMAP_FIXED_COLUMNS: frozenset[str] = frozenset(HeatmapFixedColumn.list())

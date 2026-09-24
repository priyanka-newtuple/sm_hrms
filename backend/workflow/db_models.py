"""Compact persistence adapters for workflow."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
    case,
    cast,
    literal,
    or_,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from actions.db_models import ActionDefinitionModel
from background_jobs.db_models import ActionRunModel
from background_jobs.models.interface import ActionRunIdempotencyKey, ActionRunStatus
from common.condition_sql import membership_expression
from common.configuration import get_configuration
from common.logger import logger
from common.protocols import EntityConditionSpec
from database.manager import Base
from exceptions import ConflictError, PersistenceError, ValidationError
from entities.db_models import EntityRecordModel, EntityStateRuntimeModel, EntityTypeModel
from field_library.db_models import FieldTypeCatalogueModel
from workflow.models import (
    DefinitionReport,
    IssueBuckets,
    MemoryDefinitionReport,
    MemoryStateMachine,
    ReportType,
    StateMachineCreateRequest,
    StateMachineDefinition,
    StateMachineRecord,
    ValidationIssue,
    WorkflowBoardDisplayFieldsRecord,
    WorkflowDraftRecord,
    WorkflowService,
    WorkflowServiceWithWorkflows,
    WorkflowServiceWorkflow,
)
from workflow.models.interface import (
    SLA_SIGNAL_ACTION_KIND,
    NUMERIC_TEXT_PATTERN,
    CurrencyValueKey,
    EnrollmentAggregateFilters,
    FieldNumericAggregate,
    JsonbType,
    TransitionAttemptRecord,
)

# Services are a short lookup list, so the page default matches the method
# library's (method_library/db_models.py) rather than inventing a new one.
SERVICE_PAGE_LIMIT = 50

_CANVAS_METADATA_UNSET = object()


@dataclass(frozen=True)
class WorkflowEnrollmentSummaryRow:
    state_id: str
    organization_id: str
    entity_id: str
    entity_type_id: str
    entity_type: str
    entity_data: dict[str, object]
    owner_id: str | None
    assignee_id: str | None
    due_date: object | None
    entity_created_at: datetime | None
    entity_updated_at: datetime | None
    archived_at: datetime | None
    workflow_id: str
    machine_name: str
    machine_display_name: str
    machine_version: int
    machine_definition: StateMachineDefinition
    current_state: str
    state_version: int
    enrollment_created_at: datetime | None
    state_entered_at: datetime | None
    last_transition_at: datetime | None
    sla_due_at: datetime | None


def _definitions_schema() -> str:
    """Return the definitions schema name derived from the app schema at call time."""
    return f"{get_configuration().postgresql_configuration.app_schema}_definitions"


def _audit_schema() -> str:
    """Return the audit schema name derived from the app schema at call time."""
    return f"{get_configuration().postgresql_configuration.app_schema}_audit"


class TransitionAttemptModel(Base):
    """Per-transition outcome row. Lives in the `_audit` schema."""

    __tablename__ = "transition_attempts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_transition_attempts_org_idempotency_key",
        ),
        Index("ix_audit_transition_attempts_entity_occurred", "entity_id", "occurred_at"),
        Index("ix_audit_transition_attempts_workflow_id", "workflow_id"),
        Index("ix_audit_transition_attempts_status", "status"),
        Index("ix_audit_transition_attempts_organization_id", "organization_id"),
        {"schema": _audit_schema()},
    )

    transition_attempt_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False)
    entity_id = Column(String(36), nullable=False)
    workflow_id = Column(String(36), nullable=False)
    from_state = Column(String(128), nullable=True)
    to_state = Column(String(128), nullable=True)
    trigger = Column(String(128), nullable=True)
    actor_id = Column(String(128), nullable=True)
    actor_name = Column(String(255), nullable=True)
    actor_role = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False)
    failure_code = Column(String(128), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    inputs = Column(JSONB, nullable=True)
    outputs = Column(JSONB, nullable=True)
    guard_evaluations = Column(JSONB, nullable=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UnknownWorkflowServiceError(Exception):
    """The requested service does not exist in this organization.

    Separate from PersistenceError so the manager returns a 4xx, not a 500.
    Mirrors UnknownMethodCategoryError in method_library/db_models.py.
    """


class DuplicateWorkflowServiceNameError(Exception):
    """This organization already has a service by that name."""


class WorkflowServiceInUseError(Exception):
    """A workflow is still filed under this service, so it cannot be deleted."""


class WorkflowStateMachineModel(Base):
    """SQLAlchemy workflow definition store."""

    __tablename__ = "workflow_state_machines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    machine_key = Column(String(128), nullable=False, index=True)
    machine_name = Column(String(128), nullable=False, index=True)
    description = Column(Text, nullable=True)
    entity_type = Column(String(128), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    definition_json = Column(Text, nullable=False)
    canvas_metadata_json = Column(JSON, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Nullable, optional grouping onto workflow_services. Lives on the
    # definition itself (StateMachineDefinition.service_id) rather than being
    # re-captured per publish, mirroring how description/entity_type work.
    service_id = Column(String(36), nullable=True)
    __table_args__ = (
        Index(
            "uq_workflow_machine_version_active",
            "organization_id", "machine_name", "version",
            unique=True,
            postgresql_where=(text("archived_at IS NULL")),
        ),
        Index("ix_workflow_machine_active", "organization_id", "machine_name", "is_active"),
        Index("ix_workflow_machine_archived_at", "organization_id", "archived_at"),
        Index("ix_workflow_state_machines_service_id", "service_id"),
        # Unqualified on the workflow_state_machines side, same reasoning as
        # workflow_method_pins' FK back to it: this table has no explicit
        # schema and resolves through the connection's search_path.
        ForeignKeyConstraint(
            ["service_id", "organization_id"],
            [
                f"{_definitions_schema()}.workflow_services.id",
                f"{_definitions_schema()}.workflow_services.organization_id",
            ],
            name="fk_workflow_state_machines_service",
        ),
    )


class WorkflowMethodPinModel(Base):
    """One method version pinned to one state of one published workflow.

    Lives beside the method library in the definitions schema, because a pin is
    workflow configuration rather than runtime data.

    `workflow_state_machine_id` points at a specific published row, and publishing
    always writes a new row, so each published version keeps the pins it was built
    with. That is what makes the pin history readable after a republish.

    The method foreign keys carry no ON DELETE clause on purpose: the database
    refusing to delete a pinned method is what backs
    `MethodLibraryModelService.delete_method`'s guard.
    """

    __tablename__ = "workflow_method_pins"
    __table_args__ = (
        Index(
            "ix_workflow_method_pins_machine_state",
            "workflow_state_machine_id",
            "state_key",
        ),
        # One pin per method per state, matching State.method_refs' own rule.
        UniqueConstraint(
            "workflow_state_machine_id",
            "state_key",
            "method_id",
            name="uq_workflow_method_pins_machine_state_method",
        ),
        Index("ix_workflow_method_pins_organization_id", "organization_id"),
        Index("ix_workflow_method_pins_method_version_id", "method_version_id"),
        # Unqualified on purpose: workflow_state_machines has no explicit schema
        # and resolves through the connection's search_path.
        ForeignKeyConstraint(
            ["workflow_state_machine_id"],
            ["workflow_state_machines.id"],
            name="fk_workflow_method_pins_state_machine",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["method_id", "organization_id"],
            [
                f"{_definitions_schema()}.method_library_methods.method_id",
                f"{_definitions_schema()}.method_library_methods.organization_id",
            ],
            name="fk_workflow_method_pins_method",
        ),
        ForeignKeyConstraint(
            ["method_version_id", "organization_id"],
            [
                f"{_definitions_schema()}.method_library_method_versions.version_id",
                f"{_definitions_schema()}.method_library_method_versions.organization_id",
            ],
            name="fk_workflow_method_pins_method_version",
        ),
        {"schema": _definitions_schema()},
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False)
    workflow_state_machine_id = Column(String(36), nullable=False)
    # The state's `name`, which is how a definition keys its states.
    state_key = Column(String(128), nullable=False)
    method_id = Column(String(36), nullable=False)
    method_version_id = Column(String(36), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)



class WorkflowServiceModel(Base):
    """A grouping for workflows, unique by name within an organization.

    Mirrors MethodLibraryCategoryModel (method_library/db_models.py) exactly.
    Uniqueness is case insensitive, so "Cell Supply" and "cell supply" are the
    same service to one organization and unrelated across two.
    """

    __tablename__ = "workflow_services"
    __table_args__ = (
        Index(
            "uq_workflow_services_org_name",
            "organization_id",
            text("lower(name)"),
            unique=True,
        ),
        Index("ix_workflow_services_organization_id", "organization_id"),
        # Target of the tenant-safe composite FK from workflow_state_machines.
        UniqueConstraint("organization_id", "id", name="uq_workflow_services_org_id"),
        {"schema": _definitions_schema()},
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False)
    name = Column(String(256), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

class WorkflowBoardDisplayConfigModel(Base):
    """Up to 3 extra entity fields shown on one workflow's Kanban cards.

    One row per `(organization_id, machine_name)` — independent of the
    versioned `workflow_state_machines` rows.
    """

    __tablename__ = "workflow_board_display_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False)
    machine_name = Column(String(128), nullable=False, index=True)
    fields_json = Column(JSONB, nullable=False, default=list)
    updated_by = Column(String(36), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (
        Index(
            "uq_workflow_board_display_config_org_machine",
            "organization_id", "machine_name",
            unique=True,
        ),
    )


class WorkflowDefinitionReportModel(Base):
    """SQLAlchemy unified definition report store."""

    # `created_at` is a server default, so without this SQLAlchemy expires the instance on
    # commit and re-SELECTs the row to read it back. eager_defaults makes the INSERT use
    # RETURNING and fetch it in the same round trip. The timestamp still comes from the
    # database clock; only the extra query goes away.
    __mapper_args__: ClassVar[dict[str, bool]] = {"eager_defaults": True}

    __tablename__ = "workflow_definition_reports"

    report_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False, index=True)
    report_type = Column(String(32), nullable=False, index=True)
    machine_name = Column(String(128), nullable=False, index=True)
    version = Column(Integer, nullable=True)
    base_version = Column(Integer, nullable=True)
    candidate_version = Column(Integer, nullable=True)
    valid = Column(Boolean, nullable=True)
    checked_entities = Column(Integer, nullable=True)
    compatible_entities = Column(Integer, nullable=True)
    incompatible_entities = Column(Integer, nullable=True)
    issues_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WorkflowModelService:
    """Compact persistence service for workflow."""

    def __init__(self, database_service_manager) -> None:
        """Bind to the shared Postgres pool, or fall back to in-memory mode.

        When `database_service_manager` is None or doesn't expose a
        postgres_db_service, the service uses in-process dicts (used by
        unit tests that don't want a real DB)."""
        self.database_manager = database_service_manager
        self.current_db = (
            self.database_manager.postgres_db_service()
            if self.database_manager and hasattr(self.database_manager, "postgres_db_service")
            else None
        )
        self._machines: dict[tuple[str, str, int], MemoryStateMachine] = {}
        self._reports: dict[str, MemoryDefinitionReport] = {}
        self._board_display_configs: dict[tuple[str, str], WorkflowBoardDisplayFieldsRecord] = {}
        self.action_runs_enqueue_fn: Callable[[str], None] | None = None

    def _use_memory(self) -> bool:
        """Return whether memory mode is active."""
        return self.current_db is None

    def _session(self) -> Session:
        """Create a database session."""
        if self.current_db is None:
            raise PersistenceError("Database service manager unavailable")
        return self.current_db.get_db_session()

    @contextmanager
    def _db_session(self):
        """Yield a session and guarantee it is closed on exit."""
        session = self._session()
        try:
            yield session
        finally:
            session.close()

    @staticmethod
    def read_condition_expression(condition: EntityConditionSpec):
        """SQL form of one entity read condition, or None if it can't be translated.

        Mirrors `common.protocols.resolve_and_compare` exactly, including its
        two guards: a missing key and an empty string both count as no-match,
        for every operator.

        The one place the two representations differ is stringification —
        Python compares `str(value)`, so a JSON boolean reads as `"True"`,
        where Postgres' `->>` gives `"true"`. `initcap` reconciles them.
        Containers still differ (`str(['a'])` vs `["a"]`), but only in the
        permissive direction, which `apply_read_policy_to_data` catches: the
        Python check runs again on every row that reaches the response, so
        this predicate can narrow the scan but can never widen what an actor
        is allowed to see.
        """
        if condition.conditions is not None:
            if not condition.conditions or condition.operator not in {"AND", "OR"}:
                return None
            children = [
                WorkflowModelService.read_condition_expression(child)
                for child in condition.conditions
            ]
            if any(child is None for child in children):
                return None
            return and_(*children) if condition.operator == "AND" else or_(*children)
        raw = EntityRecordModel.data[condition.entity_field].astext
        value = case(
            (
                func.jsonb_typeof(EntityRecordModel.data[condition.entity_field]) == "boolean",
                func.initcap(raw),
            ),
            else_=raw,
        )
        present = and_(raw.isnot(None), raw != "")
        if condition.operator == "==":
            return and_(present, value == condition.condition_value)
        if condition.operator == "!=":
            return and_(present, value != condition.condition_value)
        if condition.operator in {"in", "not_in"}:
            return membership_expression(EntityRecordModel.data[condition.entity_field], condition)
        return None

    def _enrollment_summary_base_query(
        self,
        session: Session,
        *,
        organization_id: str,
        machine_name: str | None = None,
        machine_names: set[str] | None = None,
        current_state: str | None = None,
        exclude_states: set[str] | None = None,
        entity_type_name: str | None = None,
        entity_type_id: str | None = None,
        entity_type_ids: set[str] | None = None,
        include_archived: bool = False,
        entity_ids: set[str] | None = None,
        assignee_ids: set[str] | None = None,
        include_unassigned: bool = False,
        search: str | None = None,
        field_filters: dict[str, str | list[str]] | None = None,
        searchable_fields_by_type: dict[str, set[str] | None] | None = None,
        read_conditions_by_type: dict[str, list[EntityConditionSpec]] | None = None,
        identifier: str | None = None,
    ):
        """Shared filter chain for list/count/facet enrollment-summary queries.

        Returns None when a filter set makes the result provably empty (e.g. an
        empty `machine_names`/`entity_ids`/`entity_type_ids` set) — callers
        short-circuit on that."""
        query = (
            session.query(EntityStateRuntimeModel, EntityRecordModel, WorkflowStateMachineModel, EntityTypeModel)
            .join(
                EntityRecordModel,
                (EntityRecordModel.organization_id == EntityStateRuntimeModel.organization_id)
                & (EntityRecordModel.entity_id == EntityStateRuntimeModel.entity_id),
            )
            .join(
                WorkflowStateMachineModel,
                (WorkflowStateMachineModel.organization_id == EntityStateRuntimeModel.organization_id)
                & (WorkflowStateMachineModel.id == EntityStateRuntimeModel.workflow_id),
            )
            .join(
                EntityTypeModel,
                (EntityTypeModel.organization_id == EntityRecordModel.organization_id)
                & (EntityTypeModel.entity_type_id == EntityRecordModel.entity_type_id),
            )
            .filter(EntityStateRuntimeModel.organization_id == organization_id)
        )
        if not include_archived:
            query = query.filter(EntityRecordModel.archived_at.is_(None))
        if machine_name:
            query = query.filter(WorkflowStateMachineModel.machine_name == machine_name)
        elif machine_names is not None:
            if not machine_names:
                return None
            query = query.filter(WorkflowStateMachineModel.machine_name.in_(machine_names))
        if current_state:
            query = query.filter(EntityStateRuntimeModel.current_state == current_state)
        if exclude_states:
            query = query.filter(EntityStateRuntimeModel.current_state.notin_(exclude_states))
        if entity_type_name:
            query = query.filter(EntityTypeModel.name == entity_type_name)
        elif entity_type_id:
            query = query.filter(EntityRecordModel.entity_type_id == entity_type_id)
        if entity_type_ids is not None:
            if not entity_type_ids:
                return None
            query = query.filter(EntityRecordModel.entity_type_id.in_(entity_type_ids))
        for type_id, conditions in (read_conditions_by_type or {}).items():
            expressions = [
                expression
                for expression in (self.read_condition_expression(c) for c in conditions)
                if expression is not None
            ]
            if not expressions:
                continue
            # Scoped to its own entity type: a conditional view permission on
            # one type says nothing about rows of another, so rows of every
            # other readable type pass this clause untouched.
            query = query.filter(
                or_(EntityRecordModel.entity_type_id != type_id, or_(*expressions))
            )
        if entity_ids is not None:
            if not entity_ids:
                return None
            query = query.filter(EntityRecordModel.entity_id.in_(entity_ids))
        if assignee_ids or include_unassigned:
            clauses = []
            if assignee_ids:
                clauses.append(EntityRecordModel.assignee_id.in_(assignee_ids))
            if include_unassigned:
                clauses.append(EntityRecordModel.assignee_id.is_(None))
            query = query.filter(or_(*clauses))
        if identifier:
            query = query.filter(EntityRecordModel.data["identifier"].astext == identifier)
        for field, expected in (field_filters or {}).items():
            expected_values = expected if isinstance(expected, list) else [expected]
            if not expected_values:
                return None
            field_matches = or_(
                *(
                    (EntityRecordModel.data[field].astext == value)
                    | (EntityRecordModel.data[field].contains(json.dumps(value)))
                    for value in expected_values
                )
            )
            if searchable_fields_by_type is None:
                query = query.filter(field_matches)
                continue
            clauses = []
            for type_id, visible_fields in searchable_fields_by_type.items():
                if visible_fields is None or field in visible_fields:
                    clauses.append(
                        (EntityRecordModel.entity_type_id == type_id) & field_matches
                    )
            if not clauses:
                return None
            query = query.filter(or_(*clauses))
        if search and search.strip():
            escaped = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            # `search` runs in SQL, ahead of the read policy that masks and
            # drops fields when the rows are projected — so matching the whole
            # JSONB blob would let an actor confirm the contents of fields
            # their role cannot view. Match only the keys each entity type's
            # policy leaves readable; `None` means "no field restriction".
            if searchable_fields_by_type is None:
                query = query.filter(
                    cast(EntityRecordModel.data, Text).ilike(pattern, escape="\\")
                )
            else:
                clauses = []
                for type_id, fields in searchable_fields_by_type.items():
                    if fields is None:
                        match = cast(EntityRecordModel.data, Text).ilike(pattern, escape="\\")
                    elif fields:
                        match = or_(
                            *[
                                EntityRecordModel.data[field].astext.ilike(pattern, escape="\\")
                                for field in sorted(fields)
                            ]
                        )
                    else:
                        continue
                    clauses.append((EntityRecordModel.entity_type_id == type_id) & match)
                if not clauses:
                    return None
                query = query.filter(or_(*clauses))
        return query

    @staticmethod
    def _enrollment_sort_expression(sort_by: str):
        if sort_by == "identifier":
            return EntityRecordModel.data["identifier"].astext
        if sort_by == "display_name":
            return func.coalesce(
                EntityRecordModel.data["identifier"].astext,
                EntityRecordModel.data["name"].astext,
                EntityRecordModel.data["title"].astext,
                EntityRecordModel.data["full_name"].astext,
            )
        if sort_by == "state":
            return EntityStateRuntimeModel.current_state
        if sort_by == "created":
            return EntityRecordModel.created_at
        if sort_by == "due_date":
            return EntityRecordModel.due_date
        raise ValueError(f"unsupported sort_by '{sort_by}'")

    def list_enrollment_summary_rows(
        self,
        *,
        organization_id: str,
        machine_name: str | None = None,
        machine_names: set[str] | None = None,
        current_state: str | None = None,
        exclude_states: set[str] | None = None,
        entity_type_name: str | None = None,
        entity_type_id: str | None = None,
        entity_type_ids: set[str] | None = None,
        include_archived: bool = False,
        entity_ids: set[str] | None = None,
        assignee_ids: set[str] | None = None,
        include_unassigned: bool = False,
        search: str | None = None,
        field_filters: dict[str, str | list[str]] | None = None,
        searchable_fields_by_type: dict[str, set[str] | None] | None = None,
        read_conditions_by_type: dict[str, list[EntityConditionSpec]] | None = None,
        identifier: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        offset: int | None = None,
        limit: int = 51,
    ) -> list[WorkflowEnrollmentSummaryRow]:
        """Return one set-based page of enrollment + entity + workflow rows."""
        with self._db_session() as session:
            try:
                query = self._enrollment_summary_base_query(
                    session,
                    organization_id=organization_id,
                    machine_name=machine_name,
                    machine_names=machine_names,
                    current_state=current_state,
                    exclude_states=exclude_states,
                    entity_type_name=entity_type_name,
                    entity_type_id=entity_type_id,
                    entity_type_ids=entity_type_ids,
                    include_archived=include_archived,
                    entity_ids=entity_ids,
                    assignee_ids=assignee_ids,
                    include_unassigned=include_unassigned,
                    search=search,
                    field_filters=field_filters,
                    searchable_fields_by_type=searchable_fields_by_type,
                    read_conditions_by_type=read_conditions_by_type,
                    identifier=identifier,
                )
                if query is None:
                    return []
                if sort_by:
                    sort_expr = self._enrollment_sort_expression(sort_by)
                    query = query.order_by(
                        sort_expr.desc() if sort_dir == "desc" else sort_expr.asc(),
                        EntityStateRuntimeModel.state_id.asc(),
                    )
                else:
                    # Newest arrival in this state first. `state_entered_at`
                    # moves on every transition; `created_at` never does.
                    query = query.order_by(
                        EntityStateRuntimeModel.state_entered_at.desc(),
                        EntityStateRuntimeModel.state_id.desc(),
                    )
                if offset is not None:
                    query = query.offset(max(0, offset))
                rows = query.limit(max(1, limit)).all()
                definition_cache: dict[str, StateMachineDefinition] = {}
                summaries: list[WorkflowEnrollmentSummaryRow] = []
                for state, entity, machine, entity_type in rows:
                    definition = definition_cache.get(machine.id)
                    if definition is None:
                        definition = StateMachineDefinition.model_validate(
                            json.loads(machine.definition_json)
                        )
                        definition_cache[machine.id] = definition
                    summaries.append(
                        WorkflowEnrollmentSummaryRow(
                            state_id=state.state_id,
                            organization_id=state.organization_id,
                            entity_id=entity.entity_id,
                            entity_type_id=entity.entity_type_id,
                            entity_type=entity_type.name,
                            entity_data=dict(entity.data or {}),
                            owner_id=entity.owner_id,
                            assignee_id=entity.assignee_id,
                            due_date=entity.due_date,
                            entity_created_at=entity.created_at,
                            entity_updated_at=entity.updated_at,
                            archived_at=entity.archived_at,
                            workflow_id=state.workflow_id,
                            machine_name=machine.machine_name,
                            machine_display_name=definition.name or machine.machine_name,
                            machine_version=machine.version,
                            machine_definition=definition,
                            current_state=state.current_state,
                            state_version=state.state_version,
                            enrollment_created_at=state.created_at,
                            state_entered_at=state.state_entered_at,
                            last_transition_at=state.last_transition_at,
                            sla_due_at=state.sla_due_at,
                        )
                    )
                return summaries
            except Exception as exc:
                logger.exception("workflow enrollment summary query failed")
                raise PersistenceError(f"Unable to list workflow enrollment summaries: {exc}") from exc

    def enrollment_rows_exist(
        self,
        *,
        organization_id: str,
        machine_name: str | None = None,
        machine_names: set[str] | None = None,
        current_state: str | None = None,
        exclude_states: set[str] | None = None,
        entity_type_name: str | None = None,
        entity_type_id: str | None = None,
        entity_type_ids: set[str] | None = None,
        include_archived: bool = False,
        entity_ids: set[str] | None = None,
        assignee_ids: set[str] | None = None,
        include_unassigned: bool = False,
        search: str | None = None,
        field_filters: dict[str, str | list[str]] | None = None,
        searchable_fields_by_type: dict[str, set[str] | None] | None = None,
        read_conditions_by_type: dict[str, list[EntityConditionSpec]] | None = None,
        identifier: str | None = None,
    ) -> bool:
        """Whether the filter set matches anything at all — one `LIMIT 1` probe.

        Selects a literal rather than the row tuple: callers ask this to decide
        how to run a later query, never to read data.
        """
        with self._db_session() as session:
            try:
                query = self._enrollment_summary_base_query(
                    session,
                    organization_id=organization_id,
                    machine_name=machine_name,
                    machine_names=machine_names,
                    current_state=current_state,
                    exclude_states=exclude_states,
                    entity_type_name=entity_type_name,
                    entity_type_id=entity_type_id,
                    entity_type_ids=entity_type_ids,
                    include_archived=include_archived,
                    entity_ids=entity_ids,
                    assignee_ids=assignee_ids,
                    include_unassigned=include_unassigned,
                    search=search,
                    field_filters=field_filters,
                    searchable_fields_by_type=searchable_fields_by_type,
                    read_conditions_by_type=read_conditions_by_type,
                    identifier=identifier,
                )
                if query is None:
                    return False
                return query.with_entities(literal(1)).limit(1).first() is not None
            except Exception as exc:
                logger.exception("workflow enrollment existence probe failed")
                raise PersistenceError(f"Unable to probe workflow enrollments: {exc}") from exc

    def count_enrollment_rows_by_state(
        self, filters: EnrollmentAggregateFilters
    ) -> dict[str, int]:
        """`current_state` -> row count, as one GROUP BY over the shared filter chain.

        Deliberately takes no `current_state` filter: callers that want a single
        state's total read it out of the returned map, so this one aggregate
        serves both the board's per-column badges and the table's total_count
        instead of a second COUNT round-trip. Counts rows without hydrating them.
        """
        with self._db_session() as session:
            try:
                query = self._enrollment_summary_base_query(session, **asdict(filters))
                if query is None:
                    return {}
                rows = (
                    query.with_entities(
                        EntityStateRuntimeModel.current_state,
                        func.count(),
                    )
                    .group_by(EntityStateRuntimeModel.current_state)
                    .all()
                )
                return dict(rows)
            except Exception as exc:
                logger.exception("workflow enrollment state-count query failed")
                raise PersistenceError(f"Unable to count workflow enrollments by state: {exc}") from exc

    @staticmethod
    def _summable_amount_expression(field: str):
        """Numeric value of `data[field]`, or SQL NULL when it isn't a number.

        Handles both a plain JSON number and a currency object (`{"amount":
        ..., "currency_code": ...}`) through one expression, so the caller
        does not have to know a field's configured type up front.

        The regex guard is what makes the cast safe: entity data is free-form
        JSON, so any row may hold text where a number is expected. Postgres
        evaluates only the matching CASE branch, so a non-numeric value never
        reaches `::numeric` — it yields NULL and `SUM` skips it, which is
        exactly how a genuinely absent value behaves.
        """
        value = EntityRecordModel.data[field]
        raw = case(
            (
                func.jsonb_typeof(value) == JsonbType.OBJECT,
                value[CurrencyValueKey.AMOUNT].astext,
            ),
            else_=value.astext,
        )
        return case((raw.op("~")(NUMERIC_TEXT_PATTERN), cast(raw, Numeric)), else_=None)

    @staticmethod
    def _currency_code_expression(field: str):
        """The currency code carried by `data[field]`, or NULL if it carries none.

        Trimmed, and blank-to-NULL, so a whitespace-only code is not counted as
        a distinct currency here while the scan path discards it — the two must
        agree or mixed-currency detection differs by which path ran.
        """
        value = EntityRecordModel.data[field]
        return case(
            (
                func.jsonb_typeof(value) == JsonbType.OBJECT,
                func.nullif(func.trim(value[CurrencyValueKey.CURRENCY_CODE].astext), ""),
            ),
            else_=None,
        )

    @staticmethod
    def _type_scoped_expression(expression, allowed_entity_type_ids: set[str] | None):
        """Null out `expression` for rows of a type the actor may not read it on.

        A field permission is per entity type, so a mixed-type result set can
        legitimately sum a field for some rows and have to ignore it for
        others. `None` means every type in the result set allows it.
        """
        if allowed_entity_type_ids is None:
            return expression
        return case(
            (EntityRecordModel.entity_type_id.in_(allowed_entity_type_ids), expression),
            else_=None,
        )

    def _sum_columns(self, field: str, allowed_type_ids: set[str] | None):
        """The (summed amount, distinct currency codes) pair selected per field."""
        amount = self._type_scoped_expression(
            self._summable_amount_expression(field), allowed_type_ids
        )
        code = self._type_scoped_expression(
            self._currency_code_expression(field), allowed_type_ids
        )
        return [func.coalesce(func.sum(amount), 0), func.array_agg(code.distinct())]

    def sum_enrollment_fields(
        self,
        filters: EnrollmentAggregateFilters,
        *,
        sum_fields: dict[str, set[str] | None],
        current_state: str | None = None,
    ) -> dict[str, FieldNumericAggregate]:
        """Field -> summed amount across every row the shared filter chain matches.

        `sum_fields` maps each requested field to the entity type ids allowed
        to contribute to it (`None` = all types in the result set), so a field
        the actor's role hides on one type is not summed from that type's rows.

        Unlike `count_enrollment_rows_by_state`, this takes `current_state` and
        returns one grand total per field: the counts have to span every state
        to fill a board's column badges, whereas a total only ever describes
        the rows on screen. Sums without hydrating a row.
        """
        if not sum_fields:
            return {}
        with self._db_session() as session:
            try:
                query = self._enrollment_summary_base_query(
                    session, current_state=current_state, **asdict(filters)
                )
                if query is None:
                    return {}
                ordered_fields = sorted(sum_fields)
                columns = [
                    column
                    for field in ordered_fields
                    for column in self._sum_columns(field, sum_fields[field])
                ]
                row = query.with_entities(*columns).one()
                return {
                    field: FieldNumericAggregate(
                        total=Decimal(row[index * 2] or 0),
                        currency_codes=frozenset(
                            code for code in (row[index * 2 + 1] or []) if code
                        ),
                    )
                    for index, field in enumerate(ordered_fields)
                }
            except Exception as exc:
                logger.exception("workflow enrollment field-sum query failed")
                raise PersistenceError(
                    f"Unable to sum workflow enrollment fields: {exc}"
                ) from exc

    def list_enrollment_summary_identifier_options(
        self,
        *,
        organization_id: str,
        machine_name: str | None = None,
        machine_names: set[str] | None = None,
        current_state: str | None = None,
        exclude_states: set[str] | None = None,
        entity_type_name: str | None = None,
        entity_type_id: str | None = None,
        entity_type_ids: set[str] | None = None,
        include_archived: bool = False,
        entity_ids: set[str] | None = None,
        assignee_ids: set[str] | None = None,
        include_unassigned: bool = False,
        search: str | None = None,
        field_filters: dict[str, str | list[str]] | None = None,
        searchable_fields_by_type: dict[str, set[str] | None] | None = None,
        read_conditions_by_type: dict[str, list[EntityConditionSpec]] | None = None,
        limit: int = 200,
    ) -> list[str]:
        """Bounded distinct identifier values for the table's identifier filter.

        ponytail: fixed 200-candidate cap; revisit if a tenant has more distinct
        identifiers than that."""
        with self._db_session() as session:
            try:
                query = self._enrollment_summary_base_query(
                    session,
                    organization_id=organization_id,
                    machine_name=machine_name,
                    machine_names=machine_names,
                    current_state=current_state,
                    exclude_states=exclude_states,
                    entity_type_name=entity_type_name,
                    entity_type_id=entity_type_id,
                    entity_type_ids=entity_type_ids,
                    include_archived=include_archived,
                    entity_ids=entity_ids,
                    assignee_ids=assignee_ids,
                    include_unassigned=include_unassigned,
                    search=search,
                    field_filters=field_filters,
                    searchable_fields_by_type=searchable_fields_by_type,
                    read_conditions_by_type=read_conditions_by_type,
                )
                if query is None:
                    return []
                identifier_col = EntityRecordModel.data["identifier"].astext
                rows = (
                    query.with_entities(identifier_col)
                    .filter(identifier_col.isnot(None))
                    .distinct()
                    .order_by(identifier_col.asc())
                    .limit(max(1, limit))
                    .all()
                )
                return [row[0] for row in rows if row[0]]
            except Exception as exc:
                logger.exception("workflow enrollment identifier-options query failed")
                raise PersistenceError(f"Unable to list identifier options: {exc}") from exc

    def create_state_machine_published(
        self,
        request: StateMachineCreateRequest,
        *,
        organization_id: str,
        created_by: str | None = None,
        method_pins: list[tuple[str, str, str]] | None = None,
    ) -> StateMachineRecord:
        """Persist a published state machine version.

        `method_pins` are written in this same transaction, as
        (state_key, method_id, method_version_id). They have to be: the pins are
        what stop a pinned method being deleted, so a publish that activated a new
        version and then failed to record them would leave method-derived fields
        in an active workflow with nothing protecting their source. Deleting a
        method concurrently is exactly what would trip that foreign key, so the
        two land together or neither does.
        """
        with self._db_session() as session:
            try:
                existing = (
                    session.query(WorkflowStateMachineModel)
                    .filter_by(
                        organization_id=organization_id,
                        machine_name=request.machine_name,
                        version=request.version,
                    )
                    .filter(WorkflowStateMachineModel.archived_at.is_(None))
                    .one_or_none()
                )
                if existing is not None:
                    raise ConflictError(
                        f"state machine '{request.machine_name}' version {request.version} already exists"
                    )
                self._assert_service_exists(
                    session, organization_id, request.definition.service_id
                )
                if request.is_active:
                    session.execute(
                        update(WorkflowStateMachineModel)
                        .where(
                            WorkflowStateMachineModel.organization_id == organization_id,
                            WorkflowStateMachineModel.machine_name == request.machine_name,
                            WorkflowStateMachineModel.archived_at.is_(None),
                        )
                        .values(is_active=False)
                    )
                model = WorkflowStateMachineModel(
                    organization_id=organization_id,
                    machine_key=request.definition.machine_key,
                    machine_name=request.machine_name,
                    description=request.definition.description,
                    entity_type=request.definition.entity_type,
                    version=request.version,
                    is_active=request.is_active,
                    definition_json=request.definition.model_dump_json(),
                    created_by=created_by,
                    service_id=request.definition.service_id,
                )
                session.add(model)
                session.flush()
                try:
                    self._write_method_pins(
                        session,
                        organization_id=organization_id,
                        workflow_state_machine_id=model.id,
                        pins=method_pins or [],
                    )
                except IntegrityError as exc:
                    # Caught here rather than by the handler below, which reads
                    # every IntegrityError as a duplicate version. A pin that
                    # will not insert means its method moved or went away while
                    # this publish was being assembled.
                    session.rollback()
                    raise ConflictError(
                        "a method this workflow pins changed while it was being "
                        "published; nothing was published"
                    ) from exc
                session.commit()
                session.refresh(model)
                record = self._machine(model)
                assert record is not None
                return record
            except UnknownWorkflowServiceError:
                session.rollback()
                raise
            except ConflictError as ce:
                logger.exception(
                    "workflow create_state_machine_published conflict "
                    f"org={organization_id} machine={request.machine_name} "
                    f"version={request.version} with error {ce}"
                )
                raise
            except IntegrityError as exc:
                session.rollback()
                logger.exception(
                    "workflow create_state_machine_published integrity error "
                    f"org={organization_id} machine={request.machine_name} "
                    f"version={request.version} with error {exc}"
                )
                raise ConflictError(
                    f"state machine '{request.machine_name}' version {request.version} already exists"
                ) from exc
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                logger.exception(
                    "workflow create_state_machine_published failed "
                    f"org={organization_id} machine={request.machine_name} "
                    f"version={request.version} with error {exc}"
                )
                raise PersistenceError(f"Unable to create state machine: {exc}") from exc

    def create_state_machine_draft(
        self,
        *,
        organization_id: str,
        machine_key: str,
        machine_name: str,
        definition: dict[str, object],
        canvas_metadata: dict | None | object = _CANVAS_METADATA_UNSET,
        created_by: str | None = None,
    ) -> WorkflowDraftRecord:
        """Create one workflow draft row."""
        draft_id = str(uuid4())
        with self._db_session() as session:
            try:
                model = WorkflowStateMachineModel(
                    id=draft_id,
                    organization_id=organization_id,
                    machine_key=machine_key,
                    machine_name=machine_name,
                    description=str(definition.get("description")) if definition.get("description") is not None else None,
                    entity_type=str(definition.get("entity_type")) if definition.get("entity_type") is not None else None,
                    version=0,
                    is_active=False,
                    definition_json=json.dumps(definition),
                    canvas_metadata_json=None if canvas_metadata is _CANVAS_METADATA_UNSET else canvas_metadata,
                    created_by=created_by,
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                record = self._draft(model)
                assert record is not None
                return record
            except IntegrityError as exc:
                session.rollback()
                logger.exception(
                    "workflow create_state_machine_draft integrity error "
                    f"org={organization_id} machine={machine_name} with error {exc}"
                )
                raise ConflictError(f"draft state machine '{machine_name}' already exists") from exc
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                raise PersistenceError(f"Unable to create draft state machine: {exc}") from exc

    def list_state_machines(
        self,
        *,
        organization_id: str,
        machine_name: str | None = None,
        scope: str = "published",
        include_archived: bool = False,
    ) -> list[StateMachineRecord | WorkflowDraftRecord]:
        """List workflows by scope (`published`, `draft`, `all`).
        Archived rows are hidden unless `include_archived=True`."""
        try:
            with self._db_session() as session:
                query = session.query(WorkflowStateMachineModel).filter_by(organization_id=organization_id)
                if not include_archived:
                    query = query.filter(WorkflowStateMachineModel.archived_at.is_(None))
                if scope == "published":
                    query = query.filter(WorkflowStateMachineModel.version >= 1)
                elif scope == "draft":
                    query = query.filter(WorkflowStateMachineModel.version == 0)
                elif scope != "all":
                    logger.warning("scope did not match")
                    raise ValidationError("scope must be one of: published, draft, all")
                if machine_name:
                    query = query.filter_by(machine_name=machine_name)
                items: list[StateMachineRecord | WorkflowDraftRecord] = []
                invalid_entries: list[dict[str, object]] = []
                rows = query.order_by(
                    WorkflowStateMachineModel.machine_name.asc(),
                    WorkflowStateMachineModel.version.desc(),
                ).all()
                for row in rows:
                    try:
                        parsed = self._draft(row) if row.version == 0 else self._machine(row)
                    except ValidationError as exc:
                        invalid_entries.append(
                            {
                                "id": getattr(row, "id", None),
                                "machine_key": getattr(row, "machine_key", None),
                                "machine_name": getattr(row, "machine_name", None),
                                "version": getattr(row, "version", None),
                                "error": exc.detail,
                            }
                        )
                        continue
                    if parsed is not None:
                        items.append(parsed)
                if invalid_entries:
                    invalid_names = [e.get("machine_name") for e in invalid_entries]
                    logger.warning(
                        "workflow list_state_machines skipping invalid rows "
                        f"org={organization_id} scope={scope} "
                        f"machine_names={invalid_names}"
                    )
                return items
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "workflow list_state_machines failed "
                f"org={organization_id} machine={machine_name} scope={scope} with error {exc}"
            )
            raise PersistenceError(f"Unable to list state machines: {exc}") from exc

    def update_state_machine_draft(
        self,
        *,
        organization_id: str,
        row_id: str,
        definition: dict[str, object],
        canvas_metadata: dict | None | object = _CANVAS_METADATA_UNSET,
    ) -> WorkflowDraftRecord | None:
        """Update one draft state machine definition in-place."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(WorkflowStateMachineModel)
                    .filter_by(organization_id=organization_id, id=row_id, version=0)
                    .filter(WorkflowStateMachineModel.archived_at.is_(None))
                    .one_or_none()
                )
                if model is None:
                    return None
                model.machine_key = str(definition.get("machine_key") or model.machine_key)
                model.description = (
                    str(definition.get("description"))
                    if definition.get("description") is not None
                    else model.description
                )
                model.entity_type = (
                    str(definition.get("entity_type"))
                    if definition.get("entity_type") is not None
                    else model.entity_type
                )
                # Presence, not truthiness: the draft save is a whole-document
                # write, so an explicit null is the caller clearing the service
                # back to "no service". Testing `is not None` made the field
                # set-once — it could never be unset again.
                if "service_id" in definition:
                    raw_service_id = definition.get("service_id")
                    new_service_id = str(raw_service_id) if raw_service_id is not None else None
                    self._assert_service_exists(session, organization_id, new_service_id)
                    model.service_id = new_service_id
                model.definition_json = json.dumps(definition)
                if canvas_metadata is not _CANVAS_METADATA_UNSET:
                    model.canvas_metadata_json = canvas_metadata
                session.commit()
                session.refresh(model)
                return self._draft(model)
            except UnknownWorkflowServiceError:
                session.rollback()
                raise
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                logger.exception(
                    "workflow update_state_machine_draft failed "
                    f"org={organization_id} row_id={row_id} with error {exc}"
                )
                raise PersistenceError(f"Unable to update draft state machine definition: {exc}") from exc

    def delete_state_machine_by_row_id(
        self,
        *,
        organization_id: str,
        row_id: str,
    ) -> StateMachineRecord | WorkflowDraftRecord | None:
        """Soft-delete one workflow row by its primary-key row ID.

        Sets is_active=False and archived_at to the current timestamp rather than removing the row.
        Returns the record as it was before archiving, or None when no matching
        live row exists."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(WorkflowStateMachineModel)
                    .filter_by(
                        organization_id=organization_id,
                        id=row_id,
                    )
                    .filter(WorkflowStateMachineModel.archived_at.is_(None))
                    .one_or_none()
                )
                if model is None:
                    return None
                deleted = self._draft(model) if model.version == 0 else self._machine(model)
                model.is_active = False
                model.archived_at = datetime.now(UTC)
                session.commit()
                return deleted
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                logger.exception(
                    "workflow delete_state_machine_by_row_id failed "
                    f"org={organization_id} row_id={row_id} with error {exc}"
                )
                raise PersistenceError(f"Unable to soft-delete workflow by row id: {exc}") from exc

    def get_state_machine(self, *, organization_id: str, machine_name: str, version: int) -> StateMachineRecord | None:
        """Get one state machine version."""
        if self._use_memory():
            return self._machine(self._machines.get((organization_id, machine_name, version)))
        with self._db_session() as session:
            try:
                return self._machine(
                    session.query(WorkflowStateMachineModel)
                    .filter_by(
                        organization_id=organization_id,
                        machine_name=machine_name,
                        version=version,
                    )
                    .filter(WorkflowStateMachineModel.archived_at.is_(None))
                    .first()
                )
            except ValidationError as ve:
                logger.exception(
                    "workflow get_state_machine validation error "
                    f"org={organization_id} machine={machine_name} version={version} with error {ve}"
                )
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "workflow get_state_machine failed "
                    f"org={organization_id} machine={machine_name} version={version} with error {exc}"
                )
                raise PersistenceError(f"Unable to get state machine: {exc}") from exc

    def get_active_state_machine(
        self, *, organization_id: str, machine_name: str
    ) -> StateMachineRecord | None:
        """Get the active state machine version."""
        if self._use_memory():
            for item in self._machines.values():
                if (
                    item.organization_id == organization_id
                    and item.machine_name == machine_name
                    and item.is_active
                ):
                    return self._machine(item)
            return None
        with self._db_session() as session:
            try:
                return self._machine(
                    session.query(WorkflowStateMachineModel)
                    .filter_by(
                        organization_id=organization_id,
                        machine_name=machine_name,
                        is_active=True,
                    )
                    .filter(WorkflowStateMachineModel.archived_at.is_(None))
                    .first()
                )
            except ValidationError as ve:
                logger.exception(
                    "workflow get_active_state_machine validation error "
                    f"org={organization_id} machine={machine_name} with error {ve}"
                )
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "workflow get_active_state_machine failed "
                    f"org={organization_id} machine={machine_name} with error {exc}"
                )
                raise PersistenceError(f"Unable to get active state machine: {exc}") from exc

    @staticmethod
    def _to_display_record(model: WorkflowBoardDisplayConfigModel) -> WorkflowBoardDisplayFieldsRecord:
        """Map one persisted row onto its contract. Shared by the get/upsert paths."""
        return WorkflowBoardDisplayFieldsRecord(
            machine_name=model.machine_name,
            fields=list(model.fields_json or []),
            updated_at=model.updated_at,
            updated_by=model.updated_by,
        )

    def get_board_display_fields(
        self, *, organization_id: str, machine_name: str
    ) -> WorkflowBoardDisplayFieldsRecord:
        """Get the configured extra card fields for one workflow.

        Returns an empty-fields record (never None) when nothing has been
        configured yet, so callers don't need a separate not-found branch.
        """
        if self._use_memory():
            existing = self._board_display_configs.get((organization_id, machine_name))
            if existing is not None:
                return existing
            return WorkflowBoardDisplayFieldsRecord(machine_name=machine_name, fields=[])
        with self._db_session() as session:
            try:
                model = (
                    session.query(WorkflowBoardDisplayConfigModel)
                    .filter_by(organization_id=organization_id, machine_name=machine_name)
                    .one_or_none()
                )
                if model is None:
                    return WorkflowBoardDisplayFieldsRecord(machine_name=machine_name, fields=[])
                return self._to_display_record(model)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "workflow get_board_display_fields failed "
                    f"org={organization_id} machine={machine_name} with error {exc}"
                )
                raise PersistenceError(f"Unable to get board display fields: {exc}") from exc

    def upsert_board_display_fields(
        self,
        *,
        organization_id: str,
        machine_name: str,
        fields: list[str],
        updated_by: str | None,
    ) -> WorkflowBoardDisplayFieldsRecord:
        """Replace the configured extra card fields for one workflow."""
        if self._use_memory():
            record = WorkflowBoardDisplayFieldsRecord(
                machine_name=machine_name,
                fields=list(fields),
                updated_at=datetime.now(UTC),
                updated_by=updated_by,
            )
            self._board_display_configs[(organization_id, machine_name)] = record
            return record
        with self._db_session() as session:
            try:
                # Atomic upsert (avoids a race between concurrent saves),
                # same mechanism as `_get_next_auto_number`.
                stmt = pg_insert(WorkflowBoardDisplayConfigModel).values(
                    id=str(uuid4()),
                    organization_id=organization_id,
                    machine_name=machine_name,
                    fields_json=list(fields),
                    updated_by=updated_by,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["organization_id", "machine_name"],
                    set_={
                        "fields_json": stmt.excluded.fields_json,
                        "updated_by": stmt.excluded.updated_by,
                        "updated_at": func.now(),
                    },
                ).returning(WorkflowBoardDisplayConfigModel)
                model = session.execute(stmt).scalar_one()
                session.commit()
                return self._to_display_record(model)
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                logger.exception(
                    "workflow upsert_board_display_fields failed "
                    f"org={organization_id} machine={machine_name} with error {exc}"
                )
                raise PersistenceError(f"Unable to save board display fields: {exc}") from exc

    def get_state_machine_by_row_id(
        self,
        *,
        organization_id: str,
        row_id: str,
    ) -> StateMachineRecord | WorkflowDraftRecord | None:
        """Get one exact workflow row by primary key row ID."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(WorkflowStateMachineModel)
                    .filter_by(
                        organization_id=organization_id,
                        id=row_id,
                    )
                    .filter(WorkflowStateMachineModel.archived_at.is_(None))
                    .one_or_none()
                )
                if model is None:
                    return None
                if model.version == 0:
                    return self._draft(model)
                return self._machine(model)
            except ValidationError as ve:
                logger.exception(
                    "workflow get_state_machine_by_row_id validation error "
                    f"org={organization_id} row_id={row_id} with error {ve}"
                )
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "workflow get_state_machine_by_row_id failed "
                    f"org={organization_id} row_id={row_id} with error {exc}"
                )
                raise PersistenceError(f"Unable to get state machine by row id: {exc}") from exc

    def get_next_version(self, *, organization_id: str, machine_name: str) -> int:
        """Return the next version number."""
        versions = [
            item.version
            for item in self.list_state_machines(
                organization_id=organization_id, machine_name=machine_name
            )
        ]
        return (max(versions) if versions else 0) + 1

    def update_state_machine_definition(
        self,
        *,
        organization_id: str,
        machine_name: str,
        version: int,
        definition: dict[str, object],
        is_active: bool | None = None,
        canvas_metadata: dict | None | object = _CANVAS_METADATA_UNSET,
    ) -> WorkflowDraftRecord | None:
        """Replace one persisted definition with a raw dict, without validation."""
        key = (organization_id, machine_name, version)
        machine_key = str(definition.get("machine_key") or machine_name)
        description = definition.get("description")
        entity_type = definition.get("entity_type")
        if self._use_memory():
            existing = self._machines.get(key)
            if existing is None:
                return None
            existing.machine_key = machine_key
            existing.name = str(definition.get("name") or existing.name)
            existing.description = (
                str(description) if description is not None else existing.description
            )
            existing.entity_type = (
                str(entity_type) if entity_type is not None else existing.entity_type
            )
            if is_active is not None:
                existing.is_active = bool(is_active)
            if canvas_metadata is not _CANVAS_METADATA_UNSET:
                existing.canvas_metadata = canvas_metadata
            return WorkflowDraftRecord(
                id=getattr(existing, "id", None),
                machine_key=existing.machine_key,
                machine_name=existing.machine_name,
                name=getattr(existing, "name", None),
                description=existing.description,
                entity_type=existing.entity_type,
                version=existing.version,
                is_active=existing.is_active,
                definition=dict(definition),
                canvas_metadata=existing.canvas_metadata,
                organization_id=existing.organization_id,
                created_by=getattr(existing, "created_by", None),
                created_at=existing.created_at,
            )
        with self._db_session() as session:
            try:
                model = (
                    session.query(WorkflowStateMachineModel)
                    .filter_by(
                        organization_id=organization_id, machine_name=machine_name, version=version
                    )
                    .filter(WorkflowStateMachineModel.archived_at.is_(None))
                    .first()
                )
                if model is None:
                    return None
                model.machine_key = machine_key
                if description is not None:
                    model.description = str(description)
                if entity_type is not None:
                    model.entity_type = str(entity_type)
                if is_active is not None:
                    model.is_active = bool(is_active)
                model.definition_json = json.dumps(definition)
                if canvas_metadata is not _CANVAS_METADATA_UNSET:
                    model.canvas_metadata_json = canvas_metadata
                session.commit()
                session.refresh(model)
                return WorkflowDraftRecord(
                    id=model.id,
                    machine_key=model.machine_key,
                    machine_name=model.machine_name,
                    name=str(definition.get("name"))
                    if definition.get("name") is not None
                    else None,
                    description=model.description,
                    entity_type=model.entity_type,
                    version=model.version,
                    is_active=model.is_active,
                    definition=dict(definition),
                    canvas_metadata=model.canvas_metadata_json,
                    organization_id=model.organization_id,
                    created_by=model.created_by,
                    created_at=model.created_at,
                )
            except Exception as exc:
                session.rollback()
                logger.exception(
                    "workflow update_state_machine_definition failed "
                    f"org={organization_id} machine={machine_name} "
                    f"version={version} with error {exc}"
                )
                raise PersistenceError(f"Unable to update state machine definition: {exc}") from exc

    def activate_state_machine(
        self, *, organization_id: str, machine_name: str, version: int
    ) -> StateMachineRecord | None:
        """Activate one version and deactivate peers."""
        try:
            if self._use_memory():
                target = self._machines.get((organization_id, machine_name, version))
                if target is None:
                    return None
                self._deactivate_memory_versions(organization_id, machine_name)
                target.is_active = True
                return self._machine(target)
            with self._db_session() as session:
                target = (
                    session.query(WorkflowStateMachineModel)
                    .filter_by(
                        organization_id=organization_id, machine_name=machine_name, version=version
                    )
                    .filter(WorkflowStateMachineModel.archived_at.is_(None))
                    .first()
                )
                if target is None:
                    return None
                session.execute(
                    update(WorkflowStateMachineModel)
                    .where(
                        WorkflowStateMachineModel.organization_id == organization_id,
                        WorkflowStateMachineModel.machine_name == machine_name,
                        WorkflowStateMachineModel.archived_at.is_(None),
                    )
                    .values(is_active=False)
                )
                target.is_active = True
                session.add(target)
                session.commit()
                session.refresh(target)
                return self._machine(target)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "workflow activate_state_machine failed "
                f"org={organization_id} machine={machine_name} "
                f"version={version} with error {exc}"
            )
            raise PersistenceError(f"Unable to activate state machine: {exc}") from exc

    def create_validation_report(
        self,
        *,
        organization_id: str,
        machine_name: str,
        version: int,
        valid: bool,
        issues: list[object],
    ) -> DefinitionReport:
        """Persist a validation report."""
        return self._create_report(
            organization_id=organization_id,
            report_type=ReportType.VALIDATION,
            machine_name=machine_name,
            version=version,
            valid=valid,
            issues=issues,
        )

    def action_run_exists_by_idempotency_key(
        self, *, organization_id: str, idempotency_key: str
    ) -> bool:
        """Return whether an action_run already exists for the given idempotency key.

        Scoped to the organization like every other read of this table. The unique constraint
        on `idempotency_key` is global rather than per-organization, so a key already taken by
        another tenant is not reported here — the insert then raises `ConflictError`, which the
        caller already treats as "another arrival scheduled it".
        """
        if self._use_memory():
            return False
        with self._db_session() as session:
            try:
                row = (
                    session.query(ActionRunModel.run_id)
                    .filter(ActionRunModel.organization_id == organization_id)
                    .filter(ActionRunModel.idempotency_key == idempotency_key)
                    .filter(ActionRunModel.status != ActionRunStatus.FAILED)
                    .first()
                )
                return row is not None
            except Exception as exc:
                raise PersistenceError(
                    f"Unable to check action_run idempotency key: {exc}"
                ) from exc

    def has_in_flight_state_action_run(
        self, *, organization_id: str, entity_id: str, state: str
    ) -> bool:
        """Return whether a not-yet-finished action run exists for this entity state.

        Matches every key scoped to one entity state — state entry, chain continuation and
        manual rerun — because they all start with the same prefix. SLA breach signals are
        keyed differently on purpose and are excluded, so a pending deadline never counts as
        the state's own work being in flight.

        The prefix comes from `ActionRunIdempotencyKey` rather than being spelled out here: it
        is the same method the keys are built from, so this match cannot drift away from them.
        """
        if self._use_memory():
            return False
        escaped_prefix = (
            ActionRunIdempotencyKey.entity_state_prefix(entity_id, state)
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        with self._db_session() as session:
            try:
                row = (
                    session.query(ActionRunModel.run_id)
                    .filter(ActionRunModel.organization_id == organization_id)
                    .filter(ActionRunModel.entity_id == entity_id)
                    .filter(
                        ActionRunModel.status.in_(
                            [
                                ActionRunStatus.PENDING,
                                ActionRunStatus.RUNNING,
                                ActionRunStatus.PENDING_EXTERNAL,
                            ]
                        )
                    )
                    .filter(ActionRunModel.idempotency_key.like(escaped_prefix + "%", escape="\\"))
                    .first()
                )
                return row is not None
            except Exception as exc:
                logger.error(
                    f"in-flight action run check failed entity={entity_id} state={state}: {exc}"
                )
                raise PersistenceError(
                    f"Unable to check in-flight action runs: {exc}"
                ) from exc

    def create_action_run(
        self,
        *,
        run_id: str,
        organization_id: str,
        entity_id: str,
        definition_id: str | None,
        action_kind: str,
        config_json: str,
        idempotency_key: str,
        scheduled_at: object | None = None,
    ) -> None:
        """Create one pending action_run record."""
        if self._use_memory():
            return
        with self._db_session() as session:
            try:
                resolved_definition_id = definition_id
                if resolved_definition_id is None:
                    defn = (
                        session.query(ActionDefinitionModel)
                        .filter(ActionDefinitionModel.kind == action_kind)
                        .first()
                    )
                    resolved_definition_id = str(defn.definition_id) if defn else None
                session.add(
                    ActionRunModel(
                        run_id=run_id,
                        organization_id=organization_id,
                        entity_id=entity_id,
                        definition_id=resolved_definition_id,
                        action_kind=action_kind,
                        config_json=json.loads(config_json),
                        status=ActionRunStatus.PENDING,
                        attempts=0,
                        idempotency_key=idempotency_key,
                        scheduled_at=scheduled_at,
                    )
                )
                session.commit()
                if self.action_runs_enqueue_fn is not None:
                    try:
                        self.action_runs_enqueue_fn(run_id)
                    except Exception as enqueue_exc:
                        logger.warning(
                            "action_run %s created but Redis enqueue failed "
                            "(org_id=%s entity_id=%s action_kind=%s); "
                            "run stays pending until reconciliation: %s",
                            run_id,
                            organization_id,
                            entity_id,
                            action_kind,
                            enqueue_exc,
                        )
            except IntegrityError as exc:
                session.rollback()
                raise ConflictError("action_run idempotency conflict") from exc
            except Exception as exc:
                session.rollback()
                raise PersistenceError(f"Unable to create action_run: {exc}") from exc

    def cancel_pending_signal(self, *, entity_id: str, organization_id: str) -> None:
        """Cancel any pending signal.fire action run for this entity."""
        if self._use_memory():
            return
        with self._db_session() as session:
            try:
                session.query(ActionRunModel).filter(
                    ActionRunModel.entity_id == entity_id,
                    ActionRunModel.organization_id == organization_id,
                    ActionRunModel.action_kind == SLA_SIGNAL_ACTION_KIND,
                    ActionRunModel.status == ActionRunStatus.PENDING,
                ).update({"status": ActionRunStatus.CANCELLED})
                session.commit()
            except Exception as exc:
                session.rollback()
                raise PersistenceError(f"Unable to cancel pending signal: {exc}") from exc




    def list_engine_field_types(self) -> dict[str, tuple[str | None, str]]:
        """The field-type catalogue as {code: (engine_type, config_kind)}.

        Engine-wide reference data, not per organization. Read here rather than
        through the field library service so the workflow layer keeps its single
        persistence seam; the catalogue is what translates a library field type
        into the `EntityField.type` the engine understands.
        """
        if self._use_memory():
            return {}
        with self._db_session() as session:
            try:
                rows = session.query(
                    FieldTypeCatalogueModel.code,
                    FieldTypeCatalogueModel.engine_type,
                    FieldTypeCatalogueModel.config_kind,
                ).all()
                return {code: (engine_type, config_kind) for code, engine_type, config_kind in rows}
            except Exception as exc:
                logger.exception(f"workflow list_engine_field_types failed with error {exc}")
                raise PersistenceError(f"Unable to read the field type catalogue: {exc}") from exc

    @staticmethod
    def _write_method_pins(
        session: Session,
        *,
        organization_id: str,
        workflow_state_machine_id: str,
        pins: list[tuple[str, str, str]],
    ) -> int:
        """Set one workflow row's pins inside the caller's transaction.

        Replaces wholesale, which is how a method a state no longer references
        stops being pinned. The commit belongs to the caller.
        """
        session.query(WorkflowMethodPinModel).filter_by(
            organization_id=organization_id,
            workflow_state_machine_id=workflow_state_machine_id,
        ).delete(synchronize_session=False)
        for state_key, method_id, method_version_id in pins:
            session.add(
                WorkflowMethodPinModel(
                    id=str(uuid4()),
                    organization_id=organization_id,
                    workflow_state_machine_id=workflow_state_machine_id,
                    state_key=state_key,
                    method_id=method_id,
                    method_version_id=method_version_id,
                )
            )
        return len(pins)

    def replace_method_pins(
        self,
        *,
        organization_id: str,
        workflow_state_machine_id: str,
        pins: list[tuple[str, str, str]],
    ) -> int:
        """Set one published workflow's method pins to exactly `pins`.

        Each pin is (state_key, method_id, method_version_id). Rows for this
        workflow row are replaced wholesale, which is how a method that a state no
        longer references stops being pinned. Other published versions of the same
        workflow keep their own rows, so republishing never rewrites history.
        """
        if self._use_memory():
            return 0
        with self._db_session() as session:
            try:
                written = self._write_method_pins(
                    session,
                    organization_id=organization_id,
                    workflow_state_machine_id=workflow_state_machine_id,
                    pins=pins,
                )
                session.commit()
                return written
            except Exception as exc:
                session.rollback()
                logger.exception(
                    "workflow replace_method_pins failed "
                    f"org={organization_id} row_id={workflow_state_machine_id} error={exc}"
                )
                raise PersistenceError(f"Unable to record the method pins: {exc}") from exc

    def list_method_pins(
        self, *, organization_id: str, workflow_state_machine_id: str
    ) -> list[tuple[str, str, str]]:
        """One published workflow's pins as (state_key, method_id, version_id)."""
        if self._use_memory():
            return []
        with self._db_session() as session:
            try:
                rows = (
                    session.query(
                        WorkflowMethodPinModel.state_key,
                        WorkflowMethodPinModel.method_id,
                        WorkflowMethodPinModel.method_version_id,
                    )
                    .filter_by(
                        organization_id=organization_id,
                        workflow_state_machine_id=workflow_state_machine_id,
                    )
                    .order_by(
                        WorkflowMethodPinModel.state_key.asc(),
                        WorkflowMethodPinModel.method_id.asc(),
                    )
                    .all()
                )
                return [tuple(row) for row in rows]
            except Exception as exc:
                logger.exception(f"workflow list_method_pins failed with error {exc}")
                raise PersistenceError(f"Unable to read the method pins: {exc}") from exc

    def get_validation_report(self, *, report_id: str) -> DefinitionReport | None:
        """Fetch a validation report by id."""
        report = self.get_definition_report(report_id=report_id)
        return report if report and report.report_type == ReportType.VALIDATION else None

    def get_definition_report(self, *, report_id: str) -> DefinitionReport | None:
        """Fetch a definition report by id."""
        if self._use_memory():
            return self._report(self._reports.get(report_id))
        with self._db_session() as session:
            return self._report(
                session.query(WorkflowDefinitionReportModel).filter_by(report_id=report_id).first()
            )

    def get_latest_validation_report(
        self, *, organization_id: str, machine_name: str, version: int
    ) -> DefinitionReport | None:
        """Fetch the latest validation report for a workflow version."""
        if self._use_memory():
            items = [
                self._report(item)
                for item in self._reports.values()
                if item.organization_id == organization_id
                and item.report_type == ReportType.VALIDATION
                and item.machine_name == machine_name
                and item.version == version
            ]
            items = [item for item in items if item is not None]
            items.sort(key=lambda item: item.created_at or datetime.min, reverse=True)
            return items[0] if items else None
        with self._db_session() as session:
            return self._report(
                session.query(WorkflowDefinitionReportModel)
                .filter_by(
                    organization_id=organization_id,
                    report_type=ReportType.VALIDATION,
                    machine_name=machine_name,
                    version=version,
                )
                .order_by(WorkflowDefinitionReportModel.created_at.desc())
                .first()
            )

    def _create_report(
        self,
        *,
        organization_id: str,
        report_type: str,
        machine_name: str,
        issues: list[object],
        **kwargs,
    ) -> DefinitionReport:
        """Persist a unified definition report."""
        report_id = str(uuid4())
        if self._use_memory():
            record = MemoryDefinitionReport(
                report_id=report_id,
                organization_id=organization_id,
                report_type=report_type,
                machine_name=machine_name,
                issues=list(issues),
                created_at=datetime.now(UTC),
                **kwargs,
            )
            self._reports[report_id] = record
            report = self._report(record)
            assert report is not None
            return report
        with self._db_session() as session:
            model = WorkflowDefinitionReportModel(
                report_id=report_id,
                organization_id=organization_id,
                report_type=report_type,
                machine_name=machine_name,
                issues_json=json.dumps([issue.model_dump() for issue in issues]),
                **kwargs,
            )
            session.add(model)
            # flush (not commit) so eager_defaults fetches `created_at` via INSERT ... RETURNING,
            # then build the DTO while the instance is still live. Committing first would expire
            # it and force a second SELECT to read the row back.
            session.flush()
            report = self._report(model)
            session.commit()
            assert report is not None
            return report

    def _deactivate_memory_versions(self, organization_id: str, machine_name: str) -> None:
        """Deactivate memory versions for a machine."""
        for item in self._machines.values():
            if item.organization_id == organization_id and item.machine_name == machine_name:
                item.is_active = False

    @staticmethod
    def _machine(
        item: MemoryStateMachine | WorkflowStateMachineModel | None,
    ) -> StateMachineRecord | None:
        """Convert stored workflow to response contract."""
        if item is None:
            return None
        if isinstance(item, MemoryStateMachine):
            return StateMachineRecord(
                machine_key=item.machine_key,
                machine_name=item.machine_name,
                name=item.name,
                description=item.description,
                entity_type=item.entity_type,
                version=item.version,
                is_active=item.is_active,
                definition=item.definition,
                canvas_metadata=item.canvas_metadata,
                organization_id=item.organization_id,
                created_by=getattr(item, "created_by", None),
                created_at=item.created_at,
            )
        try:
            definition = StateMachineDefinition.model_validate(json.loads(item.definition_json))
        except (PydanticValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            machine_name = getattr(item, "machine_name", "unknown")
            machine_key = getattr(item, "machine_key", None)
            version = getattr(item, "version", "unknown")
            logger.exception(
                "workflow _machine invalid persisted definition "
                f"machine={machine_name} machine_key={machine_key} "
                f"version={version} with error {exc}"
            )
            raise ValidationError(
                f"state machine '{machine_name}' version '{version}' has invalid persisted definition"
            ) from exc
        return StateMachineRecord(
            id=item.id,
            machine_key=getattr(item, "machine_key", definition.machine_key),
            machine_name=item.machine_name,
            name=definition.name,
            description=getattr(item, "description", definition.description),
            entity_type=getattr(item, "entity_type", definition.entity_type),
            service_id=getattr(item, "service_id", definition.service_id),
            version=item.version,
            is_active=item.is_active,
            definition=definition,
            canvas_metadata=getattr(item, "canvas_metadata_json", None),
            organization_id=item.organization_id,
            created_by=getattr(item, "created_by", None),
            created_at=item.created_at,
        )

    @staticmethod
    def _draft(item: WorkflowStateMachineModel | None) -> WorkflowDraftRecord | None:
        """Convert persisted draft row to draft contract."""
        if item is None:
            return None
        try:
            definition = json.loads(item.definition_json or "{}")
        except json.JSONDecodeError as exc:
            logger.exception(
                "workflow _draft invalid persisted JSON "
                f"id={item.id} machine={item.machine_name} "
                f"version={item.version} with error {exc}"
            )
            raise ValidationError(
                "draft state machine has invalid persisted draft JSON"
            ) from exc
        return WorkflowDraftRecord(
            id=item.id,
            machine_key=item.machine_key,
            machine_name=item.machine_name,
            name=str(definition.get("name")) if isinstance(definition, dict) and definition.get("name") is not None else None,
            description=item.description,
            entity_type=item.entity_type,
            service_id=item.service_id,
            version=0,
            is_active=False,
            definition=definition if isinstance(definition, dict) else {},
            canvas_metadata=item.canvas_metadata_json,
            organization_id=item.organization_id,
            created_by=item.created_by,
            created_at=item.created_at,
        )

    @staticmethod
    def _report(item: MemoryDefinitionReport | WorkflowDefinitionReportModel | None) -> DefinitionReport | None:
        """Convert stored report to response contract."""
        if item is None:
            return None
        raw_issues = (
            item.issues
            if isinstance(item, MemoryDefinitionReport)
            else json.loads(item.issues_json or "[]")
        )
        issues = [
            issue if isinstance(issue, ValidationIssue) else ValidationIssue.model_validate(issue)
            for issue in raw_issues
        ]
        buckets = IssueBuckets()
        next_actions: list[str] = []
        seen_actions: set[str] = set()
        for issue in issues:
            bucket_name = issue.bucket or "form_errors"
            getattr(buckets, bucket_name).append(issue)
            if issue.action and issue.action not in seen_actions:
                seen_actions.add(issue.action)
                next_actions.append(issue.action)
        return DefinitionReport(
            report_id=item.report_id,
            report_type=item.report_type,
            machine_name=item.machine_name,
            version=getattr(item, "version", None),
            valid=getattr(item, "valid", None),
            issues=issues,
            buckets=buckets,
            next_actions=next_actions,
            created_at=item.created_at,
        )

    # ── TransitionAttempt ──────────────────────────────────────────────────────

    def record_transition_attempt(
        self,
        *,
        organization_id: str,
        entity_id: str,
        workflow_id: str,
        status: str,
        from_state: str | None = None,
        to_state: str | None = None,
        trigger: str | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
        actor_role: str | None = None,
        failure_code: str | None = None,
        idempotency_key: str | None = None,
        inputs: dict | None = None,
        outputs: dict | None = None,
        guard_evaluations: dict | None = None,
    ) -> TransitionAttemptRecord:
        """Append a transition outcome. Idempotent on `(organization_id, idempotency_key)`."""
        with self._db_session() as session:
            try:
                if idempotency_key is not None:
                    existing = (
                        session.query(TransitionAttemptModel)
                        .filter_by(organization_id=organization_id, idempotency_key=idempotency_key)
                        .first()
                    )
                    if existing is not None:
                        attempt = self._transition_attempt(existing)
                        assert attempt is not None
                        return attempt
                model = TransitionAttemptModel(
                    transition_attempt_id=str(uuid4()),
                    organization_id=organization_id,
                    entity_id=entity_id,
                    workflow_id=workflow_id,
                    from_state=from_state,
                    to_state=to_state,
                    trigger=trigger,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    actor_role=actor_role,
                    status=status,
                    failure_code=failure_code,
                    idempotency_key=idempotency_key,
                    inputs=dict(inputs) if inputs is not None else None,
                    outputs=dict(outputs) if outputs is not None else None,
                    guard_evaluations=dict(guard_evaluations) if guard_evaluations is not None else None,
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                attempt = self._transition_attempt(model)
                assert attempt is not None
                return attempt
            except IntegrityError as exc:
                session.rollback()
                logger.debug("record_transition_attempt IntegrityError (idempotency race): %s", exc)
                if idempotency_key is not None:
                    existing = (
                        session.query(TransitionAttemptModel)
                        .filter_by(organization_id=organization_id, idempotency_key=idempotency_key)
                        .first()
                    )
                    if existing is not None:
                        attempt = self._transition_attempt(existing)
                        assert attempt is not None
                        return attempt
                raise PersistenceError(f"Unable to record transition attempt: {exc}") from exc
            except Exception as exc:
                session.rollback()
                logger.exception("record_transition_attempt failed", extra={"org_id": organization_id})
                raise PersistenceError(f"Unable to record transition attempt: {exc}") from exc

    def find_transition_attempt_by_idempotency_key(
        self,
        *,
        organization_id: str,
        idempotency_key: str,
    ) -> TransitionAttemptRecord | None:
        """Look up a previously recorded attempt by `(organization_id, idempotency_key)`."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(TransitionAttemptModel)
                    .filter_by(organization_id=organization_id, idempotency_key=idempotency_key)
                    .first()
                )
                return self._transition_attempt(model)
            except Exception as exc:
                logger.debug("find_transition_attempt_by_idempotency_key failed: %s", exc)
                raise PersistenceError(f"Unable to find transition attempt: {exc}") from exc

    def list_transition_attempts_for_entity(
        self,
        *,
        organization_id: str,
        entity_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TransitionAttemptRecord], int]:
        """List transition attempts newest-first with pagination. Returns `(items, total)`."""
        with self._db_session() as session:
            try:
                base = session.query(TransitionAttemptModel).filter_by(
                    organization_id=organization_id, entity_id=entity_id
                )
                total = base.count()
                rows = (
                    base.order_by(TransitionAttemptModel.occurred_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                attempts: list[TransitionAttemptRecord] = []
                for row in rows:
                    attempt = self._transition_attempt(row)
                    assert attempt is not None
                    attempts.append(attempt)
                return attempts, total
            except Exception as exc:
                logger.debug("list_transition_attempts_for_entity failed: %s", exc)
                raise PersistenceError(f"Unable to list transition attempts: {exc}") from exc

    @staticmethod
    def _transition_attempt(item: TransitionAttemptModel | None) -> TransitionAttemptRecord | None:
        """Hydrate a `TransitionAttemptModel` row into a `TransitionAttemptRecord`."""
        if item is None:
            return None
        return TransitionAttemptRecord(
            transition_attempt_id=item.transition_attempt_id,
            organization_id=item.organization_id,
            entity_id=item.entity_id,
            workflow_id=item.workflow_id,
            from_state=item.from_state,
            to_state=item.to_state,
            trigger=item.trigger,
            actor_id=item.actor_id,
            actor_name=item.actor_name,
            actor_role=item.actor_role,
            status=item.status,
            failure_code=item.failure_code,
            idempotency_key=item.idempotency_key,
            inputs=dict(item.inputs) if item.inputs is not None else None,
            outputs=dict(item.outputs) if item.outputs is not None else None,
            guard_evaluations=dict(item.guard_evaluations) if item.guard_evaluations is not None else None,
            occurred_at=item.occurred_at,
        )

    @staticmethod
    def _service(row: WorkflowServiceModel) -> WorkflowService:
        """Map a service row onto its contract."""
        return WorkflowService(
            service_id=row.id,
            organization_id=row.organization_id,
            name=row.name,
            created_at=row.created_at,
        )

    def create_service(self, *, organization_id: str, name: str) -> WorkflowService:
        """Insert a service, raising DuplicateWorkflowServiceNameError on a name clash.

        The clash is caught from the unique index rather than pre-checked, so two
        concurrent creates cannot both pass a check and then both insert.
        """
        with self._db_session() as session:
            try:
                row = WorkflowServiceModel(
                    id=str(uuid4()), organization_id=organization_id, name=name.strip()
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                return self._service(row)
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateWorkflowServiceNameError(
                    f"a service named '{name.strip()}' already exists in this organization"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_service failed: %s", exc)
                raise PersistenceError(f"Unable to create the service: {exc}") from exc

    def list_services(self, *, organization_id: str) -> list[WorkflowService]:
        """Every service in the organization, ordered by name.

        Unpaginated on purpose: this is the lookup list behind a picker, not a
        history that grows.
        """
        with self._db_session() as session:
            try:
                rows = (
                    session.query(WorkflowServiceModel)
                    .filter(WorkflowServiceModel.organization_id == organization_id)
                    .order_by(WorkflowServiceModel.name.asc())
                    .all()
                )
                return [self._service(row) for row in rows]
            except Exception as exc:
                logger.debug("list_services failed: %s", exc)
                raise PersistenceError(f"Unable to list services: {exc}") from exc

    def list_services_with_workflows(
        self,
        *,
        organization_id: str,
        limit: int = SERVICE_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[WorkflowServiceWithWorkflows], int]:
        """A page of services, each carrying the workflows filed under it.

        Two queries whatever the page size: one for the services, one for every
        workflow belonging to them. Rows are collapsed to the highest
        non-archived version per machine name, so a workflow published five
        times is listed once.
        """
        with self._db_session() as session:
            try:
                base = session.query(WorkflowServiceModel).filter(
                    WorkflowServiceModel.organization_id == organization_id
                )
                total = base.order_by(None).count()
                service_rows = (
                    base.order_by(WorkflowServiceModel.name.asc())
                    .limit(limit)
                    .offset(offset)
                    .all()
                )
                service_ids = [row.id for row in service_rows]
                grouped: dict[str, dict[str, WorkflowServiceWorkflow]] = defaultdict(dict)
                if service_ids:
                    workflow_rows = (
                        session.query(WorkflowStateMachineModel)
                        .filter(
                            WorkflowStateMachineModel.organization_id == organization_id,
                            WorkflowStateMachineModel.service_id.in_(service_ids),
                            WorkflowStateMachineModel.archived_at.is_(None),
                        )
                        .order_by(
                            WorkflowStateMachineModel.machine_name.asc(),
                            WorkflowStateMachineModel.version.asc(),
                        )
                        .all()
                    )
                    # Ascending version, so the last write per machine name wins
                    # and each workflow is represented by its highest version.
                    for row in workflow_rows:
                        grouped[row.service_id][row.machine_name] = WorkflowServiceWorkflow(
                            id=row.id,
                            machine_key=row.machine_key,
                            machine_name=row.machine_name,
                            name=row.machine_name,
                            description=row.description,
                            entity_type=row.entity_type,
                            version=row.version,
                            is_active=bool(row.is_active),
                            created_at=row.created_at,
                        )
                items: list[WorkflowServiceWithWorkflows] = []
                for row in service_rows:
                    workflows = sorted(
                        grouped.get(row.id, {}).values(), key=lambda item: item.machine_name
                    )
                    service = self._service(row)
                    items.append(
                        WorkflowServiceWithWorkflows(
                            service_id=service.service_id,
                            organization_id=service.organization_id,
                            name=service.name,
                            created_at=service.created_at,
                            workflow_count=len(workflows),
                            workflows=workflows,
                        )
                    )
                return items, total
            except Exception as exc:
                logger.debug("list_services_with_workflows failed: %s", exc)
                raise PersistenceError(f"Unable to list services with workflows: {exc}") from exc

    def rename_service(
        self, *, organization_id: str, service_id: str, name: str
    ) -> WorkflowService | None:
        """Rename in place. None when the service is not in this organization.

        The workflows filed under it keep pointing at the same id, so nothing
        moves out of the service.
        """
        with self._db_session() as session:
            try:
                row = self._service_row(session, organization_id, service_id)
                if row is None:
                    return None
                row.name = name.strip()
                session.commit()
                session.refresh(row)
                return self._service(row)
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateWorkflowServiceNameError(
                    f"a service named '{name.strip()}' already exists in this organization"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("rename_service failed: %s", exc)
                raise PersistenceError(f"Unable to rename the service: {exc}") from exc

    def delete_service(self, *, organization_id: str, service_id: str) -> bool:
        """Hard delete a service. Returns False when it was already gone.

        The foreign key from workflow_state_machines has no ON DELETE clause, so
        the database refuses while a workflow is still filed under it. That
        refusal is caught and raised as WorkflowServiceInUseError rather than
        surfacing as a 500.
        """
        with self._db_session() as session:
            try:
                row = self._service_row(session, organization_id, service_id)
                if row is None:
                    return False
                session.delete(row)
                session.commit()
                return True
            except IntegrityError as exc:
                session.rollback()
                raise WorkflowServiceInUseError(
                    "a workflow is still filed under this service, so it cannot be deleted"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("delete_service failed: %s", exc)
                raise PersistenceError(f"Unable to delete the service: {exc}") from exc

    @classmethod
    def _assert_service_exists(
        cls, session: Session, organization_id: str, service_id: str | None
    ) -> None:
        """Refuse a service that is not this organization's own.

        The composite foreign key already refuses it, but only as an
        IntegrityError the caller sees as a 500. service_id is caller-supplied
        and can go stale, so it is checked first and reported as a 4xx.
        """
        if service_id is None:
            return
        if cls._service_row(session, organization_id, service_id) is None:
            raise UnknownWorkflowServiceError(f"service '{service_id}' was not found")

    @staticmethod
    def _service_row(
        session: Session, organization_id: str, service_id: str
    ) -> WorkflowServiceModel | None:
        """Load one service inside the caller's session, scoped to its org."""
        return (
            session.query(WorkflowServiceModel)
            .filter(
                WorkflowServiceModel.organization_id == organization_id,
                WorkflowServiceModel.id == service_id,
            )
            .first()
        )

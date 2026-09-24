"""Persistence adapters for entities."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, Date, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql import func
from sqlalchemy.types import JSON  # legacy ORMs (Entity/EntityRelation/EntityEvent) still on JSON

from common.auto_number import apply_auto_number_defaults, auto_number_field_ids
from common.identifier_template import (
    SEQ_COUNTER_KEY_PREFIX,
    format_seq,
    has_seq_token,
    next_suffixed,
    parse_tokens,
    prefix_context,
    render_identifier,
)
from common.logger import logger
from database.manager import Base
from exceptions import ConflictError, NotFoundError, PersistenceError, ValidationError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from forms.db_models import FormsModelService

from entities.models.interface import (
    IDENTIFIER_FIELD_KEY,
    EntityEventRecord,
    EntityRecord,
    EntityRelation as EntityRelationContract,
    EntityStateRecord,
    EntityType,
    EntityTypeRelation,
    FieldDefinition,
    FormConfigContract,
    RelationType,
    local_field_name,
    parent_id_field_name,
)
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRecordUpdateRequest,
    EntityRelationCreateRequest,
    EntityRelationDeclarationCreateRequest,
    EntityRelationDeclarationUpdateRequest,
    EntityTypeCreateRequest,
    EntityTypeRelationCreateRequest,
    EntityTypeUpdateRequest,
    UpsertFormConfigRequest,
)


def _definitions_schema() -> str:
    """Return the Postgres schema that holds canonical type/workflow definitions."""
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def _runtime_schema() -> str:
    """Return the Postgres schema that holds runtime entity records and enrollments."""
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_runtime"


def _audit_schema() -> str:
    """Return the Postgres schema that holds append-only audit tables."""
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_audit"


# ── SQLAlchemy ORM models ─────────────────────────────────────────────────────


class EntityTypeModel(Base):
    """Canonical entity type registry. Lives in the `_definitions` schema."""

    __tablename__ = "entity_types"
    __table_args__ = (
        Index("ix_entity_types_organization_id", "organization_id"),
        Index("ix_entity_types_org_name_active", "organization_id", "name", "is_active"),
        Index(
            "uq_entity_types_org_name_version_active",
            "organization_id", "name", "version",
            unique=True,
            postgresql_where=sa.text("is_active = TRUE"),
        ),
        {"schema": _definitions_schema()},
    )

    entity_type_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    schema = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EntityTypeRelationModel(Base):
    """Declared relation between two entity types, incl. field-inheritance config.
    Lives in the `_definitions` schema."""

    __tablename__ = "entity_type_relations"
    __table_args__ = (
        Index(
            "uq_entity_type_relations_active_org_from_to",
            "organization_id",
            "from_entity_type_id",
            "to_entity_type_id",
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        ),
        Index("ix_entity_type_relations_org_from", "organization_id", "from_entity_type_id"),
        {"schema": _definitions_schema()},
    )

    relation_def_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    from_entity_type_id = Column(String(36), nullable=False)
    to_entity_type_id = Column(String(36), nullable=False)
    relation_name = Column(String(128), nullable=True)
    relation_type = Column(String(32), nullable=False, default=RelationType.SNAPSHOT.value)
    relation_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class EntityRecordModel(Base):
    """Canonical runtime entity instance. Lives in the `_runtime` schema."""

    __tablename__ = "entities"
    __table_args__ = (
        Index("ix_runtime_entities_organization_id", "organization_id"),
        Index("ix_runtime_entities_entity_type_id", "entity_type_id"),
        Index(
            "ix_runtime_entities_org_type_active",
            "organization_id",
            "entity_type_id",
            "archived_at",
        ),
        Index(
            "ix_runtime_entities_org_type_active_created",
            "organization_id",
            "entity_type_id",
            "archived_at",
            "created_at",
            "entity_id",
        ),
        {"schema": _runtime_schema()},
    )

    entity_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    entity_type_id = Column(String(36), nullable=False)
    data = Column(JSONB, nullable=False, default=dict)
    custom_form_schema = Column(JSONB, nullable=True)
    custom_form_data = Column(JSONB, nullable=True)
    owner_id = Column(String(128), nullable=True)
    assignee_id = Column(String(128), nullable=True)
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    archived_at = Column(DateTime(timezone=True), nullable=True)


class EntityRelationModel(Base):
    """Directed edge between two runtime entities. Lives in the `_runtime` schema."""

    __tablename__ = "entity_relations"
    __table_args__ = (
        UniqueConstraint(
            "from_entity_id",
            "to_entity_id",
            "relation_type",
            name="uq_entity_relations_from_to_type",
        ),
        Index(
            "ix_runtime_entity_relations_from_type",
            "from_entity_id",
            "relation_type",
        ),
        Index(
            "ix_runtime_entity_relations_to_type",
            "to_entity_id",
            "relation_type",
        ),
        Index("ix_runtime_entity_relations_organization_id", "organization_id"),
        {"schema": _runtime_schema()},
    )

    relation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    from_entity_id = Column(String(36), nullable=False)
    to_entity_id = Column(String(36), nullable=False)
    relation_type = Column(String(128), nullable=False)
    relation_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EntityStateRuntimeModel(Base):
    """One workflow enrollment for a runtime entity. Lives in `_runtime` schema.

    Synthetic `state_id` PK lets a single entity hold many concurrent state
    rows (one per workflow enrollment). `(entity_id, workflow_id)` is unique.
    `workflow_id` is currently a plain column; the FK to `definitions.workflows`
    will land once the legacy table is fully retired.
    """

    __tablename__ = "entity_state"
    __table_args__ = (
        UniqueConstraint("entity_id", "workflow_id", name="uq_entity_state_entity_workflow"),
        Index("ix_runtime_entity_state_organization_id", "organization_id"),
        Index("ix_runtime_entity_state_entity_id", "entity_id"),
        Index("ix_runtime_entity_state_workflow_id", "workflow_id"),
        Index(
            "ix_runtime_entity_state_org_state_created",
            "organization_id",
            "current_state",
            "created_at",
            "state_id",
        ),
        Index(
            "ix_runtime_entity_state_org_workflow_created",
            "organization_id",
            "workflow_id",
            "created_at",
            "state_id",
        ),
        {"schema": _runtime_schema()},
    )

    state_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    entity_id = Column(String(36), nullable=False)
    workflow_id = Column(String(36), nullable=False)
    current_state = Column(String(128), nullable=False)
    state_version = Column(Integer, nullable=False, default=0)
    state_entered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_transition_at = Column(DateTime(timezone=True), nullable=True)
    sla_due_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class EntityEventAuditModel(Base):
    """Per-entity append-only event row. Lives in the `_audit` schema."""

    __tablename__ = "entity_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_entity_events_org_idempotency_key",
        ),
        Index("ix_audit_entity_events_entity_occurred", "entity_id", "occurred_at"),
        Index("ix_audit_entity_events_organization_id", "organization_id"),
        Index("ix_audit_entity_events_event_type", "event_type"),
        {"schema": _audit_schema()},
    )

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    entity_id = Column(String(36), nullable=False)
    event_type = Column(String(128), nullable=False)
    actor_type = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=True)
    actor_name = Column(String(255), nullable=True)
    actor_role = Column(String(64), nullable=True)
    correlation_id = Column(String(36), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)



@dataclass
class FormConfigRecord:
    organization_id: str
    form_key: str
    fields: list[FieldDefinition] = field(default_factory=list)
    version: int = 1


class AutoNumberCounterModel(Base):
    """Per-(org, entity_type, field) sequential counter for auto_number fields."""

    __tablename__ = "auto_number_counters"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type_id",
            "field_key",
            name="uq_auto_number_counters_org_type_field",
        ),
        Index("ix_auto_number_counters_org_type", "organization_id", "entity_type_id"),
        {"schema": _runtime_schema()},
    )

    counter_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    entity_type_id = Column(String(36), nullable=False)
    field_key = Column(String(128), nullable=False)
    current_value = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def _get_next_auto_number(
    session: "Session",
    organization_id: str,
    entity_type_id: str,
    field_key: str,
) -> int:
    """Atomically increment and return the next sequential value for a field counter.

    Uses PostgreSQL INSERT ... ON CONFLICT DO UPDATE ... RETURNING so each call
    within a transaction returns a unique monotonically increasing integer.
    The commit is left to the caller's transaction.
    """
    _schema = _runtime_schema()
    sql = sa.text(
        f"INSERT INTO {_schema}.auto_number_counters "
        "(counter_id, organization_id, entity_type_id, field_key, current_value) "
        "VALUES (:counter_id, :organization_id, :entity_type_id, :field_key, 1) "
        "ON CONFLICT (organization_id, entity_type_id, field_key) "
        "DO UPDATE SET current_value = auto_number_counters.current_value + 1 "
        "RETURNING current_value"
    )
    result = session.execute(sql, {
        "counter_id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "entity_type_id": entity_type_id,
        "field_key": field_key,
    })
    return result.scalar()


def _identifier_template_from_schema(schema_definition: dict | None) -> str | None:
    """Non-empty identifier_template string from an entity type schema, else None."""
    raw = (schema_definition or {}).get("identifier_template")
    template = str(raw).strip() if raw is not None else ""
    return template or None


def _existing_identifiers_for_base(
    session: "Session", organization_id: str, entity_type_id: str, base: str
) -> set[str]:
    """Identifiers equal to `base` or `base_<suffix>` for the type — archived excluded."""
    ident = EntityRecordModel.data.op("->>")(IDENTIFIER_FIELD_KEY)
    escaped = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (
        session.query(ident)
        .filter(
            EntityRecordModel.organization_id == organization_id,
            EntityRecordModel.entity_type_id == entity_type_id,
            EntityRecordModel.archived_at.is_(None),
            sa.or_(ident == base, ident.like(f"{escaped}\\_%", escape="\\")),
        )
        .all()
    )
    return {row[0] for row in rows if row[0]}


def _next_identifier_seq(
    session: "Session", organization_id: str, entity_type_id: str, scope: str
) -> str:
    """Next prefix-scoped counter value (spec §3: '{{seq}}' is per prefix context)."""
    counter_key = (SEQ_COUNTER_KEY_PREFIX + scope)[:100]
    return format_seq(
        _get_next_auto_number(session, organization_id, entity_type_id, counter_key)
    )


def apply_identifier_template(
    service: "EntitiesModelService | None",
    session: "Session",
    *,
    organization_id: str,
    entity_type: EntityTypeModel,
    entity_id: str | None,
    data: dict,
) -> dict:
    """Generate and set data['identifier'] when the type has a template (spec §4).

    `entity_id=None` (or `service=None`) skips reference-token resolution —
    for create paths that carry no relations (public forms). Client-supplied
    identifier is always overwritten."""
    template = _identifier_template_from_schema(entity_type.schema)
    if template is None:
        return data

    values = dict(data or {})
    if entity_id is not None and service is not None and parse_tokens(template):
        overlay = service._resolve_inherited_fields_with_session(
            session,
            organization_id=organization_id,
            entity_type_id=entity_type.entity_type_id,
            entity_id=entity_id,
        )
        values.update(overlay or {})
        # `{{<related_type>_identifier}}` resolves straight off the relation
        # link — no reference form field needed. Mapped fields win on clash.
        if any(
            t.endswith("_identifier") and t not in values
            for t in parse_tokens(template)
        ):
            related = service._related_identifier_values_with_session(
                session,
                organization_id=organization_id,
                entity_type_id=entity_type.entity_type_id,
                entity_id=entity_id,
            )
            for key, value in related.items():
                values.setdefault(key, value)

    scope = prefix_context(template, values)
    seq_value = None
    if has_seq_token(template):
        seq_value = _next_identifier_seq(
            session, organization_id, entity_type.entity_type_id, scope
        )

    base = render_identifier(template, values, seq_value=seq_value)
    if not base:
        # Empty render: counter fallback keyed by the (empty) prefix context (spec §3.5).
        base = _next_identifier_seq(
            session, organization_id, entity_type.entity_type_id, scope
        )

    existing = _existing_identifiers_for_base(
        session, organization_id, entity_type.entity_type_id, base
    )
    out = dict(data or {})
    out[IDENTIFIER_FIELD_KEY] = next_suffixed(base, existing)
    return out


class AuthEventAuditModel(Base):
    """Auth audit log row. Lives in the `_audit` schema, FK-free on entity_id
    so synthetic auth subjects (unknown email, pre-user login attempts) work
    without a runtime.entities row to point at."""

    __tablename__ = "auth_events"
    __table_args__ = (
        Index("ix_audit_auth_events_organization_id", "organization_id"),
        Index("ix_audit_auth_events_event_type", "event_type"),
        Index("ix_audit_auth_events_user_id", "user_id"),
        Index("ix_audit_auth_events_org_occurred", "organization_id", "occurred_at"),
        {"schema": _audit_schema()},
    )

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    event_type = Column(String(128), nullable=False)
    user_id = Column(String(36), nullable=True)
    email = Column(String(320), nullable=True)
    actor_type = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=True)
    correlation_id = Column(String(36), nullable=True)
    payload = Column(JSONB, nullable=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EntitiesModelService:
    """Persistence service for entity metadata + runtime entity records.

    Backed entirely by Postgres via `database_service_manager.postgres_db_service()`.
    `form_config` continues to use a transient in-process registry pending its
    own DB-backed rewrite.
    """

    def __init__(
        self, database_service_manager, forms_db_model_service: FormsModelService | None = None
    ) -> None:
        """Bind to the shared Postgres pool.

        Postgres is mandatory — there is no in-memory fallback for the
        entities suite because the new schema-isolated tables (definitions /
        runtime / audit) only exist in Postgres."""
        if database_service_manager is None or not hasattr(
            database_service_manager, "postgres_db_service"
        ):
            raise PersistenceError(
                "EntitiesModelService requires a database_service_manager with postgres_db_service()"
            )
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = self.database_manager.postgres_db_service()
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.module_name = "entities"
        self.forms_db_model_service = forms_db_model_service
        self._form_config_registry: dict[tuple[str, str], FormConfigRecord] = {}

    def _session(self) -> Session:
        """Open a fresh SQLAlchemy session against the shared pool."""
        return self.current_db.get_db_session()

    @contextmanager
    def _db_session(self):
        """Context manager that yields a session and guarantees `close()` on exit."""
        session = self._session()
        try:
            yield session
        finally:
            session.close()

    def _active_declarations_by_to_type(
        self,
        session: Session,
        *,
        organization_id: str,
        to_entity_type_id: str,
    ) -> list[EntityTypeRelationModel]:
        """Return active (non-deleted) relation declarations targeting an entity type."""
        return (
            session.query(EntityTypeRelationModel)
            .filter_by(organization_id=organization_id, to_entity_type_id=to_entity_type_id)
            .filter(EntityTypeRelationModel.deleted_at.is_(None))
            .all()
        )

    def _target_field_local_names(
        self,
        declarations: list[EntityTypeRelationModel],
    ) -> set[str]:
        """Collect the target field local names declared across relation rows."""
        names: set[str] = set()
        for declaration in declarations:
            for target_key in dict(declaration.relation_metadata or {}).values():
                if not isinstance(target_key, str):
                    continue
                names.add(local_field_name(target_key))
        return names

    def _strip_inherited_fields_with_session(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_type_id: str,
        data: dict[str, object] | None,
    ) -> dict[str, object]:
        """Return entity data with declared inherited target fields removed."""
        payload = dict(data or {})
        declarations = self._active_declarations_by_to_type(
            session, organization_id=organization_id, to_entity_type_id=entity_type_id
        )
        target_field_names = self._target_field_local_names(declarations)
        if not target_field_names:
            return payload
        return {key: value for key, value in payload.items() if key not in target_field_names}

    def strip_inherited_fields(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        data: dict[str, object] | None,
    ) -> dict[str, object]:
        """Return entity data without inherited fields.

        Safety net for read paths so stale inherited values previously
        persisted by older clients do not leak back into responses.
        """
        with self._db_session() as session:
            try:
                return self._strip_inherited_fields_with_session(
                    session,
                    organization_id=organization_id,
                    entity_type_id=entity_type_id,
                    data=data,
                )
            except Exception as exc:
                logger.debug("strip_inherited_fields failed: %s", exc)
                raise PersistenceError(f"Unable to sanitize entity data: {exc}") from exc

    # ── EntityType (canonical schema registry) ───────────────────────────────

    def create_entity_type(self, request: EntityTypeCreateRequest) -> EntityType:
        """Persist a new entity type definition."""
        entity_type_id = str(uuid.uuid4())
        with self._db_session() as session:
            try:
                model = EntityTypeModel(
                    entity_type_id=entity_type_id,
                    organization_id=request.organization_id,
                    name=request.name,
                    description=request.description,
                    schema=dict(request.schema_definition),
                    version=request.version,
                    is_active=request.is_active,
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                return self._entity_type(model)
            except IntegrityError as exc:
                session.rollback()
                logger.debug("create_entity_type IntegrityError: %s", exc)
                raise ConflictError(
                    f"entity type '{request.name}' version {request.version} already exists"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_entity_type failed: %s", exc)
                raise PersistenceError(f"Unable to create entity type: {exc}") from exc

    def get_entity_type_name_by_id(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        db: Session | None = None,
    ) -> str | None:
        """Return the entity type name for the given entity_type_id, or None if not found."""
        def _query(session: Session) -> str | None:
            try:
                model = session.query(EntityTypeModel).filter_by(
                    entity_type_id=entity_type_id, organization_id=organization_id
                ).first()
                return str(model.name) if model else None
            except SQLAlchemyError as exc:
                logger.warning(f"get_entity_type_name_by_id failed (entity_type_id={entity_type_id}): {exc}")
                return None

        if db is not None:
            return _query(db)
        with self._db_session() as session:
            return _query(session)

    def get_entity_type_by_name(
        self,
        *,
        organization_id: str,
        name: str,
    ) -> EntityType | None:
        """Fetch the latest-version entity type by name, scoped to the organization."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityTypeModel)
                    .filter_by(organization_id=organization_id, name=name)
                    .order_by(EntityTypeModel.version.desc())
                    .first()
                )
                return self._entity_type(model)
            except Exception as exc:
                logger.debug("get_entity_type_by_name failed: %s", exc)
                raise PersistenceError(f"Unable to fetch entity type: {exc}") from exc

    def list_entity_types_v2(
        self, *, organization_id: str, include_inactive: bool = False
    ) -> list[EntityType]:
        """List entity types for an organization (canonical registry).
        By default only active types are returned; pass include_inactive=True
        for admin/audit views."""
        with self._db_session() as session:
            try:
                q = session.query(EntityTypeModel).filter_by(organization_id=organization_id)
                if not include_inactive:
                    q = q.filter_by(is_active=True)
                rows = q.order_by(EntityTypeModel.name.asc(), EntityTypeModel.version.asc()).all()
                return [self._entity_type(row) for row in rows]
            except Exception as exc:
                logger.debug("list_entity_types_v2 failed: %s", exc)
                raise PersistenceError(f"Unable to list entity types: {exc}") from exc

    def update_entity_type_by_name(
        self,
        *,
        organization_id: str,
        name: str,
        request: EntityTypeUpdateRequest,
    ) -> EntityType | None:
        """Update mutable fields on the latest-version entity type by name."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityTypeModel)
                    .filter_by(organization_id=organization_id, name=name)
                    .order_by(EntityTypeModel.version.desc())
                    .first()
                )
                if model is None:
                    return None
                if request.name is not None:
                    model.name = request.name
                if request.description is not None:
                    model.description = request.description
                if request.schema_definition is not None:
                    model.schema = dict(request.schema_definition)
                if request.is_active is not None:
                    model.is_active = request.is_active
                session.commit()
                session.refresh(model)
                return self._entity_type(model)
            except IntegrityError as exc:
                session.rollback()
                logger.debug("update_entity_type_by_name IntegrityError: %s", exc)
                raise ConflictError(f"Unable to update entity type: {exc}") from exc
            except Exception as exc:
                session.rollback()
                logger.debug("update_entity_type_by_name failed: %s", exc)
                raise PersistenceError(f"Unable to update entity type: {exc}") from exc

    def entity_type_exists_in_org(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
    ) -> bool:
        """Tenant-scoped existence check used as a pre-flight for entity record
        creation. Backstops the composite FK with a clean 400 instead of 500.
        Archived (is_active=False) types still pass — the type exists, so
        existing workflows can continue creating records for it."""
        with self._db_session() as session:
            try:
                return (
                    session.query(EntityTypeModel)
                    .filter_by(
                        organization_id=organization_id,
                        entity_type_id=entity_type_id,
                    )
                    .first()
                    is not None
                )
            except Exception as exc:
                logger.debug("entity_type_exists_in_org failed: %s", exc)
                raise PersistenceError(f"Unable to look up entity type: {exc}") from exc

    def archive_entity_type_by_name(
        self,
        *,
        organization_id: str,
        name: str,
    ) -> EntityType | None:
        """Soft-delete: set is_active=False and stamp archived_at."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityTypeModel)
                    .filter_by(organization_id=organization_id, name=name, is_active=True)
                    .order_by(EntityTypeModel.version.desc())
                    .first()
                )
                if model is None:
                    return None
                model.is_active = False
                model.archived_at = datetime.now(UTC)
                session.commit()
                session.refresh(model)
                return self._entity_type(model)
            except Exception as exc:
                session.rollback()
                logger.error("archive_entity_type_by_name failed: %s", exc)
                raise PersistenceError(f"Unable to archive entity type: {exc}") from exc

    @staticmethod
    def _entity_type(item: EntityTypeModel | None) -> EntityType | None:
        """Hydrate an `EntityTypeModel` row into an `EntityType` contract."""
        if item is None:
            return None
        return EntityType(
            entity_type_id=item.entity_type_id,
            organization_id=item.organization_id,
            name=item.name,
            description=item.description,
            schema_definition=dict(item.schema or {}),
            version=item.version,
            is_active=item.is_active,
            archived_at=item.archived_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    # ── EntityTypeRelation (relation definitions between entity types) ────────

    def create_entity_type_relation(
        self, request: EntityTypeRelationCreateRequest
    ) -> EntityTypeRelation:
        """Persist a new entity type relation definition."""
        if not request.from_entity_type_id:
            raise ValidationError("from_entity_type_id is required")
        if not self.entity_type_exists_in_org(
            organization_id=request.organization_id,
            entity_type_id=request.from_entity_type_id,
        ):
            raise ValidationError(
                f"entity type '{request.from_entity_type_id}' not found in organization "
                f"'{request.organization_id}'"
            )
        if not self.entity_type_exists_in_org(
            organization_id=request.organization_id,
            entity_type_id=request.to_entity_type_id,
        ):
            raise ValidationError(
                f"entity type '{request.to_entity_type_id}' not found in organization "
                f"'{request.organization_id}'"
            )
        with self._db_session() as session:
            try:
                forward = EntityTypeRelationModel(
                    organization_id=request.organization_id,
                    from_entity_type_id=request.from_entity_type_id,
                    to_entity_type_id=request.to_entity_type_id,
                    relation_name=request.relation_name,
                )
                reverse = EntityTypeRelationModel(
                    organization_id=request.organization_id,
                    from_entity_type_id=request.to_entity_type_id,
                    to_entity_type_id=request.from_entity_type_id,
                    relation_name=request.relation_name,
                )
                session.add(forward)
                session.add(reverse)
                session.commit()
                session.refresh(forward)
                return self._entity_type_relation(forward)
            except IntegrityError as exc:
                session.rollback()
                logger.debug("create_entity_type_relation IntegrityError: %s", exc)
                raise ConflictError(f"Relation already exists: {exc}") from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_entity_type_relation failed: %s", exc)
                raise PersistenceError(f"Unable to create entity type relation: {exc}") from exc

    def list_entity_type_relations(
        self,
        *,
        organization_id: str,
        from_entity_type_id: str | None = None,
    ) -> list[EntityTypeRelation]:
        """List entity type relation definitions, optionally filtered by source type."""
        with self._db_session() as session:
            try:
                q = session.query(EntityTypeRelationModel).filter_by(
                    organization_id=organization_id
                )
                if from_entity_type_id:
                    q = q.filter_by(from_entity_type_id=from_entity_type_id)
                rows = q.order_by(EntityTypeRelationModel.relation_name.asc()).all()
                return [self._entity_type_relation(row) for row in rows]
            except Exception as exc:
                logger.debug("list_entity_type_relations failed: %s", exc)
                raise PersistenceError(f"Unable to list entity type relations: {exc}") from exc

    def list_entity_relation_declarations(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        direction: str = "from",
    ) -> list[EntityTypeRelation]:
        """List active (non-deleted) relation declarations involving an entity type.

        `direction`: "from" — the type is the provider; "to" — the type is the
        target; "both" — either side. Rows created via the legacy named-relation
        endpoints share this table and are returned as-is.
        """
        if direction not in {"from", "to", "both"}:
            raise ValidationError(f"invalid direction '{direction}'")
        with self._db_session() as session:
            try:
                q = session.query(EntityTypeRelationModel).filter(
                    EntityTypeRelationModel.organization_id == organization_id,
                    EntityTypeRelationModel.deleted_at.is_(None),
                )
                if direction == "from":
                    q = q.filter(EntityTypeRelationModel.from_entity_type_id == entity_type_id)
                elif direction == "to":
                    q = q.filter(EntityTypeRelationModel.to_entity_type_id == entity_type_id)
                else:
                    q = q.filter(
                        sa.or_(
                            EntityTypeRelationModel.from_entity_type_id == entity_type_id,
                            EntityTypeRelationModel.to_entity_type_id == entity_type_id,
                        )
                    )
                rows = q.order_by(EntityTypeRelationModel.created_at.asc()).all()
                return [self._entity_type_relation(row) for row in rows]
            except ValidationError:
                raise
            except Exception as exc:
                logger.debug("list_entity_relation_declarations failed: %s", exc)
                raise PersistenceError(f"Unable to list relation declarations: {exc}") from exc

    def delete_entity_type_relation(self, *, organization_id: str, relation_def_id: str) -> bool:
        """Delete an entity type relation definition and its reverse row atomically."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(EntityTypeRelationModel)
                    .filter_by(organization_id=organization_id, relation_def_id=relation_def_id)
                    .first()
                )
                if row is None:
                    return False
                reverse = (
                    session.query(EntityTypeRelationModel)
                    .filter_by(
                        organization_id=organization_id,
                        from_entity_type_id=row.to_entity_type_id,
                        to_entity_type_id=row.from_entity_type_id,
                        relation_name=row.relation_name,
                    )
                    .first()
                )
                session.delete(row)
                if reverse is not None:
                    session.delete(reverse)
                session.commit()
                return True
            except Exception as exc:
                session.rollback()
                logger.debug("delete_entity_type_relation failed: %s", exc)
                raise PersistenceError(f"Unable to delete entity type relation: {exc}") from exc

    @staticmethod
    def _entity_type_relation(item: EntityTypeRelationModel | None) -> EntityTypeRelation | None:
        if item is None:
            return None
        return EntityTypeRelation(
            relation_def_id=item.relation_def_id,
            organization_id=item.organization_id,
            from_entity_type_id=item.from_entity_type_id,
            to_entity_type_id=item.to_entity_type_id,
            relation_name=item.relation_name,
            relation_type=RelationType(item.relation_type),
            relation_metadata=dict(item.relation_metadata or {}),
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.deleted_at,
        )

    # ── Relation declaration (field-inheritance) CRUD ────────────────────────

    def create_entity_relation_declaration(
        self, request: EntityRelationDeclarationCreateRequest, *, default_relation_type: str
    ) -> EntityTypeRelation:
        """Persist a new field-inheritance relation declaration between two entity types."""
        if not self.entity_type_exists_in_org(
            organization_id=request.organization_id,
            entity_type_id=request.from_entity_type_id,
        ):
            raise ValidationError(
                f"entity type '{request.from_entity_type_id}' not found in organization "
                f"'{request.organization_id}'"
            )
        if not self.entity_type_exists_in_org(
            organization_id=request.organization_id,
            entity_type_id=request.to_entity_type_id,
        ):
            raise ValidationError(
                f"entity type '{request.to_entity_type_id}' not found in organization "
                f"'{request.organization_id}'"
            )
        relation_type = (
            request.relation_type.value
            if request.relation_type is not None
            else default_relation_type
        )
        with self._db_session() as session:
            try:
                model = EntityTypeRelationModel(
                    organization_id=request.organization_id,
                    from_entity_type_id=request.from_entity_type_id,
                    to_entity_type_id=request.to_entity_type_id,
                    relation_name=None,
                    relation_type=relation_type,
                    relation_metadata=dict(request.relation_metadata or {}),
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                return self._entity_type_relation(model)
            except (ValidationError, ConflictError):
                session.rollback()
                raise
            except IntegrityError as exc:
                session.rollback()
                logger.debug("create_entity_relation_declaration IntegrityError: %s", exc)
                raise ConflictError(
                    "an active declaration already exists for this entity type pair"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_entity_relation_declaration failed: %s", exc)
                raise PersistenceError(f"Unable to create relation declaration: {exc}") from exc

    def update_entity_relation_declaration_metadata(
        self,
        *,
        organization_id: str,
        relation_def_id: str,
        request: EntityRelationDeclarationUpdateRequest,
    ) -> EntityTypeRelation | None:
        """Patch relation_metadata on an active declaration. No retroactive effect."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityTypeRelationModel)
                    .filter_by(organization_id=organization_id, relation_def_id=relation_def_id)
                    .filter(EntityTypeRelationModel.deleted_at.is_(None))
                    .first()
                )
                if model is None:
                    return None
                model.relation_metadata = dict(request.relation_metadata or {})
                session.commit()
                session.refresh(model)
                return self._entity_type_relation(model)
            except (ValidationError, ConflictError):
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("update_entity_relation_declaration_metadata failed: %s", exc)
                raise PersistenceError(f"Unable to update relation declaration: {exc}") from exc

    def soft_delete_entity_relation_declaration(
        self, *, organization_id: str, relation_def_id: str
    ) -> EntityTypeRelation | None:
        """Soft-delete an active declaration. Snapshot rows are left in place, dormant."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityTypeRelationModel)
                    .filter_by(organization_id=organization_id, relation_def_id=relation_def_id)
                    .filter(EntityTypeRelationModel.deleted_at.is_(None))
                    .first()
                )
                if model is None:
                    return None
                model.deleted_at = datetime.now(UTC)
                session.commit()
                session.refresh(model)
                return self._entity_type_relation(model)
            except Exception as exc:
                session.rollback()
                logger.debug("soft_delete_entity_relation_declaration failed: %s", exc)
                raise PersistenceError(f"Unable to delete relation declaration: {exc}") from exc

    def get_active_relation_declarations_by_to_type(
        self, *, organization_id: str, to_entity_type_id: str
    ) -> list[EntityTypeRelation]:
        """Public read: active relation declarations targeting an entity type."""
        with self._db_session() as session:
            try:
                rows = self._active_declarations_by_to_type(
                    session,
                    organization_id=organization_id,
                    to_entity_type_id=to_entity_type_id,
                )
                return [self._entity_type_relation(row) for row in rows]
            except Exception as exc:
                logger.debug("get_active_relation_declarations_by_to_type failed: %s", exc)
                raise PersistenceError(f"Unable to list relation declarations: {exc}") from exc

    def get_active_relation_declarations_by_to_types(
        self, *, organization_id: str, to_entity_type_ids: set[str]
    ) -> list[EntityTypeRelation]:
        """Batched sibling of `get_active_relation_declarations_by_to_type` — one query
        for every target entity type at once, via `to_entity_type_id.in_(...)`."""
        if not to_entity_type_ids:
            return []
        with self._db_session() as session:
            try:
                rows = (
                    session.query(EntityTypeRelationModel)
                    .filter(
                        EntityTypeRelationModel.organization_id == organization_id,
                        EntityTypeRelationModel.to_entity_type_id.in_(to_entity_type_ids),
                        EntityTypeRelationModel.deleted_at.is_(None),
                    )
                    .all()
                )
                return [self._entity_type_relation(row) for row in rows]
            except Exception as exc:
                logger.debug("get_active_relation_declarations_by_to_types failed: %s", exc)
                raise PersistenceError(f"Unable to list relation declarations: {exc}") from exc

    def get_active_relation_declaration_for_pair(
        self,
        *,
        organization_id: str,
        from_entity_type_id: str,
        to_entity_type_id: str,
    ) -> EntityTypeRelation | None:
        """Public read: the single active declaration for one (from, to) type pair, if any."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityTypeRelationModel)
                    .filter_by(
                        organization_id=organization_id,
                        from_entity_type_id=from_entity_type_id,
                        to_entity_type_id=to_entity_type_id,
                    )
                    .filter(EntityTypeRelationModel.deleted_at.is_(None))
                    .first()
                )
                return self._entity_type_relation(model)
            except Exception as exc:
                logger.debug("get_active_relation_declaration_for_pair failed: %s", exc)
                raise PersistenceError(f"Unable to fetch relation declaration: {exc}") from exc

    # ── EntityRecord (runtime entity instances) ─────────────────────────────

    def get_auto_number_previews(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
    ) -> dict[str, str]:
        """Return next formatted auto_number value per field (current_value + 1, not yet incremented)."""
        from common.auto_number import _format_value

        with self._db_session() as session:
            schema_fields = self._auto_number_schema_fields(session, organization_id, entity_type_id)
            auto_fields = [
                f for f in schema_fields
                if str(f.get("type", "")).lower() == "auto_number"
            ]
            if not auto_fields:
                return {}

            counters = {
                row.field_key: row.current_value
                for row in session.query(AutoNumberCounterModel).filter_by(
                    organization_id=organization_id,
                    entity_type_id=entity_type_id,
                ).all()
            }

            result = {}
            for field in auto_fields:
                field_id = field.get("field") or field.get("name")
                if not field_id:
                    continue
                cfg = field.get("auto_number_config") or {}
                current = counters.get(str(field_id), 0)
                result[str(field_id)] = _format_value(current + 1, cfg)
            return result

    def _auto_number_schema_fields(
        self, session, organization_id: str, entity_type_id: str
    ) -> list[dict]:
        """Return all active-schema field dicts for an entity type (by id)."""
        from forms.db_models import active_schema_fields_by_type_id

        return active_schema_fields_by_type_id(session, organization_id, entity_type_id)

    def _apply_auto_number_defaults(
        self,
        session,
        *,
        organization_id: str,
        entity_type_id: str,
        data: dict,
    ) -> dict:
        """Fill auto_number fields defined on the entity type's active schema(s)."""
        schema_fields = self._auto_number_schema_fields(
            session, organization_id, entity_type_id
        )
        if not any(
            str(f.get("type", "")).lower() == "auto_number" for f in schema_fields
        ):
            return data

        out = dict(data or {})
        apply_auto_number_defaults(
            schema_fields,
            out,
            lambda field_key: _get_next_auto_number(session, organization_id, entity_type_id, field_key),
            overwrite=True,
        )
        return out

    def _lock_auto_number_on_update(
        self,
        session,
        *,
        organization_id: str,
        entity_type_id: str,
        old_data: dict,
        new_data: dict,
    ) -> dict:
        """Prevent edits to auto_number fields: any existing value is forced back
        onto the incoming data, and genuinely-missing values (legacy records) are
        backfilled. The generated identifier can never be changed or removed."""
        schema_fields = self._auto_number_schema_fields(
            session, organization_id, entity_type_id
        )
        field_ids = auto_number_field_ids(schema_fields)
        if not field_ids:
            return new_data

        out = dict(new_data or {})
        old = old_data or {}
        for field_id in field_ids:
            if old.get(field_id):
                out[field_id] = old[field_id]
        apply_auto_number_defaults(
            schema_fields,
            out,
            lambda field_key: _get_next_auto_number(session, organization_id, entity_type_id, field_key),
        )
        return out

    def create_entity_record(
        self,
        request: EntityRecordCreateRequest,
        *,
        require_reference_sources: bool = True,
    ) -> EntityRecord:
        """Persist a new runtime entity record, plus one `entity_relations` link
        row per matched active declaration targeting its entity type — same
        transaction. Each entry in `request.source_entity_ids` is matched to
        the active declaration whose `from_entity_type_id` equals that
        source's own type."""
        entity_id = str(uuid.uuid4())
        with self._db_session() as session:
            try:
                sanitized_data = self._strip_inherited_fields_with_session(
                    session,
                    organization_id=request.organization_id,
                    entity_type_id=request.entity_type_id,
                    data=request.data,
                )
                sanitized_data = self._apply_auto_number_defaults(
                    session,
                    organization_id=request.organization_id,
                    entity_type_id=request.entity_type_id,
                    data=sanitized_data,
                )
                type_model = (
                    session.query(EntityTypeModel)
                    .filter_by(
                        organization_id=request.organization_id,
                        entity_type_id=request.entity_type_id,
                    )
                    .first()
                )
                templated = (
                    type_model is not None
                    and _identifier_template_from_schema(type_model.schema) is not None
                )
                if templated:
                    # Template mode ignores client-supplied identifiers; strip
                    # before the first flush so a duplicate value can't trip
                    # the unique index ahead of generation.
                    sanitized_data = dict(sanitized_data or {})
                    sanitized_data.pop(IDENTIFIER_FIELD_KEY, None)
                model = EntityRecordModel(
                    entity_id=entity_id,
                    organization_id=request.organization_id,
                    entity_type_id=request.entity_type_id,
                    data=sanitized_data,
                    owner_id=request.owner_id,
                    assignee_id=request.assignee_id,
                    due_date=request.due_date,
                )
                session.add(model)
                session.flush()

                declarations = self._active_declarations_by_to_type(
                    session,
                    organization_id=request.organization_id,
                    to_entity_type_id=request.entity_type_id,
                )
                if declarations:
                    self._link_sources_to_new_entity(
                        session,
                        organization_id=request.organization_id,
                        entity_id=entity_id,
                        declarations=declarations,
                        source_entity_ids=list(request.source_entity_ids or []),
                        require_reference_sources=require_reference_sources,
                    )

                if templated and type_model is not None:
                    self._apply_identifier_template_in_txn(
                        session,
                        organization_id=request.organization_id,
                        type_model=type_model,
                        entity_id=entity_id,
                        model=model,
                    )

                session.commit()
                session.refresh(model)
                return self._entity_record(model)
            except ValidationError:
                session.rollback()
                raise
            except IntegrityError as exc:
                session.rollback()
                logger.debug("create_entity_record IntegrityError: %s", exc)
                raise ConflictError(f"Unable to create entity record: {exc}") from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_entity_record failed: %s", exc)
                raise PersistenceError(f"Unable to create entity record: {exc}") from exc

    def _apply_identifier_template_in_txn(
        self,
        session: Session,
        *,
        organization_id: str,
        type_model: EntityTypeModel,
        entity_id: str,
        model: EntityRecordModel,
    ) -> None:
        """Template-mode identifier generation inside the create transaction.
        Caller has already established that `type_model` has a template.

        Runs after relations are linked (reference tokens resolve from the
        uncommitted link rows) and before commit. Retries once on the partial
        unique index — a concurrent create can steal the suffix between the
        collision query and the flush."""
        # ponytail: single retry; move to counter-keyed identifiers if
        # contention ever shows up in logs
        for attempt in (1, 2):
            try:
                with session.begin_nested():
                    model.data = apply_identifier_template(
                        self,
                        session,
                        organization_id=organization_id,
                        entity_type=type_model,
                        entity_id=entity_id,
                        data=dict(model.data or {}),
                    )
                    session.flush()
                break
            except IntegrityError as exc:
                if attempt == 2:
                    raise
                logger.debug(
                    "identifier suffix collision, retrying: %s",
                    exc,
                    extra={"organization_id": organization_id, "entity_id": entity_id},
                )

    def _related_identifier_values_with_session(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_type_id: str,
        entity_id: str,
    ) -> dict[str, object]:
        """`<related_type>_identifier` values from linked source entities.

        One entry per declaration targeting this type whose link exists —
        the linked provider's own identifier, keyed `<provider_name>_identifier`.
        First declaration wins per provider name."""
        values: dict[str, object] = {}
        declarations = self._active_declarations_by_to_type(
            session, organization_id=organization_id, to_entity_type_id=entity_type_id
        )
        for declaration in declarations:
            name = (
                session.query(EntityTypeModel.name)
                .filter_by(
                    organization_id=organization_id,
                    entity_type_id=declaration.from_entity_type_id,
                )
                .scalar()
            )
            if not name:
                continue
            token = f"{local_field_name(name)}_identifier"
            if token in values:
                continue
            link = self._find_link_for_declaration(
                session,
                organization_id=organization_id,
                to_entity_id=entity_id,
                from_entity_type_id=declaration.from_entity_type_id,
                relation_type=declaration.relation_type,
            )
            if link is None:
                continue
            source = (
                session.query(EntityRecordModel)
                .filter_by(organization_id=organization_id, entity_id=link.from_entity_id)
                .first()
            )
            if source is not None:
                values[token] = (source.data or {}).get(IDENTIFIER_FIELD_KEY)
        return values

    def related_identifier_tokens(
        self, organization_id: str, entity_type_name: str
    ) -> set[str]:
        """Valid `<related_type>_identifier` template tokens for a type name —
        one per active relation declaration targeting it. Empty on any failure."""
        try:
            with self._db_session() as session:
                type_id = (
                    session.query(EntityTypeModel.entity_type_id)
                    .filter_by(organization_id=organization_id, name=entity_type_name)
                    .filter(EntityTypeModel.is_active.is_(True))
                    .scalar()
                )
                if not type_id:
                    return set()
                declarations = self._active_declarations_by_to_type(
                    session, organization_id=organization_id, to_entity_type_id=type_id
                )
                tokens: set[str] = set()
                for declaration in declarations:
                    name = (
                        session.query(EntityTypeModel.name)
                        .filter_by(
                            organization_id=organization_id,
                            entity_type_id=declaration.from_entity_type_id,
                        )
                        .scalar()
                    )
                    if name:
                        tokens.add(f"{local_field_name(name)}_identifier")
                return tokens
        except Exception as exc:
            logger.debug("related_identifier_tokens failed: %s", exc)
            return set()

    def get_identifier_template(
        self, organization_id: str, entity_type_id: str
    ) -> str | None:
        """Active identifier_template for the type, or None (manual mode)."""
        try:
            with self._db_session() as session:
                model = (
                    session.query(EntityTypeModel)
                    .filter_by(
                        organization_id=organization_id, entity_type_id=entity_type_id
                    )
                    .first()
                )
                if model is None:
                    return None
                return _identifier_template_from_schema(model.schema)
        except Exception as exc:
            logger.debug("get_identifier_template failed: %s", exc)
            return None

    def identifier_exists(
        self, organization_id: str, entity_type_id: str, identifier: str
    ) -> bool:
        """Point lookup for a taken identifier — archived rows excluded."""
        with self._db_session() as session:
            ident = EntityRecordModel.data.op("->>")(IDENTIFIER_FIELD_KEY)
            return session.query(
                session.query(EntityRecordModel)
                .filter(
                    EntityRecordModel.organization_id == organization_id,
                    EntityRecordModel.entity_type_id == entity_type_id,
                    EntityRecordModel.archived_at.is_(None),
                    ident == identifier,
                )
                .exists()
            ).scalar()

    def _entity_type_ids_for_sources(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_ids: list[str],
    ) -> dict[str, str]:
        """Return {entity_id: entity_type_id} for the given (non-archived) records."""
        if not entity_ids:
            return {}
        rows = (
            session.query(EntityRecordModel.entity_id, EntityRecordModel.entity_type_id)
            .filter(
                EntityRecordModel.organization_id == organization_id,
                EntityRecordModel.entity_id.in_(entity_ids),
                EntityRecordModel.archived_at.is_(None),
            )
            .all()
        )
        return {row[0]: row[1] for row in rows}

    def _link_sources_to_new_entity(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_id: str,
        declarations: list[EntityTypeRelationModel],
        source_entity_ids: list[str],
        require_reference_sources: bool = True,
    ) -> None:
        """Validate and link each provided source to its matching declaration,
        writing one `entity_relations` row per matched (declaration, source)
        pair. Raises ValidationError for missing/unmatched/required sources.

        Thin wrapper over `_link_sources_to_entity` for the creation call site,
        which is guaranteed to have no pre-existing links yet."""
        self._link_sources_to_entity(
            session,
            organization_id=organization_id,
            entity_id=entity_id,
            declarations=declarations,
            source_entity_ids=source_entity_ids,
            skip_existing_links=False,
            require_reference_sources=require_reference_sources,
        )

    def _link_sources_to_entity(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_id: str,
        declarations: list[EntityTypeRelationModel],
        source_entity_ids: list[str],
        skip_existing_links: bool,
        require_reference_sources: bool = True,
    ) -> None:
        """Validate and link each provided source to its matching declaration,
        writing one `entity_relations` row per matched (declaration, source)
        pair. Raises ValidationError for missing/unmatched/required sources.

        `skip_existing_links` — when True (linking sources onto an entity that
        already exists, e.g. after agent-driven creation), a declaration that
        already has a link row for this entity is left untouched instead of
        inserting a duplicate; there is no relinking. Always False at creation
        time, where the entity is guaranteed to have no existing links yet.
        """
        source_types = self._entity_type_ids_for_sources(
            session, organization_id=organization_id, entity_ids=source_entity_ids
        )
        missing = [sid for sid in source_entity_ids if sid not in source_types]
        if missing:
            raise ValidationError(
                f"source record(s) not found in your organization: {', '.join(missing)}"
            )
        type_to_source: dict[str, str] = {}
        for source_id, source_type_id in source_types.items():
            if source_type_id in type_to_source:
                raise ValidationError(
                    f"multiple source entities provided for the same provider type "
                    f"'{source_type_id}'"
                )
            type_to_source[source_type_id] = source_id

        declared_from_types = {declaration.from_entity_type_id for declaration in declarations}
        unmatched_types = set(type_to_source) - declared_from_types
        if unmatched_types:
            unmatched_ids = sorted(type_to_source[t] for t in unmatched_types)
            raise ValidationError(
                "source record(s) do not match any active relation declaration for "
                f"this entity type: {', '.join(unmatched_ids)}"
            )

        for declaration in declarations:
            source_id = type_to_source.get(declaration.from_entity_type_id)
            if source_id is None:
                # REFERENCE declarations require a linked source — except when the
                # caller opts out (agent/document-driven creation, where a new
                # entity has no provider record yet and the link is added later).
                if declaration.relation_type == RelationType.REFERENCE.value and require_reference_sources:
                    raise ValidationError(
                        f"A linked record of type '{declaration.from_entity_type_id}' "
                        "is required to create this record."
                    )
                continue  # SNAPSHOT, or opted-out REFERENCE — no source of this type given, no link row
            if skip_existing_links and self._find_link_for_declaration(
                session,
                organization_id=organization_id,
                to_entity_id=entity_id,
                from_entity_type_id=declaration.from_entity_type_id,
                relation_type=declaration.relation_type,
            ) is not None:
                continue  # already linked — no relinking support
            link_metadata = self._build_link_metadata_for_declaration(
                session,
                organization_id=organization_id,
                declaration=declaration,
                source_entity_id=source_id,
            )
            session.add(
                EntityRelationModel(
                    organization_id=organization_id,
                    from_entity_id=source_id,
                    to_entity_id=entity_id,
                    relation_type=declaration.relation_type,
                    relation_metadata=link_metadata,
                )
            )

    def _build_link_metadata_for_declaration(
        self,
        session: Session,
        *,
        organization_id: str,
        declaration: EntityTypeRelationModel,
        source_entity_id: str,
    ) -> dict[str, object]:
        """Build the `entity_relations.relation_metadata` payload for one link.

        REFERENCE — always empty; values are read live from `from_entity_id`.
        SNAPSHOT — frozen field values copied from the source at this moment.
        """
        if declaration.relation_type == RelationType.REFERENCE.value:
            return {}
        source = (
            session.query(EntityRecordModel)
            .filter_by(organization_id=organization_id, entity_id=source_entity_id)
            .filter(EntityRecordModel.archived_at.is_(None))
            .first()
        )
        if source is None:
            raise ValidationError(
                "The selected source record was not found in your organization."
            )
        source_data = dict(source.data or {})
        mapping = {
            source_key: target_key
            for source_key, target_key in dict(declaration.relation_metadata or {}).items()
            if isinstance(source_key, str) and isinstance(target_key, str)
        }
        return {
            local_field_name(target_key): source_data.get(
                local_field_name(source_key)
            )
            for source_key, target_key in mapping.items()
        }

    def get_entity_record_by_id(
        self,
        *,
        organization_id: str,
        entity_id: str,
        include_archived: bool = False,
    ) -> EntityRecord | None:
        """Fetch a runtime entity by id, scoped to the actor's org. Archived
        rows are filtered out unless `include_archived=True`."""
        with self._db_session() as session:
            try:
                query = session.query(EntityRecordModel).filter_by(
                    entity_id=entity_id, organization_id=organization_id
                )
                if not include_archived:
                    query = query.filter(EntityRecordModel.archived_at.is_(None))
                model = query.first()
                return self._entity_record(model)
            except Exception as exc:
                logger.debug("get_entity_record_by_id failed: %s", exc)
                raise PersistenceError(f"Unable to fetch entity record: {exc}") from exc

    def list_entity_records(
        self,
        *,
        organization_id: str,
        entity_type_id: str | None = None,
        include_archived: bool = False,
    ) -> list[EntityRecord]:
        """List runtime entities for an organization, optionally filtered by
        entity_type. Archived rows are hidden unless `include_archived=True`."""
        with self._db_session() as session:
            try:
                query = session.query(EntityRecordModel).filter_by(organization_id=organization_id)
                if entity_type_id is not None:
                    query = query.filter_by(entity_type_id=entity_type_id)
                if not include_archived:
                    query = query.filter(EntityRecordModel.archived_at.is_(None))
                rows = query.order_by(EntityRecordModel.created_at.asc()).all()
                return [self._entity_record(row) for row in rows]
            except Exception as exc:
                logger.debug("list_entity_records failed: %s", exc)
                raise PersistenceError(f"Unable to list entity records: {exc}") from exc

    def list_entity_record_summary_page(
        self,
        *,
        organization_id: str,
        entity_type_id: str | None = None,
        entity_type_name: str | None = None,
        include_archived: bool = False,
        entity_ids: set[str] | None = None,
        after_updated_at: datetime | None = None,
        after_entity_id: str | None = None,
        limit: int = 51,
    ) -> list[tuple[EntityRecord, str]]:
        """Set-based cursor page for the records summary API, newest update first."""
        with self._db_session() as session:
            try:
                query = (
                    session.query(EntityRecordModel, EntityTypeModel.name)
                    .join(
                        EntityTypeModel,
                        (EntityTypeModel.organization_id == EntityRecordModel.organization_id)
                        & (EntityTypeModel.entity_type_id == EntityRecordModel.entity_type_id),
                    )
                    .filter(EntityRecordModel.organization_id == organization_id)
                )
                if entity_type_name:
                    query = query.filter(EntityTypeModel.name == entity_type_name)
                elif entity_type_id:
                    query = query.filter(EntityRecordModel.entity_type_id == entity_type_id)
                if not include_archived:
                    query = query.filter(EntityRecordModel.archived_at.is_(None))
                if entity_ids is not None:
                    if not entity_ids:
                        return []
                    query = query.filter(EntityRecordModel.entity_id.in_(entity_ids))
                if after_updated_at is not None and after_entity_id:
                    query = query.filter(
                        (EntityRecordModel.updated_at < after_updated_at)
                        | (
                            (EntityRecordModel.updated_at == after_updated_at)
                            & (EntityRecordModel.entity_id < after_entity_id)
                        )
                    )
                rows = (
                    query.order_by(
                        EntityRecordModel.updated_at.desc(), EntityRecordModel.entity_id.desc()
                    )
                    .limit(max(1, limit))
                    .all()
                )
                return [(self._entity_record(record), type_name) for record, type_name in rows]
            except Exception as exc:
                logger.debug("list_entity_record_summary_page failed: %s", exc)
                raise PersistenceError(f"Unable to list entity record summaries: {exc}") from exc

    def inheritable_field_names_by_type(
        self, *, organization_id: str, entity_type_ids: set[str]
    ) -> dict[str, set[str]]:
        """Field keys each entity type can inherit from a related record.

        `resolve_inherited_fields_for_records` merges these *over* a record's
        own JSONB, so for these keys the effective value is not the one stored
        on the row. A caller that wants to evaluate a field as a SQL predicate
        has to know which keys that rules out — everything else can be read
        straight off `data`.
        """
        if not entity_type_ids:
            return {}
        with self._db_session() as session:
            try:
                declaration_rows = (
                    session.query(EntityTypeRelationModel, EntityTypeModel.name)
                    .join(
                        EntityTypeModel,
                        (EntityTypeModel.organization_id == EntityTypeRelationModel.organization_id)
                        & (EntityTypeModel.entity_type_id == EntityTypeRelationModel.from_entity_type_id),
                    )
                    .filter(
                        EntityTypeRelationModel.organization_id == organization_id,
                        EntityTypeRelationModel.to_entity_type_id.in_(entity_type_ids),
                        EntityTypeRelationModel.deleted_at.is_(None),
                    )
                    .all()
                )
                by_type: dict[str, set[str]] = {}
                for declaration, source_type_name in declaration_rows:
                    names = {
                        local_field_name(value)
                        for value in dict(declaration.relation_metadata or {}).values()
                        if isinstance(value, str)
                    }
                    names.add(parent_id_field_name(source_type_name))
                    by_type.setdefault(declaration.to_entity_type_id, set()).update(names)

                # Method-block-level inherited fields are overlay-resolved too,
                # and have no relation_metadata entry, so they must be added
                # here or a read-policy condition on one would be pushed to SQL
                # against a stored value that does not exist.
                for type_id, pinned in self._pinned_inherited_fields_by_type_with_session(
                    session, organization_id=organization_id, entity_type_ids=entity_type_ids
                ).items():
                    by_type.setdefault(type_id, set()).update(pinned.keys())
                return by_type
            except Exception as exc:
                logger.debug("inheritable_field_names_by_type failed: %s", exc)
                raise PersistenceError(
                    f"Unable to resolve inheritable field names: {exc}"
                ) from exc

    def resolve_inherited_fields_for_records(
        self,
        *,
        organization_id: str,
        records: list[EntityRecord],
        field_names: set[str],
    ) -> dict[str, dict[str, object]]:
        """Batch-resolve only inherited fields requested by a summary projection."""
        if not records or not field_names:
            return {}
        entity_ids = [record.entity_id for record in records]
        target_type_ids = {record.entity_type_id for record in records}
        with self._db_session() as session:
            try:
                declaration_rows = (
                    session.query(EntityTypeRelationModel, EntityTypeModel.name)
                    .join(
                        EntityTypeModel,
                        (EntityTypeModel.organization_id == EntityTypeRelationModel.organization_id)
                        & (EntityTypeModel.entity_type_id == EntityTypeRelationModel.from_entity_type_id),
                    )
                    .filter(
                        EntityTypeRelationModel.organization_id == organization_id,
                        EntityTypeRelationModel.to_entity_type_id.in_(target_type_ids),
                        EntityTypeRelationModel.deleted_at.is_(None),
                    )
                    .all()
                )
                relevant_declarations: list[tuple[EntityTypeRelationModel, str]] = []
                for declaration, source_type_name in declaration_rows:
                    targets = {
                        local_field_name(value)
                        for value in dict(declaration.relation_metadata or {}).values()
                        if isinstance(value, str)
                    }
                    parent_field = parent_id_field_name(source_type_name)
                    if targets & field_names or parent_field in field_names:
                        relevant_declarations.append((declaration, source_type_name))

                # Method-block-level inheritance: which requested fields does
                # each record inherit through its pinned schema? Worked out up
                # front because such a field has NO relation_metadata entry, so
                # the early return below would otherwise drop it unseen.
                enrolled = self._enrolled_workflow_ids(
                    session, organization_id=organization_id, entity_ids=entity_ids
                )
                pinned_mappings = self._pinned_inherited_mappings_for_workflows(
                    session,
                    organization_id=organization_id,
                    workflow_ids={wf for wfs in enrolled.values() for wf in wfs},
                )
                # entity_id -> source type name -> {source_key: target_key},
                # trimmed to the fields actually requested.
                pinned_by_record: dict[str, dict[str, dict[str, str]]] = {}
                for record in records:
                    for workflow_id in enrolled.get(record.entity_id, set()):
                        for source_type, mapping in pinned_mappings.get(workflow_id, {}).items():
                            wanted = {
                                local_field_name(src): local_field_name(tgt)
                                for src, tgt in mapping.items()
                                if local_field_name(tgt) in field_names
                            }
                            if wanted:
                                pinned_by_record.setdefault(record.entity_id, {}).setdefault(
                                    source_type, {}
                                ).update(wanted)
                pinned_source_type_ids = self._entity_type_ids_by_name(
                    session,
                    organization_id=organization_id,
                    names={st for by_source in pinned_by_record.values() for st in by_source},
                )

                if not relevant_declarations and not pinned_by_record:
                    return {}
                links = (
                    session.query(EntityRelationModel)
                    .filter(
                        EntityRelationModel.organization_id == organization_id,
                        EntityRelationModel.to_entity_id.in_(entity_ids),
                    )
                    .order_by(EntityRelationModel.created_at.asc())
                    .all()
                )
                source_ids = {link.from_entity_id for link in links}
                sources = (
                    session.query(EntityRecordModel)
                    .filter(
                        EntityRecordModel.organization_id == organization_id,
                        EntityRecordModel.entity_id.in_(source_ids),
                    )
                    .all()
                    if source_ids
                    else []
                )
                source_by_id = {source.entity_id: source for source in sources}
                links_by_target: dict[str, list[EntityRelationModel]] = {}
                for link in links:
                    links_by_target.setdefault(link.to_entity_id, []).append(link)
                declarations_by_type: dict[str, list[EntityTypeRelationModel]] = {}
                for declaration, _ in relevant_declarations:
                    declarations_by_type.setdefault(declaration.to_entity_type_id, []).append(declaration)
                source_type_names = {
                    declaration.from_entity_type_id: source_type_name
                    for declaration, source_type_name in relevant_declarations
                }
                # Every active declaration for the record's type, keyed by
                # (to_type, from_type): the pinned overlay needs the declaration
                # for its link + REFERENCE/SNAPSHOT mode even when the blanket
                # path found nothing in its metadata worth resolving.
                declaration_by_pair: dict[tuple[str, str], EntityTypeRelationModel] = {
                    (declaration.to_entity_type_id, declaration.from_entity_type_id): declaration
                    for declaration, _ in declaration_rows
                }

                resolved_by_entity: dict[str, dict[str, object]] = {}
                for record in records:
                    resolved: dict[str, object] = {}
                    for declaration in declarations_by_type.get(record.entity_type_id, []):
                        mapping = {
                            local_field_name(source): local_field_name(target)
                            for source, target in dict(declaration.relation_metadata or {}).items()
                            if isinstance(source, str) and isinstance(target, str)
                            and local_field_name(target) in field_names
                        }
                        if not mapping:
                            mapping = {}
                        link = next(
                            (
                                candidate
                                for candidate in links_by_target.get(record.entity_id, [])
                                if candidate.relation_type == declaration.relation_type
                                and source_by_id.get(candidate.from_entity_id) is not None
                                and source_by_id[candidate.from_entity_id].entity_type_id
                                == declaration.from_entity_type_id
                            ),
                            None,
                        )
                        parent_field = parent_id_field_name(
                            source_type_names.get(declaration.from_entity_type_id, "")
                        )
                        if parent_field in field_names and link is not None:
                            resolved.setdefault(parent_field, link.from_entity_id)
                        if declaration.relation_type == RelationType.REFERENCE.value:
                            source_data = (
                                dict(source_by_id[link.from_entity_id].data or {})
                                if link is not None and source_by_id[link.from_entity_id].archived_at is None
                                else {}
                            )
                            for source_field, target_field in mapping.items():
                                resolved[target_field] = source_data.get(source_field)
                        else:
                            snapshot = dict(link.relation_metadata or {}) if link is not None else {}
                            for target_field in mapping.values():
                                resolved[target_field] = snapshot.get(target_field)

                    # Method-block-level overlay, alongside the blanket result:
                    # same links, same sources, same two resolution modes, and
                    # setdefault so a key the blanket path already produced is
                    # left exactly as it was.
                    for source_type, mapping in pinned_by_record.get(record.entity_id, {}).items():
                        from_type_id = pinned_source_type_ids.get(source_type)
                        declaration = (
                            declaration_by_pair.get((record.entity_type_id, from_type_id))
                            if from_type_id
                            else None
                        )
                        if declaration is None:
                            continue
                        link = next(
                            (
                                candidate
                                for candidate in links_by_target.get(record.entity_id, [])
                                if candidate.relation_type == declaration.relation_type
                                and source_by_id.get(candidate.from_entity_id) is not None
                                and source_by_id[candidate.from_entity_id].entity_type_id
                                == declaration.from_entity_type_id
                            ),
                            None,
                        )
                        if declaration.relation_type == RelationType.REFERENCE.value:
                            source_data = (
                                dict(source_by_id[link.from_entity_id].data or {})
                                if link is not None and source_by_id[link.from_entity_id].archived_at is None
                                else {}
                            )
                            for source_field, target_field in mapping.items():
                                resolved.setdefault(target_field, source_data.get(source_field))
                        else:
                            snapshot = dict(link.relation_metadata or {}) if link is not None else {}
                            for target_field in mapping.values():
                                resolved.setdefault(target_field, snapshot.get(target_field))
                    if resolved:
                        resolved_by_entity[record.entity_id] = resolved
                return resolved_by_entity
            except Exception as exc:
                logger.debug("resolve_inherited_fields_for_records failed: %s", exc)
                raise PersistenceError(f"Unable to resolve inherited summary fields: {exc}") from exc

    def list_entity_records_by_ids(
        self,
        *,
        organization_id: str,
        entity_ids: set[str],
        include_archived: bool = False,
    ) -> list[EntityRecord]:
        """List runtime entities by id, scoped to one organization."""
        if not entity_ids:
            return []
        with self._db_session() as session:
            try:
                query = session.query(EntityRecordModel).filter(
                    EntityRecordModel.organization_id == organization_id,
                    EntityRecordModel.entity_id.in_(entity_ids),
                )
                if not include_archived:
                    query = query.filter(EntityRecordModel.archived_at.is_(None))
                rows = query.order_by(EntityRecordModel.created_at.asc()).all()
                return [self._entity_record(row) for row in rows]
            except Exception as exc:
                logger.debug("list_entity_records_by_ids failed: %s", exc)
                raise PersistenceError(f"Unable to list entity records by ids: {exc}") from exc

    def list_entity_records_by_type_name(
        self,
        *,
        organization_id: str,
        entity_type_name: str,
        include_archived: bool = False,
        search: str | None = None,
        limit: int | None = None,
    ) -> list[EntityRecord]:
        """List entity records by type name, resolving name → type_id internally.
        Returns empty list when the type name does not exist in the org.

        `search` does a case-insensitive substring match over the record's raw
        JSON `data` — callers exposing results to users must re-verify matches
        against the actor-visible view (see the manager wrapper), since this
        predicate sees hidden/masked fields. `limit` caps the result count
        (clamped to 500; user-facing clamping happens in the manager)."""
        with self._db_session() as session:
            try:
                type_row = (
                    session.query(EntityTypeModel)
                    .filter_by(organization_id=organization_id, name=entity_type_name)
                    .order_by(EntityTypeModel.version.desc())
                    .first()
                )
                if type_row is None:
                    return []
                query = session.query(EntityRecordModel).filter_by(
                    organization_id=organization_id,
                    entity_type_id=type_row.entity_type_id,
                )
                if not include_archived:
                    query = query.filter(EntityRecordModel.archived_at.is_(None))
                if search and search.strip():
                    escaped = (
                        search.strip()
                        .replace("\\", "\\\\")
                        .replace("%", "\\%")
                        .replace("_", "\\_")
                    )
                    query = query.filter(
                        sa.cast(EntityRecordModel.data, sa.Text).ilike(
                            f"%{escaped}%", escape="\\"
                        )
                    )
                query = query.order_by(EntityRecordModel.created_at.asc())
                if limit is not None:
                    query = query.limit(max(1, min(limit, 500)))
                rows = query.all()
                return [self._entity_record(row) for row in rows]
            except Exception as exc:
                logger.debug("list_entity_records_by_type_name failed: %s", exc)
                raise PersistenceError(
                    f"Unable to list entity records by type name: {exc}"
                ) from exc

    def update_entity_record(
        self,
        *,
        organization_id: str,
        entity_id: str,
        request: EntityRecordUpdateRequest,
    ) -> EntityRecord | None:
        """Patch mutable fields on a live (non-archived) entity record.

        Locks the row before reading it: append_to_data_list_field locks the
        same row for its own read-append-write, and a lock only prevents a
        lost update if every writer of this row takes it, not just one side.
        """
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRecordModel)
                    .filter_by(entity_id=entity_id, organization_id=organization_id)
                    .filter(EntityRecordModel.archived_at.is_(None))
                    .with_for_update()
                    .first()
                )
                if model is None:
                    return None
                if request.data is not None:
                    old_data = dict(model.data or {})
                    self._apply_snapshot_field_updates(
                        session,
                        organization_id=organization_id,
                        entity_type_id=model.entity_type_id,
                        entity_id=entity_id,
                        data=request.data,
                    )
                    new_data = self._strip_inherited_fields_with_session(
                        session,
                        organization_id=organization_id,
                        entity_type_id=model.entity_type_id,
                        data=request.data,
                    )
                    model.data = self._lock_auto_number_on_update(
                        session,
                        organization_id=organization_id,
                        entity_type_id=model.entity_type_id,
                        old_data=old_data,
                        new_data=new_data,
                    )
                if request.owner_id is not None:
                    model.owner_id = request.owner_id
                if "due_date" in request.model_fields_set:
                    model.due_date = request.due_date
                if request.source_entity_ids:
                    declarations = self._active_declarations_by_to_type(
                        session,
                        organization_id=organization_id,
                        to_entity_type_id=model.entity_type_id,
                    )
                    if declarations:
                        self._link_sources_to_entity(
                            session,
                            organization_id=organization_id,
                            entity_id=entity_id,
                            declarations=declarations,
                            source_entity_ids=list(request.source_entity_ids or []),
                            skip_existing_links=True,
                        )
                session.commit()
                session.refresh(model)
                return self._entity_record(model)
            except ValidationError:
                session.rollback()
                raise
            except IntegrityError as exc:
                session.rollback()
                logger.debug("update_entity_record IntegrityError: %s", exc)
                raise ConflictError("Entity record conflicts with an existing record") from exc
            except Exception as exc:
                session.rollback()
                logger.debug("update_entity_record failed: %s", exc)
                raise PersistenceError(f"Unable to update entity record: {exc}") from exc

    def append_to_data_list_field(
        self, *, organization_id: str, entity_id: str, field_key: str, value: str
    ) -> EntityRecord | None:
        """Atomically append one value onto a list-valued field in entity.data.

        Locks the row for the whole read-append-write so two concurrent appends
        (or an append racing an unrelated edit) can never silently overwrite one
        another the way two independent update_entity_record calls could — each
        would read its own stale snapshot and replace `data` wholesale.
        """
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRecordModel)
                    .filter_by(entity_id=entity_id, organization_id=organization_id)
                    .filter(EntityRecordModel.archived_at.is_(None))
                    .with_for_update()
                    .first()
                )
                if model is None:
                    return None
                data = dict(model.data or {})
                current = data.get(field_key)
                if current is None:
                    items: list[str] = []
                elif isinstance(current, list) and all(isinstance(item, str) for item in current):
                    items = list(current)
                else:
                    raise ValidationError(
                        f"field '{field_key}' must contain a list of ids to append to"
                    )
                items.append(value)
                data[field_key] = items
                model.data = data
                session.commit()
                session.refresh(model)
                return self._entity_record(model)
            except ValidationError:
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("append_to_data_list_field failed: %s", exc)
                raise PersistenceError(f"Unable to append to field: {exc}") from exc

    def _find_link_for_declaration(
        self,
        session: Session,
        *,
        organization_id: str,
        to_entity_id: str,
        from_entity_type_id: str,
        relation_type: str,
    ) -> EntityRelationModel | None:
        """Find the `entity_relations` link row backing one declaration for one
        accepter record — the provider side must match the declaration's
        `from_entity_type_id`, and the link's own `relation_type` must match
        the declaration's, to avoid colliding with unrelated graph edges that
        happen to share this table.

        `_link_sources_to_new_entity` only ever allows one source per provider
        type per accepter at creation time, and there is no relinking, so this
        should always resolve to at most one row. Ordered by `created_at` as a
        defensive backstop — if that invariant is ever violated, the oldest
        link wins deterministically instead of `.first()` picking an
        arbitrary row."""
        return (
            session.query(EntityRelationModel)
            .join(EntityRecordModel, EntityRecordModel.entity_id == EntityRelationModel.from_entity_id)
            .filter(
                EntityRelationModel.organization_id == organization_id,
                EntityRelationModel.to_entity_id == to_entity_id,
                EntityRelationModel.relation_type == relation_type,
                EntityRecordModel.entity_type_id == from_entity_type_id,
            )
            .order_by(EntityRelationModel.created_at.asc())
            .first()
        )

    def _apply_snapshot_field_updates(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_type_id: str,
        entity_id: str,
        data: dict[str, object],
    ) -> None:
        """Route SNAPSHOT-declared inherited field values in `data` onto their
        `entity_relations` link row. REFERENCE fields are never routed here —
        callers must reject them before reaching this layer; any that slip
        through are simply stripped from entity data with no effect.

        If no link exists yet (SNAPSHOT declared with no source ever linked),
        there is nowhere to store the value — the write is a no-op, logged."""
        declarations = self._active_declarations_by_to_type(
            session, organization_id=organization_id, to_entity_type_id=entity_type_id
        )
        for declaration in declarations:
            if declaration.relation_type != RelationType.SNAPSHOT.value:
                continue
            target_fields = {
                local_field_name(target_key)
                for target_key in dict(declaration.relation_metadata or {}).values()
                if isinstance(target_key, str)
            }
            updates = {key: value for key, value in data.items() if key in target_fields}
            if not updates:
                continue
            link = self._find_link_for_declaration(
                session,
                organization_id=organization_id,
                to_entity_id=entity_id,
                from_entity_type_id=declaration.from_entity_type_id,
                relation_type=declaration.relation_type,
            )
            if link is None:
                logger.debug(
                    "snapshot field update skipped — no source linked for declaration",
                    extra={"entity_id": entity_id, "relation_def_id": declaration.relation_def_id},
                )
                continue
            link.relation_metadata = {**dict(link.relation_metadata or {}), **updates}

    def set_entity_assignee(
        self,
        *,
        organization_id: str,
        entity_id: str,
        assignee_id: str | None,
    ) -> EntityRecord | None:
        """Set or clear the assignee on a live (non-archived) entity record.

        Unlike `update_entity_record`, a `None` assignee_id is written through
        (clears the assignment) rather than treated as "leave unchanged"."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRecordModel)
                    .filter_by(entity_id=entity_id, organization_id=organization_id)
                    .filter(EntityRecordModel.archived_at.is_(None))
                    .first()
                )
                if model is None:
                    return None
                model.assignee_id = assignee_id
                session.commit()
                session.refresh(model)
                return self._entity_record(model)
            except Exception as exc:
                session.rollback()
                logger.debug("set_entity_assignee failed: %s", exc)
                raise PersistenceError(f"Unable to set entity assignee: {exc}") from exc

    def archive_entity_record(
        self,
        *,
        organization_id: str,
        entity_id: str,
    ) -> EntityRecord | None:
        """Soft-archive a runtime entity. Also deletes its workflow enrollment
        rows so the entity_id can be re-enrolled cleanly via `restore_entity_record`.
        Audit rows in `audit.entity_events` and `audit.transition_attempts`
        are preserved — they are immutable history.

        No `entity_relations` cleanup needed here: REFERENCE reads are always
        live and already exclude archived records, so an archived provider
        naturally resolves to null on its linked accepters' next read."""
        now = datetime.now(UTC)
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRecordModel)
                    .filter_by(entity_id=entity_id, organization_id=organization_id)
                    .first()
                )
                if model is None:
                    return None
                if model.archived_at is None:
                    model.archived_at = now
                session.query(EntityStateRuntimeModel).filter_by(
                    organization_id=organization_id, entity_id=entity_id
                ).delete(synchronize_session=False)
                session.commit()
                session.refresh(model)
                return self._entity_record(model)
            except Exception as exc:
                session.rollback()
                logger.debug("archive_entity_record failed: %s", exc)
                raise PersistenceError(f"Unable to archive entity record: {exc}") from exc

    def restore_entity_record(
        self,
        *,
        organization_id: str,
        entity_id: str,
        entity_type_id: str | None = None,
        data: dict | None = None,
        owner_id: str | None = None,
    ) -> EntityRecord | None:
        """Clear `archived_at` on a previously archived runtime entity and
        optionally refresh its data / entity_type_id / owner. Returns None if
        no row exists for the (organization_id, entity_id). Returns the
        existing live row unchanged when called on a non-archived entity."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRecordModel)
                    .filter_by(entity_id=entity_id, organization_id=organization_id)
                    .first()
                )
                if model is None:
                    return None
                model.archived_at = None
                if entity_type_id is not None:
                    model.entity_type_id = entity_type_id
                if data is not None:
                    next_entity_type_id = entity_type_id or model.entity_type_id
                    # auto_number is immutable: force any existing generated id
                    # back onto the incoming data, even on unarchive/restore.
                    locked_data = self._lock_auto_number_on_update(
                        session,
                        organization_id=organization_id,
                        entity_type_id=next_entity_type_id,
                        old_data=dict(model.data or {}),
                        new_data=data,
                    )
                    model.data = self._strip_inherited_fields_with_session(
                        session,
                        organization_id=organization_id,
                        entity_type_id=next_entity_type_id,
                        data=locked_data,
                    )
                if owner_id is not None:
                    model.owner_id = owner_id
                session.commit()
                session.refresh(model)
                return self._entity_record(model)
            except Exception as exc:
                session.rollback()
                logger.debug("restore_entity_record failed: %s", exc)
                raise PersistenceError(f"Unable to restore entity record: {exc}") from exc

    @staticmethod
    def _entity_record(item: EntityRecordModel | None) -> EntityRecord | None:
        """Hydrate an `EntityRecordModel` row into an `EntityRecord` contract."""
        if item is None:
            return None
        return EntityRecord(
            entity_id=item.entity_id,
            organization_id=item.organization_id,
            entity_type_id=item.entity_type_id,
            data=dict(item.data or {}),
            custom_form_schema=dict(item.custom_form_schema or {}),
            custom_form_data=dict(item.custom_form_data or {}),
            owner_id=item.owner_id,
            assignee_id=item.assignee_id,
            due_date=item.due_date,
            created_at=item.created_at,
            updated_at=item.updated_at,
            archived_at=item.archived_at,
        )

    # ── Field-inheritance read resolver (entity_relations based) ────────────

    def resolve_inherited_fields(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        entity_id: str,
    ) -> dict[str, object]:
        """Resolve inherited field values at read time.

        For each active declaration targeting `entity_type_id`, find the
        matching `entity_relations` link (if any) and resolve its fields:
        REFERENCE reads the linked provider live; SNAPSHOT reads the frozen
        values off the link row itself. Never raises — a resolver failure
        returns an empty dict so the entity read itself never fails."""
        try:
            with self._db_session() as session:
                return self._resolve_inherited_fields_with_session(
                    session,
                    organization_id=organization_id,
                    entity_type_id=entity_type_id,
                    entity_id=entity_id,
                )
        except Exception as exc:
            logger.debug("resolve_inherited_fields failed: %s", exc)
            return {}

    def _resolve_inherited_fields_with_session(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_type_id: str,
        entity_id: str,
    ) -> dict[str, object]:
        """Session-scoped body of :meth:`resolve_inherited_fields` — reusable
        inside an open transaction so uncommitted link rows are visible
        (identifier-template generation at create time)."""
        declarations = self._active_declarations_by_to_type(
            session, organization_id=organization_id, to_entity_type_id=entity_type_id
        )
        if not declarations:
            return {}
        resolved: dict[str, object] = {}
        for declaration in declarations:
            mapping = {
                source_key: target_key
                for source_key, target_key in dict(declaration.relation_metadata or {}).items()
                if isinstance(source_key, str) and isinstance(target_key, str)
            }
            link = self._find_link_for_declaration(
                session,
                organization_id=organization_id,
                to_entity_id=entity_id,
                from_entity_type_id=declaration.from_entity_type_id,
                relation_type=declaration.relation_type,
            )
            # Auto-expose the linked parent's own record id as `<parent_type>_id`
            # (e.g. client_id), no mapping required. Best-effort: never let this
            # abort resolution of the explicitly-mapped fields below.
            if link is not None:
                try:
                    parent_field = self._parent_id_field_for_type(
                        session,
                        organization_id=organization_id,
                        entity_type_id=declaration.from_entity_type_id,
                    )
                    if parent_field:
                        resolved.setdefault(parent_field, link.from_entity_id)
                except Exception:
                    logger.debug("auto parent-id resolution skipped", exc_info=True)
            if declaration.relation_type == RelationType.REFERENCE.value:
                resolved.update(
                    self._resolve_reference_fields(session, organization_id, mapping, link)
                )
            else:
                resolved.update(self._resolve_snapshot_fields(mapping, link))
        # Method-block-level inheritance rides alongside: it only fills keys
        # the blanket path left unset, so nothing above changes for a type that
        # has not opted anything in.
        try:
            for key, value in self._resolve_pinned_inherited_fields(
                session,
                organization_id=organization_id,
                entity_id=entity_id,
                declarations=declarations,
            ).items():
                resolved.setdefault(key, value)
        except Exception:
            logger.debug("pinned inherited field resolution skipped", exc_info=True)
        return resolved

    def _resolve_reference_fields(
        self,
        session: Session,
        organization_id: str,
        mapping: dict[str, str],
        link: EntityRelationModel | None,
    ) -> dict[str, object]:
        """Fetch the live provider entity through the link and apply the mapping."""
        target_to_source = {
            local_field_name(target): local_field_name(source)
            for source, target in mapping.items()
        }
        if link is None:
            return dict.fromkeys(target_to_source, None)
        source = (
            session.query(EntityRecordModel)
            .filter_by(organization_id=organization_id, entity_id=link.from_entity_id)
            .filter(EntityRecordModel.archived_at.is_(None))
            .first()
        )
        source_data = dict(source.data or {}) if source is not None else {}
        return {
            target_field: source_data.get(source_field)
            for target_field, source_field in target_to_source.items()
        }

    def _resolve_snapshot_fields(
        self,
        mapping: dict[str, str],
        link: EntityRelationModel | None,
    ) -> dict[str, object]:
        """Read frozen field values directly off the link's `relation_metadata`."""
        target_fields = {local_field_name(target) for target in mapping.values()}
        link_data = dict(link.relation_metadata or {}) if link is not None else {}
        return {field_name: link_data.get(field_name) for field_name in target_fields}

    # ── Method-block-level inheritance ──────────────────────────────────────
    #
    # A pinned method field with ownership='inherited' is recorded on the
    # PUBLISHED workflow's entity_schema (workflow/manager.py,
    # _entity_field_from_method_field) and deliberately NOT projected into
    # entity_type_relations.relation_metadata. So the blanket resolution above
    # never sees it. These helpers read it back from the definition the record
    # is actually enrolled in, and hand the existing REFERENCE/SNAPSHOT
    # machinery a mapping in the exact shape relation_metadata uses, so the
    # value comes from the same link lookup and the same two code paths.
    #
    # Everything here is additive and best-effort: it runs AFTER the blanket
    # path and only fills keys the blanket path did not, so a type with no
    # opted-in fields resolves byte-for-byte as before. A failure to read a
    # definition degrades to "no per-block fields", never to an error.
    #
    # `workflow_state_machines` is read with raw SQL rather than its ORM model
    # because workflow.db_models imports this module; importing it back would
    # be a cycle. The table is unqualified for the same reason the model is:
    # it lives in the base app schema, which the session's search_path
    # already resolves.

    def _enrolled_workflow_ids(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_ids: list[str],
    ) -> dict[str, set[str]]:
        """workflow_state_machines.id for every enrollment each record holds."""
        if not entity_ids:
            return {}
        rows = (
            session.query(EntityStateRuntimeModel.entity_id, EntityStateRuntimeModel.workflow_id)
            .filter(
                EntityStateRuntimeModel.organization_id == organization_id,
                EntityStateRuntimeModel.entity_id.in_(entity_ids),
            )
            .all()
        )
        by_entity: dict[str, set[str]] = {}
        for entity_id, workflow_id in rows:
            if workflow_id:
                by_entity.setdefault(entity_id, set()).add(workflow_id)
        return by_entity

    def _pinned_inherited_mappings_for_workflows(
        self,
        session: Session,
        *,
        organization_id: str,
        workflow_ids: set[str],
    ) -> dict[str, dict[str, dict[str, str]]]:
        """Per workflow id: { source entity type NAME: relation_metadata-shaped mapping }.

        The mapping is {"<SourceType>.<source_field>": "<TargetType>.<field>"},
        identical to what `entity_type_relations.relation_metadata` holds, so
        `_resolve_reference_fields` / `_resolve_snapshot_fields` apply unchanged.
        Only fields with ownership='inherited' and a well-formed source count.
        """
        if not workflow_ids:
            return {}
        result: dict[str, dict[str, dict[str, str]]] = {}
        try:
            rows = session.execute(
                sa.text(
                    "SELECT id, entity_type, definition_json "
                    "FROM workflow_state_machines "
                    "WHERE organization_id = :organization_id AND id IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"organization_id": organization_id, "ids": list(workflow_ids)},
            ).all()
        except Exception:
            logger.debug("pinned inherited mapping lookup skipped", exc_info=True)
            return {}
        for workflow_id, target_type, definition_json in rows:
            try:
                definition = json.loads(definition_json or "{}")
                fields = (definition.get("entity_schema") or {}).get("fields") or []
            except Exception:
                logger.debug("pinned inherited mapping: bad definition", exc_info=True)
                continue
            by_source: dict[str, dict[str, str]] = {}
            for schema_field in fields:
                if not isinstance(schema_field, dict):
                    continue
                if str(schema_field.get("ownership") or "").lower() != "inherited":
                    continue
                source = schema_field.get("source")
                if not isinstance(source, dict):
                    continue
                source_type = str(source.get("context_entity_type") or "").strip()
                source_field = str(source.get("context_field") or "").strip()
                target_field = str(schema_field.get("field") or "").strip()
                if not (source_type and source_field and target_field):
                    continue
                by_source.setdefault(source_type, {})[f"{source_type}.{source_field}"] = (
                    f"{target_type}.{target_field}"
                )
            if by_source:
                result[workflow_id] = by_source
        return result

    def _pinned_inherited_fields_by_type_with_session(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_type_ids: set[str],
    ) -> dict[str, dict[str, tuple[tuple[str, str], ...]]]:
        """Per target entity type id: {field: ((source type NAME, source field), ...)}
        for every field an ACTIVE published workflow of that type pins with
        ownership='inherited'.

        Type-level on purpose, like `relation_metadata`: it answers "can this
        field ever be inherited on this type", which is what RBAC gating and
        SQL-pushdown decisions need. Whether a given record actually carries
        the value is decided per record by the resolvers, from its enrollment.
        Best-effort: an unreadable definition is skipped, never raised.

        Every DISTINCT source is kept, not just the first one seen. One entity
        type can carry several active workflows, and two of them may pin the
        same target field from different source types. Keeping only the first
        would gate that field's permissions against an arbitrary one of them;
        callers instead gate against all of them and take the most restrictive
        answer, since a type-level lookup cannot know which workflow any given
        record is enrolled in.
        """
        if not entity_type_ids:
            return {}
        result: dict[str, dict[str, tuple[tuple[str, str], ...]]] = {}
        try:
            type_rows = (
                session.query(EntityTypeModel.entity_type_id, EntityTypeModel.name)
                .filter(
                    EntityTypeModel.organization_id == organization_id,
                    EntityTypeModel.entity_type_id.in_(entity_type_ids),
                )
                .all()
            )
            type_id_by_name = {name: type_id for type_id, name in type_rows}
            if not type_id_by_name:
                return {}
            wf_rows = session.execute(
                sa.text(
                    "SELECT entity_type, definition_json "
                    "FROM workflow_state_machines "
                    "WHERE organization_id = :organization_id "
                    "AND entity_type IN :names "
                    "AND is_active = TRUE AND archived_at IS NULL"
                ).bindparams(sa.bindparam("names", expanding=True)),
                {"organization_id": organization_id, "names": list(type_id_by_name)},
            ).all()
        except Exception:
            logger.debug("pinned inherited fields by type: lookup skipped", exc_info=True)
            return {}
        for type_name, definition_json in wf_rows:
            type_id = type_id_by_name.get(type_name)
            if not type_id:
                continue
            try:
                fields = (
                    (json.loads(definition_json or "{}").get("entity_schema") or {}).get("fields") or []
                )
            except Exception:
                continue
            for schema_field in fields:
                if not isinstance(schema_field, dict):
                    continue
                if str(schema_field.get("ownership") or "").lower() != "inherited":
                    continue
                source = schema_field.get("source")
                target_field = str(schema_field.get("field") or "").strip()
                if not isinstance(source, dict) or not target_field:
                    continue
                source_type = str(source.get("context_entity_type") or "").strip()
                source_field = str(source.get("context_field") or "").strip()
                if not (source_type and source_field):
                    continue
                by_field = result.setdefault(type_id, {})
                existing = by_field.get(target_field, ())
                if (source_type, source_field) in existing:
                    continue
                if existing:
                    logger.warning(
                        "target field is pinned as inherited from more than one source "
                        "by different active workflows on the same entity type; "
                        "permissions will be gated against all of them",
                        extra={
                            "organization_id": organization_id,
                            "entity_type": type_name,
                            "field": target_field,
                            "sources": [f"{t}.{f}" for t, f in (*existing, (source_type, source_field))],
                        },
                    )
                by_field[target_field] = (*existing, (source_type, source_field))
        return result

    def active_workflow_schema_fields(
        self, organization_id: str, entity_type_id: str
    ) -> list[dict]:
        """Schema fields from the entity type's active published workflow.

        Raises rather than returning [] on failure: [] is how a caller learns
        the type declares no such field, so a failed read must not mimic one.
        """
        with self._db_session() as session:
            try:
                type_name = (
                    session.query(EntityTypeModel.name)
                    .filter(
                        EntityTypeModel.organization_id == organization_id,
                        EntityTypeModel.entity_type_id == entity_type_id,
                    )
                    .scalar()
                )
                if not type_name:
                    return []
                definitions = (
                    session.execute(
                        sa.text(
                            "SELECT definition_json FROM workflow_state_machines "
                            "WHERE organization_id = :organization_id "
                            "AND entity_type = :entity_type "
                            "AND is_active = TRUE AND archived_at IS NULL"
                        ),
                        {"organization_id": organization_id, "entity_type": type_name},
                    )
                    .scalars()
                    .all()
                )
            except SQLAlchemyError as exc:
                logger.warning(
                    f"active workflow schema lookup failed (org_id={organization_id} "
                    f"entity_type_id={entity_type_id}): {exc}"
                )
                raise PersistenceError(f"Unable to read the active workflow schema: {exc}") from exc
        fields: list[dict] = []
        for definition in definitions:
            fields.extend(
                self._fields_from_definition_json(definition, organization_id, entity_type_id)
            )
        return fields

    @staticmethod
    def _fields_from_definition_json(
        definition_json: str | None, organization_id: str, entity_type_id: str
    ) -> list[dict]:
        """One published definition's entity_schema fields."""
        try:
            declared = (
                json.loads(definition_json or "{}").get("entity_schema") or {}
            ).get("fields") or []
        except (TypeError, ValueError) as exc:
            logger.warning(
                f"active workflow schema is not readable (org_id={organization_id} "
                f"entity_type_id={entity_type_id}): {exc}"
            )
            raise PersistenceError(f"Unable to read the active workflow schema: {exc}") from exc
        return [field for field in declared if isinstance(field, dict)]

    def pinned_inherited_sources_by_type(
        self,
        *,
        organization_id: str,
        entity_type_ids: set[str],
    ) -> dict[str, dict[str, tuple[tuple[str, str], ...]]]:
        """Public form of the above with the source types resolved to their IDs:
        {target type id: {field: ((source type ID, source field), ...)}}. This is
        what the inherited-field permissions service needs to gate a per-block
        field against the actor's access to its real source, exactly as it does
        for relation_metadata fields.

        A field with more than one entry is pinned from different sources by
        different active workflows on the same type; the permissions service
        gates it against every one of them.
        """
        with self._db_session() as session:
            try:
                by_name = self._pinned_inherited_fields_by_type_with_session(
                    session, organization_id=organization_id, entity_type_ids=entity_type_ids
                )
                names = {
                    src
                    for fields in by_name.values()
                    for sources in fields.values()
                    for src, _ in sources
                }
                ids = self._entity_type_ids_by_name(
                    session, organization_id=organization_id, names=names
                )
                resolved: dict[str, dict[str, tuple[tuple[str, str], ...]]] = {}
                for type_id, fields in by_name.items():
                    for field, sources in fields.items():
                        pairs = tuple(
                            (ids[src], src_field) for src, src_field in sources if src in ids
                        )
                        if pairs:
                            resolved.setdefault(type_id, {})[field] = pairs
                return resolved
            except Exception:
                logger.debug("pinned_inherited_sources_by_type failed", exc_info=True)
                return {}

    def pinned_inherited_field_names_for_record(
        self,
        *,
        organization_id: str,
        entity_id: str,
    ) -> set[str]:
        """Field keys that resolve as inherited on THIS record because one of the
        workflows it is enrolled in pins them with ownership='inherited'.

        The per-record counterpart of the relation_metadata target-field set the
        write guard already uses: a caller writing one of these keys is writing a
        value that the read overlay will mask, so the write must be refused the
        same way a relation_metadata target is. Scoped to the record on purpose:
        another record of the same type that is not enrolled in that workflow
        may own the very same key. Best-effort, returns an empty set on failure
        so a hiccup here can never block an ordinary write.
        """
        with self._db_session() as session:
            try:
                workflow_ids = self._enrolled_workflow_ids(
                    session, organization_id=organization_id, entity_ids=[entity_id]
                ).get(entity_id, set())
                if not workflow_ids:
                    return set()
                by_workflow = self._pinned_inherited_mappings_for_workflows(
                    session, organization_id=organization_id, workflow_ids=workflow_ids
                )
                return {
                    local_field_name(target)
                    for by_source in by_workflow.values()
                    for mapping in by_source.values()
                    for target in mapping.values()
                    if isinstance(target, str)
                }
            except Exception:
                logger.debug("pinned_inherited_field_names_for_record failed", exc_info=True)
                return set()

    def _entity_type_ids_by_name(
        self,
        session: Session,
        *,
        organization_id: str,
        names: set[str],
    ) -> dict[str, str]:
        if not names:
            return {}
        rows = (
            session.query(EntityTypeModel.name, EntityTypeModel.entity_type_id)
            .filter(
                EntityTypeModel.organization_id == organization_id,
                EntityTypeModel.name.in_(names),
            )
            .all()
        )
        return {name: type_id for name, type_id in rows}

    def _resolve_pinned_inherited_fields(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_id: str,
        declarations: list[EntityTypeRelationModel],
    ) -> dict[str, object]:
        """Single-record overlay for fields opted in at the method-block level.

        Uses the declarations the blanket path already loaded for this record's
        type: a per-block field still needs a declared relation to find its
        link (publish refuses to pin one without), it just does not need a
        relation_metadata entry.
        """
        by_workflow = self._enrolled_workflow_ids(
            session, organization_id=organization_id, entity_ids=[entity_id]
        )
        workflow_ids = by_workflow.get(entity_id, set())
        if not workflow_ids:
            return {}
        mappings = self._pinned_inherited_mappings_for_workflows(
            session, organization_id=organization_id, workflow_ids=workflow_ids
        )
        if not mappings:
            return {}
        # A field inherited in ANY of the record's enrollments is inherited for
        # the record; merge the per-workflow mappings by source type.
        merged_by_source: dict[str, dict[str, str]] = {}
        for by_source in mappings.values():
            for source_type, mapping in by_source.items():
                merged_by_source.setdefault(source_type, {}).update(mapping)
        type_ids = self._entity_type_ids_by_name(
            session, organization_id=organization_id, names=set(merged_by_source)
        )
        declarations_by_from = {
            declaration.from_entity_type_id: declaration for declaration in declarations
        }
        resolved: dict[str, object] = {}
        for source_type, mapping in merged_by_source.items():
            declaration = declarations_by_from.get(type_ids.get(source_type, ""))
            if declaration is None:
                # Publish guards against this; if it happens anyway (relation
                # deleted after publish), the field simply does not resolve.
                continue
            link = self._find_link_for_declaration(
                session,
                organization_id=organization_id,
                to_entity_id=entity_id,
                from_entity_type_id=declaration.from_entity_type_id,
                relation_type=declaration.relation_type,
            )
            if declaration.relation_type == RelationType.REFERENCE.value:
                resolved.update(
                    self._resolve_reference_fields(session, organization_id, mapping, link)
                )
            else:
                resolved.update(self._resolve_snapshot_fields(mapping, link))
        return resolved

    def _parent_id_field_for_type(
        self,
        session: Session,
        *,
        organization_id: str,
        entity_type_id: str,
    ) -> str | None:
        """Auto field name (`<parent_type>_id`) for a parent/source entity type, or None."""
        name = (
            session.query(EntityTypeModel.name)
            .filter_by(organization_id=organization_id, entity_type_id=entity_type_id)
            .scalar()
        )
        return parent_id_field_name(name) if name else None

    def entity_records_exist_in_org(
        self,
        *,
        organization_id: str,
        entity_ids: list[str],
    ) -> set[str]:
        """Return the subset of `entity_ids` that exist (non-archived) in the
        given org. Used to backstop the composite FK with a clean 400."""
        with self._db_session() as session:
            try:
                rows = (
                    session.query(EntityRecordModel.entity_id)
                    .filter(
                        EntityRecordModel.organization_id == organization_id,
                        EntityRecordModel.entity_id.in_(entity_ids),
                        EntityRecordModel.archived_at.is_(None),
                    )
                    .all()
                )
                return {row[0] for row in rows}
            except Exception as exc:
                logger.debug("entity_records_exist_in_org failed: %s", exc)
                raise PersistenceError(f"Unable to look up entity records: {exc}") from exc

    def create_entity_relation(
        self,
        request: EntityRelationCreateRequest,
    ) -> EntityRelationContract:
        """Persist a bidirectional relation between two runtime entities.
        Inserts two rows (A→B and B→A) in a single transaction so both
        entities see the relation when queried."""
        forward_id = str(uuid.uuid4())
        reverse_id = str(uuid.uuid4())
        metadata = (
            dict(request.relation_metadata) if request.relation_metadata is not None else None
        )
        with self._db_session() as session:
            try:
                forward = EntityRelationModel(
                    relation_id=forward_id,
                    organization_id=request.organization_id,
                    from_entity_id=request.from_entity_id,
                    to_entity_id=request.to_entity_id,
                    relation_type=request.relation_type,
                    relation_metadata=metadata,
                )
                reverse = EntityRelationModel(
                    relation_id=reverse_id,
                    organization_id=request.organization_id,
                    from_entity_id=request.to_entity_id,
                    to_entity_id=request.from_entity_id,
                    relation_type=request.relation_type,
                    relation_metadata=metadata,
                )
                session.add(forward)
                session.add(reverse)
                session.commit()
                session.refresh(forward)
                return self._entity_relation(forward)
            except IntegrityError as exc:
                session.rollback()
                logger.debug("create_entity_relation IntegrityError: %s", exc)
                raise ConflictError(
                    f"relation '{request.relation_type}' between "
                    f"{request.from_entity_id} and {request.to_entity_id} already exists"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_entity_relation failed: %s", exc)
                raise PersistenceError(f"Unable to create entity relation: {exc}") from exc

    def get_entity_relation_by_id(
        self,
        *,
        organization_id: str,
        relation_id: str,
    ) -> EntityRelationContract | None:
        """Fetch a single relation by id, scoped to the actor's org."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRelationModel)
                    .filter_by(relation_id=relation_id, organization_id=organization_id)
                    .first()
                )
                return self._entity_relation(model)
            except Exception as exc:
                logger.debug("get_entity_relation_by_id failed: %s", exc)
                raise PersistenceError(f"Unable to fetch entity relation: {exc}") from exc

    def list_entity_relations_for_entity(
        self,
        *,
        organization_id: str,
        entity_id: str,
        direction: str = "both",
        relation_type: str | None = None,
    ) -> list[EntityRelationContract]:
        """List relations involving `entity_id`. `direction` is one of
        `"out"` (entity is `from_*`), `"in"` (entity is `to_*`), or `"both"`."""
        if direction not in {"out", "in", "both"}:
            raise PersistenceError(f"invalid direction '{direction}'")
        with self._db_session() as session:
            try:
                query = session.query(EntityRelationModel).filter_by(
                    organization_id=organization_id
                )
                if direction == "out":
                    query = query.filter(EntityRelationModel.from_entity_id == entity_id)
                elif direction == "in":
                    query = query.filter(EntityRelationModel.to_entity_id == entity_id)
                else:
                    query = query.filter(
                        (EntityRelationModel.from_entity_id == entity_id)
                        | (EntityRelationModel.to_entity_id == entity_id)
                    )
                if relation_type is not None:
                    query = query.filter(EntityRelationModel.relation_type == relation_type)
                rows = query.order_by(EntityRelationModel.created_at.asc()).all()
                return [self._entity_relation(row) for row in rows]
            except Exception as exc:
                logger.debug("list_entity_relations_for_entity failed: %s", exc)
                raise PersistenceError(f"Unable to list entity relations: {exc}") from exc

    def delete_entity_relation(
        self,
        *,
        organization_id: str,
        relation_id: str,
    ) -> EntityRelationContract | None:
        """Hard-delete a relation by id, and also delete its reverse row.
        Returns the deleted forward snapshot, or None if not found."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRelationModel)
                    .filter_by(relation_id=relation_id, organization_id=organization_id)
                    .first()
                )
                if model is None:
                    return None
                snapshot = self._entity_relation(model)
                # Also delete the reverse row inserted at creation time
                reverse = (
                    session.query(EntityRelationModel)
                    .filter_by(
                        organization_id=organization_id,
                        from_entity_id=model.to_entity_id,
                        to_entity_id=model.from_entity_id,
                        relation_type=model.relation_type,
                    )
                    .first()
                )
                session.delete(model)
                if reverse is not None:
                    session.delete(reverse)
                session.commit()
                return snapshot
            except Exception as exc:
                session.rollback()
                logger.debug("delete_entity_relation failed: %s", exc)
                raise PersistenceError(f"Unable to delete entity relation: {exc}") from exc

    @staticmethod
    def _entity_relation(item: EntityRelationModel | None) -> EntityRelationContract | None:
        """Hydrate an `EntityRelationModel` row into the relation contract."""
        if item is None:
            return None
        return EntityRelationContract(
            relation_id=item.relation_id,
            organization_id=item.organization_id,
            from_entity_id=item.from_entity_id,
            to_entity_id=item.to_entity_id,
            relation_type=item.relation_type,
            relation_metadata=(
                dict(item.relation_metadata) if item.relation_metadata is not None else None
            ),
            created_at=item.created_at,
        )

    # ── EntityState (workflow enrollments) ──────────────────────────────────

    def enroll_entity_in_workflow(
        self,
        *,
        organization_id: str,
        entity_id: str,
        workflow_id: str,
        current_state: str,
        sla_due_at: datetime | None = None,
    ) -> EntityStateRecord:
        """Create a new state row for `(entity_id, workflow_id)`. Raises
        ConflictError if the entity is already enrolled in that workflow."""
        state_id = str(uuid.uuid4())
        with self._db_session() as session:
            try:
                model = EntityStateRuntimeModel(
                    state_id=state_id,
                    organization_id=organization_id,
                    entity_id=entity_id,
                    workflow_id=workflow_id,
                    current_state=current_state,
                    state_version=0,
                    sla_due_at=sla_due_at,
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                return self._entity_state(model)
            except IntegrityError as exc:
                session.rollback()
                # duplicate (entity_id, workflow_id) enrollment — surface as domain ConflictError
                logger.debug("enroll_entity_in_workflow IntegrityError: %s", exc)
                raise ConflictError(
                    f"entity '{entity_id}' is already enrolled in workflow '{workflow_id}'"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("enroll_entity_in_workflow failed: %s", exc)
                raise PersistenceError(f"Unable to enroll entity: {exc}") from exc

    def store_custom_form_schema(
        self, *, organization_id: str, entity_id: str, custom_form_schema: dict
    ) -> None:
        """Persist a record's fetched dynamic forms, that column only."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRecordModel)
                    .filter_by(organization_id=organization_id, entity_id=entity_id)
                    .with_for_update()
                    .first()
                )
                if model is None:
                    logger.warning("store_custom_form_schema: entity record %s not found", entity_id)
                    raise NotFoundError(f"entity record '{entity_id}' not found")
                model.custom_form_schema = dict(custom_form_schema or {})
                session.commit()
            except NotFoundError:
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("store_custom_form_schema failed: %s", exc)
                raise PersistenceError(f"Unable to store the custom form schema: {exc}") from exc

    def merge_custom_form_data(
        self, *, organization_id: str, entity_id: str, values: dict
    ) -> None:
        """Merge answers into a record's custom form data, key by key.

        Locks the row first, so the results write-back and someone editing a
        cell cannot lose each other's keys. Merging rather than replacing is
        what makes that safe: neither writer has to know the whole form.
        """
        if not values:
            return
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityRecordModel)
                    .filter_by(organization_id=organization_id, entity_id=entity_id)
                    .with_for_update()
                    .first()
                )
                if model is None:
                    logger.warning("merge_custom_form_data: entity record %s not found", entity_id)
                    raise NotFoundError(f"entity record '{entity_id}' not found")
                model.custom_form_data = {**(model.custom_form_data or {}), **values}
                session.commit()
            except NotFoundError:
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("merge_custom_form_data failed: %s", exc)
                raise PersistenceError(f"Unable to store custom form answers: {exc}") from exc

    def get_entity_state_by_id(
        self,
        *,
        organization_id: str,
        state_id: str,
    ) -> EntityStateRecord | None:
        """Fetch a workflow enrollment row by its synthetic state_id."""
        with self._db_session() as session:
            try:
                model = (
                    session.query(EntityStateRuntimeModel)
                    .filter_by(state_id=state_id, organization_id=organization_id)
                    .first()
                )
                return self._entity_state(model)
            except Exception as exc:
                logger.debug("get_entity_state_by_id failed: %s", exc)
                raise PersistenceError(f"Unable to fetch entity state: {exc}") from exc

    def list_entity_states_for_entity(
        self,
        *,
        organization_id: str,
        entity_id: str,
        workflow_id: str | None = None,
    ) -> list[EntityStateRecord]:
        """List all workflow enrollments for `entity_id`, optionally filtered
        to a single workflow. One entity can sit in multiple workflows."""
        with self._db_session() as session:
            try:
                query = session.query(EntityStateRuntimeModel).filter_by(
                    organization_id=organization_id, entity_id=entity_id
                )
                if workflow_id is not None:
                    query = query.filter_by(workflow_id=workflow_id)
                rows = query.order_by(EntityStateRuntimeModel.state_entered_at.asc()).all()
                return [self._entity_state(row) for row in rows]
            except Exception as exc:
                logger.debug("list_entity_states_for_entity failed: %s", exc)
                raise PersistenceError(f"Unable to list entity states: {exc}") from exc

    def has_non_terminal_entities_for_workflow(
        self,
        *,
        organization_id: str,
        workflow_ids: list[str],
        terminal_states: list[str],
    ) -> bool:
        """Return True if any entity enrolled in `workflow_ids` is NOT in a terminal state."""
        with self._db_session() as session:
            try:
                query = session.query(EntityStateRuntimeModel).filter(
                    EntityStateRuntimeModel.organization_id == organization_id,
                    EntityStateRuntimeModel.workflow_id.in_(workflow_ids),
                )
                if terminal_states:
                    query = query.filter(
                        EntityStateRuntimeModel.current_state.notin_(terminal_states)
                    )
                return session.query(query.exists()).scalar()
            except Exception as exc:
                logger.error("has_non_terminal_entities_for_workflow failed: %s", exc)
                raise PersistenceError(f"Unable to check active entities for workflow: {exc}") from exc

    def transition_entity_state(
        self,
        *,
        organization_id: str,
        state_id: str,
        expected_state_version: int,
        next_state: str,
        state_entered_at: datetime,
        last_transition_at: datetime,
        sla_due_at: datetime | None,
    ) -> EntityStateRecord | None:
        """Optimistic-lock state transition. Returns updated row or None on
        version conflict (caller decides whether that's a retry or a 409)."""
        with self._db_session() as session:
            try:
                updated = (
                    session.query(EntityStateRuntimeModel)
                    .filter_by(
                        organization_id=organization_id,
                        state_id=state_id,
                        state_version=expected_state_version,
                    )
                    .update(
                        {
                            "current_state": next_state,
                            "state_version": expected_state_version + 1,
                            "state_entered_at": state_entered_at,
                            "last_transition_at": last_transition_at,
                            "sla_due_at": sla_due_at,
                        }
                    )
                )
                if updated == 0:
                    session.rollback()
                    return None
                session.commit()
                model = (
                    session.query(EntityStateRuntimeModel)
                    .filter_by(state_id=state_id, organization_id=organization_id)
                    .first()
                )
                return self._entity_state(model)
            except Exception as exc:
                session.rollback()
                logger.debug("transition_entity_state failed: %s", exc)
                raise PersistenceError(f"Unable to transition entity state: {exc}") from exc

    @staticmethod
    def _entity_state(item: EntityStateRuntimeModel | None) -> EntityStateRecord | None:
        """Hydrate an `EntityStateRuntimeModel` row into the state contract."""
        if item is None:
            return None
        return EntityStateRecord(
            state_id=item.state_id,
            organization_id=item.organization_id,
            entity_id=item.entity_id,
            workflow_id=item.workflow_id,
            current_state=item.current_state,
            state_version=item.state_version,
            state_entered_at=item.state_entered_at,
            last_transition_at=item.last_transition_at,
            sla_due_at=item.sla_due_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    # ── EntityEvent (audit timeline) ────────────────────────────────────────

    def emit_entity_event(
        self,
        *,
        organization_id: str,
        entity_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str | None = None,
        actor_name: str | None = None,
        actor_role: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        payload: dict | None = None,
    ) -> EntityEventRecord:
        """Append an event row. If `idempotency_key` collides for the org,
        returns the existing row (idempotent emit). Used by the workflow
        engine and integrations to record domain events."""
        with self._db_session() as session:
            try:
                if idempotency_key is not None:
                    existing = (
                        session.query(EntityEventAuditModel)
                        .filter_by(
                            organization_id=organization_id,
                            idempotency_key=idempotency_key,
                        )
                        .first()
                    )
                    if existing is not None:
                        return self._entity_event(existing)
                model = EntityEventAuditModel(
                    event_id=str(uuid.uuid4()),
                    organization_id=organization_id,
                    entity_id=entity_id,
                    event_type=event_type,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    actor_role=actor_role,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    payload=dict(payload or {}),
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                return self._entity_event(model)
            except IntegrityError as exc:
                session.rollback()
                # Race on idempotency_key: re-fetch the winner.
                logger.debug("emit_entity_event IntegrityError (idempotency race): %s", exc)
                if idempotency_key is not None:
                    existing = (
                        session.query(EntityEventAuditModel)
                        .filter_by(
                            organization_id=organization_id,
                            idempotency_key=idempotency_key,
                        )
                        .first()
                    )
                    if existing is not None:
                        return self._entity_event(existing)
                raise PersistenceError(f"Unable to emit entity event: {exc}") from exc
            except Exception as exc:
                session.rollback()
                logger.debug("emit_entity_event failed: %s", exc)
                raise PersistenceError(f"Unable to emit entity event: {exc}") from exc

    def list_entity_events_for_entity(
        self,
        *,
        organization_id: str,
        entity_id: str,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EntityEventRecord], int]:
        """List audit events for `entity_id` newest-first with pagination.

        Returns (page_items, total_count) where total_count reflects the count
        of rows matching all applied filters (event_type included when given)."""
        with self._db_session() as session:
            try:
                base_query = session.query(EntityEventAuditModel).filter_by(
                    organization_id=organization_id, entity_id=entity_id
                )
                if event_type is not None:
                    base_query = base_query.filter_by(event_type=event_type)
                total = base_query.count()
                rows = (
                    base_query
                    .order_by(EntityEventAuditModel.occurred_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return [self._entity_event(row) for row in rows], total
            except Exception as exc:
                logger.debug("list_entity_events_for_entity failed: %s", exc)
                raise PersistenceError(f"Unable to list entity events: {exc}") from exc

    @staticmethod
    def _entity_event(item: EntityEventAuditModel | None) -> EntityEventRecord | None:
        """Hydrate an `EntityEventAuditModel` row into the event contract."""
        if item is None:
            return None
        return EntityEventRecord(
            event_id=item.event_id,
            organization_id=item.organization_id,
            entity_id=item.entity_id,
            event_type=item.event_type,
            actor_type=item.actor_type,
            actor_id=item.actor_id,
            actor_name=item.actor_name,
            actor_role=item.actor_role,
            correlation_id=item.correlation_id,
            idempotency_key=item.idempotency_key,
            payload=dict(item.payload or {}),
            occurred_at=item.occurred_at,
        )

    def upsert_form_config(self, request: UpsertFormConfigRequest) -> FormConfigRecord:
        """Insert or replace a form configuration for `(organization_id,
        form_key)`. Storage is in-process; not persisted to Postgres."""
        try:
            key = (request.organization_id, request.form_key)
            record = FormConfigRecord(
                organization_id=request.organization_id,
                form_key=request.form_key,
                fields=list(request.fields),
                version=request.version,
            )
            self._form_config_registry[key] = record
            return record
        except Exception as exc:
            logger.debug("upsert_form_config failed: %s", exc)
            raise PersistenceError(f"Unable to upsert form config: {exc}") from exc

    def get_form_config(self, organization_id: str, form_key: str) -> FormConfigContract | None:
        """Look up a form config by `(organization_id, form_key)`. Returns None
        when no configuration is registered."""
        record = self._form_config_registry.get((organization_id, form_key))
        if record is None:
            return None
        return FormConfigContract(
            organization_id=record.organization_id,
            form_key=record.form_key,
            fields=list(record.fields),
            version=record.version,
        )

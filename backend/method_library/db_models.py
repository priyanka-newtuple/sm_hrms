"""Persistence adapters for the method library.

Owns four tables:
  - `method_library_categories` — groupings, unique by name per organization.
  - `method_library_methods` — a method's live state, one row each.
  - `method_library_method_versions` — versioned field lists.
  - `method_library_method_version_fields` — the fields inside one version.

Composite foreign keys carry organization_id throughout, the same tenant-safety
pattern the field library uses, so no row can join parents from two tenants.
"""

from __future__ import annotations

import os
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    or_,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

from common.logger import logger
from database.manager import Base
from exceptions import NotFoundError, PersistenceError
from field_library.db_models import FieldLibraryFieldModel, FieldLibraryFieldVersionModel
from method_library.models.interface import (
    CATEGORY_NAME_MAX_LENGTH,
    ENTITY_TYPE_MAX_LENGTH,
    INHERIT_FROM_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    OWNERSHIP_MAX_LENGTH,
    METHOD_NAME_MAX_LENGTH,
    PLACEHOLDER_MAX_LENGTH,
    MethodCategory,
    MethodIdentity,
    MethodVersion,
    MethodVersionField,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from method_library.models.request import MethodFieldInput


IDENTIFIER_LENGTH = 36
FIRST_VERSION = 1
# Mirrors the field library's own page size; there is no shared constant.
DEFAULT_PAGE_LIMIT = 50


def _definitions_schema() -> str:
    """Return the Postgres schema that holds canonical definition tables."""
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


class DuplicateMethodFieldError(Exception):
    """The same field appears twice in one method's field list.

    Separate from PersistenceError so the manager returns a 4xx, not a 500.
    """


class UnknownMethodFieldError(Exception):
    """A requested field does not exist in this organization.

    Separate from PersistenceError so the manager returns a 4xx, not a 500.
    """


class MethodInUseError(Exception):
    """A published workflow state pins this method, so it cannot be deleted.

    Separate from PersistenceError so the manager returns a 4xx, not a 500.
    """


class UnknownMethodFieldVersionError(Exception):
    """A requested version does not belong to the field it was given for.

    Covers both an explicit link-time version_id and a repin target.
    """


class UnknownMethodCategoryError(Exception):
    """The requested category does not exist in this organization.

    Separate from PersistenceError so the manager returns a 4xx, not a 500. The
    composite foreign key would refuse the write anyway, but only as an
    IntegrityError, which reads to a caller as a server fault.
    """


class DuplicateCategoryNameError(Exception):
    """This organization already has a category by that name.

    Separate from PersistenceError so the manager returns a 4xx, not a 500.
    """


class CategoryInUseError(Exception):
    """A method is still filed under this category, so it cannot be deleted.

    Separate from PersistenceError so the manager returns a 4xx, not a 500.
    """


class MethodLibraryCategoryModel(Base):
    """A grouping for methods. Name is unique per organization, case-insensitively."""

    __tablename__ = "method_library_categories"
    __table_args__ = (
        Index(
            "uq_method_library_categories_org_name",
            "organization_id",
            text("lower(name)"),
            unique=True,
        ),
        Index("ix_method_library_categories_organization_id", "organization_id"),
        # Target of the tenant-safe composite FK from methods.
        UniqueConstraint("organization_id", "id", name="uq_method_library_categories_org_id"),
        {"schema": _definitions_schema()},
    )

    id = Column(String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    name = Column(String(CATEGORY_NAME_MAX_LENGTH), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MethodLibraryOrgCounterModel(Base):
    """One row per organization holding the next method_code to hand out.

    Exists so numbering is atomic. Computing "max + 1" would let two creates in
    the same organization read the same maximum before either commits and both
    take the same number.
    """

    __tablename__ = "method_library_org_counters"
    __table_args__ = ({"schema": _definitions_schema()},)

    organization_id = Column(String(IDENTIFIER_LENGTH), primary_key=True)
    next_value = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MethodLibraryMethodModel(Base):
    """A method's live state.

    `method_code` is a per-organization sequence number the database assigns and
    never reuses. Name, description and category are edited in place and never
    produce a version, the same way a field's name is. The field list is what
    gets versioned, on the tables below.
    """

    __tablename__ = "method_library_methods"
    __table_args__ = (
        # A plain uniqueness guarantee is enough: numbers are handed out by the
        # counter and never reused, so archived rows keep theirs and there is no
        # need to exclude them.
        UniqueConstraint(
            "organization_id", "method_code", name="uq_method_library_methods_org_code"
        ),
        Index("ix_method_library_methods_organization_id", "organization_id"),
        Index("ix_method_library_methods_category_id", "category_id"),
        # Target of the tenant-safe composite FK from versions.
        UniqueConstraint("organization_id", "method_id", name="uq_method_library_methods_org_id"),
        ForeignKeyConstraint(
            ["category_id", "organization_id"],
            [
                f"{_definitions_schema()}.method_library_categories.id",
                f"{_definitions_schema()}.method_library_categories.organization_id",
            ],
            name="fk_method_library_methods_category",
        ),
        {"schema": _definitions_schema()},
    )

    method_id = Column(String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    # Per-organization sequence number, assigned by the database on create and
    # never passed in by a caller. See _next_method_code.
    method_code = Column(Integer, nullable=False)
    name = Column(String(METHOD_NAME_MAX_LENGTH), nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(String(IDENTIFIER_LENGTH), nullable=True)
    created_by = Column(String(IDENTIFIER_LENGTH), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MethodLibraryMethodEntityTypeModel(Base):
    """One entity type a method is offered on.

    A method with no rows here is offered nowhere, which is what makes the
    workflow state picker hide untagged methods rather than list everything.
    `entity_type` is text with no key into `entity_types`, matching how
    `workflow_state_machines` stores it, because live workflows reference
    entity types that were never registered there.
    """

    __tablename__ = "method_library_method_entity_types"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "method_id",
            "entity_type",
            name="uq_method_entity_types_org_method_entity",
        ),
        Index("ix_method_entity_types_org_entity", "organization_id", "entity_type"),
        Index("ix_method_entity_types_method_id", "method_id"),
        ForeignKeyConstraint(
            ["method_id", "organization_id"],
            [
                f"{_definitions_schema()}.method_library_methods.method_id",
                f"{_definitions_schema()}.method_library_methods.organization_id",
            ],
            name="fk_method_entity_types_method",
            ondelete="CASCADE",
        ),
        {"schema": _definitions_schema()},
    )

    id = Column(String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4()))
    method_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    entity_type = Column(String(ENTITY_TYPE_MAX_LENGTH), nullable=False)
    created_by = Column(String(IDENTIFIER_LENGTH), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MethodLibraryMethodVersionModel(Base):
    """One version of a method's field list.

    A new version is created whenever the field list changes: a field added,
    removed, reordered, or its label, placeholder or required flag edited.

    TODO: this is still unconditional, matching how field settings version today.
    workflow_method_pins now records which method versions a published workflow
    references, so the check this was waiting on is finally possible: edit in
    place while nothing pins the method, version only once something does.
    Deliberately left alone here, since changing when versions are created is a
    behaviour change of its own rather than part of adding the pins.
    """

    __tablename__ = "method_library_method_versions"
    __table_args__ = (
        UniqueConstraint(
            "method_id", "version", name="uq_method_library_versions_method_version"
        ),
        # At most one current version per method, enforced by the database.
        Index(
            "uq_method_library_versions_method_latest",
            "method_id",
            unique=True,
            postgresql_where=text("is_latest"),
        ),
        Index("ix_method_library_versions_method_id", "method_id"),
        Index("ix_method_library_versions_organization_id", "organization_id"),
        # Target of the tenant-safe composite FK from version fields.
        UniqueConstraint(
            "version_id", "organization_id", name="uq_method_library_versions_version_org"
        ),
        ForeignKeyConstraint(
            ["method_id", "organization_id"],
            [
                f"{_definitions_schema()}.method_library_methods.method_id",
                f"{_definitions_schema()}.method_library_methods.organization_id",
            ],
            name="fk_method_library_versions_method",
            ondelete="CASCADE",
        ),
        {"schema": _definitions_schema()},
    )

    version_id = Column(String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4()))
    method_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    version = Column(Integer, nullable=False)
    is_latest = Column(Boolean, nullable=False, default=True)
    connector_id = Column(String(IDENTIFIER_LENGTH), nullable=True)
    created_by = Column(String(IDENTIFIER_LENGTH), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MethodLibraryMethodVersionFieldModel(Base):
    """One field listed inside one method version.

    Pins a Field Library version, so the field's type and settings are whatever
    they were when this method version was created. The FK into the field library
    deliberately does not cascade, so the database itself refuses to hard-delete a
    field that a method version still lists, the same guard already in place for
    forms.
    """

    __tablename__ = "method_library_method_version_fields"
    __table_args__ = (
        UniqueConstraint(
            "method_version_id",
            "library_field_id",
            name="uq_method_library_version_fields_version_field",
        ),
        Index("ix_method_library_version_fields_version_id", "method_version_id"),
        Index("ix_method_library_version_fields_library_field_id", "library_field_id"),
        Index("ix_method_library_version_fields_organization_id", "organization_id"),
        ForeignKeyConstraint(
            ["method_version_id", "organization_id"],
            [
                f"{_definitions_schema()}.method_library_method_versions.version_id",
                f"{_definitions_schema()}.method_library_method_versions.organization_id",
            ],
            name="fk_method_library_version_fields_version",
            ondelete="CASCADE",
        ),
        # Pins the field version, and ties it to the field named alongside it so
        # the two cannot drift. No cascade: this is the guard that blocks a hard
        # delete of a field a method still lists.
        ForeignKeyConstraint(
            ["field_version_id", "library_field_id"],
            [
                f"{_definitions_schema()}.field_library_field_versions.version_id",
                f"{_definitions_schema()}.field_library_field_versions.library_field_id",
            ],
            name="fk_method_library_version_fields_field_version",
        ),
        ForeignKeyConstraint(
            ["field_version_id", "organization_id"],
            [
                f"{_definitions_schema()}.field_library_field_versions.version_id",
                f"{_definitions_schema()}.field_library_field_versions.organization_id",
            ],
            name="fk_method_library_version_fields_field_org",
        ),
        {"schema": _definitions_schema()},
    )

    id = Column(String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4()))
    method_version_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    library_field_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    field_version_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    label = Column(String(LABEL_MAX_LENGTH), nullable=True)
    placeholder = Column(String(PLACEHOLDER_MAX_LENGTH), nullable=True)
    required = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)
    # Optional source intent: which entity type + field this field's value should
    # be resolved from once the method is attached to a workflow state, without
    # the method itself knowing which entity type that will be (Phase 1 keeps
    # methods entity-agnostic). Both null, or both set — never one alone; a field
    # without this behaves exactly as it does today.
    source_entity_type = Column(String(256), nullable=True)
    source_field_key = Column(String(256), nullable=True)
    # "<EntityTypeName>.<field>" this usage should inherit its value from at
    # pin time, or None to enter it directly. Per-usage, not on the field
    # itself, so the same reusable field can be owned in one Method and
    # inherited in another.
    inherit_from = Column(String(INHERIT_FROM_MAX_LENGTH), nullable=True)
    # The opt-in for method-block-level inheritance. 'inherited' means: at pin
    # time, resolve this field from the record linked through the relation
    # named by `source_entity_type` / `source_field_key` above — which is what
    # those two columns were added for, and this is their first reader. Unlike
    # `inherit_from`, this is NOT projected into the entity type's relation
    # metadata at publish, so it applies only where this Method Block is in
    # use, never to every record of the type. NULL = not stated = today's
    # behaviour. Values are `workflow.models.interface.FieldOwnership`.
    ownership = Column(String(OWNERSHIP_MAX_LENGTH), nullable=True)
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MethodLibraryModelService:
    """Read methods, their current version, and that version's field list."""

    def __init__(self, database_service_manager: object) -> None:
        """Bind to Postgres. The definitions schema only exists there."""
        if database_service_manager is None or not hasattr(
            database_service_manager, "postgres_db_service"
        ):
            raise PersistenceError(
                "MethodLibraryModelService requires a database_service_manager with "
                "postgres_db_service()"
            )
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = self.database_manager.postgres_db_service()
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.module_name = "method_library"

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

    @staticmethod
    def _identity(
        row: MethodLibraryMethodModel,
        category_name: str | None,
        entity_types: list[str] | None = None,
    ) -> MethodIdentity:
        """Map a method row onto its contract."""
        return MethodIdentity(
            entity_types=entity_types or [],
            method_id=row.method_id,
            organization_id=row.organization_id,
            method_code=row.method_code,
            name=row.name,
            description=row.description,
            category_id=row.category_id,
            category_name=category_name,
            created_by=row.created_by,
            is_archived=row.archived_at is not None,
            created_at=row.created_at,
        )

    @staticmethod
    def _entity_types_for(
        session: Session, organization_id: str, method_ids: list[str]
    ) -> dict[str, list[str]]:
        """Tagged entity types per method, fetched for a whole page in one query."""
        if not method_ids:
            return {}
        rows = (
            session.query(
                MethodLibraryMethodEntityTypeModel.method_id,
                MethodLibraryMethodEntityTypeModel.entity_type,
            )
            .filter(
                MethodLibraryMethodEntityTypeModel.organization_id == organization_id,
                MethodLibraryMethodEntityTypeModel.method_id.in_(method_ids),
            )
            .order_by(MethodLibraryMethodEntityTypeModel.entity_type)
            .all()
        )
        grouped: dict[str, list[str]] = defaultdict(list)
        for method_id, entity_type in rows:
            grouped[method_id].append(entity_type)
        return grouped

    def replace_entity_types(
        self,
        *,
        organization_id: str,
        method_id: str,
        entity_types: list[str],
        actor_id: str | None = None,
    ) -> list[str]:
        """Set a method's entity-type tags to exactly `entity_types`.

        An empty list is allowed and clears every tag, which hides the method
        from all workflow state pickers without archiving it.
        """
        with self._db_session() as session:
            try:
                method = (
                    session.query(MethodLibraryMethodModel)
                    .filter(
                        MethodLibraryMethodModel.organization_id == organization_id,
                        MethodLibraryMethodModel.method_id == method_id,
                    )
                    .one_or_none()
                )
                if method is None:
                    raise NotFoundError(f"Method {method_id} not found")
                desired = list(dict.fromkeys(e.strip() for e in entity_types if e and e.strip()))
                session.query(MethodLibraryMethodEntityTypeModel).filter(
                    MethodLibraryMethodEntityTypeModel.organization_id == organization_id,
                    MethodLibraryMethodEntityTypeModel.method_id == method_id,
                ).delete(synchronize_session=False)
                for entity_type in desired:
                    session.add(
                        MethodLibraryMethodEntityTypeModel(
                            method_id=method_id,
                            organization_id=organization_id,
                            entity_type=entity_type,
                            created_by=actor_id,
                        )
                    )
                session.commit()
                return sorted(desired)
            except NotFoundError:
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("replace_entity_types failed: %s", exc)
                raise PersistenceError(f"Unable to set method entity types: {exc}") from exc

    @staticmethod
    def _version(row: MethodLibraryMethodVersionModel) -> MethodVersion:
        """Map a version row onto its contract."""
        return MethodVersion(
            version_id=row.version_id,
            method_id=row.method_id,
            organization_id=row.organization_id,
            version=row.version,
            is_latest=bool(row.is_latest),
            connector_id=row.connector_id,
            created_by=row.created_by,
        )

    @staticmethod
    def _next_method_code(session: Session, organization_id: str) -> int:
        """Atomically claim this organization's next method_code.

        INSERT ... ON CONFLICT DO UPDATE ... RETURNING, the same mechanism
        `_get_next_auto_number` uses for entity auto-numbers. The increment and
        the read happen in one statement, so two concurrent creates in the same
        organization cannot both take the same number the way a "max + 1" read
        would allow. The commit belongs to the caller's transaction.
        """
        schema = _definitions_schema()
        sql = text(
            f"INSERT INTO {schema}.method_library_org_counters "
            "(organization_id, next_value) VALUES (:organization_id, 1) "
            "ON CONFLICT (organization_id) "
            "DO UPDATE SET next_value = method_library_org_counters.next_value + 1 "
            "RETURNING next_value"
        )
        return int(session.execute(sql, {"organization_id": organization_id}).scalar())

    def create_method(
        self,
        *,
        organization_id: str,
        name: str,
        description: str | None = None,
        category_id: str | None = None,
        created_by: str | None = None,
    ) -> MethodIdentity:
        """Insert a method, claiming its method_code from the counter.

        The caller never supplies method_code. Claiming the number and inserting
        the row share one transaction, so a failed insert does not strand a
        number in use by nothing; it is simply never reused.
        """
        with self._db_session() as session:
            try:
                self._assert_category_exists(session, organization_id, category_id)
                method = MethodLibraryMethodModel(
                    method_id=str(uuid4()),
                    organization_id=organization_id,
                    method_code=self._next_method_code(session, organization_id),
                    name=name,
                    description=description,
                    category_id=category_id,
                    created_by=created_by,
                )
                session.add(method)
                session.commit()
                session.refresh(method)
                category_name = (
                    session.query(MethodLibraryCategoryModel.name)
                    .filter(
                        MethodLibraryCategoryModel.id == method.category_id,
                        MethodLibraryCategoryModel.organization_id == organization_id,
                    )
                    .scalar()
                    if method.category_id
                    else None
                )
                return self._identity(method, category_name)
            except UnknownMethodCategoryError:
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("create_method failed: %s", exc)
                raise PersistenceError(f"Unable to create the method: {exc}") from exc

    @staticmethod
    def _resolve_field_pins(
        session: Session, organization_id: str, field_inputs: list[MethodFieldInput]
    ) -> dict[str, str]:
        """Map each requested field to the version it should pin.

        An explicit `version_id` pins that exact version; omitted, it resolves
        to the field's current latest. Scoped to the organization and to
        non-archived fields, so a foreign or archived field has no rows here.
        """
        wanted = [entry.library_field_id for entry in field_inputs]
        if not wanted:
            return {}
        duplicates = {field_id for field_id in wanted if wanted.count(field_id) > 1}
        if duplicates:
            raise DuplicateMethodFieldError(
                "a method cannot list the same field twice: "
                + ", ".join(sorted(duplicates))
            )
        rows = (
            session.query(
                FieldLibraryFieldVersionModel.library_field_id,
                FieldLibraryFieldVersionModel.version_id,
                FieldLibraryFieldVersionModel.is_latest,
            )
            .join(
                FieldLibraryFieldModel,
                and_(
                    FieldLibraryFieldModel.library_field_id
                    == FieldLibraryFieldVersionModel.library_field_id,
                    FieldLibraryFieldModel.organization_id
                    == FieldLibraryFieldVersionModel.organization_id,
                ),
            )
            .filter(
                FieldLibraryFieldVersionModel.organization_id == organization_id,
                FieldLibraryFieldVersionModel.library_field_id.in_(set(wanted)),
                FieldLibraryFieldModel.archived_at.is_(None),
            )
            .all()
        )
        latest_by_field: dict[str, str] = {}
        versions_by_field: dict[str, set[str]] = defaultdict(set)
        for library_field_id, version_id, is_latest in rows:
            versions_by_field[library_field_id].add(version_id)
            if is_latest:
                latest_by_field[library_field_id] = version_id

        pins: dict[str, str] = {}
        missing_fields: list[str] = []
        bad_versions: list[str] = []
        for entry in field_inputs:
            if entry.version_id:
                if entry.version_id in versions_by_field.get(entry.library_field_id, ()):
                    pins[entry.library_field_id] = entry.version_id
                else:
                    bad_versions.append(
                        f"{entry.library_field_id} (version {entry.version_id})"
                    )
            elif entry.library_field_id in latest_by_field:
                pins[entry.library_field_id] = latest_by_field[entry.library_field_id]
            else:
                missing_fields.append(entry.library_field_id)

        if bad_versions:
            raise UnknownMethodFieldVersionError(
                "these versions do not belong to their field, or the field is "
                "archived: " + ", ".join(sorted(bad_versions))
            )
        if missing_fields:
            raise UnknownMethodFieldError(
                "these fields are not available in this organization, because they "
                "do not exist or have been archived: " + ", ".join(sorted(set(missing_fields)))
            )
        return pins

    @staticmethod
    def _version_belongs_to_field(
        session: Session, organization_id: str, library_field_id: str, version_id: str
    ) -> bool:
        """Whether one Field Library version genuinely belongs to this field.

        No archived_at check, unlike `_resolve_field_pins`: repin only moves an
        existing pin among a field's own versions, it never adopts a new field.
        """
        return (
            session.query(FieldLibraryFieldVersionModel.version_id)
            .filter(
                FieldLibraryFieldVersionModel.organization_id == organization_id,
                FieldLibraryFieldVersionModel.library_field_id == library_field_id,
                FieldLibraryFieldVersionModel.version_id == version_id,
            )
            .first()
            is not None
        )

    def _insert_version_fields(
        self,
        session: Session,
        *,
        organization_id: str,
        method_version_id: str,
        field_inputs: list[MethodFieldInput],
    ) -> None:
        """Insert one row per field, each pinned to that field's latest version."""
        pins = self._resolve_field_pins(session, organization_id, field_inputs)
        for entry in field_inputs:
            session.add(
                MethodLibraryMethodVersionFieldModel(
                    id=str(uuid4()),
                    method_version_id=method_version_id,
                    library_field_id=entry.library_field_id,
                    field_version_id=pins[entry.library_field_id],
                    label=entry.label,
                    placeholder=entry.placeholder,
                    required=bool(entry.required),
                    position=int(entry.position),
                    source_entity_type=entry.source_entity_type,
                    source_field_key=entry.source_field_key,
                    inherit_from=entry.inherit_from,
                    ownership=entry.ownership,
                    organization_id=organization_id,
                )
            )

    def create_method_with_fields(
        self,
        *,
        organization_id: str,
        name: str,
        description: str | None,
        category_id: str | None,
        field_inputs: list[MethodFieldInput],
        created_by: str | None,
    ) -> tuple[MethodIdentity, MethodVersion]:
        """Create a method, its version 1, and that version's fields, atomically.

        Everything lands together or nothing does, so a method can never exist
        without a version for the workflow layer to resolve.
        """
        with self._db_session() as session:
            try:
                self._assert_category_exists(session, organization_id, category_id)
                method = MethodLibraryMethodModel(
                    method_id=str(uuid4()),
                    organization_id=organization_id,
                    method_code=self._next_method_code(session, organization_id),
                    name=name,
                    description=description,
                    category_id=category_id,
                    created_by=created_by,
                )
                session.add(method)
                session.flush()
                version = MethodLibraryMethodVersionModel(
                    version_id=str(uuid4()),
                    method_id=method.method_id,
                    organization_id=organization_id,
                    version=FIRST_VERSION,
                    is_latest=True,
                    created_by=created_by,
                )
                session.add(version)
                session.flush()
                self._insert_version_fields(
                    session,
                    organization_id=organization_id,
                    method_version_id=version.version_id,
                    field_inputs=field_inputs,
                )
                session.commit()
                session.refresh(method)
                session.refresh(version)
                return self._identity(method, None), self._version(version)
            except (
                DuplicateMethodFieldError,
                UnknownMethodFieldError,
                UnknownMethodFieldVersionError,
                UnknownMethodCategoryError,
            ):
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("create_method_with_fields failed: %s", exc)
                raise PersistenceError(f"Unable to create the method: {exc}") from exc

    @staticmethod
    def _clone_source_version(
        session: Session, organization_id: str, method_id: str, version_id: str | None
    ) -> MethodLibraryMethodVersionModel:
        """The version a clone copies: the named one, or the method's latest.

        A supplied version_id is matched against this method and organization, so
        one belonging to another method or another tenant is rejected rather than
        quietly cloned.
        """
        query = session.query(MethodLibraryMethodVersionModel).filter(
            MethodLibraryMethodVersionModel.organization_id == organization_id,
            MethodLibraryMethodVersionModel.method_id == method_id,
        )
        if version_id:
            row = query.filter(
                MethodLibraryMethodVersionModel.version_id == version_id
            ).first()
            if row is None:
                raise NotFoundError(
                    f"version '{version_id}' does not belong to method '{method_id}'"
                )
            return row
        row = query.filter(MethodLibraryMethodVersionModel.is_latest.is_(True)).first()
        if row is None:
            raise NotFoundError(f"method '{method_id}' has no current version")
        return row

    @staticmethod
    def _copy_version_fields(
        session: Session,
        *,
        organization_id: str,
        source_version_id: str,
        method_version_id: str,
    ) -> None:
        """Copy one version's field rows onto a new version, pins intact.

        Deliberately not routed through _insert_version_fields: that re-resolves
        every field to its current latest version, which is right for an edit and
        wrong for a clone. Copying `field_version_id` verbatim is what makes
        cloning an old version reproduce it rather than silently upgrade it.
        """
        rows = (
            session.query(MethodLibraryMethodVersionFieldModel)
            .filter(
                MethodLibraryMethodVersionFieldModel.organization_id == organization_id,
                MethodLibraryMethodVersionFieldModel.method_version_id == source_version_id,
            )
            .order_by(
                MethodLibraryMethodVersionFieldModel.position.asc(),
                # Stable tiebreaker: rows written before positions were
                # settled can still share one, and order must not vary.
                MethodLibraryMethodVersionFieldModel.id.asc(),
            )
            .all()
        )
        for row in rows:
            session.add(
                MethodLibraryMethodVersionFieldModel(
                    id=str(uuid4()),
                    method_version_id=method_version_id,
                    library_field_id=row.library_field_id,
                    field_version_id=row.field_version_id,
                    label=row.label,
                    placeholder=row.placeholder,
                    required=bool(row.required),
                    position=int(row.position),
                    source_entity_type=row.source_entity_type,
                    source_field_key=row.source_field_key,
                    inherit_from=row.inherit_from,
                    ownership=row.ownership,
                    organization_id=organization_id,
                )
            )

    def clone_method(
        self,
        *,
        organization_id: str,
        source_method_id: str,
        source_version_id: str | None,
        name: str,
        category_id: str | None,
        created_by: str | None,
    ) -> tuple[MethodIdentity, MethodVersion]:
        """Copy one version of a method into a new method, atomically.

        The new method is independent from the moment it exists: its own
        method_code, its own version 1 whatever version it was cloned from, and no
        record tying it back to the source.
        """
        with self._db_session() as session:
            try:
                source = (
                    session.query(MethodLibraryMethodModel)
                    .filter(
                        MethodLibraryMethodModel.organization_id == organization_id,
                        MethodLibraryMethodModel.method_id == source_method_id,
                    )
                    .first()
                )
                if source is None:
                    raise NotFoundError(f"method '{source_method_id}' was not found")
                self._assert_category_exists(session, organization_id, category_id)
                source_version = self._clone_source_version(
                    session, organization_id, source_method_id, source_version_id
                )
                method = MethodLibraryMethodModel(
                    method_id=str(uuid4()),
                    organization_id=organization_id,
                    method_code=self._next_method_code(session, organization_id),
                    name=name,
                    description=source.description,
                    category_id=category_id if category_id is not None else source.category_id,
                    created_by=created_by,
                )
                session.add(method)
                session.flush()
                version = MethodLibraryMethodVersionModel(
                    version_id=str(uuid4()),
                    method_id=method.method_id,
                    organization_id=organization_id,
                    version=FIRST_VERSION,
                    is_latest=True,
                    created_by=created_by,
                )
                session.add(version)
                session.flush()
                self._copy_version_fields(
                    session,
                    organization_id=organization_id,
                    source_version_id=source_version.version_id,
                    method_version_id=version.version_id,
                )
                session.commit()
                session.refresh(method)
                session.refresh(version)
                return self._identity(method, None), self._version(version)
            except (NotFoundError, UnknownMethodCategoryError):
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("clone_method failed: %s", exc)
                raise PersistenceError(f"Unable to clone the method: {exc}") from exc

    def update_method_metadata(
        self,
        *,
        organization_id: str,
        method_id: str,
        changes: dict[str, object],
    ) -> MethodIdentity | None:
        """Apply an in-place edit to name, description or category.

        Never creates a version: these are live editable state. Only the keys
        present in `changes` are touched, so omitting one leaves it alone.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(MethodLibraryMethodModel)
                    .filter(
                        MethodLibraryMethodModel.organization_id == organization_id,
                        MethodLibraryMethodModel.method_id == method_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                if "category_id" in changes:
                    self._assert_category_exists(
                        session, organization_id, changes["category_id"]
                    )
                for attribute, value in changes.items():
                    setattr(row, attribute, value)
                session.commit()
                session.refresh(row)
                category_name = (
                    session.query(MethodLibraryCategoryModel.name)
                    .filter(
                        MethodLibraryCategoryModel.id == row.category_id,
                        MethodLibraryCategoryModel.organization_id == organization_id,
                    )
                    .scalar()
                    if row.category_id
                    else None
                )
                return self._identity(row, category_name)
            except UnknownMethodCategoryError:
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("update_method_metadata failed: %s", exc)
                raise PersistenceError(f"Unable to update the method: {exc}") from exc

    def replace_method_field_list(
        self,
        *,
        organization_id: str,
        method_id: str,
        field_inputs: list[MethodFieldInput],
        connector_id: str | None = None,
        created_by: str | None,
    ) -> MethodVersion:
        """Supersede the current version with a new one holding the given fields.

        The previous version row is demoted, never deleted, so the method's
        history stays traceable and anything pinned to it keeps resolving.
        """
        with self._db_session() as session:
            try:
                current = (
                    session.query(MethodLibraryMethodVersionModel)
                    .filter(
                        MethodLibraryMethodVersionModel.organization_id == organization_id,
                        MethodLibraryMethodVersionModel.method_id == method_id,
                        MethodLibraryMethodVersionModel.is_latest.is_(True),
                    )
                    .with_for_update()
                    .first()
                )
                if current is None:
                    raise NotFoundError(f"method '{method_id}' has no current version")
                # Demote first: the partial unique index allows one flagged
                # version, so the old flag must clear before the new row lands.
                current.is_latest = False
                session.flush()
                version = MethodLibraryMethodVersionModel(
                    version_id=str(uuid4()),
                    method_id=method_id,
                    organization_id=organization_id,
                    version=int(current.version) + 1,
                    is_latest=True,
                    connector_id=connector_id,
                    created_by=created_by,
                )
                session.add(version)
                session.flush()
                self._insert_version_fields(
                    session,
                    organization_id=organization_id,
                    method_version_id=version.version_id,
                    field_inputs=field_inputs,
                )
                session.commit()
                session.refresh(version)
                return self._version(version)
            except (
                NotFoundError,
                DuplicateMethodFieldError,
                UnknownMethodFieldError,
                UnknownMethodFieldVersionError,
            ):
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("replace_method_field_list failed: %s", exc)
                raise PersistenceError(f"Unable to replace the field list: {exc}") from exc

    @staticmethod
    def _repin_version_fields(
        session: Session,
        *,
        organization_id: str,
        source_rows: list[MethodLibraryMethodVersionFieldModel],
        method_version_id: str,
        link_id: str,
        version_id: str,
    ) -> None:
        """Carry every field row onto a new version, repinning only `link_id`.

        Mirrors _copy_version_fields's shape (clone's equivalent carry-over),
        except one row's field_version_id is replaced along the way rather than
        preserved verbatim.
        """
        for row in source_rows:
            session.add(
                MethodLibraryMethodVersionFieldModel(
                    id=str(uuid4()),
                    method_version_id=method_version_id,
                    library_field_id=row.library_field_id,
                    field_version_id=(
                        version_id if row.id == link_id else row.field_version_id
                    ),
                    label=row.label,
                    placeholder=row.placeholder,
                    required=bool(row.required),
                    position=int(row.position),
                    source_entity_type=row.source_entity_type,
                    source_field_key=row.source_field_key,
                    inherit_from=row.inherit_from,
                    ownership=row.ownership,
                    organization_id=organization_id,
                )
            )

    def repin_method_field(
        self,
        *,
        organization_id: str,
        method_id: str,
        link_id: str,
        version_id: str,
        created_by: str | None,
    ) -> MethodVersion:
        """Move one field on a method to a different version of that same field.

        Targeted: every other field row carries over unchanged. Still produces
        a new method version rather than an in-place edit, same as any other
        field-list change — a workflow can pin to a specific method version
        (workflow_method_pins), and an in-place edit would break that pin.
        """
        with self._db_session() as session:
            try:
                current = (
                    session.query(MethodLibraryMethodVersionModel)
                    .filter(
                        MethodLibraryMethodVersionModel.organization_id == organization_id,
                        MethodLibraryMethodVersionModel.method_id == method_id,
                        MethodLibraryMethodVersionModel.is_latest.is_(True),
                    )
                    .with_for_update()
                    .first()
                )
                if current is None:
                    raise NotFoundError(f"method '{method_id}' has no current version")
                existing_rows = (
                    session.query(MethodLibraryMethodVersionFieldModel)
                    .filter(
                        MethodLibraryMethodVersionFieldModel.organization_id
                        == organization_id,
                        MethodLibraryMethodVersionFieldModel.method_version_id
                        == current.version_id,
                    )
                    .order_by(MethodLibraryMethodVersionFieldModel.position.asc())
                    .all()
                )
                target = next((row for row in existing_rows if row.id == link_id), None)
                if target is None:
                    raise NotFoundError(
                        f"field link '{link_id}' was not found on method '{method_id}'"
                    )
                if not self._version_belongs_to_field(
                    session, organization_id, target.library_field_id, version_id
                ):
                    raise UnknownMethodFieldVersionError(
                        f"version '{version_id}' does not belong to field "
                        f"'{target.library_field_id}'"
                    )
                # Demote first: the partial unique index allows one flagged
                # version, so the old flag must clear before the new row lands.
                current.is_latest = False
                session.flush()
                new_version = MethodLibraryMethodVersionModel(
                    version_id=str(uuid4()),
                    method_id=method_id,
                    organization_id=organization_id,
                    version=int(current.version) + 1,
                    is_latest=True,
                    created_by=created_by,
                )
                session.add(new_version)
                session.flush()
                self._repin_version_fields(
                    session,
                    organization_id=organization_id,
                    source_rows=existing_rows,
                    method_version_id=new_version.version_id,
                    link_id=link_id,
                    version_id=version_id,
                )
                session.commit()
                session.refresh(new_version)
                return self._version(new_version)
            except (NotFoundError, UnknownMethodFieldVersionError):
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                logger.debug("repin_method_field failed: %s", exc)
                raise PersistenceError(f"Unable to repin the method field: {exc}") from exc

    def delete_method(self, *, organization_id: str, method_id: str) -> bool:
        """Hard delete a method. Returns False when it was already gone.

        Its versions and version fields go with it: both foreign keys cascade, so
        no manual cleanup is needed.

        Refused while a published workflow state pins any of the method's
        versions, the way the field library refuses to hard-delete a field a form
        still uses. The pin table's foreign key would refuse it anyway; checking
        first turns that into a clear error instead of an integrity failure.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(MethodLibraryMethodModel)
                    .filter(
                        MethodLibraryMethodModel.organization_id == organization_id,
                        MethodLibraryMethodModel.method_id == method_id,
                    )
                    .first()
                )
                if row is None:
                    return False
                pinned = self._count_workflow_pins(session, organization_id, method_id)
                if pinned:
                    raise MethodInUseError(
                        f"this method is pinned by {pinned} published workflow "
                        "state(s) and cannot be deleted"
                    )
                session.delete(row)
                session.commit()
                return True
            except MethodInUseError:
                session.rollback()
                raise
            except IntegrityError as exc:
                session.rollback()
                raise MethodInUseError(
                    "this method is still referenced by a published workflow and "
                    "cannot be deleted"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("delete_method failed: %s", exc)
                raise PersistenceError(f"Unable to delete the method: {exc}") from exc

    def archive_method(
        self, *, organization_id: str, method_id: str
    ) -> MethodIdentity | None:
        """Stamp the method as archived. Versions and version fields are untouched.

        Unconditional, same as field library's archive_field: reversible and
        hidden rather than destructive, never blocked by use elsewhere. Idempotent.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(MethodLibraryMethodModel)
                    .filter(
                        MethodLibraryMethodModel.organization_id == organization_id,
                        MethodLibraryMethodModel.method_id == method_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                if row.archived_at is None:
                    row.archived_at = datetime.now(UTC)
                    session.commit()
                    session.refresh(row)
                category_name = (
                    session.query(MethodLibraryCategoryModel.name)
                    .filter(
                        MethodLibraryCategoryModel.id == row.category_id,
                        MethodLibraryCategoryModel.organization_id == organization_id,
                    )
                    .scalar()
                    if row.category_id
                    else None
                )
                return self._identity(row, category_name)
            except Exception as exc:
                session.rollback()
                logger.debug("archive_method failed: %s", exc)
                raise PersistenceError(f"Unable to archive the method: {exc}") from exc

    def unarchive_method(
        self, *, organization_id: str, method_id: str
    ) -> MethodIdentity | None:
        """Clear the archived stamp. Idempotent: a live method is returned as is."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(MethodLibraryMethodModel)
                    .filter(
                        MethodLibraryMethodModel.organization_id == organization_id,
                        MethodLibraryMethodModel.method_id == method_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                if row.archived_at is not None:
                    row.archived_at = None
                    session.commit()
                    session.refresh(row)
                category_name = (
                    session.query(MethodLibraryCategoryModel.name)
                    .filter(
                        MethodLibraryCategoryModel.id == row.category_id,
                        MethodLibraryCategoryModel.organization_id == organization_id,
                    )
                    .scalar()
                    if row.category_id
                    else None
                )
                return self._identity(row, category_name)
            except Exception as exc:
                session.rollback()
                logger.debug("unarchive_method failed: %s", exc)
                raise PersistenceError(f"Unable to unarchive the method: {exc}") from exc

    @staticmethod
    def _count_workflow_pins(session: Session, organization_id: str, method_id: str) -> int:
        """How many workflow states pin any version of this method.

        Read as raw SQL against the pin table rather than through the workflow
        module's models: the method library owns the guard, and importing the
        workflow layer here would point the dependency the wrong way.
        """
        schema = _definitions_schema()
        sql = text(
            f"SELECT COUNT(*) FROM {schema}.workflow_method_pins "
            "WHERE organization_id = :organization_id AND method_id = :method_id"
        )
        return int(
            session.execute(
                sql, {"organization_id": organization_id, "method_id": method_id}
            ).scalar()
            or 0
        )

    @staticmethod
    def _escape_like(term: str) -> str:
        """Neutralise LIKE wildcards in user input.

        Without this an underscore or percent in a search term would act as a
        wildcard and match far more than the user typed.
        """
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def list_methods(
        self,
        *,
        organization_id: str,
        include_archived: bool = False,
        search: str | None = None,
        entity_type: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[MethodIdentity], int]:
        """A page of methods with their category name, plus the total match count.

        `search` matches part of the method name or its category name, case
        insensitively. The category is joined in rather than fetched per row, so a
        page costs two queries however many methods it holds.

        `entity_type` keeps only methods tagged for that entity type, so an
        untagged method is excluded here rather than filtered out by the caller.
        """
        with self._db_session() as session:
            try:
                query = (
                    session.query(MethodLibraryMethodModel, MethodLibraryCategoryModel.name)
                    .outerjoin(
                        MethodLibraryCategoryModel,
                        and_(
                            MethodLibraryCategoryModel.id
                            == MethodLibraryMethodModel.category_id,
                            MethodLibraryCategoryModel.organization_id
                            == MethodLibraryMethodModel.organization_id,
                        ),
                    )
                    .filter(MethodLibraryMethodModel.organization_id == organization_id)
                )
                if not include_archived:
                    query = query.filter(MethodLibraryMethodModel.archived_at.is_(None))
                normalized_entity_type = (entity_type or "").strip()
                if normalized_entity_type:
                    query = query.filter(
                        session.query(MethodLibraryMethodEntityTypeModel)
                        .filter(
                            MethodLibraryMethodEntityTypeModel.method_id
                            == MethodLibraryMethodModel.method_id,
                            MethodLibraryMethodEntityTypeModel.organization_id
                            == MethodLibraryMethodModel.organization_id,
                            MethodLibraryMethodEntityTypeModel.entity_type
                            == normalized_entity_type,
                        )
                        .exists()
                    )
                normalized_search = (search or "").strip()
                if normalized_search:
                    pattern = f"%{self._escape_like(normalized_search)}%"
                    query = query.filter(
                        or_(
                            MethodLibraryMethodModel.name.ilike(pattern, escape="\\"),
                            MethodLibraryCategoryModel.name.ilike(pattern, escape="\\"),
                        )
                    )
                total = query.order_by(None).count()
                rows = (
                    query.order_by(MethodLibraryMethodModel.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                    .all()
                )
                tags = self._entity_types_for(
                    session, organization_id, [method.method_id for method, _ in rows]
                )
                return [
                    self._identity(method, name, tags.get(method.method_id, []))
                    for method, name in rows
                ], total
            except Exception as exc:
                logger.debug("list_methods failed: %s", exc)
                raise PersistenceError(f"Unable to list methods: {exc}") from exc

    def list_method_versions(
        self,
        *,
        organization_id: str,
        method_id: str,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[MethodVersion], int]:
        """A page of one method's version history, newest first, plus the total.

        Raises rather than returning an empty page when the method does not exist
        in this organization, so a caller can tell "no such method" apart from
        "this method has no versions".
        """
        with self._db_session() as session:
            try:
                exists = (
                    session.query(MethodLibraryMethodModel.method_id)
                    .filter(
                        MethodLibraryMethodModel.organization_id == organization_id,
                        MethodLibraryMethodModel.method_id == method_id,
                    )
                    .first()
                )
                if exists is None:
                    raise NotFoundError(f"method '{method_id}' was not found")
                query = session.query(MethodLibraryMethodVersionModel).filter(
                    MethodLibraryMethodVersionModel.organization_id == organization_id,
                    MethodLibraryMethodVersionModel.method_id == method_id,
                )
                total = query.order_by(None).count()
                rows = (
                    query.order_by(MethodLibraryMethodVersionModel.version.desc())
                    .limit(limit)
                    .offset(offset)
                    .all()
                )
                return [self._version(row) for row in rows], total
            except NotFoundError:
                raise
            except Exception as exc:
                logger.debug("list_method_versions failed: %s", exc)
                raise PersistenceError(f"Unable to list method versions: {exc}") from exc

    def get_method(
        self, *, organization_id: str, method_id: str
    ) -> MethodIdentity | None:
        """One method with its category name. None when absent in this organization."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(MethodLibraryMethodModel, MethodLibraryCategoryModel.name)
                    .outerjoin(
                        MethodLibraryCategoryModel,
                        and_(
                            MethodLibraryCategoryModel.id
                            == MethodLibraryMethodModel.category_id,
                            MethodLibraryCategoryModel.organization_id
                            == MethodLibraryMethodModel.organization_id,
                        ),
                    )
                    .filter(
                        MethodLibraryMethodModel.organization_id == organization_id,
                        MethodLibraryMethodModel.method_id == method_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                method, category_name = row
                tags = self._entity_types_for(session, organization_id, [method_id])
                return self._identity(method, category_name, tags.get(method_id, []))
            except Exception as exc:
                logger.debug("get_method failed: %s", exc)
                raise PersistenceError(f"Unable to fetch the method: {exc}") from exc

    def get_version(
        self, *, organization_id: str, version_id: str
    ) -> MethodVersion | None:
        """One version by its own id, for a caller holding a pin."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(MethodLibraryMethodVersionModel)
                    .filter(
                        MethodLibraryMethodVersionModel.organization_id == organization_id,
                        MethodLibraryMethodVersionModel.version_id == version_id,
                    )
                    .first()
                )
                return self._version(row) if row is not None else None
            except Exception as exc:
                logger.debug("get_version failed: %s", exc)
                raise PersistenceError(f"Unable to fetch the method version: {exc}") from exc

    def get_latest_version(
        self, *, organization_id: str, method_id: str
    ) -> MethodVersion | None:
        """The method's current version, via the is_latest flag.

        Stands in for "the pinned version" until workflows can pin one; a caller
        that later resolves a pinned version_id reads it the same way.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(MethodLibraryMethodVersionModel)
                    .filter(
                        MethodLibraryMethodVersionModel.organization_id == organization_id,
                        MethodLibraryMethodVersionModel.method_id == method_id,
                        MethodLibraryMethodVersionModel.is_latest.is_(True),
                    )
                    .first()
                )
                return self._version(row) if row is not None else None
            except Exception as exc:
                logger.debug("get_latest_version failed: %s", exc)
                raise PersistenceError(f"Unable to fetch the method version: {exc}") from exc

    def list_version_fields(
        self, *, organization_id: str, method_version_id: str
    ) -> list[MethodVersionField]:
        """The version's fields in order, each merged with its pinned field shape.

        One join into `field_library_field_versions`, so a method with many fields
        still costs a single query rather than one per field. `field_type` and
        `settings` come from the pinned version, not the field's current state.
        """
        with self._db_session() as session:
            try:
                rows = (
                    session.query(
                        MethodLibraryMethodVersionFieldModel,
                        FieldLibraryFieldVersionModel,
                        FieldLibraryFieldModel.field_key,
                    )
                    .join(
                        FieldLibraryFieldVersionModel,
                        and_(
                            FieldLibraryFieldVersionModel.version_id
                            == MethodLibraryMethodVersionFieldModel.field_version_id,
                            FieldLibraryFieldVersionModel.library_field_id
                            == MethodLibraryMethodVersionFieldModel.library_field_id,
                        ),
                    )
                    .join(
                        FieldLibraryFieldModel,
                        FieldLibraryFieldModel.library_field_id
                        == MethodLibraryMethodVersionFieldModel.library_field_id,
                    )
                    .filter(
                        MethodLibraryMethodVersionFieldModel.organization_id
                        == organization_id,
                        MethodLibraryMethodVersionFieldModel.method_version_id
                        == method_version_id,
                    )
                    .order_by(
                        MethodLibraryMethodVersionFieldModel.position.asc(),
                        # Stable tiebreaker: rows written before positions were
                        # settled can still share one, and order must not vary.
                        MethodLibraryMethodVersionFieldModel.id.asc(),
                    )
                    .all()
                )
                return [
                    MethodVersionField(
                        id=entry.id,
                        method_version_id=entry.method_version_id,
                        library_field_id=entry.library_field_id,
                        field_version_id=entry.field_version_id,
                        label=entry.label,
                        placeholder=entry.placeholder,
                        required=bool(entry.required),
                        position=int(entry.position),
                        inherit_from=entry.inherit_from,
                        ownership=entry.ownership,
                        # field_key lives on the identity; type and settings come
                        # from the pinned version, so they reflect the shape the
                        # method was built against rather than today's.
                        field_key=field_key,
                        field_type=field_version.field_type,
                        settings=dict(field_version.settings or {}),
                        source_entity_type=entry.source_entity_type,
                        source_field_key=entry.source_field_key,
                    )
                    for entry, field_version, field_key in rows
                ]
            except Exception as exc:
                logger.debug("list_version_fields failed: %s", exc)
                raise PersistenceError(
                    f"Unable to list the method version's fields: {exc}"
                ) from exc

    @staticmethod
    def _category(row: MethodLibraryCategoryModel) -> MethodCategory:
        """Map a category row onto its contract."""
        return MethodCategory(
            category_id=row.id,
            organization_id=row.organization_id,
            name=row.name,
            created_at=row.created_at,
        )

    def create_category(self, *, organization_id: str, name: str) -> MethodCategory:
        """Insert a category, raising DuplicateCategoryNameError on a name clash.

        The clash is caught from the unique index rather than pre-checked, so two
        concurrent creates cannot both pass a check and then both insert.
        """
        with self._db_session() as session:
            try:
                row = MethodLibraryCategoryModel(
                    id=str(uuid4()), organization_id=organization_id, name=name.strip()
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                return self._category(row)
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateCategoryNameError(
                    f"a category named '{name.strip()}' already exists in this organization"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_category failed: %s", exc)
                raise PersistenceError(f"Unable to create the category: {exc}") from exc

    def list_categories(self, *, organization_id: str) -> list[MethodCategory]:
        """Every category in the organization, ordered by name.

        Unpaginated on purpose: this is the lookup list behind a picker, not a
        history that grows.
        """
        with self._db_session() as session:
            try:
                rows = (
                    session.query(MethodLibraryCategoryModel)
                    .filter(MethodLibraryCategoryModel.organization_id == organization_id)
                    .order_by(MethodLibraryCategoryModel.name.asc())
                    .all()
                )
                return [self._category(row) for row in rows]
            except Exception as exc:
                logger.debug("list_categories failed: %s", exc)
                raise PersistenceError(f"Unable to list categories: {exc}") from exc

    def rename_category(
        self, *, organization_id: str, category_id: str, name: str
    ) -> MethodCategory | None:
        """Rename in place. None when the category is not in this organization.

        The methods filed under it keep pointing at the same id, so nothing moves
        out of the category.
        """
        with self._db_session() as session:
            try:
                row = self._category_row(session, organization_id, category_id)
                if row is None:
                    return None
                row.name = name.strip()
                session.commit()
                session.refresh(row)
                return self._category(row)
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateCategoryNameError(
                    f"a category named '{name.strip()}' already exists in this organization"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("rename_category failed: %s", exc)
                raise PersistenceError(f"Unable to rename the category: {exc}") from exc

    def delete_category(self, *, organization_id: str, category_id: str) -> bool:
        """Hard delete a category. Returns False when it was already gone.

        The foreign key from methods has no ON DELETE clause, so the database
        refuses while a method is still filed under it. That refusal is caught and
        raised as CategoryInUseError rather than surfacing as a 500.
        """
        with self._db_session() as session:
            try:
                row = self._category_row(session, organization_id, category_id)
                if row is None:
                    return False
                session.delete(row)
                session.commit()
                return True
            except IntegrityError as exc:
                session.rollback()
                raise CategoryInUseError(
                    "a method is still filed under this category, so it cannot be deleted"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("delete_category failed: %s", exc)
                raise PersistenceError(f"Unable to delete the category: {exc}") from exc

    @classmethod
    def _assert_category_exists(
        cls, session: Session, organization_id: str, category_id: str | None
    ) -> None:
        """Refuse a category that is not this organization's own.

        The composite foreign key already refuses it, but only as an
        IntegrityError the caller sees as a 500. category_id is caller-supplied
        and can go stale, so it is checked first and reported as a 4xx.
        """
        if category_id is None:
            return
        if cls._category_row(session, organization_id, category_id) is None:
            raise UnknownMethodCategoryError(f"category '{category_id}' was not found")

    @staticmethod
    def _category_row(
        session: Session, organization_id: str, category_id: str
    ) -> MethodLibraryCategoryModel | None:
        """Load one category inside the caller's session, scoped to its org."""
        return (
            session.query(MethodLibraryCategoryModel)
            .filter(
                MethodLibraryCategoryModel.organization_id == organization_id,
                MethodLibraryCategoryModel.id == category_id,
            )
            .first()
        )

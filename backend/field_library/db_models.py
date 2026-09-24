"""Persistence adapters for the field library.

Owns the type catalogue and its per-organization enablement, the fields
themselves, and the table linking fields to forms.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    or_,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

from common.logger import logger
from database.manager import Base
from exceptions import NotFoundError, PersistenceError
from field_library.models.interface import (
    KEY_COLUMN_WIDTH,
    NAME_COLUMN_WIDTH,
    TYPE_CODE_COLUMN_WIDTH,
    FieldIdentity,
    FieldTypeCatalogueEntry,
    FieldVersion,
    FieldWithVersion,
    FormFieldLink,
    OrganizationFieldTypeSetting,
)
from forms.db_models import EntityTypeSchemaModel, schema_content_hash
from user.db_models import User


class FieldInUseError(Exception):
    """A form still references this field, so it cannot be hard deleted.

    Separate from PersistenceError so the manager can return a 4xx, not a 500.
    """


class DuplicateFieldError(Exception):
    """Name or key already taken in this organization.

    Separate from PersistenceError so the manager can return a 4xx, not a 500.
    """


if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Column widths track the migration, never the configurable validation limits,
# so the ORM always describes the database as it actually is.
FIELD_TYPE_CODE_LENGTH = TYPE_CODE_COLUMN_WIDTH
FIELD_TYPE_LABEL_LENGTH = 128
IDENTIFIER_LENGTH = 36
FIELD_NAME_LENGTH = NAME_COLUMN_WIDTH
FIELD_KEY_LENGTH = KEY_COLUMN_WIDTH
FIRST_VERSION = 1
# Matches the limit/offset defaults used by the other list endpoints.
DEFAULT_PAGE_LIMIT = 50


def _definitions_schema() -> str:
    """Return the Postgres schema that holds canonical definition tables."""
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


class FieldTypeCatalogueModel(Base):
    """One field type the engine supports. Engine-wide, not per organization."""

    __tablename__ = "field_type_catalogue"
    __table_args__ = (
        Index("ix_field_type_catalogue_is_available", "is_available"),
        {"schema": _definitions_schema()},
    )

    code = Column(String(FIELD_TYPE_CODE_LENGTH), primary_key=True)
    label = Column(String(FIELD_TYPE_LABEL_LENGTH), nullable=False)
    # NULL, never "", when the engine has no type to map onto yet. NULL forces
    # callers to handle the not-built case instead of accepting a blank value.
    engine_type = Column(String(FIELD_TYPE_CODE_LENGTH), nullable=True)
    config_kind = Column(String(FIELD_TYPE_CODE_LENGTH), nullable=False, default="none")
    # False while the engine has no storage/validation for the type yet
    # (Document, Timer/Duration). Seeded rows exist so the catalogue is complete.
    is_available = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FieldLibraryFieldModel(Base):
    """A field's live state. field_key is its only permanent member.

    Name is edited in place. Type is versioned content, like settings: changing it
    always creates a new version, never an in-place edit, and this row is updated
    to match the newest version's type.
    """

    __tablename__ = "field_library_fields"
    __table_args__ = (
        # Name is unique per organization per type, so "Volume" can exist as both
        # an integer and a text field. field_key stays unique on its own. Both are
        # case-insensitive and live-rows-only, so archiving frees them for reuse.
        Index(
            "uq_field_library_fields_org_name_type_active",
            "organization_id",
            text("lower(name)"),
            "field_type",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index(
            "uq_field_library_fields_org_key_active",
            "organization_id",
            text("lower(field_key)"),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index("ix_field_library_fields_organization_id", "organization_id"),
        # Target of the connector's composite FK; see EntityTypeSchemaFieldModel.
        UniqueConstraint(
            "organization_id", "library_field_id", name="uq_field_library_fields_org_field"
        ),
        {"schema": _definitions_schema()},
    )

    library_field_id = Column(
        String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4())
    )
    # Sequential counter alongside the UUID, for display and ordering without
    # exposing an opaque identifier. Assigned by the database, never by us.
    field_count_id = Column(Integer, Identity(always=False), nullable=False, unique=True)
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    name = Column(String(FIELD_NAME_LENGTH), nullable=False)
    field_key = Column(String(FIELD_KEY_LENGTH), nullable=False)
    field_type = Column(String(FIELD_TYPE_CODE_LENGTH), nullable=False)
    created_by = Column(String(IDENTIFIER_LENGTH), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FieldLibraryFieldVersionModel(Base):
    """One version of a field's content: name, type, description and settings.

    Insert-only apart from `is_latest` being cleared when superseded, and apart
    from description, which has its own in-place edit path. Anything pinned to a
    version keeps resolving to the type and settings it linked.
    """

    __tablename__ = "field_library_field_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_field_id", "organization_id"],
            [
                f"{_definitions_schema()}.field_library_fields.library_field_id",
                f"{_definitions_schema()}.field_library_fields.organization_id",
            ],
            name="fk_field_library_versions_field",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "library_field_id", "version", name="uq_field_library_versions_field_version"
        ),
        # Redundant alone; each is the target of a composite FK on the connector,
        # one pinning tenant and one pinning version-to-field.
        UniqueConstraint(
            "version_id", "organization_id", name="uq_field_library_versions_version_org"
        ),
        UniqueConstraint(
            "version_id", "library_field_id", name="uq_field_library_versions_version_field"
        ),
        # At most one current version per field, enforced by the database.
        Index(
            "uq_field_library_versions_field_latest",
            "library_field_id",
            unique=True,
            postgresql_where=text("is_latest"),
        ),
        Index("ix_field_library_versions_library_field_id", "library_field_id"),
        Index("ix_field_library_versions_organization_id", "organization_id"),
        {"schema": _definitions_schema()},
    )

    version_id = Column(String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4()))
    library_field_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    version = Column(Integer, nullable=False)
    # The identity's name and type when this version was created, both frozen, so
    # a later change leaves older versions showing what they were made under.
    name = Column(String(FIELD_NAME_LENGTH), nullable=False)
    field_type = Column(String(FIELD_TYPE_CODE_LENGTH), nullable=False)
    description = Column(Text, nullable=True)
    settings = Column(JSONB, nullable=False, default=dict)
    is_latest = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(IDENTIFIER_LENGTH), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EntityTypeSchemaFieldModel(Base):
    """Join row: which field version a form uses, in what order, and how it behaves.

    Pins a specific version, so a later edit never changes an existing form.
    Composite keys stop a link crossing tenants or mismatching version and field.

    Per-form behaviour lives in `field_metadata` on this row. Once a link carries
    it, that is the authoritative source for how the field behaves on this form.
    The same keys still exist inside the library version's `settings`, but nothing
    should read those for per-form behaviour from here on. That duplication is
    intentional for now; removing it from `settings` is deliberately deferred and
    is not part of this change.
    """

    __tablename__ = "entity_type_schema_fields"
    __table_args__ = (
        UniqueConstraint(
            "schema_id", "library_field_id", name="uq_entity_type_schema_fields_schema_field"
        ),
        # Composite so the database refuses a link whose form or field belongs to
        # another organization. Single-column keys prove existence, not tenancy.
        ForeignKeyConstraint(
            ["schema_id", "organization_id"],
            [
                f"{_definitions_schema()}.entity_type_schema.id",
                f"{_definitions_schema()}.entity_type_schema.organization_id",
            ],
            name="fk_entity_type_schema_fields_schema",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["library_field_id", "organization_id"],
            [
                f"{_definitions_schema()}.field_library_fields.library_field_id",
                f"{_definitions_schema()}.field_library_fields.organization_id",
            ],
            name="fk_entity_type_schema_fields_library_field",
        ),
        # Pins the link to one version, and ties that version to the field named
        # alongside it, so the two can never drift apart.
        ForeignKeyConstraint(
            ["version_id", "organization_id"],
            [
                f"{_definitions_schema()}.field_library_field_versions.version_id",
                f"{_definitions_schema()}.field_library_field_versions.organization_id",
            ],
            name="fk_entity_type_schema_fields_version",
        ),
        ForeignKeyConstraint(
            ["version_id", "library_field_id"],
            [
                f"{_definitions_schema()}.field_library_field_versions.version_id",
                f"{_definitions_schema()}.field_library_field_versions.library_field_id",
            ],
            name="fk_entity_type_schema_fields_version_field",
        ),
        Index("ix_entity_type_schema_fields_schema_id", "schema_id"),
        Index("ix_entity_type_schema_fields_version_id", "version_id"),
        Index("ix_entity_type_schema_fields_library_field_id", "library_field_id"),
        Index("ix_entity_type_schema_fields_organization_id", "organization_id"),
        {"schema": _definitions_schema()},
    )

    id = Column(String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4()))
    schema_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    version_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    # Denormalised from the version, like organization_id, so the one-field-per-form
    # rule works without a join. Tied to version_id by a composite FK.
    library_field_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    # Denormalised from the form, matching the pattern used across this module,
    # so every read can filter by organization directly instead of joining.
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    # The field's order within its form.
    position = Column(Integer, nullable=False, default=0)
    # How this field behaves on this particular form: required, nullable, default,
    # ownership, source, editable, col_span, placeholder, and a label override.
    #
    # Authoritative once present. The library version's `settings` still carries
    # the same keys, but per-form behaviour is read from here, not from there.
    # Named `field_metadata` because `metadata` is reserved on declarative models;
    # the database column is still `metadata`, matching the rest of the codebase.
    field_metadata = Column(
        "metadata", JSONB, nullable=True, server_default=text("'{}'::jsonb")
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrganizationFieldTypeModel(Base):
    """One organization's decision about one catalogue entry."""

    __tablename__ = "organization_field_types"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "field_type_code", name="uq_organization_field_types_org_code"
        ),
        Index("ix_organization_field_types_organization_id", "organization_id"),
        {"schema": _definitions_schema()},
    )

    id = Column(String(IDENTIFIER_LENGTH), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(IDENTIFIER_LENGTH), nullable=False)
    field_type_code = Column(String(FIELD_TYPE_CODE_LENGTH), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FieldLibraryModelService:
    """Read the field-type catalogue and each organization's enablement rows."""

    def __init__(self, database_service_manager: object) -> None:
        """Bind to Postgres. There is no in-memory fallback: the catalogue tables
        live in the definitions schema, which only exists in Postgres."""
        if database_service_manager is None or not hasattr(
            database_service_manager, "postgres_db_service"
        ):
            raise PersistenceError(
                "FieldLibraryModelService requires a database_service_manager with "
                "postgres_db_service()"
            )
        self.database_manager = database_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = self.database_manager.postgres_db_service()
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.module_name = "field_library"

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
    def _catalogue_entry(row: FieldTypeCatalogueModel) -> FieldTypeCatalogueEntry:
        """Map a catalogue row onto its contract."""
        return FieldTypeCatalogueEntry(
            code=row.code,
            label=row.label,
            engine_type=row.engine_type,
            config_kind=row.config_kind,
            is_available=bool(row.is_available),
            sort_order=int(row.sort_order),
        )

    def list_catalogue(self) -> list[FieldTypeCatalogueEntry]:
        """Every catalogue entry in display order, available or not.

        Unavailable ones are returned so the selector can show them disabled.
        """
        with self._db_session() as session:
            try:
                rows = (
                    session.query(FieldTypeCatalogueModel)
                    .order_by(
                        FieldTypeCatalogueModel.sort_order.asc(),
                        FieldTypeCatalogueModel.code.asc(),
                    )
                    .all()
                )
                return [self._catalogue_entry(row) for row in rows]
            except Exception as exc:
                logger.debug("list_catalogue failed: %s", exc)
                raise PersistenceError(f"Unable to list the field-type catalogue: {exc}") from exc

    # ── Field library: identities and versions ────────────────────────────────

    @staticmethod
    def _resolve_creator_names(session: Session, user_ids: set[str]) -> dict[str, str]:
        """Map user ids to display names in one query.

        Batched deliberately: resolving per row would put a query behind every
        entry in a version list or a page of fields.
        """
        wanted = {uid for uid in user_ids if uid}
        if not wanted:
            return {}
        rows = session.query(User.id, User.full_name).filter(User.id.in_(wanted)).all()
        return {user_id: full_name for user_id, full_name in rows if full_name}

    @staticmethod
    def _identity(
        row: FieldLibraryFieldModel, creator_names: dict[str, str] | None = None
    ) -> FieldIdentity:
        """Map a field row onto its contract."""
        return FieldIdentity(
            library_field_id=row.library_field_id,
            field_count_id=row.field_count_id,
            organization_id=row.organization_id,
            name=row.name,
            field_key=row.field_key,
            field_type=row.field_type,
            created_by=row.created_by,
            created_by_name=(creator_names or {}).get(row.created_by or ""),
            is_archived=row.archived_at is not None,
        )

    @staticmethod
    def _version(
        row: FieldLibraryFieldVersionModel, creator_names: dict[str, str] | None = None
    ) -> FieldVersion:
        """Map a version row onto its contract."""
        return FieldVersion(
            version_id=row.version_id,
            library_field_id=row.library_field_id,
            organization_id=row.organization_id,
            version=row.version,
            name=row.name,
            field_type=row.field_type,
            description=row.description,
            settings=dict(row.settings or {}),
            is_latest=bool(row.is_latest),
            created_by=row.created_by,
            created_by_name=(creator_names or {}).get(row.created_by or ""),
        )

    def create_field(
        self,
        *,
        organization_id: str,
        name: str,
        field_key: str,
        field_type: str,
        description: str | None,
        settings: dict[str, object],
        created_by: str | None,
    ) -> FieldWithVersion:
        """Insert a field and its version 1 in one transaction.

        Both land together or neither does, so a field can never exist without a
        version for a form to link to.
        """
        with self._db_session() as session:
            try:
                field = FieldLibraryFieldModel(
                    library_field_id=str(uuid4()),
                    organization_id=organization_id,
                    name=name,
                    field_key=field_key,
                    field_type=field_type,
                    created_by=created_by,
                )
                session.add(field)
                session.flush()
                version = FieldLibraryFieldVersionModel(
                    version_id=str(uuid4()),
                    library_field_id=field.library_field_id,
                    organization_id=organization_id,
                    version=FIRST_VERSION,
                    name=name,
                    field_type=field_type,
                    description=description,
                    settings=dict(settings or {}),
                    is_latest=True,
                    created_by=created_by,
                )
                session.add(version)
                session.commit()
                session.refresh(field)
                session.refresh(version)
                names = self._resolve_creator_names(session, {created_by or ""})
                return FieldWithVersion(
                    identity=self._identity(field, names),
                    version=self._version(version, names),
                )
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateFieldError(
                    "a live field with this name and type, or this key, already "
                    "exists in this organization"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_field failed: %s", exc)
                raise PersistenceError(f"Unable to create the library field: {exc}") from exc

    def get_field(
        self, *, organization_id: str, library_field_id: str
    ) -> FieldIdentity | None:
        """One field identity, scoped to the organization. None when absent."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(FieldLibraryFieldModel)
                    .filter(
                        FieldLibraryFieldModel.organization_id == organization_id,
                        FieldLibraryFieldModel.library_field_id == library_field_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                names = self._resolve_creator_names(session, {row.created_by or ""})
                return self._identity(row, names)
            except Exception as exc:
                logger.debug("get_field failed: %s", exc)
                raise PersistenceError(f"Unable to fetch the library field: {exc}") from exc

    @staticmethod
    def _escape_like(term: str) -> str:
        """Neutralise LIKE wildcards in user input.

        `field_key` values routinely contain `_`, which LIKE reads as any single
        character, so an unescaped term matches far more than the user typed.
        """
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def list_fields(
        self,
        *,
        organization_id: str,
        include_archived: bool = False,
        search: str | None = None,
        field_type: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[FieldWithVersion], int]:
        """A page of fields with their current version, plus the total match count.

        The current version is joined in rather than fetched per row, so a page
        costs two queries (the page and the count) no matter how many fields it holds.
        """
        with self._db_session() as session:
            try:
                query = (
                    session.query(FieldLibraryFieldModel, FieldLibraryFieldVersionModel)
                    .join(
                        FieldLibraryFieldVersionModel,
                        and_(
                            FieldLibraryFieldVersionModel.library_field_id
                            == FieldLibraryFieldModel.library_field_id,
                            FieldLibraryFieldVersionModel.is_latest.is_(True),
                        ),
                    )
                    .filter(FieldLibraryFieldModel.organization_id == organization_id)
                )
                if not include_archived:
                    query = query.filter(FieldLibraryFieldModel.archived_at.is_(None))
                if field_type:
                    query = query.filter(FieldLibraryFieldModel.field_type == field_type)
                normalized_search = (search or "").strip()
                if normalized_search:
                    pattern = f"%{self._escape_like(normalized_search)}%"
                    query = query.filter(
                        or_(
                            FieldLibraryFieldModel.name.ilike(pattern, escape="\\"),
                            FieldLibraryFieldModel.field_key.ilike(pattern, escape="\\"),
                        )
                    )
                total = query.order_by(None).count()
                rows = (
                    query.order_by(FieldLibraryFieldModel.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                    .all()
                )
                creator_ids = {field.created_by or "" for field, _ in rows}
                creator_ids |= {version.created_by or "" for _, version in rows}
                names = self._resolve_creator_names(session, creator_ids)
                items = [
                    FieldWithVersion(
                        identity=self._identity(field, names),
                        version=self._version(version, names),
                    )
                    for field, version in rows
                ]
                return items, total
            except Exception as exc:
                logger.debug("list_fields failed: %s", exc)
                raise PersistenceError(f"Unable to list library fields: {exc}") from exc

    def get_latest_version(
        self, *, organization_id: str, library_field_id: str
    ) -> FieldVersion | None:
        """The current version of one field, via the is_latest flag."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(FieldLibraryFieldVersionModel)
                    .filter(
                        FieldLibraryFieldVersionModel.organization_id == organization_id,
                        FieldLibraryFieldVersionModel.library_field_id == library_field_id,
                        FieldLibraryFieldVersionModel.is_latest.is_(True),
                    )
                    .first()
                )
                if row is None:
                    return None
                names = self._resolve_creator_names(session, {row.created_by or ""})
                return self._version(row, names)
            except Exception as exc:
                logger.debug("get_latest_version failed: %s", exc)
                raise PersistenceError(f"Unable to fetch the latest version: {exc}") from exc

    def get_version(self, *, organization_id: str, version_id: str) -> FieldVersion | None:
        """One version by id, scoped to the organization. None when absent.

        Reads a version directly rather than through its field, which is what a
        pinned reference needs: the pin names a version, not a position in the
        field's history.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(FieldLibraryFieldVersionModel)
                    .filter(
                        FieldLibraryFieldVersionModel.organization_id == organization_id,
                        FieldLibraryFieldVersionModel.version_id == version_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                names = self._resolve_creator_names(session, {row.created_by or ""})
                return self._version(row, names)
            except Exception as exc:
                logger.debug("get_version failed: %s", exc)
                raise PersistenceError(f"Unable to fetch the field version: {exc}") from exc

    def list_versions(
        self, *, organization_id: str, library_field_id: str
    ) -> list[FieldVersion]:
        """Every version of one field, newest first, for a version picker."""
        with self._db_session() as session:
            try:
                rows = (
                    session.query(FieldLibraryFieldVersionModel)
                    .filter(
                        FieldLibraryFieldVersionModel.organization_id == organization_id,
                        FieldLibraryFieldVersionModel.library_field_id == library_field_id,
                    )
                    .order_by(FieldLibraryFieldVersionModel.version.desc())
                    .all()
                )
                names = self._resolve_creator_names(
                    session, {row.created_by or "" for row in rows}
                )
                return [self._version(row, names) for row in rows]
            except Exception as exc:
                logger.debug("list_versions failed: %s", exc)
                raise PersistenceError(f"Unable to list field versions: {exc}") from exc

    def add_version(
        self,
        *,
        organization_id: str,
        library_field_id: str,
        description: str | None,
        settings: dict[str, object],
        created_by: str | None,
        field_type: str | None = None,
    ) -> FieldVersion:
        """Insert the next version and demote the previous one, atomically.

        The old flag is cleared first because the partial unique index allows only
        one flagged version; one transaction means a failure leaves the old one
        current.

        `field_type` None keeps the current type, which is the common case. A value
        stamps the new version with it and updates the identity to match, so the
        identity always mirrors the newest version's type. Older versions keep the
        type they were created under.
        """
        with self._db_session() as session:
            try:
                current = (
                    session.query(FieldLibraryFieldVersionModel)
                    .filter(
                        FieldLibraryFieldVersionModel.organization_id == organization_id,
                        FieldLibraryFieldVersionModel.library_field_id == library_field_id,
                        FieldLibraryFieldVersionModel.is_latest.is_(True),
                    )
                    .with_for_update()
                    .first()
                )
                if current is None:
                    raise NotFoundError(
                        f"library field '{library_field_id}' has no current version"
                    )
                identity = (
                    session.query(FieldLibraryFieldModel)
                    .filter(
                        FieldLibraryFieldModel.organization_id == organization_id,
                        FieldLibraryFieldModel.library_field_id == library_field_id,
                    )
                    .first()
                )
                if identity is None:
                    raise NotFoundError(f"library field '{library_field_id}' was not found")
                next_number = int(current.version) + 1
                # A type change lands on the identity as well, so the live row
                # mirrors the newest version. Omitted, the current type carries on.
                version_type = field_type or identity.field_type
                if field_type and field_type != identity.field_type:
                    identity.field_type = field_type
                current.is_latest = False
                session.flush()
                version = FieldLibraryFieldVersionModel(
                    version_id=str(uuid4()),
                    library_field_id=library_field_id,
                    organization_id=organization_id,
                    version=next_number,
                    # Snapshot name and type as they stand now, not as at v1.
                    name=identity.name,
                    field_type=version_type,
                    description=description,
                    settings=dict(settings or {}),
                    is_latest=True,
                    created_by=created_by,
                )
                session.add(version)
                session.commit()
                session.refresh(version)
                names = self._resolve_creator_names(session, {created_by or ""})
                return self._version(version, names)
            except NotFoundError:
                session.rollback()
                raise
            except IntegrityError as exc:
                # Changing the type can collide with another live field sharing
                # this name at the target type.
                session.rollback()
                raise DuplicateFieldError(
                    "another live field in this organization already uses this name "
                    "at that type"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("add_version failed: %s", exc)
                raise PersistenceError(f"Unable to add a field version: {exc}") from exc

    def update_latest_description(
        self,
        *,
        organization_id: str,
        library_field_id: str,
        description: str | None,
    ) -> FieldVersion | None:
        """Rewrite the current version's description in place.

        Touches only the row flagged is_latest, and only that column, so the
        version number, is_latest and every older version are left alone.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(FieldLibraryFieldVersionModel)
                    .filter(
                        FieldLibraryFieldVersionModel.organization_id == organization_id,
                        FieldLibraryFieldVersionModel.library_field_id == library_field_id,
                        FieldLibraryFieldVersionModel.is_latest.is_(True),
                    )
                    .with_for_update()
                    .first()
                )
                if row is None:
                    return None
                row.description = description
                session.commit()
                session.refresh(row)
                names = self._resolve_creator_names(session, {row.created_by or ""})
                return self._version(row, names)
            except Exception as exc:
                session.rollback()
                logger.debug("update_latest_description failed: %s", exc)
                raise PersistenceError(
                    f"Unable to update the field description: {exc}"
                ) from exc

    def rename_field(
        self, *, organization_id: str, library_field_id: str, name: str
    ) -> FieldIdentity | None:
        """Update the display name in place. Creates no version."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(FieldLibraryFieldModel)
                    .filter(
                        FieldLibraryFieldModel.organization_id == organization_id,
                        FieldLibraryFieldModel.library_field_id == library_field_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                row.name = name
                session.commit()
                session.refresh(row)
                names = self._resolve_creator_names(session, {row.created_by or ""})
                return self._identity(row, names)
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateFieldError(
                    "another live field of this type in this organization already uses "
                    "that name"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("rename_field failed: %s", exc)
                raise PersistenceError(f"Unable to rename the library field: {exc}") from exc

    def count_referencing_forms(
        self, *, organization_id: str, library_field_id: str
    ) -> int:
        """How many forms reference this field, across every one of its versions.

        Counts distinct forms rather than rows so the number matches what a user
        would recognise, even though one field can appear at most once per form.
        """
        with self._db_session() as session:
            try:
                return (
                    session.query(EntityTypeSchemaFieldModel.schema_id)
                    .filter(
                        EntityTypeSchemaFieldModel.organization_id == organization_id,
                        EntityTypeSchemaFieldModel.library_field_id == library_field_id,
                    )
                    .distinct()
                    .count()
                )
            except Exception as exc:
                logger.debug("count_referencing_forms failed: %s", exc)
                raise PersistenceError(
                    f"Unable to count forms using the field: {exc}"
                ) from exc

    def hard_delete_field(self, *, organization_id: str, library_field_id: str) -> bool:
        """Delete the field row outright. Returns False when it was already gone.

        Versions go with it through the cascading foreign key. If a form still
        references the field the database refuses the delete, which is the
        backstop behind the manager's own check.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(FieldLibraryFieldModel)
                    .filter(
                        FieldLibraryFieldModel.organization_id == organization_id,
                        FieldLibraryFieldModel.library_field_id == library_field_id,
                    )
                    .first()
                )
                if row is None:
                    return False
                session.delete(row)
                session.commit()
                return True
            except IntegrityError as exc:
                session.rollback()
                raise FieldInUseError(
                    "this field is still referenced by a form and cannot be deleted"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("hard_delete_field failed: %s", exc)
                raise PersistenceError(f"Unable to delete the library field: {exc}") from exc

    def archive_field(
        self, *, organization_id: str, library_field_id: str
    ) -> FieldIdentity | None:
        """Stamp the identity row as archived. No version row is deleted."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(FieldLibraryFieldModel)
                    .filter(
                        FieldLibraryFieldModel.organization_id == organization_id,
                        FieldLibraryFieldModel.library_field_id == library_field_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                if row.archived_at is None:
                    row.archived_at = datetime.now(UTC)
                    session.commit()
                    session.refresh(row)
                names = self._resolve_creator_names(session, {row.created_by or ""})
                return self._identity(row, names)
            except Exception as exc:
                session.rollback()
                logger.debug("archive_field failed: %s", exc)
                raise PersistenceError(f"Unable to archive the library field: {exc}") from exc

    def list_organization_settings(
        self, *, organization_id: str
    ) -> list[OrganizationFieldTypeSetting]:
        """One organization's enablement rows. Empty list means "never configured"."""
        with self._db_session() as session:
            try:
                rows = (
                    session.query(OrganizationFieldTypeModel)
                    .filter(OrganizationFieldTypeModel.organization_id == organization_id)
                    .all()
                )
                return [
                    OrganizationFieldTypeSetting(
                        organization_id=row.organization_id,
                        field_type_code=row.field_type_code,
                        enabled=bool(row.enabled),
                    )
                    for row in rows
                ]
            except Exception as exc:
                logger.debug("list_organization_settings failed: %s", exc)
                raise PersistenceError(
                    f"Unable to list field-type settings for organization: {exc}"
                ) from exc


class DuplicateFormFieldLinkError(Exception):
    """This form already links this field.

    Separate from PersistenceError so the manager returns a 4xx, not a 500. The
    unique index on (schema_id, library_field_id) refuses it either way; catching
    it here turns an integrity failure into a clear message.
    """


class FormFieldLinkModelService:
    """Read and write which Field Library version each form uses.

    Sits beside FieldLibraryModelService rather than inside it: the field library
    owns fields and versions, this owns the join between a form and one of them.
    """

    def __init__(self, database_service_manager: object) -> None:
        """Bind to Postgres. The definitions schema only exists there."""
        if database_service_manager is None or not hasattr(
            database_service_manager, "postgres_db_service"
        ):
            raise PersistenceError(
                "FormFieldLinkModelService requires a database_service_manager with "
                "postgres_db_service()"
            )
        self.database_manager = database_service_manager
        self.current_db = self.database_manager.postgres_db_service()
        self.module_name = "field_library"

    def _session(self) -> Session:
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
    def _link(row: EntityTypeSchemaFieldModel) -> FormFieldLink:
        """Map a link row onto its contract."""
        return FormFieldLink(
            id=row.id,
            schema_id=row.schema_id,
            organization_id=row.organization_id,
            library_field_id=row.library_field_id,
            version_id=row.version_id,
            position=int(row.position),
            metadata=dict(row.field_metadata or {}),
        )

    def form_exists(self, *, organization_id: str, schema_id: str) -> bool:
        """Whether the form is this organization's own."""
        with self._db_session() as session:
            try:
                return (
                    session.query(EntityTypeSchemaModel.id)
                    .filter(
                        EntityTypeSchemaModel.organization_id == organization_id,
                        EntityTypeSchemaModel.id == schema_id,
                    )
                    .first()
                    is not None
                )
            except Exception as exc:
                logger.debug("form_exists failed: %s", exc)
                raise PersistenceError(f"Unable to look up the form: {exc}") from exc

    def version_belongs_to_field(
        self, *, organization_id: str, library_field_id: str, version_id: str
    ) -> bool:
        """Whether one version is a version of this field, in this organization.

        Both halves matter: a version of another field would pin the link to a
        shape the field never had, and the composite foreign key refuses it
        anyway, as an integrity error rather than a clear message.
        """
        with self._db_session() as session:
            try:
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
            except Exception as exc:
                logger.debug("version_belongs_to_field failed: %s", exc)
                raise PersistenceError(f"Unable to look up the field version: {exc}") from exc

    @staticmethod
    def _field_key(field: dict[str, object]) -> str:
        """Return the storage key accepted by the form schema contracts."""
        return str(field.get("field") or field.get("name") or field.get("id") or "").strip()

    @staticmethod
    def _projection(session: Session, row: EntityTypeSchemaFieldModel) -> dict[str, object]:
        """Resolve one pinned link into the authoritative ``fields_json`` shape."""
        version = (
            session.query(FieldLibraryFieldVersionModel)
            .filter(
                FieldLibraryFieldVersionModel.organization_id == row.organization_id,
                FieldLibraryFieldVersionModel.library_field_id == row.library_field_id,
                FieldLibraryFieldVersionModel.version_id == row.version_id,
            )
            .one()
        )
        identity = (
            session.query(FieldLibraryFieldModel)
            .filter(
                FieldLibraryFieldModel.organization_id == row.organization_id,
                FieldLibraryFieldModel.library_field_id == row.library_field_id,
            )
            .one()
        )
        catalogue = session.get(FieldTypeCatalogueModel, version.field_type)
        engine_type = catalogue.engine_type if catalogue is not None else None
        if not engine_type:
            raise PersistenceError(
                f"field type '{version.field_type}' has no engine representation"
            )

        metadata = dict(row.field_metadata or {})
        projected = dict(version.settings or {})
        projected.update(metadata)
        projected.update(
            {
                "field": identity.field_key,
                "name": version.name,
                "label": metadata.get("label") or version.name,
                "type": engine_type,
                "description": version.description,
                "library_field_id": row.library_field_id,
                "field_version_id": row.version_id,
            }
        )
        return projected

    @classmethod
    def _put_projection(
        cls,
        schema: EntityTypeSchemaModel,
        projection: dict[str, object],
        *,
        position: int,
    ) -> None:
        """Insert or replace one linked field without duplicating its storage key."""
        library_field_id = str(projection["library_field_id"])
        field_key = cls._field_key(projection).lower()
        fields = [
            dict(field)
            for field in (schema.fields_json or [])
            if str(field.get("library_field_id") or "") != library_field_id
            and cls._field_key(field).lower() != field_key
        ]
        fields.insert(min(position, len(fields)), projection)
        schema.fields_json = fields
        schema.content_hash = schema_content_hash(schema.entity_type, fields)

    @staticmethod
    def _remove_projection(
        schema: EntityTypeSchemaModel, *, library_field_id: str
    ) -> None:
        """Remove only the authoritative projection owned by one library link."""
        schema.fields_json = [
            dict(field)
            for field in (schema.fields_json or [])
            if str(field.get("library_field_id") or "") != library_field_id
        ]
        schema.content_hash = schema_content_hash(schema.entity_type, schema.fields_json)

    def create_link(
        self,
        *,
        organization_id: str,
        schema_id: str,
        library_field_id: str,
        version_id: str,
        position: int,
    ) -> FormFieldLink:
        """Link one field version to one form. Raises on a repeat of that pair."""
        with self._db_session() as session:
            try:
                row = EntityTypeSchemaFieldModel(
                    id=str(uuid4()),
                    schema_id=schema_id,
                    version_id=version_id,
                    library_field_id=library_field_id,
                    organization_id=organization_id,
                    position=position,
                )
                session.add(row)
                session.flush()
                schema = (
                    session.query(EntityTypeSchemaModel)
                    .filter(
                        EntityTypeSchemaModel.organization_id == organization_id,
                        EntityTypeSchemaModel.id == schema_id,
                    )
                    .one()
                )
                self._put_projection(
                    schema,
                    self._projection(session, row),
                    position=position,
                )
                session.commit()
                session.refresh(row)
                return self._link(row)
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateFormFieldLinkError(
                    "this form already uses that field"
                ) from exc
            except Exception as exc:
                session.rollback()
                logger.debug("create_link failed: %s", exc)
                raise PersistenceError(f"Unable to link the field to the form: {exc}") from exc

    def list_links(self, *, organization_id: str, schema_id: str) -> list[FormFieldLink]:
        """One form's links, in the order the form shows them."""
        with self._db_session() as session:
            try:
                rows = (
                    session.query(EntityTypeSchemaFieldModel)
                    .filter(
                        EntityTypeSchemaFieldModel.organization_id == organization_id,
                        EntityTypeSchemaFieldModel.schema_id == schema_id,
                    )
                    .order_by(
                        EntityTypeSchemaFieldModel.position.asc(),
                        EntityTypeSchemaFieldModel.id.asc(),
                    )
                    .all()
                )
                return [self._link(row) for row in rows]
            except Exception as exc:
                logger.debug("list_links failed: %s", exc)
                raise PersistenceError(f"Unable to list the form's fields: {exc}") from exc

    def get_link(self, *, organization_id: str, link_id: str) -> FormFieldLink | None:
        """One link, scoped to the organization. None when absent."""
        with self._db_session() as session:
            try:
                row = (
                    session.query(EntityTypeSchemaFieldModel)
                    .filter(
                        EntityTypeSchemaFieldModel.organization_id == organization_id,
                        EntityTypeSchemaFieldModel.id == link_id,
                    )
                    .first()
                )
                return self._link(row) if row is not None else None
            except Exception as exc:
                logger.debug("get_link failed: %s", exc)
                raise PersistenceError(f"Unable to fetch the form field link: {exc}") from exc

    def repin_link(
        self, *, organization_id: str, link_id: str, version_id: str
    ) -> FormFieldLink | None:
        """Point an existing link at a different version. None when absent.

        The field itself never moves: a link only ever changes which version of
        the field it already carries the form is reading.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(EntityTypeSchemaFieldModel)
                    .filter(
                        EntityTypeSchemaFieldModel.organization_id == organization_id,
                        EntityTypeSchemaFieldModel.id == link_id,
                    )
                    .first()
                )
                if row is None:
                    return None
                row.version_id = version_id
                session.flush()
                schema = (
                    session.query(EntityTypeSchemaModel)
                    .filter(
                        EntityTypeSchemaModel.organization_id == organization_id,
                        EntityTypeSchemaModel.id == row.schema_id,
                    )
                    .one()
                )
                self._put_projection(
                    schema,
                    self._projection(session, row),
                    position=row.position,
                )
                session.commit()
                session.refresh(row)
                return self._link(row)
            except Exception as exc:
                session.rollback()
                logger.debug("repin_link failed: %s", exc)
                raise PersistenceError(f"Unable to repin the form field: {exc}") from exc

    def delete_link(self, *, organization_id: str, link_id: str) -> bool:
        """Remove one link. Returns False when it was already gone.

        Deletes the join row only. The field and every version of it are
        untouched, and stay available to any other form.
        """
        with self._db_session() as session:
            try:
                row = (
                    session.query(EntityTypeSchemaFieldModel)
                    .filter(
                        EntityTypeSchemaFieldModel.organization_id == organization_id,
                        EntityTypeSchemaFieldModel.id == link_id,
                    )
                    .first()
                )
                if row is None:
                    return False
                schema = (
                    session.query(EntityTypeSchemaModel)
                    .filter(
                        EntityTypeSchemaModel.organization_id == organization_id,
                        EntityTypeSchemaModel.id == row.schema_id,
                    )
                    .one()
                )
                self._remove_projection(
                    schema, library_field_id=row.library_field_id
                )
                session.delete(row)
                session.commit()
                return True
            except Exception as exc:
                session.rollback()
                logger.debug("delete_link failed: %s", exc)
                raise PersistenceError(f"Unable to unlink the field: {exc}") from exc

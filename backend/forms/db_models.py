"""Persistence adapters for forms."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    or_,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

from common.auto_number import apply_auto_number_defaults, auto_number_field_ids
from database.manager import Base
from entities.db_models import (
    EntityRecordModel,
    EntityTypeModel,
    _get_next_auto_number,
    _identifier_template_from_schema,
    apply_identifier_template,
)
from entities.models.interface import IDENTIFIER_FIELD_KEY
from exceptions import ConflictError, PersistenceError, ValidationError
from forms.models.interface import EntityTypeSchemaContract, PicklistContract
from mail.db_models import EmailTemplateModel

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from database.manager import DatabaseServiceManager
    from forms.models.request import PicklistCreateRequest, PicklistUpdateRequest


# ── ORM Models ────────────────────────────────────────────────────────────────


class PicklistModel(Base):
    """Stores organisation-scoped picklists (dropdown option sets) for form fields."""

    __tablename__ = "picklists"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), nullable=False)
    name = Column(String(256), nullable=False)
    options = Column(JSONB, nullable=False, default=list)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_picklists_org_name_active",
            "organization_id", "name",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index("ix_picklists_organization_id", "organization_id"),
    )


def _definitions_schema() -> str:
    """Return the schema name used for definitions-owned form metadata tables."""
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


class EntityTypeSchemaModel(Base):
    """Reusable form schema for one entity type."""

    __tablename__ = "entity_type_schema"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "schema_key", name="uq_entity_type_schema_org_schema_key"
        ),
        Index("ix_entity_type_schema_organization_id", "organization_id"),
        Index("ix_entity_type_schema_schema_key", "schema_key"),
        Index("ix_entity_type_schema_entity_type", "entity_type"),
        Index("ix_entity_type_schema_content_hash", "content_hash"),
        Index("ix_entity_type_schema_lookup", "organization_id", "schema_key", "is_active"),
        {"schema": _definitions_schema()},
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(String(36), nullable=False)
    schema_key = Column(String(128), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    entity_type = Column(String(128), nullable=False)
    fields_json = Column(JSONB, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    # Sort position among the forms sharing this entity_type; lower shows first.
    display_order = Column(Integer, nullable=False, default=0)
    content_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def schema_content_hash(entity_type: str, fields: list[dict[str, object]]) -> str:
    """Return the canonical content hash for an authoritative form schema."""
    serialized = json.dumps(
        {"entity_type": entity_type, "fields": fields},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def active_schema_fields(
    session, organization_id: str, entity_type_name: str
) -> list[dict]:
    """Merged ``fields_json`` across every active schema for an entity type name."""
    schemas = (
        session.query(EntityTypeSchemaModel)
        .filter(
            EntityTypeSchemaModel.organization_id == organization_id,
            EntityTypeSchemaModel.entity_type == entity_type_name,
            EntityTypeSchemaModel.is_active.is_(True),
        )
        .all()
    )
    fields: list[dict] = []
    for schema in schemas:
        fields.extend(schema.fields_json or [])
    return fields


def active_schema_fields_by_type_id(
    session, organization_id: str, entity_type_id: str
) -> list[dict]:
    """Same as :func:`active_schema_fields`, resolving the type by id first.

    Returns an empty list when the entity type does not exist.
    """
    type_model = (
        session.query(EntityTypeModel)
        .filter_by(organization_id=organization_id, entity_type_id=entity_type_id)
        .first()
    )
    if type_model is None:
        return []
    return active_schema_fields(session, organization_id, type_model.name)



# ── Service ───────────────────────────────────────────────────────────────────


class FormsModelService:
    """Forms persistence service — owns entity type schemas and picklists."""

    module_name = "forms"

    def __init__(
        self,
        database_service_manager: DatabaseServiceManager | None = None,
        background_jobs_manager: Any = None,
        mail_manager: Any = None,
    ) -> None:
        """Store the services needed for form persistence and cross-module lookups."""
        self.module_name = "forms"
        self.database_service_manager = database_service_manager
        self.background_jobs_manager = background_jobs_manager
        self.mail_db = mail_manager

    # ── Entity Type Schema ─────────────────────────────────────────────────────

    def create_form_entity_schema(
        self,
        db: Session,
        *,
        organization_id: str,
        schema_key: str,
        name: str,
        description: str | None,
        entity_type: str,
        fields: list[dict[str, object]],
        is_active: bool,
        content_hash: str,
        display_order: int = 0,
    ) -> EntityTypeSchemaContract:
        """Insert a new entity type schema row and return its contract form."""
        try:
            existing = (
                db.query(EntityTypeSchemaModel)
                .filter_by(organization_id=organization_id, schema_key=schema_key)
                .first()
            )
            if existing is not None:
                raise ConflictError(f"entity type schema '{schema_key}' already exists")
            model = EntityTypeSchemaModel(
                organization_id=organization_id,
                schema_key=schema_key,
                name=name,
                description=description,
                entity_type=entity_type,
                fields_json=fields,
                is_active=is_active,
                display_order=display_order,
                content_hash=content_hash,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._entity_schema_to_contract(model)
        except ConflictError:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(f"entity type schema '{schema_key}' already exists") from exc
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to create entity type schema: {exc}") from exc

    @contextmanager
    def _db_session(self) -> Iterator[Session]:
        """Yield a session opened from this service's own connection pool."""
        session = self.database_service_manager.postgres_db_service().get_db_session()
        try:
            yield session
        finally:
            session.close()

    def list_form_entity_schemas(
        self,
        *,
        organization_id: str,
        schema_key: str | None = None,
        entity_type: str | None = None,
    ) -> list[EntityTypeSchemaContract]:
        """List entity type schemas for one organization with optional filtering.

        Opens its own session, like every other module's db_models. Callers used to pass the
        FastAPI request session down through the manager; they no longer have to.
        """
        with self._db_session() as db:
            try:
                query = db.query(EntityTypeSchemaModel).filter_by(organization_id=organization_id)
                if schema_key is not None:
                    query = query.filter_by(schema_key=schema_key)
                if entity_type is not None:
                    query = query.filter_by(entity_type=entity_type)
                ordered = query.order_by(
                    EntityTypeSchemaModel.display_order.asc(),
                    EntityTypeSchemaModel.schema_key.asc(),
                ).all()
                return [self._entity_schema_to_contract(item) for item in ordered]
            except Exception as exc:
                raise PersistenceError(f"Unable to list entity type schemas: {exc}") from exc

    def get_form_entity_schema(
        self,
        db: Session,
        *,
        organization_id: str,
        schema_key: str,
    ) -> EntityTypeSchemaContract | None:
        """Fetch one entity type schema by organization and schema key."""
        try:
            item = (
                db.query(EntityTypeSchemaModel)
                .filter_by(organization_id=organization_id, schema_key=schema_key)
                .first()
            )
            return self._entity_schema_to_contract(item) if item else None
        except Exception as exc:
            raise PersistenceError(f"Unable to get entity type schema: {exc}") from exc

    def update_form_entity_schema(
        self,
        db: Session,
        *,
        organization_id: str,
        schema_key: str,
        name: str,
        description: str | None,
        entity_type: str,
        fields: list[dict[str, object]],
        is_active: bool,
        content_hash: str,
        display_order: int | None = None,
    ) -> EntityTypeSchemaContract | None:
        """Update an entity type schema and return the refreshed contract."""
        try:
            item = (
                db.query(EntityTypeSchemaModel)
                .filter_by(organization_id=organization_id, schema_key=schema_key)
                .first()
            )
            if item is None:
                return None
            linked_fields = [
                (index, dict(field))
                for index, field in enumerate(item.fields_json or [])
                if field.get("library_field_id")
            ]
            linked_keys = {
                str(field.get("field") or field.get("name") or field.get("id") or "").lower()
                for _, field in linked_fields
            }
            fields = [
                dict(field)
                for field in fields
                if not field.get("library_field_id")
                and str(field.get("field") or field.get("name") or field.get("id") or "").lower()
                not in linked_keys
            ]
            for index, linked_field in linked_fields:
                fields.insert(min(index, len(fields)), linked_field)
            item.name = name
            item.description = description
            item.entity_type = entity_type
            item.fields_json = fields
            item.is_active = is_active
            if display_order is not None:
                item.display_order = display_order
            item.content_hash = schema_content_hash(entity_type, fields)
            db.commit()
            db.refresh(item)
            return self._entity_schema_to_contract(item)
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to update entity type schema: {exc}") from exc

    def delete_form_entity_schema(
        self,
        db: Session,
        *,
        organization_id: str,
        schema_key: str,
    ) -> bool:
        """Delete an entity type schema and report whether a row was removed."""
        try:
            item = (
                db.query(EntityTypeSchemaModel)
                .filter_by(organization_id=organization_id, schema_key=schema_key)
                .first()
            )
            if item is None:
                return False
            db.delete(item)
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to delete entity type schema: {exc}") from exc

    @staticmethod
    def _entity_schema_to_contract(item: EntityTypeSchemaModel) -> EntityTypeSchemaContract:
        """Convert a schema ORM row into the domain contract."""
        try:
            return EntityTypeSchemaContract.model_validate(
                {
                    "id": item.id,
                    "schema_key": item.schema_key,
                    "name": item.name,
                    "description": item.description,
                    "entity_type": item.entity_type,
                    "fields": item.fields_json or [],
                    "is_active": item.is_active,
                    "display_order": item.display_order,
                    "content_hash": item.content_hash,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
            )
        except Exception as exc:
            schema_key = getattr(item, "schema_key", "unknown")
            raise ValidationError(f"entity type schema '{schema_key}' is invalid: {exc}") from exc

    # ── Picklists ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_picklist(db: Session, organization_id: str, picklist_id: str) -> PicklistModel | None:
        """Fetch a non-archived picklist row by UUID id scoped to one organization."""
        return (
            db.query(PicklistModel)
            .filter(
                PicklistModel.organization_id == organization_id,
                PicklistModel.id == picklist_id,
                PicklistModel.archived_at.is_(None),
            )
            .first()
        )

    def create_picklist(
        self, db: Session, organization_id: str, request: PicklistCreateRequest
    ) -> PicklistContract:
        """Insert a new organization-scoped picklist."""
        try:
            model = PicklistModel(
                organization_id=organization_id,
                name=request.name,
                options=[opt.model_dump() for opt in request.options],
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._picklist_to_contract(model)
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(
                f"Picklist '{request.name}' already exists for organization '{organization_id}'"
            ) from exc
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to create picklist: {exc}") from exc

    def list_picklists(self, db: Session, organization_id: str) -> list[PicklistContract]:
        """List non-archived picklists for one organization in creation order."""
        try:
            rows = (
                db.query(PicklistModel)
                .filter(
                    PicklistModel.organization_id == organization_id,
                    PicklistModel.archived_at.is_(None),
                )
                .order_by(PicklistModel.created_at)
                .all()
            )
            return [self._picklist_to_contract(row) for row in rows]
        except Exception as exc:
            raise PersistenceError(f"Unable to list picklists: {exc}") from exc

    def get_picklist(
        self, db: Session, organization_id: str, picklist_id: str
    ) -> PicklistContract | None:
        """Fetch a single picklist by organization and picklist id."""
        try:
            row = self._get_picklist(db, organization_id, picklist_id)
            return self._picklist_to_contract(row) if row else None
        except Exception as exc:
            raise PersistenceError(f"Unable to get picklist: {exc}") from exc

    def update_picklist(
        self, db: Session, organization_id: str, picklist_id: str, request: PicklistUpdateRequest
    ) -> PicklistContract | None:
        """Update the mutable fields of an existing picklist."""
        try:
            row = self._get_picklist(db, organization_id, picklist_id)
            if row is None:
                return None
            if request.name is not None:
                row.name = request.name
            if request.options is not None:
                row.options = [opt.model_dump() for opt in request.options]
            db.commit()
            db.refresh(row)
            return self._picklist_to_contract(row)
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to update picklist: {exc}") from exc

    def delete_picklist(self, db: Session, organization_id: str, picklist_id: str) -> bool:
        """Soft-delete a picklist by setting archived_at."""
        try:
            row = self._get_picklist(db, organization_id, picklist_id)
            if row is None:
                return False
            row.archived_at = datetime.now(UTC)
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to delete picklist: {exc}") from exc

    @staticmethod
    def _picklist_to_contract(model: PicklistModel) -> PicklistContract:
        """Convert a picklist ORM row into the domain contract."""
        return PicklistContract(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            options=model.options or [],
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    # ── Public form (cross-module) ─────────────────────────────────────────────

    def get_public_form_by_entity(self, db: Session, entity_id: str) -> dict[str, Any] | None:
        """Find the most recent pending_external receive_data run for an entity and return its form payload."""
        try:
            if self.background_jobs_manager is None:
                raise PersistenceError("background_jobs service is not configured")
            run = self.background_jobs_manager.get_pending_external_run_for_entity(db, entity_id)
            if run is None:
                return None
            return self._build_form_payload(db, run)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Unable to get public form for entity: {exc}") from exc

    def get_pending_external_run_by_run_id(self, db: Session, run_id: str) -> dict[str, Any] | None:
        """Return a pending_external action run by run_id, or None."""
        try:
            if self.background_jobs_manager is None:
                raise PersistenceError("background_jobs service is not configured")
            return self.background_jobs_manager.get_pending_external_run_by_run_id(db, run_id)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Unable to get pending external run: {exc}") from exc

    def _build_form_payload(self, db: Session, run: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve the form schema for a run and return the combined payload with entity values."""
        try:
            config = run["config_json"] if isinstance(run["config_json"], dict) else {}
            organization_id = str(run["organization_id"])
            entity_id = str(run["entity_id"])
            form_id = str(config.get("form_id") or "").strip()
            if not form_id and str(run.get("action_kind") or "") == "mail.send_email":
                # A standalone send-email run (no receive_data action behind it) has
                # no form_id of its own — the form it embeds is configured on the
                # email template it sent, so resolve it from there.
                template_id = str(config.get("template_id") or "").strip()
                if template_id:
                    template = (
                        db.query(EmailTemplateModel)
                        .filter(EmailTemplateModel.template_id == template_id)
                        .filter(
                            (EmailTemplateModel.organization_id == organization_id)
                            | (EmailTemplateModel.is_system.is_(True))
                        )
                        .first()
                    )
                    if template and template.form_id:
                        form_id = str(template.form_id).strip()
            total_steps_raw = config.get("total_steps")
            try:
                total_steps: int | None = int(total_steps_raw) if total_steps_raw is not None else None
            except (ValueError, TypeError):
                total_steps = None
            if not form_id:
                return None
            schema = (
                db.query(EntityTypeSchemaModel)
                .filter(EntityTypeSchemaModel.organization_id == organization_id)
                .filter(
                    or_(
                        EntityTypeSchemaModel.schema_key == form_id,
                        EntityTypeSchemaModel.id == form_id,
                    )
                )
                .filter(EntityTypeSchemaModel.is_active.is_(True))
                .first()
            )
            if schema is None:
                return None

            entity = (
                db.query(EntityRecordModel)
                .filter(
                    EntityRecordModel.entity_id == entity_id,
                    EntityRecordModel.organization_id == organization_id,
                    EntityRecordModel.archived_at.is_(None),
                )
                .first()
            )
            entity_data: dict[str, Any] = dict(entity.data) if entity and entity.data else {}

            fields_with_values = []
            for field in schema.fields_json or []:
                field_key = field.get("field") or field.get("name") or ""
                enriched = dict(field)
                enriched["current_value"] = entity_data.get(field_key)
                fields_with_values.append(enriched)

            return {
                "run_id": str(run["run_id"]),
                "organization_id": organization_id,
                "entity_id": entity_id,
                "action_kind": str(run.get("action_kind") or ""),
                "status": str(run["status"]),
                "external_timeout_at": run.get("external_timeout_at"),
                "config": config,
                "form": {
                    "schema_key": str(schema.schema_key),
                    "name": str(schema.name),
                    "description": schema.description,
                    "entity_type": str(schema.entity_type),
                    "fields": fields_with_values,
                    **({"total_steps": total_steps} if total_steps is not None else {}),
                },
            }
        except Exception as exc:
            raise PersistenceError(f"Unable to build form payload: {exc}") from exc

    def patch_entity_data(
        self,
        db: Session,
        entity_id: str,
        organization_id: str,
        fields: dict[str, Any],
    ) -> None:
        """Merge submitted fields into the entity's data column without overwriting other fields."""
        try:
            entity = (
                db.query(EntityRecordModel)
                .filter(
                    EntityRecordModel.entity_id == entity_id,
                    EntityRecordModel.organization_id == organization_id,
                    EntityRecordModel.archived_at.is_(None),
                )
                .with_for_update()
                .first()
            )
            if entity is None:
                raise PersistenceError(f"Entity {entity_id} not found")
            merged = dict(entity.data or {})
            # auto_number fields are backend-generated and non-editable: never let
            # a patch overwrite or clear an existing generated identifier.
            locked = set(
                self._auto_number_ids_for_type_id(
                    db, organization_id, entity.entity_type_id
                )
            )
            type_model = (
                db.query(EntityTypeModel)
                .filter_by(
                    organization_id=organization_id,
                    entity_type_id=entity.entity_type_id,
                )
                .first()
            )
            if type_model is not None and _identifier_template_from_schema(type_model.schema):
                locked.add(IDENTIFIER_FIELD_KEY)
            merged.update({k: v for k, v in fields.items() if k not in locked})
            entity.data = merged
            db.commit()
        except PersistenceError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to patch entity data: {exc}") from exc

    def _auto_number_ids_for_type_id(
        self, db: Session, organization_id: str, entity_type_id: str
    ) -> set[str]:
        """Resolve the auto_number field ids on an entity type's active schema(s)."""
        schema_fields = active_schema_fields_by_type_id(
            db, organization_id, entity_type_id
        )
        return auto_number_field_ids(schema_fields)

    def _with_auto_numbers(
        self, db: Session, organization_id: str, target_type: Any, data: dict
    ) -> dict:
        """Fill auto_number fields defined on the target type's active schema(s)."""
        schema_fields = active_schema_fields(db, organization_id, target_type.name)
        if not any(str(f.get("type", "")).lower() == "auto_number" for f in schema_fields):
            return data

        out = dict(data or {})
        apply_auto_number_defaults(
            schema_fields,
            out,
            lambda field_key: _get_next_auto_number(
                db, organization_id, target_type.entity_type_id, field_key
            ),
            overwrite=True,
        )
        return out

    def get_public_form_by_token(self, db: Session, run_id: str) -> dict[str, Any] | None:
        """Load the action run by run_id and return its form payload."""
        try:
            if self.background_jobs_manager is None:
                raise PersistenceError("background_jobs service is not configured")
            run = self.background_jobs_manager.get_action_run(db, run_id)
            if run is None:
                return None
            return self._build_form_payload(db, run)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Unable to get public form by token: {exc}") from exc

    def _insert_entity_with_templated_identifier(
        self,
        db: Session,
        *,
        organization_id: str,
        target_type: EntityTypeModel,
        fields: dict | None,
        owner_id: str | None,
    ) -> EntityRecordModel:
        """Auto-numbers + templated identifier + INSERT (flushed, not committed).

        Retries the identifier once on the partial unique index — a concurrent
        create can steal the suffix between the collision query and the flush
        (same savepoint pattern as the entities-path create)."""
        new_data = self._with_auto_numbers(
            db, organization_id, target_type, dict(fields or {})
        )
        for attempt in (1, 2):
            try:
                with db.begin_nested():
                    new_entity = EntityRecordModel(
                        entity_id=str(uuid4()),
                        organization_id=organization_id,
                        entity_type_id=target_type.entity_type_id,
                        data=apply_identifier_template(
                            None,
                            db,
                            organization_id=organization_id,
                            entity_type=target_type,
                            entity_id=None,
                            data=dict(new_data),
                        ),
                        owner_id=owner_id,
                    )
                    db.add(new_entity)
                    db.flush()
                return new_entity
            except IntegrityError as exc:
                if attempt == 2:
                    raise ConflictError(
                        "Unable to allocate a unique identifier for the new entity"
                    ) from exc
        raise PersistenceError("unreachable")  # for the type checker

    def submit_public_form(
        self,
        db: Session,
        *,
        run_id: str,
        organization_id: str,
        entity_id: str,
        fields: dict[str, Any],
        form_entity_type: str | None = None,
    ) -> dict[str, Any]:
        """Persist submitted form fields."""
        try:
            if self.background_jobs_manager is None:
                raise PersistenceError("background_jobs service is not configured")

            entity = (
                db.query(EntityRecordModel)
                .filter(EntityRecordModel.organization_id == organization_id)
                .filter(EntityRecordModel.entity_id == entity_id)
                .first()
            )

            created_entity_id: str | None = None

            if entity is not None and form_entity_type:
                original_type_model = (
                    db.query(EntityTypeModel)
                    .filter_by(
                        organization_id=organization_id, entity_type_id=entity.entity_type_id
                    )
                    .first()
                )
                original_type_name = original_type_model.name if original_type_model else ""

                if form_entity_type != original_type_name:
                    target_type = (
                        db.query(EntityTypeModel)
                        .filter_by(
                            organization_id=organization_id, name=form_entity_type, is_active=True
                        )
                        .first()
                    )
                    if target_type is None:
                        raise PersistenceError(
                            f"entity_type '{form_entity_type}' not found or inactive"
                        )
                    # Templated identifiers: generated here too — public/deferred
                    # creates carry no relations, so reference tokens render blank.
                    new_entity = self._insert_entity_with_templated_identifier(
                        db,
                        organization_id=organization_id,
                        target_type=target_type,
                        fields=fields,
                        owner_id=entity.owner_id,
                    )
                    created_entity_id = new_entity.entity_id
            # Same-entity data merge is intentionally NOT performed here. The caller
            # (_submit_with_raw_payload) writes the fields via patch_entity_data,
            # which strips backend-generated auto_number ids. Writing (and
            # committing) the raw fields here would let a crafted public payload
            # persist an attacker-supplied auto_number value before the lock applies.

            self.background_jobs_manager.update_action_run_submitted(db, run_id, fields)
            db.commit()
            return {"created_entity_id": created_entity_id}
        except (ConflictError, PersistenceError):
            raise
        except Exception as exc:
            db.rollback()
            raise PersistenceError(f"Unable to submit public form: {exc}") from exc

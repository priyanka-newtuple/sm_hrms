"""manager layer for forms."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from common.enums import ModuleStatus
from common.logger import logger
from common.protocols import SYSTEM_USER, RolesServiceProtocol
from common.security import decode_form_link_token
from exceptions import ConflictError, NotFoundError, ServiceError, ValidationError
from forms.models.response import (
    EntityTypeSchemaListResponse,
    EntityTypeSchemaResponse,
    MetadataRegistryStatusResponse,
    PicklistListResponse,
    PicklistResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from common.configuration import Configuration
    from database.manager import DatabaseServiceManager
    from forms.db_models import FormsModelService
    from forms.models.interface import EntityTypeSchemaContract
    from forms.models.request import (
        EntityTypeSchemaCreateRequest,
        EntityTypeSchemaUpdateRequest,
        PicklistCreateRequest,
        PicklistUpdateRequest,
    )



class FormsEntitiesManager(Protocol):
    """Entity manager methods used by the forms facade."""

    def get_status(self) -> object: ...

    def upsert_form_config_for_actor(
        self,
        actor: dict[str, object],
        request: Any,
    ) -> Any: ...

    def get_form_config_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        form_key: str,
    ) -> Any: ...


class FormsServiceManager:
    """Service manager for the forms module — owns entity type schemas and picklists."""

    def __init__(
        self,
        forms_db_model_service: FormsModelService,
        database_service_manager: DatabaseServiceManager,
        config: Configuration,
        *dependencies: object,
        roles_manager: RolesServiceProtocol | None = None,
    ) -> None:
        """Initialize the forms service with persistence, config, and optional collaborators."""
        self.database_service_manager = database_service_manager
        _ = dependencies
        self.forms_db_model_service = forms_db_model_service
        self.config = config
        self.module_name = "forms"
        self._started = False
        self.entities_service_manager: FormsEntitiesManager | None = None
        self.workflow_service_manager = None
        self.roles_manager = roles_manager

    def start(self) -> None:
        """Mark the forms module as started."""
        self._started = True

    def stop(self) -> None:
        """Mark the forms module as stopped."""
        self._started = False

    def get_status(self) -> MetadataRegistryStatusResponse:
        """Return the current lifecycle status for the forms module."""
        return MetadataRegistryStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    # ── Entity Type Schema ─────────────────────────────────────────────────────

    def create_form_entity_schema_for_actor(
        self,
        actor: dict[str, object],
        payload: EntityTypeSchemaCreateRequest,
        db: Session,
    ) -> EntityTypeSchemaResponse:
        """Create a new form entity schema within the actor's organization."""
        organization_id = self._organization_id(actor)
        content_hash = self._content_hash(payload.entity_type, payload.fields)
        existing = self.forms_db_model_service.get_form_entity_schema(
            db, organization_id=organization_id, schema_key=payload.schema_key
        )
        if existing is not None:
            raise ConflictError(f"entity type schema '{payload.schema_key}' already exists")
        field_dicts = [field.model_dump(mode="json") for field in payload.fields]
        created = self.forms_db_model_service.create_form_entity_schema(
            db,
            organization_id=organization_id,
            schema_key=payload.schema_key,
            name=payload.name,
            description=payload.description,
            entity_type=payload.entity_type,
            fields=field_dicts,
            is_active=payload.is_active,
            content_hash=content_hash,
            display_order=payload.display_order,
        )
        return self._entity_schema_to_response(created)

    def get_active_entity_schemas(
        self, organization_id: str, entity_type: str
    ) -> list[EntityTypeSchemaContract]:
        """Return the active form schemas for one entity type.

        Separate from `list_form_entity_schemas_for_actor` because that one needs an actor and a
        request session, and this caller has neither: the workflow module compares a saved
        workflow entity_schema against the live form, from paths that only carry an
        organization id. Applying the `is_active` filter here keeps that policy in the manager.
        """
        schemas = self.forms_db_model_service.list_form_entity_schemas(
            organization_id=organization_id, entity_type=entity_type
        )
        return [schema for schema in schemas if schema.is_active]

    def list_form_entity_schemas_for_actor(
        self,
        actor: dict[str, object],
        schema_key: str | None = None,
        entity_type: str | None = None,
    ) -> EntityTypeSchemaListResponse:
        """List form entity schemas visible to the actor, optionally filtered by key or entity type."""
        organization_id = self._organization_id(actor)
        items = self.forms_db_model_service.list_form_entity_schemas(
            organization_id=organization_id, schema_key=schema_key, entity_type=entity_type
        )
        return EntityTypeSchemaListResponse(
            items=[self._entity_schema_to_response(item) for item in items],
            total=len(items),
        )

    def get_form_entity_schema_for_actor(
        self, actor: dict[str, object], db: Session, schema_key: str
    ) -> EntityTypeSchemaResponse:
        """Fetch one form entity schema for the actor's organization."""
        organization_id = self._organization_id(actor)
        item = self.forms_db_model_service.get_form_entity_schema(
            db, organization_id=organization_id, schema_key=schema_key
        )
        if item is None:
            raise NotFoundError(f"entity type schema '{schema_key}' was not found")
        return self._entity_schema_to_response(item)

    def update_form_entity_schema_for_actor(
        self,
        actor: dict[str, object],
        db: Session,
        schema_key: str,
        payload: EntityTypeSchemaUpdateRequest,
    ) -> EntityTypeSchemaResponse:
        """Update an existing form entity schema for the actor's organization."""
        organization_id = self._organization_id(actor)
        current = self.forms_db_model_service.get_form_entity_schema(
            db, organization_id=organization_id, schema_key=schema_key
        )
        if current is None:
            raise NotFoundError(f"entity type schema '{schema_key}' was not found")
        next_entity_type = (
            payload.entity_type if payload.entity_type is not None else current.entity_type
        )
        next_fields = payload.fields if payload.fields is not None else current.fields
        next_display_order = (
            payload.display_order if payload.display_order is not None else current.display_order
        )
        next_hash = self._content_hash(next_entity_type, next_fields)
        next_name = payload.name if payload.name is not None else current.name
        if (
            next_hash == (current.content_hash or "")
            and next_display_order == current.display_order
            and next_name == current.name
        ):
            raise ConflictError("entity type schema update has no effective changes")
        # next_fields may be contract EntityField objects (when carried over
        # from the current row, e.g. a display_order-only update) or request
        # models — serialize either to JSON-safe dicts for the JSONB column.
        field_dicts = [
            field.model_dump(mode="json") if hasattr(field, "model_dump") else field
            for field in next_fields
        ]
        updated = self.forms_db_model_service.update_form_entity_schema(
            db,
            organization_id=organization_id,
            schema_key=schema_key,
            name=payload.name if payload.name is not None else current.name,
            description=payload.description
            if payload.description is not None
            else current.description,
            entity_type=next_entity_type,
            fields=field_dicts,
            is_active=payload.is_active if payload.is_active is not None else current.is_active,
            content_hash=next_hash,
            display_order=next_display_order,
        )
        if updated is None:
            logger.warning(
                "update_form_entity_schema: schema_key=%s disappeared during update org=%s",
                schema_key,
                organization_id,
            )
            raise NotFoundError(f"entity type schema '{schema_key}' was not found")
        return self._entity_schema_to_response(updated)

    def delete_form_entity_schema_for_actor(
        self, actor: dict[str, object], db: Session, schema_key: str
    ) -> None:
        """Delete a form entity schema owned by the actor's organization."""
        organization_id = self._organization_id(actor)
        deleted = self.forms_db_model_service.delete_form_entity_schema(
            db, organization_id=organization_id, schema_key=schema_key
        )
        if not deleted:
            raise NotFoundError(f"entity type schema '{schema_key}' was not found")

    # ── Picklists ──────────────────────────────────────────────────────────────

    def list_picklists_for_actor(
        self, db: Session, actor: dict[str, object]
    ) -> PicklistListResponse:
        """List all picklists available to the actor's organization."""
        organization_id = self._require_actor_field(actor, "organization_id")
        contracts = self.forms_db_model_service.list_picklists(db, organization_id)
        items = [self._picklist_to_response(c) for c in contracts]
        return PicklistListResponse(organization_id=organization_id, items=items, total=len(items))

    def get_picklist_for_actor(
        self, db: Session, actor: dict[str, object], picklist_id: str
    ) -> PicklistResponse:
        """Fetch a single picklist by ID for the actor's organization."""
        organization_id = self._require_actor_field(actor, "organization_id")
        contract = self.forms_db_model_service.get_picklist(db, organization_id, picklist_id)
        if contract is None:
            raise NotFoundError(f"Picklist '{picklist_id}' not found")
        return self._picklist_to_response(contract)

    def create_picklist_for_actor(
        self, db: Session, actor: dict[str, object], request: PicklistCreateRequest
    ) -> PicklistResponse:
        """Create a picklist for the actor's organization."""
        organization_id = self._require_actor_field(actor, "organization_id")
        contract = self.forms_db_model_service.create_picklist(db, organization_id, request)
        return self._picklist_to_response(contract)

    def update_picklist_for_actor(
        self,
        db: Session,
        actor: dict[str, object],
        picklist_id: str,
        request: PicklistUpdateRequest,
    ) -> PicklistResponse:
        """Update an existing picklist for the actor's organization."""
        organization_id = self._require_actor_field(actor, "organization_id")
        contract = self.forms_db_model_service.update_picklist(
            db, organization_id, picklist_id, request
        )
        if contract is None:
            raise NotFoundError(f"Picklist '{picklist_id}' not found")
        return self._picklist_to_response(contract)

    def delete_picklist_for_actor(
        self, db: Session, actor: dict[str, object], picklist_id: str
    ) -> None:
        """Delete a picklist belonging to the actor's organization."""
        organization_id = self._require_actor_field(actor, "organization_id")
        deleted = self.forms_db_model_service.delete_picklist(db, organization_id, picklist_id)
        if not deleted:
            raise NotFoundError(f"Picklist '{picklist_id}' not found")

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _organization_id(actor: dict[str, object]) -> str:
        """Extract and validate the organization id from the actor payload."""
        organization_id = str(actor.get("organization_id", "")).strip()
        if not organization_id:
            raise ServiceError("actor organization context is required")
        return organization_id

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field: str) -> str:
        """Require a non-empty string field from the actor payload."""
        value = actor.get(field)
        if not value or not isinstance(value, str):
            raise ServiceError(f"Actor is missing required field: {field}")
        return value

    def _require_entities_manager(self) -> FormsEntitiesManager:
        """Return the configured entities manager or fail fast if it is missing."""
        if self.entities_service_manager is None:
            raise ServiceError("entities manager dependency is not configured")
        return self.entities_service_manager

    def _strip_non_editable_fields(
        self,
        db: Any,
        actor: dict[str, object],
        org_id: str,
        entity_type_name: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a copy of `fields` with non-editable fields removed.

        No-ops when `roles_manager` is None, `entity_type_name` is empty, or the
        actor has unrestricted edit access (roles_manager returns None for editable).
        Public submissions (actor==None or user_id=="system") are always passed through.
        """
        if self.roles_manager is None or not entity_type_name:
            return fields
        user_id = str(actor.get("user_id") or "").strip()
        if not user_id or user_id == SYSTEM_USER:
            return fields
        editable = self.roles_manager.get_editable_fields(db, user_id, org_id, entity_type_name)
        if editable is None:
            return fields
        return {k: v for k, v in fields.items() if k in editable}

    @staticmethod
    def _content_hash(entity_type: str, fields: list[Any]) -> str:
        """Compute a stable hash for schema change detection."""
        payload = {
            "entity_type": entity_type,
            "fields": [
                field.model_dump(mode="json") if hasattr(field, "model_dump") else field
                for field in fields
            ],
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _entity_schema_to_response(record: EntityTypeSchemaContract) -> EntityTypeSchemaResponse:
        """Convert a schema contract into the API response model."""
        return EntityTypeSchemaResponse(
            id=record.id,
            schema_key=record.schema_key,
            name=record.name,
            description=record.description,
            entity_type=record.entity_type,
            fields=record.fields,
            is_active=record.is_active,
            display_order=record.display_order,
            content_hash=record.content_hash,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _picklist_to_response(contract: object) -> PicklistResponse:
        """Convert a picklist contract-like object into the API response model."""
        return PicklistResponse(
            id=getattr(contract, "id", ""),
            organization_id=getattr(contract, "organization_id", ""),
            name=getattr(contract, "name", ""),
            options=getattr(contract, "options", []),
            created_at=getattr(contract, "created_at", None),
            updated_at=getattr(contract, "updated_at", None),
        )

    def get_public_form_by_token(self, db: Session, token: str) -> dict[str, Any]:
        """Decode a signed form token and return the form payload."""
        try:
            claims = decode_form_link_token(token)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        run_id = str(claims.get("run_id") or "").strip()
        entity_id = str(claims.get("entity_id") or "").strip()
        if run_id:
            result = self._get_public_form_by_run_id(db, run_id)
            if result is not None:
                return result
            raise ValidationError("form link is no longer active or has already been completed")
        return self.get_public_form_by_entity(db, entity_id)

    def submit_public_form_by_token(
        self, db: Session, token: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Decode a signed form token and submit the form."""
        try:
            claims = decode_form_link_token(token)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        run_id = str(claims.get("run_id") or "").strip()
        entity_id = str(claims.get("entity_id") or "").strip()
        if run_id:
            raw = self.forms_db_model_service.get_public_form_by_token(db, run_id)
            if raw is not None and raw.get("action_kind") in ("form.receive_data", "mail.send_email"):
                if raw["status"] != "pending_external":
                    raise ValidationError("form has already been completed or is not yet active")
                timeout_at = raw.get("external_timeout_at")
                if timeout_at is not None and datetime.now(UTC) > timeout_at:
                    raise ValidationError("form link has expired")
                return self._submit_with_raw_payload(db, raw, fields, actor=None)
        return self.submit_public_form_by_entity(db, entity_id, fields)

    def get_public_form_by_entity(self, db: Session, entity_id: str) -> dict[str, Any]:
        """Load the pending receive_data run for an entity and return its form payload."""
        entity_id = str(entity_id).strip()
        if not entity_id:
            raise ValidationError("entity_id is required")
        payload = self.forms_db_model_service.get_public_form_by_entity(db, entity_id)
        if payload is None:
            raise NotFoundError("no active form found for this entity")
        if payload["status"] != "pending_external":
            raise ValidationError("form has already been completed or is not yet active")
        timeout_at = payload.get("external_timeout_at")
        if timeout_at is not None and datetime.now(UTC) > timeout_at:
            raise ValidationError("form link has expired")
        return {
            "run_id": payload["run_id"],
            "organization_id": payload["organization_id"],
            "entity_id": payload["entity_id"],
            "status": payload["status"],
            "form": payload["form"],
        }

    def _get_public_form_by_run_id(self, db: Session, run_id: str) -> dict[str, Any] | None:
        """Load an action run by run_id and return its form payload, or None if no form schema found."""
        payload = self.forms_db_model_service.get_public_form_by_token(db, run_id)
        if payload is None:
            return None
        if payload["status"] != "pending_external":
            raise ValidationError("form has already been completed or is not yet active")
        timeout_at = payload.get("external_timeout_at")
        if timeout_at is not None and datetime.now(UTC) > timeout_at:
            raise ValidationError("form link has expired")
        return {
            "run_id": payload["run_id"],
            "organization_id": payload["organization_id"],
            "entity_id": payload["entity_id"],
            "status": payload["status"],
            "form": payload["form"],
        }

    def submit_public_form_by_entity(
        self, db: Session, entity_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist submitted form fields to the entity and advance the workflow."""
        self.get_public_form_by_entity(db, entity_id)  # validates status and timeout
        raw = self.forms_db_model_service.get_public_form_by_entity(db, entity_id)
        # Public form — no actor context; field permissions are not applied.
        return self._submit_with_raw_payload(db, raw, fields, actor=None)

    @staticmethod
    def _drop_read_only_fields(
        raw: dict[str, Any], fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Remove values for fields the form itself marks read-only.

        The form payload handed to the public page is the same one read here,
        so it is the authority on what that page was allowed to collect. Keys
        are dropped rather than rejected: a stale client that still posts them
        should submit the rest of the form rather than fail outright.
        """
        if not fields:
            return fields
        form_fields = (raw.get("form") or {}).get("fields") or []
        locked = {
            str(field.get("field") or field.get("id") or "")
            for field in form_fields
            if isinstance(field, dict) and field.get("read_only") is True
        }
        locked.discard("")
        if not locked:
            return fields
        return {key: value for key, value in fields.items() if key not in locked}

    def _submit_with_raw_payload(
        self,
        db: Session,
        raw: dict[str, Any] | None,
        fields: dict[str, Any],
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute form submission given the raw DB payload — works for any action kind.

        When `actor` is provided and `roles_manager` is wired, non-editable fields
        are stripped from `fields` before the entity data write. Public submissions
        (actor=None) always pass all fields through unchanged.
        """
        if raw is None:
            raise NotFoundError("no active form found for this entity")
        # A public submitter is unauthenticated and the request is entirely
        # client-controlled, so the form's own definition is the only authority
        # on what may be written. Dropped before the write below AND before
        # submit_public_form, whose create-new-entity branch inserts these
        # values directly.
        fields = self._drop_read_only_fields(raw, fields)
        run_id = str(raw["run_id"])
        organization_id = str(raw["organization_id"])
        entity_id = str(raw["entity_id"])
        form_entity_type = str((raw.get("form") or {}).get("entity_type") or "").strip() or None
        config = dict((raw or {}).get("config") or {})
        result = self.forms_db_model_service.submit_public_form(
            db,
            run_id=run_id,
            organization_id=organization_id,
            entity_id=entity_id,
            fields=fields,
            form_entity_type=form_entity_type,
        )
        created_entity_id = (result or {}).get("created_entity_id")

        if fields and not created_entity_id:
            write_fields = fields
            if actor is not None and self.roles_manager is not None and form_entity_type:
                _db_for_rbac = self.database_service_manager.get_db_session()
                try:
                    write_fields = self._strip_non_editable_fields(
                        _db_for_rbac, actor, organization_id, form_entity_type, fields
                    )
                finally:
                    _db_for_rbac.close()
            self.forms_db_model_service.patch_entity_data(db, entity_id, organization_id, write_fields)

        # After the entity write, so a chained next action sees the submitted fields.
        bg = self.forms_db_model_service.background_jobs_manager
        if bg is not None:
            bg.advance_chain_for_run(db, run_id)

        trigger = str((config.get("outcome_triggers") or {}).get("received") or "").strip()
        if trigger and self.workflow_service_manager is not None:
            self.workflow_service_manager.execute_transition_system(
                organization_id=organization_id,
                entity_id=entity_id,
                trigger=trigger,
            )
        self._emit_action_form_submitted_event(
            organization_id=organization_id,
            entity_id=entity_id,
            run_id=run_id,
            trigger_fired=trigger or None,
            created_entity_id=created_entity_id,
        )
        return {
            "success": True,
            "run_id": run_id,
            "entity_id": entity_id,
            "created_entity_id": created_entity_id,
        }

    def _emit_action_form_submitted_event(
        self,
        organization_id: str,
        entity_id: str,
        run_id: str,
        trigger_fired: str | None,
        created_entity_id: str | None,
    ) -> None:
        """Append ACTION_FORM_SUBMITTED to the entity audit timeline."""
        if self.workflow_service_manager is None:
            return
        try:
            self.workflow_service_manager.entities_service_manager._emit_entity_event(
                organization_id=organization_id,
                entity_id=entity_id,
                event_type="ACTION_FORM_SUBMITTED",
                actor_type="system",
                correlation_id=run_id,
                payload={
                    "run_id": run_id,
                    "action_kind": "form.receive_data",
                    "trigger_fired": trigger_fired,
                    "created_entity_id": created_entity_id,
                },
            )
        except Exception as exc:
            logger.warning(f"failed to emit ACTION_FORM_SUBMITTED run_id={run_id}: {exc}")

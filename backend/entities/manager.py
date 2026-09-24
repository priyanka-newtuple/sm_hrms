"""Business logic manager for entities."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from common.auth import actor_str
from common.enums import AuditMetadataType, ModuleStatus
from common.identifier_template import SEQ_TOKEN, TOKEN_RE, parse_tokens
from common.logger import logger
from common.protocols import (
    MASKED_FIELD_VALUE,
    EntityConditionSpec,
    EntityReadPolicy,
    RolesServiceProtocol,
    record_satisfies_any_condition,
    resolve_and_compare,
)
from exceptions import (
    AuthorizationError,
    ConflictError,
    ModularError,
    NotFoundError,
    PersistenceError,
    ServiceError,
    ValidationError,
)
from audit.models.interface import AuditEventInput
from forms.db_models import active_schema_fields, active_schema_fields_by_type_id
from user.models.interface import OrgMembershipVerdict

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from common.protocols import BackgroundTaskScheduler
    from entities.db_models import EntitiesModelService  # noqa: F401
    from audit.manager import AuditServiceManager
    from user.manager import UserServiceManager

from entities.models.interface import (
    DISPLAY_NAME_FIELD_KEYS,
    DOCUMENT_FIELD_TYPE,
    ENTITY_RECORDS_BY_TYPE_NAME_LIMIT_MAX,
    ENTITY_RECORDS_BY_TYPE_NAME_PREFILTER_CAP,
    EXTENSION_FIELDS_KEY,
    EXTENSIONS_KEY,
    IDENTIFIER_ERROR_MESSAGE_MAX,
    IDENTIFIER_FIELD_KEY,
    IDENTIFIER_LABEL_MAX,
    IDENTIFIER_TEMPLATE_MAX,
    ORIGINATOR_NOT_A_MEMBER_MESSAGE,
    ORIGINATOR_NOT_FOUND_MESSAGE,
    ORIGINATOR_USER_MISSING_MESSAGE,
    ActorType,
    AssignmentAuditKey,
    AssignmentRejection,
    AssignmentMode,
    AssignmentSource,
    AuditEventSource,
    EntityAuditEventType,
    EntityRecord,
    EntityRelation,
    EntityStateRecord,
    EntityType,
    EntityTypeRelation,
    FieldDefinition,
    FormConfigContract,
    IdentifierAllowedFieldType,
    RelationType,
    local_field_name,
    originator_inactive_account_message,
    originator_suspended_message,
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
from entities.models.response import (
    EntityRecordListResponse,
    EntityRecordResponse,
    EntityRecordSummaryPage,
    EntityRecordSummaryResponse,
    EntityRelationListResponse,
    EntityRelationResponse,
    EntityStateListResponse,
    EntityStateResponse,
    EntityTypeRecordListResponse,
    EntityTypeRecordResponse,
    EntityTypeRelationDeleteResponse,
    EntityTypeRelationListResponse,
    EntityTypeRelationResponse,
    EntityWithStatesResponse,
    FormConfigResponse,
    InheritedFieldResponse,
    MetadataRegistryStatusResponse,
    RelatedEntityFileListResponse,
)
from entities.services import (
    InheritedFieldPermissionsService,
    InheritedFieldSource,
    RelationshipsService,
)


class EntitiesServiceManager:
    """Metadata registry orchestration service."""

    def __init__(
        self,
        entities_db_model_service,
        database_service_manager,
        config,
        auth_service_manager=None,
        *dependencies,
        roles_manager: RolesServiceProtocol | None = None,
        audit_service_manager: AuditServiceManager | None = None,
        notifications_service_manager=None,
        user_service_manager: UserServiceManager | None = None,
    ) -> None:
        """Wire the manager to its DB service, config, and auth hooks."""
        self.db_model_service = entities_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.module_name = "entities"
        self._started = False
        self.auth_service_manager = auth_service_manager or self._resolve_identity_service(
            dependencies
        )
        self.roles_manager = roles_manager
        self.audit_service_manager = audit_service_manager
        self.notifications_service_manager = notifications_service_manager
        self.user_service_manager = user_service_manager
        self.filehandler_service_manager = None
        self.custom_forms_service_manager = None
        self.relationships_service = RelationshipsService(self)
        self.inherited_field_permissions = InheritedFieldPermissionsService(self)

    def start(self) -> None:
        """Mark the manager as started; called once during app boot."""
        self._started = True
        if self.user_service_manager is None:
            logger.warning(
                "EntitiesServiceManager started without user_service_manager — "
                "entity audit events will not capture actor_name or actor_role"
            )

    def stop(self) -> None:
        """Idempotent shutdown hook (no-op for in-process state)."""
        self._started = False

    def get_status(self) -> MetadataRegistryStatusResponse:
        """Return module status used by the /status endpoints."""
        return MetadataRegistryStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def upsert_form_config(
        self,
        request: UpsertFormConfigRequest | dict[str, object],
    ) -> FormConfigResponse:
        """Persist a form config (system-trusted call, no auth check)."""
        try:
            config_request = (
                request
                if isinstance(request, UpsertFormConfigRequest)
                else UpsertFormConfigRequest.from_dict(request)
            )
            record = self.db_model_service.upsert_form_config(config_request)
            return FormConfigResponse(
                organization_id=record.organization_id,
                form_key=record.form_key,
                field_count=len(record.fields),
                version=record.version,
            )
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            logger.debug("upsert_form_config ValueError: %s", exc)
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            logger.debug("upsert_form_config failed: %s", exc)
            raise ServiceError(f"Unable to upsert form config: {exc}") from exc

    def get_form_config(self, organization_id: str, form_key: str) -> FormConfigResponse | None:
        """Look up a form config by `(organization_id, form_key)`."""
        try:
            record = self.db_model_service.get_form_config(
                organization_id=organization_id, form_key=form_key
            )
            if record is None:
                return None
            return FormConfigResponse(
                organization_id=record.organization_id,
                form_key=record.form_key,
                field_count=len(record.fields),
                version=record.version,
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            logger.debug("get_form_config ValueError: %s", exc)
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            logger.debug("get_form_config failed: %s", exc)
            raise ServiceError(f"Unable to fetch form config: {exc}") from exc

    def get_form_config_definition(
        self, organization_id: str, form_key: str
    ) -> FormConfigContract | None:
        """Return the merged field definitions for an entity type's forms.

        Backs the ``get_form_schema`` tool so agents can discover the exact
        field *keys* an entity's ``data`` is stored under. ``form_key`` is the
        entity type *name* (e.g. ``project_task``); fields are merged across all
        active linked form schemas for that type and de-duplicated by key.
        Returns ``None`` when the entity type has no configured form fields.

        Unlike :meth:`get_form_config` (which returns a summary
        ``FormConfigResponse`` with only a field *count*), this exposes the full
        field list, which is what the tool consumer needs.
        """
        raw_fields = self._active_schema_fields_for_type_name(organization_id, form_key)
        fields: list[FieldDefinition] = []
        seen: set[str] = set()
        for field in raw_fields:
            key = field.get("field") or field.get("name") or field.get("id")
            if not key or str(key) in seen:
                continue
            seen.add(str(key))
            options = field.get("enum_values")
            # `model_construct` bypasses the frozen-model validator (its
            # after-validator mutates `self`, which the normal constructor
            # rejects); values are already normalized here.
            fields.append(
                FieldDefinition.model_construct(
                    name=str(key),
                    field_type=str(field.get("type") or "string"),
                    required=bool(field.get("required", False)),
                    options=tuple(str(o) for o in options)
                    if isinstance(options, (list, tuple))
                    else (),
                )
            )
        if not fields:
            return None
        return FormConfigContract.model_construct(
            organization_id=organization_id,
            form_key=form_key,
            fields=fields,
            version=1,
        )

    def get_form_fields(self, organization_id: str, form_key: str) -> list[dict]:
        """Return the merged **raw** form-field dicts for an entity type.

        ``form_key`` is the entity type *name*; fields are merged across all active
        linked form schemas for that type. Unlike :meth:`get_form_config_definition`
        (which flattens each field into the minimal ``FieldDefinition`` and drops
        everything else), this returns the raw ``fields_json`` dicts untouched — so
        callers keep rich per-field metadata such as ``table_config`` (a Table/Grid
        field's columns/row-mode). Backs the ``get_form_schema`` tool.
        """
        return self._active_schema_fields_for_type_name(organization_id, form_key)

    # ── Canonical entity type registry ───────────────────────────────────────

    def create_entity_type(self, request: EntityTypeCreateRequest) -> EntityTypeRecordResponse:
        """System-level entity-type create; no actor authorization."""
        try:
            self._validate_and_normalize_identifier_config(
                organization_id=request.organization_id or "",
                entity_type_name=request.name,
                schema_definition=request.schema_definition,
            )
            record = self.db_model_service.create_entity_type(request)
            return self._entity_type_record_response(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            logger.debug("create_entity_type ValueError: %s", exc)
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            logger.debug("create_entity_type failed: %s", exc)
            raise ServiceError(f"Unable to create entity type: {exc}") from exc

    def get_entity_type_name(self, *, organization_id: str, entity_type_id: str) -> str | None:
        """Resolve one entity type's display name from its id.

        Exists so a caller holding only an `entity_type_id` can resolve the name with a single
        indexed read, instead of listing every entity type in the organization and scanning.
        """
        return self.db_model_service.get_entity_type_name_by_id(
            organization_id=organization_id, entity_type_id=entity_type_id
        )

    def list_entity_states_for_entity(
        self, *, organization_id: str, entity_id: str, workflow_id: str | None = None
    ) -> list[EntityStateRecord]:
        """List every workflow enrollment for one entity, optionally narrowed to one workflow.

        Organization-scoped and not narrowed by any actor's permissions, so a caller resolving
        runtime facts sees all enrollments. Prefer `list_entity_states_for_actor` when answering
        a user request: that one hides workflows outside the actor's scope and returns response
        models rather than records.
        """
        return self.db_model_service.list_entity_states_for_entity(
            organization_id=organization_id, entity_id=entity_id, workflow_id=workflow_id
        )

    def get_entity_type_record(
        self, *, organization_id: str, name: str
    ) -> EntityTypeRecordResponse | None:
        """System-level fetch of an entity type by name."""
        try:
            record = self.db_model_service.get_entity_type_by_name(
                organization_id=organization_id, name=name
            )
            if record is None:
                return None
            return self._entity_type_record_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("get_entity_type_record failed: %s", exc)
            raise ServiceError(f"Unable to fetch entity type: {exc}") from exc

    def list_entity_type_records(
        self, *, organization_id: str, include_inactive: bool = True
    ) -> list[EntityTypeRecordResponse]:
        """System-level listing of entity types in an org.

        Includes inactive types by default so internal callers (e.g. the
        workflow manager's reverse-lookup) can resolve names for archived
        types. Pass include_inactive=False for actor-gated endpoints that
        should only surface active types to the UI."""
        try:
            records = self.db_model_service.list_entity_types_v2(
                organization_id=organization_id,
                include_inactive=include_inactive,
            )
            return [self._entity_type_record_response(record) for record in records]
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("list_entity_type_records failed: %s", exc)
            raise ServiceError(f"Unable to list entity types: {exc}") from exc

    def update_entity_type(
        self,
        *,
        organization_id: str,
        name: str,
        request: EntityTypeUpdateRequest,
    ) -> EntityTypeRecordResponse | None:
        """System-level update of an entity type by name."""
        try:
            if request.schema_definition is not None:
                # Rewrite template tokens for positional field renames BEFORE
                # persisting — afterwards the "old" record already holds the
                # new fields and renames are undetectable.
                self._rewrite_identifier_template_for_renames(
                    organization_id, name, request.schema_definition
                )
                self._validate_and_normalize_identifier_config(
                    organization_id=organization_id,
                    entity_type_name=request.name or name,
                    schema_definition=request.schema_definition,
                )
            record = self.db_model_service.update_entity_type_by_name(
                organization_id=organization_id,
                name=name,
                request=request,
            )
            if record is None:
                return None
            new_name = request.name
            if new_name is not None and new_name != name:
                with self.db_model_service._db_session() as db:
                    self.roles_manager.db_model_service.rename_entity_type_in_permissions(
                        db, organization_id, name, new_name
                    )
            # Cascade field renames within schema_definition
            if request.schema_definition is not None:
                self._cascade_field_renames(organization_id, name, request.schema_definition)
            return self._entity_type_record_response(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            logger.debug("update_entity_type ValueError: %s", exc)
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            logger.debug("update_entity_type failed: %s", exc)
            raise ServiceError(f"Unable to update entity type: {exc}") from exc

    def _validate_and_normalize_identifier_config(
        self,
        *,
        organization_id: str,
        entity_type_name: str,
        schema_definition: dict | None,
    ) -> None:
        """Spec §7: label/template caps, ≥1 token, tokens resolve to allowed-type fields.

        Mutates ``schema_definition`` in place to store the trimmed label/message —
        the caps are measured on the stripped value, so persisting the raw one would
        let padding smuggle past them.
        """
        if not schema_definition:
            return
        for key, cap in (
            ("identifier_label", IDENTIFIER_LABEL_MAX),
            ("identifier_error_message", IDENTIFIER_ERROR_MESSAGE_MAX),
        ):
            raw_value = schema_definition.get(key)
            if raw_value is None:
                continue
            trimmed = str(raw_value).strip()
            if len(trimmed) > cap:
                raise ValidationError(f"{key} must be at most {cap} characters")
            schema_definition[key] = trimmed
        raw = schema_definition.get("identifier_template")
        template = str(raw).strip() if raw is not None else ""
        if not template:
            return
        if len(template) > IDENTIFIER_TEMPLATE_MAX:
            raise ValidationError(
                f"identifier_template must be at most {IDENTIFIER_TEMPLATE_MAX} characters"
            )
        tokens = parse_tokens(template)
        if not tokens:
            raise ValidationError(
                "identifier_template must contain at least one {{field}} or {{seq}} token"
            )
        # Stray braces outside well-formed tokens are always a typo —
        # `{client_identifier}}` would render literally into every identifier.
        residue = TOKEN_RE.sub("", template)
        if "{" in residue or "}" in residue:
            raise ValidationError(
                "identifier_template has malformed {{ }} braces — every token must "
                "look like {{field_name}}"
            )
        field_tokens = [t for t in tokens if t != SEQ_TOKEN]
        if not field_tokens:
            return
        known: dict[str, str] = {}
        for field in schema_definition.get("fields") or []:
            fid = field.get("field") or field.get("name") or field.get("id")
            if fid:
                known[str(fid).lower()] = str(field.get("type", "")).lower()
        for field in self._active_schema_fields_for_type_name(
            organization_id, entity_type_name
        ):
            fid = field.get("field") or field.get("name") or field.get("id")
            if fid:
                known.setdefault(str(fid).lower(), str(field.get("type", "")).lower())
        bad = [
            t
            for t in field_tokens
            if t not in known or known[t] not in IdentifierAllowedFieldType.list()
        ]
        if bad:
            # `<related_type>_identifier` tokens are valid via relation
            # declarations alone — no form field required.
            relation_tokens = self.db_model_service.related_identifier_tokens(
                organization_id, entity_type_name
            )
            bad = [t for t in bad if t not in relation_tokens]
        if bad:
            raise ValidationError(
                "identifier_template references unknown or unsupported fields: "
                + ", ".join(sorted(set(bad)))
            )

    def _active_schema_fields_for_type_name(
        self, organization_id: str, entity_type_name: str
    ) -> list[dict]:
        """Merged linked-form fields for a type name; empty on any failure."""
        try:
            with self.db_model_service._db_session() as db:
                return active_schema_fields(db, organization_id, entity_type_name) or []
        except Exception as exc:
            logger.debug("_active_schema_fields_for_type_name failed: %s", exc)
            return []

    def _rewrite_identifier_template_for_renames(
        self,
        organization_id: str,
        entity_type: str,
        new_schema: dict,
    ) -> None:
        """Positional field renames also rename their tokens inside
        identifier_template (spec §7 cascade) — keeps templates unbroken."""
        template = str(new_schema.get("identifier_template") or "")
        if not template:
            return
        old_record = self.db_model_service.get_entity_type_by_name(
            organization_id=organization_id, name=entity_type
        )
        if old_record is None:
            return

        def _ids(schema: dict | None) -> list[str]:
            ids: list[str] = []
            for field in (schema or {}).get("fields", []):
                fid = field.get("id") or field.get("field") or field.get("name", "")
                if fid:
                    ids.append(str(fid))
            return ids

        old_list = _ids(old_record.schema_definition)
        new_list = _ids(new_schema)
        # Positional pairing is only meaningful when nothing was inserted or
        # deleted, and a pair whose old id still exists in the new schema is a
        # reorder, not a rename. Substitute all renames in ONE pass — applying
        # them sequentially corrupts swaps ({{a}}-{{b}} → {{a}}-{{a}}).
        if len(old_list) != len(new_list):
            return
        new_ids = {f.lower() for f in new_list}
        renames = {
            old_f.lower(): new_f
            for old_f, new_f in zip(old_list, new_list)
            if old_f != new_f and old_f.lower() not in new_ids
        }
        if not renames:
            return
        new_schema["identifier_template"] = TOKEN_RE.sub(
            lambda m: "{{" + renames[m.group(1).lower()] + "}}"
            if m.group(1).lower() in renames
            else m.group(0),
            template,
        )

    def _cascade_field_renames(
        self,
        organization_id: str,
        entity_type: str,
        new_schema: dict,
    ) -> None:
        """Cascade field renames to field_permissions when schema_definition changes."""
        old_record = self.db_model_service.get_entity_type_by_name(
            organization_id=organization_id, name=entity_type
        )
        if old_record is None:
            return
        old_fields: dict[str, str] = {}
        for field in (old_record.schema_definition or {}).get("fields", []):
            fid = field.get("id") or field.get("field") or field.get("name", "")
            if fid:
                old_fields[fid] = fid
        new_fields: dict[str, str] = {}
        for field in (new_schema or {}).get("fields", []):
            fid = field.get("id") or field.get("field") or field.get("name", "")
            if fid:
                new_fields[fid] = fid
        # Detect renames: same position, different id (simple positional match)
        old_list = list(old_fields.keys())
        new_list = list(new_fields.keys())
        with self.db_model_service._db_session() as db:
            for old_f, new_f in zip(old_list, new_list):
                if old_f != new_f:
                    self.roles_manager.db_model_service.rename_field_in_permissions(
                        db, organization_id, entity_type, old_f, new_f
                    )

    def archive_entity_type(
        self,
        *,
        organization_id: str,
        name: str,
    ) -> EntityTypeRecordResponse | None:
        """System-level soft-delete (is_active=False) of an entity type."""
        try:
            record = self.db_model_service.archive_entity_type_by_name(
                organization_id=organization_id, name=name
            )
            if record is None:
                return None
            return self._entity_type_record_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("archive_entity_type failed: %s", exc)
            raise ServiceError(f"Unable to archive entity type: {exc}") from exc

    def create_entity_type_for_actor(
        self,
        actor: dict[str, object],
        request: EntityTypeCreateRequest,
    ) -> EntityTypeRecordResponse:
        """Authorized wrapper: create_entity_type behind actor RBAC check."""
        organization_id = request.organization_id or self._require_actor_field(
            actor, "organization_id"
        )
        self._authorize_actor_operation(actor, "metadata", "write", organization_id)
        normalized = EntityTypeCreateRequest(
            organization_id=organization_id,
            name=request.name,
            description=request.description,
            schema_definition=dict(request.schema_definition),
            version=request.version,
            is_active=request.is_active,
        )
        return self.create_entity_type(normalized)

    def get_entity_type_record_for_actor(
        self,
        actor: dict[str, object],
        name: str,
    ) -> EntityTypeRecordResponse:
        """Authorized wrapper: fetch entity type after RBAC check."""
        organization_id = self._require_actor_field(actor, "organization_id")
        record = self.get_entity_type_record(organization_id=organization_id, name=name)
        if record is None:
            raise NotFoundError(f"entity type '{name}' not found")
        return record

    def list_entity_type_records_for_actor(
        self,
        actor: dict[str, object],
    ) -> EntityTypeRecordListResponse:
        """Authorized wrapper: list entity types after RBAC check.
        Only active types are returned — inactive (archived) types are hidden
        from the UI so users can't select them for new records."""
        organization_id = self._require_actor_field(actor, "organization_id")
        items = self.list_entity_type_records(
            organization_id=organization_id, include_inactive=False
        )
        return EntityTypeRecordListResponse(organization_id=organization_id, items=items)

    def update_entity_type_for_actor(
        self,
        actor: dict[str, object],
        name: str,
        request: EntityTypeUpdateRequest,
    ) -> EntityTypeRecordResponse:
        """Authorized wrapper: update entity type after RBAC check."""
        organization_id = self._require_actor_field(actor, "organization_id")
        record = self.update_entity_type(
            organization_id=organization_id, name=name, request=request
        )
        if record is None:
            raise NotFoundError(f"entity type '{name}' not found")
        return record

    def archive_entity_type_for_actor(
        self,
        actor: dict[str, object],
        name: str,
    ) -> EntityTypeRecordResponse:
        """Authorized wrapper: archive entity type after RBAC check."""
        organization_id = self._require_actor_field(actor, "organization_id")
        record = self.archive_entity_type(organization_id=organization_id, name=name)
        if record is None:
            raise NotFoundError(f"entity type '{name}' not found")
        return record

    # ── EntityTypeRelation (relation definitions) ────────────────────────────

    def create_entity_type_relation_for_actor(
        self,
        actor: dict[str, object],
        request: EntityTypeRelationCreateRequest,
    ) -> EntityTypeRelationResponse:
        """Authorized wrapper: create an entity type relation definition."""
        organization_id = self._require_actor_field(actor, "organization_id")
        normalized = EntityTypeRelationCreateRequest(
            organization_id=organization_id,
            from_entity_type_id=request.from_entity_type_id,
            to_entity_type_id=request.to_entity_type_id,
            relation_name=request.relation_name,
        )
        try:
            record = self.db_model_service.create_entity_type_relation(normalized)
            return self._entity_type_relation_response(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("create_entity_type_relation_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to create entity type relation: {exc}") from exc

    def list_entity_type_relations_for_actor(
        self,
        actor: dict[str, object],
        from_entity_type_id: str | None = None,
    ) -> EntityTypeRelationListResponse:
        """Authorized wrapper: list entity type relation definitions."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            records = self.db_model_service.list_entity_type_relations(
                organization_id=organization_id,
                from_entity_type_id=from_entity_type_id,
            )
            items = [self._entity_type_relation_response(r) for r in records]
            # Best-effort: inherited-field computation must never break the core
            # relation listing, so a failure here degrades to an empty list.
            inherited: list[InheritedFieldResponse] = []
            if from_entity_type_id:
                try:
                    inherited = self._inherited_field_items(
                        organization_id=organization_id, entity_type_id=from_entity_type_id
                    )
                except Exception as exc:
                    logger.debug("inherited-field computation skipped: %s", exc)
            return EntityTypeRelationListResponse(
                organization_id=organization_id, items=items, inherited_fields=inherited
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("list_entity_type_relations_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to list entity type relations: {exc}") from exc

    def _inherited_field_items(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
    ) -> list[InheritedFieldResponse]:
        """Inherited fields available on an entity type, from declarations targeting it.

        Each declaration that imports fields also auto-exposes the linked parent's
        own id as `<parent_type>_id`, plus its explicitly mapped fields. These
        resolve into entity data at read time, so a connector on this type can use
        them as `$entity.<field>`. Deduped by field name (first declaration wins)."""
        declarations = self.db_model_service.get_active_relation_declarations_by_to_type(
            organization_id=organization_id, to_entity_type_id=entity_type_id
        )
        type_names = {
            record.entity_type_id: record.name
            for record in self.db_model_service.list_entity_types_v2(
                organization_id=organization_id
            )
        }
        items: list[InheritedFieldResponse] = []
        seen: set[str] = set()
        for declaration in declarations:
            mapping = {
                source_key: target_key
                for source_key, target_key in dict(declaration.relation_metadata or {}).items()
                if isinstance(source_key, str) and isinstance(target_key, str)
            }
            if not mapping:
                mapping = {}
            # Auto: the linked parent's own id, exposed as `<parent_type>_id`.
            parent_name = type_names.get(declaration.from_entity_type_id)
            candidate_fields = []
            if parent_name:
                candidate_fields.append(parent_id_field_name(parent_name))
            # Explicitly mapped inherited fields.
            candidate_fields.extend(local_field_name(target) for target in mapping.values())
            for field in candidate_fields:
                if field in seen:
                    continue
                seen.add(field)
                items.append(
                    InheritedFieldResponse(
                        field=field,
                        source_entity_type_id=declaration.from_entity_type_id,
                        relation_type=declaration.relation_type,
                    )
                )
        return items

    def delete_entity_type_relation_for_actor(
        self,
        actor: dict[str, object],
        relation_def_id: str,
    ) -> None:
        """Authorized wrapper: delete an entity type relation definition."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            deleted = self.db_model_service.delete_entity_type_relation(
                organization_id=organization_id, relation_def_id=relation_def_id
            )
            if not deleted:
                raise NotFoundError(f"entity type relation '{relation_def_id}' not found")
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("delete_entity_type_relation_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to delete entity type relation: {exc}") from exc

    # ── Relation declaration (field-inheritance) ─────────────────────────────

    def create_entity_relation_declaration_for_actor(
        self,
        actor: dict[str, object],
        request: EntityRelationDeclarationCreateRequest,
    ) -> EntityTypeRelationResponse:
        """Authorized wrapper: declare a field-inheritance relation between two entity types."""
        organization_id = request.organization_id or self._require_actor_field(
            actor, "organization_id"
        )
        self._authorize_actor_operation(actor, "metadata", "write", organization_id)
        normalized = EntityRelationDeclarationCreateRequest(
            organization_id=organization_id,
            from_entity_type_id=request.from_entity_type_id,
            to_entity_type_id=request.to_entity_type_id,
            relation_type=request.relation_type,
            relation_metadata=request.relation_metadata,
        )
        try:
            record = self.db_model_service.create_entity_relation_declaration(
                normalized,
                default_relation_type=self.config._configuration.entity_relations_configuration.default_relation_type,
            )
            return self._entity_type_relation_response(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("create_entity_relation_declaration_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to create relation declaration: {exc}") from exc

    def get_entity_relation_declaration_for_actor(
        self,
        actor: dict[str, object],
        from_entity_type_id: str,
        to_entity_type_id: str,
    ) -> EntityTypeRelationResponse:
        """Authorized wrapper: fetch the active declaration for a (from, to) type pair."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            record = self.db_model_service.get_active_relation_declaration_for_pair(
                organization_id=organization_id,
                from_entity_type_id=from_entity_type_id,
                to_entity_type_id=to_entity_type_id,
            )
            if record is None:
                raise NotFoundError(
                    f"no active relation declaration from '{from_entity_type_id}' "
                    f"to '{to_entity_type_id}'"
                )
            return self._entity_type_relation_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("get_entity_relation_declaration_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to fetch relation declaration: {exc}") from exc

    def update_entity_relation_declaration_for_actor(
        self,
        actor: dict[str, object],
        relation_def_id: str,
        request: EntityRelationDeclarationUpdateRequest,
    ) -> EntityTypeRelationResponse:
        """Authorized wrapper: update relation_metadata on an active declaration."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            record = self.db_model_service.update_entity_relation_declaration_metadata(
                organization_id=organization_id,
                relation_def_id=relation_def_id,
                request=request,
            )
            if record is None:
                raise NotFoundError(f"relation declaration '{relation_def_id}' not found")
            return self._entity_type_relation_response(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("update_entity_relation_declaration_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to update relation declaration: {exc}") from exc

    def delete_entity_relation_declaration_for_actor(
        self,
        actor: dict[str, object],
        relation_def_id: str,
    ) -> EntityTypeRelationDeleteResponse:
        """Authorized wrapper: soft-delete an active relation declaration."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            record = self.db_model_service.soft_delete_entity_relation_declaration(
                organization_id=organization_id, relation_def_id=relation_def_id
            )
            if record is None:
                raise NotFoundError(f"relation declaration '{relation_def_id}' not found")
            return EntityTypeRelationDeleteResponse(
                relation_def_id=record.relation_def_id, deleted_at=record.deleted_at
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("delete_entity_relation_declaration_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to delete relation declaration: {exc}") from exc

    def list_entity_relation_declarations_for_actor(
        self,
        actor: dict[str, object],
        entity_type_id: str,
        direction: str = "from",
    ) -> EntityTypeRelationListResponse:
        """Authorized wrapper: list active relation declarations involving a type."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            records = self.db_model_service.list_entity_relation_declarations(
                organization_id=organization_id,
                entity_type_id=entity_type_id,
                direction=direction,
            )
            items = [self._entity_type_relation_response(r) for r in records]
            return EntityTypeRelationListResponse(organization_id=organization_id, items=items)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("list_entity_relation_declarations_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to list relation declarations: {exc}") from exc

    def toggle_entity_type_for_actor(
        self,
        actor: dict[str, object],
        entity_type_id: str,
    ) -> EntityTypeRecordResponse:
        """Authorized wrapper: flip is_active on an entity type after RBAC check."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            all_types = self.db_model_service.list_entity_types_v2(organization_id=organization_id)
            match = next((t for t in all_types if t.entity_type_id == entity_type_id), None)
            if match is None:
                raise NotFoundError(f"entity type '{entity_type_id}' not found")
            record = self.update_entity_type(
                organization_id=organization_id,
                name=match.name,
                request=EntityTypeUpdateRequest(is_active=not match.is_active),
            )
            if record is None:
                raise NotFoundError(f"entity type '{entity_type_id}' not found")
            return record
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("toggle_entity_type_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to toggle entity type: {exc}") from exc

    def get_auto_number_previews_for_actor(
        self,
        actor: dict[str, object],
        entity_type_name: str,
    ) -> dict[str, str]:
        """Return next formatted auto_number value per field for the given entity type."""
        organization_id = self._require_actor_field(actor, "organization_id")
        record = self.get_entity_type_record(organization_id=organization_id, name=entity_type_name)
        if record is None:
            raise NotFoundError(f"entity type '{entity_type_name}' not found")
        return self.db_model_service.get_auto_number_previews(
            organization_id=organization_id,
            entity_type_id=record.entity_type_id,
        )

    def get_identifier_template_for_actor(
        self,
        actor: dict[str, object],
        entity_type_id: str,
    ) -> str | None:
        """Return the entity type's configured identifier_template, or None (manual mode)."""
        organization_id = self._require_actor_field(actor, "organization_id")
        return self.db_model_service.get_identifier_template(organization_id, entity_type_id)

    def is_identifier_taken_for_actor(
        self,
        actor: dict[str, object],
        entity_type_id: str,
        identifier: str,
    ) -> bool:
        """Return whether a non-archived entity of this type already uses this identifier."""
        organization_id = self._require_actor_field(actor, "organization_id")
        return self.db_model_service.identifier_exists(organization_id, entity_type_id, identifier)

    # ── EntityRecord (runtime entity instances) ─────────────────────────────

    def _create_entity_record_raw(
        self,
        request: EntityRecordCreateRequest,
        *,
        require_reference_sources: bool = True,
    ) -> EntityRecord:
        """Persist a new entity record and its relations; returns the plain row,
        with no inherited-field composition applied.

        Shared by `create_entity_record` (system-level, wraps this with the old
        inherited-field composition) and `create_entity_record_for_actor` (which
        composes via `resolve_records_for_actor` instead — passing this raw row
        straight in avoids a second DB fetch for the same record).

        When `request.relations` is provided, each listed edge is created
        after the entity row commits. Relation failures are best-effort —
        the entity is returned regardless so callers can still use it.

        `require_reference_sources=False` lets agent/document-driven creation
        skip the required-REFERENCE-source check (the new record has no provider
        record yet); it is a manager argument, never a wire-payload field, so the
        public create endpoint can't be used to bypass required links.
        """
        try:
            # Tenant-isolation gate: refuse if the referenced entity_type
            # belongs to a different org. Backstops the composite FK with a
            # clean 400 instead of an opaque IntegrityError.
            if not self.db_model_service.entity_type_exists_in_org(
                organization_id=request.organization_id,
                entity_type_id=request.entity_type_id,
            ):
                raise ValidationError(
                    f"entity_type '{request.entity_type_id}' not found in organization "
                    f"'{request.organization_id}'"
                )

            request = self._recompute_calc_fields_for_create(request)
            unowned_document_file_ids = self._validate_document_field_values(
                organization_id=request.organization_id,
                entity_type_id=request.entity_type_id,
                data=request.data,
            )
            record = self.db_model_service.create_entity_record(
                request, require_reference_sources=require_reference_sources
            )
            self._attach_unowned_document_files(
                organization_id=request.organization_id,
                entity_id=record.entity_id,
                file_ids=unowned_document_file_ids,
            )
            self.relationships_service.copy_snapshot_files_for_entity(
                organization_id=request.organization_id,
                target_entity_id=record.entity_id,
                actor_id=request.owner_id or "system",
            )

            if request.relations:
                for rel in request.relations:
                    try:
                        rel_request = EntityRelationCreateRequest(
                            organization_id=request.organization_id,
                            from_entity_id=record.entity_id,
                            to_entity_id=rel.to_entity_id,
                            relation_type=rel.relation_type,
                            relation_metadata=rel.relation_metadata,
                        )
                        created_relation = self.db_model_service.create_entity_relation(rel_request)
                        self.relationships_service.copy_snapshot_files_for_relation(
                            organization_id=request.organization_id,
                            actor_id=request.owner_id or "system",
                            from_entity_id=created_relation.from_entity_id,
                            to_entity_id=created_relation.to_entity_id,
                            relation_type=created_relation.relation_type,
                        )
                    except Exception:
                        # best-effort: entity is already persisted; a failed relation edge is non-fatal
                        logger.debug(
                            "relation creation failed for entity %s (best-effort, non-fatal)",
                            record.entity_id,
                            exc_info=True,
                        )

            return record
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except ValueError as exc:
            logger.debug("create_entity_record ValueError: %s", exc)
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            logger.debug("create_entity_record failed: %s", exc)
            raise ServiceError(f"Unable to create entity record: {exc}") from exc

    def create_entity_record(
        self,
        request: EntityRecordCreateRequest,
        *,
        require_reference_sources: bool = True,
    ) -> EntityRecordResponse:
        """System-level entity record creation; no actor authorization."""
        record = self._create_entity_record_raw(
            request, require_reference_sources=require_reference_sources
        )
        return self._entity_record_response_with_inherited(record)

    def _recompute_calc_fields_for_create(
        self, request: EntityRecordCreateRequest
    ) -> EntityRecordCreateRequest:
        fields = self._schema_field_dicts_by_type_id(
            request.organization_id, request.entity_type_id
        )
        if not fields:
            return request
        from calc.apply import apply_calculations

        new_data = apply_calculations(fields, dict(request.data or {}))
        return request.model_copy(update={"data": new_data})

    def _schema_field_dicts_by_type_id(
        self, organization_id: str, entity_type_id: str
    ) -> list[dict]:
        """Raw active schema-field dicts (carry type/table_config/calc)."""
        try:
            with self.db_model_service._db_session() as db:
                return active_schema_fields_by_type_id(db, organization_id, entity_type_id) or []
        except Exception as exc:  # never block a write on calc-schema lookup failure
            logger.debug("_schema_field_dicts_by_type_id failed: %s", exc)
            return []

    def _document_schema_fields_by_type_id(
        self, organization_id: str, entity_type_id: str
    ) -> list[dict]:
        """Read schema fields without the fail-open behavior used by calculations.

        Falls back to the active workflow's published entity_schema, which is
        where a type with no Forms rows keeps its fields. Both sources raise
        rather than return [] on failure, so a broken read can never be mistaken
        for a type that declares no document fields.
        """
        try:
            with self.db_model_service._db_session() as db:
                fields = active_schema_fields_by_type_id(
                    db, organization_id, entity_type_id
                ) or []
            if fields:
                return fields
            return self.db_model_service.active_workflow_schema_fields(
                organization_id, entity_type_id
            )
        except Exception as exc:
            logger.warning("document schema lookup failed: %s", exc)
            raise ServiceError("Unable to validate document fields") from exc

    def _validate_document_field_values(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        data: dict[str, Any] | None,
    ) -> list[str]:
        """Validate document references and return the unowned files they claim.

        A document field can upload its files before its new record has an id.
        Those files are valid but initially unowned, so the create/update caller
        attaches only that subset after the record is safely persisted. Existing
        file ownership is never overwritten merely because a field references it.
        """
        if not data:
            return []
        schema_fields = self._document_schema_fields_by_type_id(organization_id, entity_type_id)
        unowned_file_ids: list[str] = []
        document_fields = {
            str(field.get("field") or field.get("id") or field.get("name") or "").strip()
            for field in schema_fields
            if str(field.get("type") or "").strip().lower() == DOCUMENT_FIELD_TYPE
        }
        for field_key in sorted(document_fields & data.keys()):
            value = data[field_key]
            if value is None or value == "":
                continue
            file_ids = self._document_file_ids(field_key, value)
            unowned_file_ids.extend(
                self._unowned_document_files(organization_id, field_key, file_ids)
            )
            data[field_key] = file_ids
        unowned_file_ids.extend(
            self._validate_extension_document_values(organization_id, schema_fields, data)
        )
        return unowned_file_ids

    def _document_file_ids(self, field_key: str, value: Any) -> list[str]:
        """One document field's value as a list of trimmed file ids."""
        if not isinstance(value, list):
            logger.warning("document field '%s' does not hold a list", field_key)
            raise ValidationError(f"document field '{field_key}' must hold a list of file ids")
        file_ids: list[str] = []
        for file_id in value:
            if not isinstance(file_id, str) or not file_id.strip():
                logger.warning("document field '%s' has an invalid file id", field_key)
                raise ValidationError(f"document field '{field_key}' has an invalid file id")
            file_ids.append(file_id.strip())
        duplicates = sorted({file_id for file_id in file_ids if file_ids.count(file_id) > 1})
        if duplicates:
            logger.warning("document field '%s' lists a file twice", field_key)
            raise ValidationError(
                f"document field '{field_key}' lists the same file twice: " + ", ".join(duplicates)
            )
        return file_ids

    def _unowned_document_files(
        self, organization_id: str, field_key: str, file_ids: list[str]
    ) -> list[str]:
        """The subset of these files no record owns yet."""
        if self.filehandler_service_manager is None:
            logger.warning("document validation ran with no filehandler service")
            raise ServiceError("document validation service is not configured")
        unowned: list[str] = []
        for file_id in file_ids:
            try:
                file_record = self.filehandler_service_manager.get_file(organization_id, file_id)
            except NotFoundError as exc:
                logger.warning("document field '%s' references missing file %s", field_key, file_id)
                raise ValidationError(
                    f"document field '{field_key}' references file '{file_id}' "
                    "that does not exist in this organization"
                ) from exc
            if not getattr(file_record, "owner_entity_id", None):
                unowned.append(file_id)
        return unowned

    def _validate_extension_document_values(
        self,
        organization_id: str,
        schema_fields: list[dict],
        data: dict[str, Any],
    ) -> list[str]:
        """Validate document fields nested in a picklist_multi option's extensions.

        Only options still present in the config are visited, matching what the
        form renders. Values under an option since removed or renamed are left
        untouched rather than pruned: the field specs that say which of them are
        file ids are gone with the option, and dropping a user's answers because
        an administrator renamed something is worse than leaving them. Their
        files therefore stay unclaimed.
        """
        unowned: list[str] = []
        for field in schema_fields:
            extensions = field.get(EXTENSIONS_KEY)
            if not isinstance(extensions, dict):
                continue
            field_key = str(
                field.get("field") or field.get("id") or field.get("name") or ""
            ).strip()
            rows = data.get(field_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                by_option = row.get(EXTENSIONS_KEY)
                if not isinstance(by_option, dict):
                    continue
                for option, entry in extensions.items():
                    values = by_option.get(option)
                    if not isinstance(values, dict) or not isinstance(entry, dict):
                        continue
                    unowned.extend(
                        self._read_option_document_values(
                            organization_id, field_key, option, entry, values
                        )
                    )
        return unowned

    def _read_option_document_values(
        self,
        organization_id: str,
        field_key: str,
        option: str,
        entry: dict,
        values: dict[str, Any],
    ) -> list[str]:
        """Validate one option's document extension fields in place."""
        unowned: list[str] = []
        for spec in entry.get(EXTENSION_FIELDS_KEY) or []:
            if not isinstance(spec, dict):
                continue
            if str(spec.get("type") or "").strip().lower() != DOCUMENT_FIELD_TYPE:
                continue
            spec_key = str(spec.get("id") or "").strip()
            value = values.get(spec_key)
            if not spec_key or value is None or value == "":
                continue
            nested_key = f"{field_key}.{option}.{spec_key}"
            file_ids = self._document_file_ids(nested_key, value)
            unowned.extend(self._unowned_document_files(organization_id, nested_key, file_ids))
            values[spec_key] = file_ids
        return unowned

    def _attach_unowned_document_files(
        self,
        *,
        organization_id: str,
        entity_id: str,
        file_ids: list[str],
    ) -> None:
        """Claim files uploaded through document fields before a record existed.

        Entity previews intentionally query the file list by ``owner_entity_id``.
        Without this handoff, a file uploaded in the create form remains invisible
        to the pipeline card despite being stored on the record as a document
        field value. Attachment is best-effort because the entity is already
        committed; a transient filehandler failure must not report a failed
        record creation and tempt the user to create a duplicate record.
        """
        if not file_ids or self.filehandler_service_manager is None:
            return
        file_db = getattr(self.filehandler_service_manager, "db_model_service", None)
        if file_db is None:
            logger.warning(
                "document files for entity %s could not be attached: filehandler storage unavailable",
                entity_id,
            )
            return
        for file_id in dict.fromkeys(file_ids):
            try:
                file_db.set_file_owner(organization_id, file_id, entity_id)
            except Exception:
                logger.warning(
                    "document field file %s could not be attached to entity %s",
                    file_id,
                    entity_id,
                    exc_info=True,
                )

    def _reject_reference_field_writes(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        payload_keys: set[str],
        entity_id: str | None = None,
    ) -> None:
        """Raise 403 if the payload writes any REFERENCE-declared inherited field.
        All-or-nothing: the entire request is rejected, no partial writes.

        With `entity_id`, fields that a method block pins as
        `ownership='inherited'` on a workflow this record is enrolled in are
        refused too. Without it (create path: nothing is enrolled yet) only the
        type-wide relation_metadata targets apply, exactly as before."""
        if not payload_keys:
            return
        declarations = self.db_model_service.get_active_relation_declarations_by_to_type(
            organization_id=organization_id, to_entity_type_id=entity_type_id
        )
        reference_target_fields = {
            local_field_name(target_key)
            for declaration in declarations
            if declaration.relation_type == RelationType.REFERENCE
            for target_key in declaration.relation_metadata.values()
            if isinstance(target_key, str)
        }
        if entity_id:
            reference_target_fields |= (
                self.db_model_service.pinned_inherited_field_names_for_record(
                    organization_id=organization_id, entity_id=entity_id
                )
            )
        offending = sorted(payload_keys & reference_target_fields)
        if offending:
            fields = ", ".join(offending)
            raise AuthorizationError(
                f"{fields} is an inherited field. Update it on the linked record instead."
            )

    def _reject_read_only_field_writes(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        payload_keys: set[str],
    ) -> None:
        """Reject client writes to fields explicitly locked by an administrator.

        This is intentionally separate from ``editable``: inherited and
        calculated fields retain their existing engine-controlled behaviour,
        while ``read_only`` is an administrator's value-level lock.

        Both sources are read and unioned rather than Forms-first: a type with
        no Forms row keeps its fields on the published workflow, and a hybrid
        type keeps Method-only fields there while its Forms row covers the
        rest. A lock the client can see has to hold here for either shape.
        Failure raises rather than returning empty, so a broken read can never
        be mistaken for "nothing is locked".
        """
        if not payload_keys:
            return
        try:
            with self.db_model_service._db_session() as db:
                form_fields = (
                    active_schema_fields_by_type_id(db, organization_id, entity_type_id) or []
                )
            workflow_fields = self.db_model_service.active_workflow_schema_fields(
                organization_id, entity_type_id
            )
        except Exception as exc:
            logger.warning("read-only field lookup failed: %s", exc)
            raise ServiceError("Unable to validate read-only fields") from exc
        read_only = {
            str(field.get("field") or field.get("id") or field.get("name"))
            for field in [*form_fields, *workflow_fields]
            if field.get("read_only") is True
        }
        offending = sorted(payload_keys & read_only)
        if offending:
            raise AuthorizationError(f"Not allowed to edit read-only fields: {', '.join(offending)}")

    def _resolve_inherited_fields(
        self,
        organization_id: str,
        entity_type_id: str,
        entity_id: str,
    ) -> dict[str, object]:
        """Delegate inherited field resolution to the DB model service."""
        return self.db_model_service.resolve_inherited_fields(
            organization_id=organization_id,
            entity_type_id=entity_type_id,
            entity_id=entity_id,
        )

    def _compose_entity_response_data(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        entity_id: str,
        data: dict[str, object],
    ) -> dict[str, object]:
        """Return entity data with stale inherited keys removed and live values overlaid."""
        sanitized = self.db_model_service.strip_inherited_fields(
            organization_id=organization_id,
            entity_type_id=entity_type_id,
            data=data,
        )
        inherited = self._resolve_inherited_fields(
            organization_id=organization_id,
            entity_type_id=entity_type_id,
            entity_id=entity_id,
        )
        if inherited:
            return {**sanitized, **inherited}
        return sanitized

    def _entity_record_response_with_inherited(self, record) -> EntityRecordResponse:
        """Hydrate an entity response with inherited fields resolved server-side."""
        response = self._entity_record_response(record)
        response.data = self._compose_entity_response_data(
            organization_id=record.organization_id,
            entity_type_id=record.entity_type_id,
            entity_id=record.entity_id,
            data=record.data,
        )
        return response

    def get_entity_record(
        self, *, organization_id: str, entity_id: str, include_archived: bool = False
    ) -> EntityRecordResponse | None:
        """System-level entity record fetch (org-scoped)."""
        try:
            record = self.db_model_service.get_entity_record_by_id(
                organization_id=organization_id,
                entity_id=entity_id,
                include_archived=include_archived,
            )
            if record is None:
                return None
            return self._entity_record_response_with_inherited(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("get_entity_record failed: %s", exc)
            raise ServiceError(f"Unable to fetch entity record: {exc}") from exc

    def list_entity_records(
        self,
        *,
        organization_id: str,
        entity_type_id: str | None = None,
        include_archived: bool = False,
    ) -> list[EntityRecordResponse]:
        """System-level entity record listing (org-scoped)."""
        try:
            records = self.db_model_service.list_entity_records(
                organization_id=organization_id,
                entity_type_id=entity_type_id,
                include_archived=include_archived,
            )
            return [self._entity_record_response_with_inherited(record) for record in records]
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("list_entity_records failed: %s", exc)
            raise ServiceError(f"Unable to list entity records: {exc}") from exc

    def list_entity_records_by_ids(
        self,
        *,
        organization_id: str,
        entity_ids: set[str],
        include_archived: bool = False,
    ) -> list[EntityRecordResponse]:
        """System-level entity record listing by id set (org-scoped)."""
        try:
            records = self.db_model_service.list_entity_records_by_ids(
                organization_id=organization_id,
                entity_ids=entity_ids,
                include_archived=include_archived,
            )
            return [self._entity_record_response_with_inherited(record) for record in records]
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("list_entity_records_by_ids failed: %s", exc)
            raise ServiceError(f"Unable to list entity records by ids: {exc}") from exc

    def global_filter_entity_ids(
        self,
        *,
        actor: dict[str, object],
        organization_id: str,
        anchor_entity_id: str | None,
        include_archived: bool = False,
    ) -> set[str] | None:
        """Return the selected entity plus directly related runtime entities."""
        if not anchor_entity_id:
            return None

        anchor = self.get_entity_record(
            organization_id=organization_id,
            entity_id=anchor_entity_id,
            include_archived=include_archived,
        )
        if anchor is None:
            raise NotFoundError(f"anchor entity '{anchor_entity_id}' was not found")

        self.guard_read(actor, organization_id, anchor.entity_type_id, anchor)

        entity_ids = {anchor.entity_id}
        relations = self.db_model_service.list_entity_relations_for_entity(
            organization_id=organization_id,
            entity_id=anchor.entity_id,
            direction="both",
        )
        for relation in relations:
            entity_ids.add(relation.from_entity_id)
            entity_ids.add(relation.to_entity_id)
        return entity_ids

    def update_entity_record(
        self,
        *,
        organization_id: str,
        entity_id: str,
        request: EntityRecordUpdateRequest,
    ) -> EntityRecordResponse | None:
        """System-level entity record update (org-scoped)."""
        try:
            request = self._recompute_calc_fields_for_update(
                organization_id=organization_id, entity_id=entity_id, request=request
            )
            if request.data is not None:
                existing = self.db_model_service.get_entity_record_by_id(
                    organization_id=organization_id, entity_id=entity_id
                )
                if existing is not None:
                    unowned_document_file_ids = self._validate_document_field_values(
                        organization_id=organization_id,
                        entity_type_id=existing.entity_type_id,
                        data=request.data,
                    )
                else:
                    unowned_document_file_ids = []
            else:
                unowned_document_file_ids = []
            record = self.db_model_service.update_entity_record(
                organization_id=organization_id,
                entity_id=entity_id,
                request=request,
            )
            if record is None:
                return None
            self._attach_unowned_document_files(
                organization_id=organization_id,
                entity_id=record.entity_id,
                file_ids=unowned_document_file_ids,
            )
            return self._entity_record_response_with_inherited(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError) as exc:
            logger.warning(
                "update_entity_record failed: %s",
                exc,
                extra={"organization_id": organization_id, "entity_id": entity_id},
            )
            raise
        except ValueError as exc:
            logger.warning(
                "update_entity_record failed: %s",
                exc,
                extra={"organization_id": organization_id, "entity_id": entity_id},
            )
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            logger.warning(
                "update_entity_record failed: %s",
                exc,
                extra={"organization_id": organization_id, "entity_id": entity_id},
            )
            raise ServiceError(f"Unable to update entity record: {exc}") from exc

    def append_to_list_field(
        self, *, organization_id: str, entity_id: str, field_key: str, value: str
    ) -> EntityRecordResponse | None:
        """System-level, race-free append onto a list-valued data field.

        Used by documents' upload flow to attach a new document id without a
        concurrent upload or edit silently clobbering it (see
        append_to_data_list_field). Deliberately narrower than
        update_entity_record: no calc-field recompute or snapshot handling,
        since a document attach never feeds either.
        """
        try:
            record = self.db_model_service.append_to_data_list_field(
                organization_id=organization_id,
                entity_id=entity_id,
                field_key=field_key,
                value=value,
            )
            if record is None:
                return None
            return self._entity_record_response_with_inherited(record)
        except (ValidationError, NotFoundError):
            raise
        except Exception as exc:
            logger.warning(
                "append_to_list_field failed: %s",
                exc,
                extra={"organization_id": organization_id, "entity_id": entity_id},
            )
            raise ServiceError(f"Unable to append to entity field: {exc}") from exc

    def _recompute_calc_fields_for_update(
        self,
        *,
        organization_id: str,
        entity_id: str,
        request: EntityRecordUpdateRequest,
    ) -> EntityRecordUpdateRequest:
        if request.data is None:
            return request
        # ponytail: plan called this `get_entity_record`, but the real accessor
        # on db_model_service (entities/db_models.py) is `get_entity_record_by_id`,
        # returning `EntityRecord` (entities/models/interface.py) with
        # `.entity_type_id` / `.data` attributes — verified by reading both files.
        existing = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        if existing is None:
            return request
        fields = self._schema_field_dicts_by_type_id(
            organization_id, existing.entity_type_id
        )
        if not fields:
            return request
        from calc.apply import apply_calculations

        base = dict(existing.data or {})
        new_data = apply_calculations(fields, dict(request.data), base=base)
        return request.model_copy(update={"data": new_data})

    def update_entity_record_data(
        self, *, organization_id: str, entity_id: str, data: dict[str, Any]
    ) -> EntityRecordResponse | None:
        """System-level entity update from a plain data dict.

        Lets callers (e.g. the background worker) update an entity without importing or building
        the EntityRecordUpdateRequest contract themselves — the request stays encapsulated here.
        """
        return self.update_entity_record(
            organization_id=organization_id,
            entity_id=entity_id,
            request=EntityRecordUpdateRequest(data=data),
        )

    def archive_entity_record(
        self, *, organization_id: str, entity_id: str
    ) -> EntityRecordResponse | None:
        """System-level soft-archive of an entity record."""
        try:
            record = self.db_model_service.archive_entity_record(
                organization_id=organization_id, entity_id=entity_id
            )
            if record is None:
                return None
            return self._entity_record_response_with_inherited(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("archive_entity_record failed: %s", exc)
            raise ServiceError(f"Unable to archive entity record: {exc}") from exc

    def restore_entity_record(
        self,
        *,
        organization_id: str,
        entity_id: str,
        entity_type_id: str | None = None,
        data: dict | None = None,
        owner_id: str | None = None,
    ) -> EntityRecordResponse | None:
        """Internal: clear archived_at on a previously archived runtime entity.
        Caller (workflow manager) has already authorized the actor."""
        try:
            record = self.db_model_service.restore_entity_record(
                organization_id=organization_id,
                entity_id=entity_id,
                entity_type_id=entity_type_id,
                data=data,
                owner_id=owner_id,
            )
            if record is None:
                return None
            return self._entity_record_response_with_inherited(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("restore_entity_record failed: %s", exc)
            raise ServiceError(f"Unable to restore entity record: {exc}") from exc

    def get_entity_type_name_for_entity(
        self, organization_id: str, entity_id: str
    ) -> str | None:
        """Return the entity type display name for the given entity id, or None if not found."""
        try:
            record = self.db_model_service.get_entity_record_by_id(
                organization_id=organization_id, entity_id=entity_id
            )
            if record is None:
                return None
            return self.db_model_service.get_entity_type_name_by_id(
                organization_id=organization_id,
                entity_type_id=record.entity_type_id,
            )
        except NotFoundError:
            return None
        except PersistenceError as exc:
            logger.warning(
                "get_entity_type_name_for_entity: persistence failure for entity %s: %s",
                entity_id,
                exc,
                extra={"organization_id": organization_id, "entity_id": entity_id},
            )
            return None
        except Exception as exc:
            logger.warning(
                "get_entity_type_name_for_entity: unexpected failure for entity %s: %s",
                entity_id,
                exc,
            )
            return None

    def _validate_unique_identifier(
        self,
        *,
        organization_id: str,
        entity_type_id: str,
        data: dict[str, object] | None,
    ) -> None:
        """Require a non-empty identifier, unique within the entity type."""
        raw = (data or {}).get(IDENTIFIER_FIELD_KEY)
        identifier = str(raw).strip() if raw is not None else ""
        if not identifier:
            raise ValidationError("Identifier is required")

        if self.db_model_service.identifier_exists(
            organization_id, entity_type_id, identifier
        ):
            raise ValidationError(
                f"An entity with identifier '{identifier}' already exists"
            )

    def create_entity_record_for_actor(
        self,
        actor: dict[str, object],
        request: EntityRecordCreateRequest,
        *,
        require_reference_sources: bool = True,
    ) -> EntityRecordResponse:
        """Authorized wrapper: create entity record after RBAC check.

        `require_reference_sources=False` (used by the create_entity tool for
        agent/document-driven creation) skips the required-REFERENCE-source check.
        """
        organization_id = request.organization_id or self._require_actor_field(
            actor, "organization_id"
        )
        self._authorize_actor_operation(actor, "entity_record", "write", organization_id)
        self._reject_read_only_field_writes(
            organization_id=organization_id,
            entity_type_id=request.entity_type_id,
            payload_keys=set(request.data.keys()),
        )
        self.guard_write(
            actor,
            organization_id,
            request.entity_type_id,
            "create",
            set(request.data.keys()) if request.data else None,
        )
        # Template mode: the identifier is generated inside the create
        # transaction (db layer) — no manual value to pre-validate.
        if not self.db_model_service.get_identifier_template(
            organization_id, request.entity_type_id
        ):
            self._validate_unique_identifier(
                organization_id=organization_id,
                entity_type_id=request.entity_type_id,
                data=request.data,
            )
        normalized = EntityRecordCreateRequest(
            organization_id=organization_id,
            entity_id=request.entity_id,
            entity_type_id=request.entity_type_id,
            data=dict(request.data),
            owner_id=request.owner_id,
            assignee_id=request.assignee_id,
            due_date=request.due_date,
            relations=request.relations,
            source_entity_ids=request.source_entity_ids,
        )
        record = self._create_entity_record_raw(
            normalized, require_reference_sources=require_reference_sources
        )
        if request.custom_form_data:
            self._store_custom_form_answers_on_create(
                organization_id=organization_id,
                entity_id=record.entity_id,
                custom_form_data=request.custom_form_data,
            )
            # Best-effort write above; re-fetch so the response (and the audit
            # event below) reflect what actually landed rather than the
            # pre-merge row — same reasoning as update's own re-fetch.
            record = (
                self.db_model_service.get_entity_record_by_id(
                    organization_id=organization_id, entity_id=record.entity_id
                )
                or record
            )
        self._try_emit_audit_event(
            actor=actor,
            organization_id=organization_id,
            entity_id=record.entity_id,
            entity_type_id=record.entity_type_id,
            event_type=EntityAuditEventType.CREATED,
            payload={
                "identifier": str((record.data or {}).get(IDENTIFIER_FIELD_KEY) or ""),
                "owner_id": record.owner_id,
            },
        )
        # `record` is already the plain row — resolve_records_for_actor formats
        # the response exactly like a GET would, no second fetch needed.
        return self._resolve_single_record_or_deny(
            actor, organization_id, record, enforce_condition=False
        )

    def _resolve_single_record_or_deny(
        self,
        actor: dict[str, object],
        organization_id: str,
        record: EntityRecord,
        *,
        enforce_condition: bool,
    ) -> EntityRecordResponse:
        """Run `resolve_records_for_actor` for exactly one record and raise
        `AuthorizationError` if the actor is denied (an empty result). Shared by
        every endpoint that formats a single-record response after a fetch or a
        write — get-one, with-states, create, update, assignee, archive, restore."""
        results = self.inherited_field_permissions.resolve_records_for_actor(
            actor, organization_id, [record], enforce_condition=enforce_condition
        )
        if not results:
            logger.warning(
                "actor denied access to entity record",
                extra={
                    "organization_id": organization_id,
                    "entity_id": record.entity_id,
                    "entity_type_id": record.entity_type_id,
                },
            )
            raise AuthorizationError("You do not have permission to view this record.")
        return results[0]

    def get_entity_record_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        organization_id: str | None = None,
    ) -> EntityRecordResponse:
        """Authorized wrapper: fetch entity record after RBAC check.
        Defaults `organization_id` to the actor's org."""
        organization_id = organization_id or self._require_actor_field(actor, "organization_id")
        record = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        if record is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        allowed = self._resolve_single_record_or_deny(
            actor, organization_id, record, enforce_condition=True
        )
        return self.resolve_custom_forms(organization_id=organization_id, record=allowed)

    def list_entity_records_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str | None = None,
        entity_type_id: str | None = None,
        include_archived: bool = False,
    ) -> EntityRecordListResponse:
        """Authorized wrapper: list entity records after RBAC check.
        Defaults `organization_id` to the actor's org. `entity_type_id` is required —
        listing across every entity type in the org at once is not supported.
        Raises `NotFoundError` if no entity type with this id exists in the
        organization (mirrors `list_entity_records_by_type_name_for_actor`)."""
        organization_id = organization_id or self._require_actor_field(actor, "organization_id")
        if not entity_type_id:
            logger.warning(
                "list_entity_records_for_actor called without entity_type_id",
                extra={"organization_id": organization_id},
            )
            raise ValidationError("entity_type_id or entity_type_name is required")
        if not self.db_model_service.get_entity_type_name_by_id(
            organization_id=organization_id, entity_type_id=entity_type_id
        ):
            logger.warning(
                "list_entity_records_for_actor: entity type not found",
                extra={"organization_id": organization_id, "entity_type_id": entity_type_id},
            )
            raise NotFoundError(f"entity type '{entity_type_id}' not found in organization")
        records = self.db_model_service.list_entity_records(
            organization_id=organization_id,
            entity_type_id=entity_type_id,
            include_archived=include_archived,
        )
        items = self.inherited_field_permissions.resolve_records_for_actor(
            actor,
            organization_id,
            records,
            enforce_condition=True,
            raise_on_denied_target=True,
            known_target_type_ids={entity_type_id},
        )
        return EntityRecordListResponse(organization_id=organization_id, items=items)

    def resolve_read_policies(
        self,
        actor: dict[str, object],
        organization_id: str,
        type_names_by_id: dict[str, str],
    ) -> dict[str, EntityReadPolicy]:
        """Resolve one reusable read policy per entity type for a list page."""
        if actor.get("actor_type", "").lower() == "system":
            return {
                type_id: EntityReadPolicy([], None, set())
                for type_id in type_names_by_id
            }
        user_id = self._require_actor_field(actor, "user_id")
        compiled_resolver = getattr(self.roles_manager, "resolve_entity_read_policies", None)
        if callable(compiled_resolver):
            with self.db_model_service._db_session() as db:
                by_name = compiled_resolver(
                    db, user_id, organization_id, set(type_names_by_id.values())
                )
            return {
                type_id: by_name[type_name]
                for type_id, type_name in type_names_by_id.items()
                if type_name in by_name
            }
        policies: dict[str, EntityReadPolicy] = {}
        with self.db_model_service._db_session() as db:
            for type_id, type_name in type_names_by_id.items():
                try:
                    conditions = self._check_entity_permission(
                        db, actor, organization_id, type_name, "view"
                    )
                except AuthorizationError:
                    continue
                visible = self.roles_manager.get_visible_fields(
                    db, user_id, organization_id, type_name
                )
                masked = self.roles_manager.get_masked_fields(
                    db, user_id, organization_id, type_name
                )
                policies[type_id] = EntityReadPolicy(
                    conditions=list(conditions),
                    visible_fields=None if visible is None else set(visible),
                    masked_fields=set(masked),
                )
        return policies

    @staticmethod
    def apply_read_policy_to_data(
        policy: EntityReadPolicy,
        *,
        entity_id: str,
        data: dict[str, object],
        projected_fields: set[str] | None = None,
        exclude_from_target_check: set[str] | None = None,
        enforce_condition: bool = True,
    ) -> dict[str, object] | None:
        """Apply a pre-resolved policy without opening another DB session.

        `exclude_from_target_check` (optional, defaults to none excluded — existing
        callers such as `workflow/manager.py` are unaffected) lists field names
        whose visibility was already decided elsewhere (inherited fields, resolved
        against their real source entity type's own policy — see
        `InheritedFieldPermissionsService.apply_from_policies`) and must not be
        re-evaluated against this (target) policy's own `visible_fields`/
        `masked_fields`, which know nothing about where an inherited field really
        came from.

        `enforce_condition` (default `True`, preserves every existing caller's
        behavior): when `False`, skip the row-condition gate entirely — mirrors
        `guard_read`'s own flag of the same name/meaning, for a write formatting its
        own response, which must never be hidden by a read-only row condition."""
        if enforce_condition and not record_satisfies_any_condition(
            policy.conditions, data, entity_id=entity_id
        ):
            return None
        excluded = exclude_from_target_check or set()
        permitted = dict(data)
        if policy.visible_fields is not None:
            permitted = {
                key: value
                for key, value in permitted.items()
                if key == IDENTIFIER_FIELD_KEY or key in policy.visible_fields or key in excluded
            }
        if projected_fields is not None:
            permitted = {
                key: value
                for key, value in permitted.items()
                if key == IDENTIFIER_FIELD_KEY or key in projected_fields
            }
        for field in policy.masked_fields:
            if field != IDENTIFIER_FIELD_KEY and field in permitted and field not in excluded:
                permitted[field] = MASKED_FIELD_VALUE
        return permitted

    @staticmethod
    def summary_display_name(data: dict[str, object], entity_id: str) -> str:
        """Name a record for display, from the first of the display keys it actually has.

        Public because the workflow board renders the same name for its rows and must resolve it
        the same way; the order is the contract, so it lives in one place rather than in each.
        Takes already-projected data, so a field the actor cannot read cannot become the name.
        """
        for key in (IDENTIFIER_FIELD_KEY, *DISPLAY_NAME_FIELD_KEYS):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return f"Untitled {entity_id[:8]}"

    @staticmethod
    def _decode_summary_cursor(cursor: str | None, expected_scope: dict[str, object]) -> tuple[datetime | None, str | None]:
        if not cursor:
            return None, None
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
            if payload.get("scope") != expected_scope:
                raise ValidationError("Cursor does not match the active entity filters")
            return datetime.fromisoformat(payload["updated_at"]), str(payload["entity_id"])
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError("Invalid entity summary cursor") from exc

    @staticmethod
    def _encode_summary_cursor(updated_at: datetime | None, entity_id: str, scope: dict[str, object]) -> str | None:
        if updated_at is None:
            return None
        payload = json.dumps(
            {"updated_at": updated_at.isoformat(), "entity_id": entity_id, "scope": scope},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    def list_entity_record_summaries_for_actor(
        self,
        actor: dict[str, object],
        *,
        entity_type_id: str | None = None,
        entity_type_name: str | None = None,
        include_archived: bool = False,
        anchor_entity_id: str | None = None,
        fields: set[str] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> EntityRecordSummaryPage:
        """Return a bounded records-browser page without full record hydration."""
        organization_id = self._require_actor_field(actor, "organization_id")
        page_size = max(1, min(limit, 200))
        scope = {
            "entity_type_id": entity_type_id,
            "entity_type_name": entity_type_name,
            "include_archived": include_archived,
            "anchor_entity_id": anchor_entity_id,
            "fields": sorted(fields or []),
        }
        after_updated_at, after_entity_id = self._decode_summary_cursor(cursor, scope)
        allowed_ids = self.global_filter_entity_ids(
            actor=actor,
            organization_id=organization_id,
            anchor_entity_id=anchor_entity_id,
            include_archived=include_archived,
        )
        rows = self.db_model_service.list_entity_record_summary_page(
            organization_id=organization_id,
            entity_type_id=entity_type_id,
            entity_type_name=entity_type_name,
            include_archived=include_archived,
            entity_ids=allowed_ids,
            after_updated_at=after_updated_at,
            after_entity_id=after_entity_id,
            limit=page_size + 1,
        )
        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        type_names = {record.entity_type_id: type_name for record, type_name in page_rows}

        # One batched pass: resolve inherited-field sources per target type, then
        # widen resolve_read_policies to also cover their source types.
        field_sources_by_target_type: dict[str, dict[str, InheritedFieldSource]] = {}
        all_type_names = dict(type_names)
        for target_type_id in type_names:
            field_sources = self.inherited_field_permissions.get_field_sources(
                organization_id, target_type_id
            )
            if not field_sources:
                continue
            field_sources_by_target_type[target_type_id] = field_sources
            # `all_sources()`, not just the primary: a field pinned from more
            # than one source is gated against every one of them, so every one
            # needs a resolved read policy here or the gate would drop it.
            for source in field_sources.values():
                for source_type_id, _ in source.all_sources():
                    if source_type_id in all_type_names:
                        continue
                    source_type_name = self.db_model_service.get_entity_type_name_by_id(
                        organization_id=organization_id, entity_type_id=source_type_id
                    )
                    if source_type_name is None:
                        logger.warning(
                            "inherited field summary source entity type not found",
                            extra={
                                "organization_id": organization_id,
                                "source_entity_type_id": source_type_id,
                                "target_entity_type_id": target_type_id,
                            },
                        )
                    all_type_names[source_type_id] = source_type_name

        policies = self.resolve_read_policies(actor, organization_id, all_type_names)
        requested_fields = set(fields or ()) | {
            IDENTIFIER_FIELD_KEY, "name", "title", "full_name"
        }
        condition_fields = {
            name
            for policy in policies.values()
            for condition in policy.conditions
            for name in condition.field_names
        }
        records = [record for record, _ in page_rows]
        inherited = self.db_model_service.resolve_inherited_fields_for_records(
            organization_id=organization_id,
            records=records,
            field_names=requested_fields | condition_fields,
        )
        items: list[EntityRecordSummaryResponse] = []
        for record, type_name in page_rows:
            policy = policies.get(record.entity_type_id)
            if policy is None:
                continue
            combined = {**dict(record.data or {}), **inherited.get(record.entity_id, {})}
            # Gate 4 must run before field masking strips the condition's field
            # (same fix as resolve_records_for_actor).
            if not record_satisfies_any_condition(policy.conditions, combined, entity_id=record.entity_id):
                continue
            field_sources = field_sources_by_target_type.get(record.entity_type_id)
            if field_sources:
                combined = self.inherited_field_permissions.apply_from_policies(
                    combined, field_sources, policies
                )
            projected = self.apply_read_policy_to_data(
                policy,
                entity_id=record.entity_id,
                data=combined,
                projected_fields=requested_fields,
                exclude_from_target_check=field_sources.keys() if field_sources else None,
                enforce_condition=False,
            )
            if projected is None:
                continue
            items.append(
                EntityRecordSummaryResponse(
                    entity_id=record.entity_id,
                    organization_id=record.organization_id,
                    entity_type_id=record.entity_type_id,
                    entity_type=type_name,
                    display_name=self.summary_display_name(projected, record.entity_id),
                    summary_fields=projected,
                    owner_id=record.owner_id,
                    assignee_id=record.assignee_id,
                    due_date=record.due_date,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    archived_at=record.archived_at,
                )
            )
        last = page_rows[-1][0] if has_more and page_rows else None
        return EntityRecordSummaryPage(
            items=items,
            next_cursor=(
                self._encode_summary_cursor(last.updated_at, last.entity_id, scope) if last else None
            ),
            has_more=has_more,
        )

    def list_entity_records_by_type_name_for_actor(
        self,
        actor: dict[str, object],
        entity_type_name: str,
        include_archived: bool = False,
        search: str | None = None,
        limit: int | None = None,
    ) -> EntityRecordListResponse:
        """Authorized wrapper: list entity records by type name after RBAC check.
        Resolves the type name to an id internally — the caller only needs the
        human-readable type name (e.g., "Candidate"). Raises `NotFoundError` if no
        entity type with this name exists in the organization."""
        organization_id = self._require_actor_field(actor, "organization_id")
        entity_type = self.db_model_service.get_entity_type_by_name(
            organization_id=organization_id, name=entity_type_name
        )
        if entity_type is None:
            logger.warning(
                "list_entity_records_by_type_name_for_actor: entity type not found",
                extra={"organization_id": organization_id, "entity_type_name": entity_type_name},
            )
            raise NotFoundError(f"entity type '{entity_type_name}' not found in organization")
        normalized_search = (search or "").strip().lower()
        # The DB-layer fetch is only a candidate prefilter — the authoritative
        # match/filter runs below against the actor-VISIBLE view, so hidden/masked
        # field contents can't be probed via result membership. Overfetch whenever
        # a `limit` is requested at all, not just for search, since the per-item
        # condition-filtering loop below can also drop rows.
        fetch_limit = (
            ENTITY_RECORDS_BY_TYPE_NAME_PREFILTER_CAP
            if (normalized_search or limit is not None)
            else None
        )
        records = self.db_model_service.list_entity_records_by_type_name(
            organization_id=organization_id,
            entity_type_name=entity_type_name,
            include_archived=include_archived,
            search=search,
            limit=fetch_limit,
        )
        items = self.inherited_field_permissions.resolve_records_for_actor(
            actor,
            organization_id,
            records,
            enforce_condition=True,
            raise_on_denied_target=True,
            known_target_type_ids={entity_type.entity_type_id},
        )
        if normalized_search:
            items = [
                item
                for item in items
                if any(
                    normalized_search in str(value).lower()
                    for value in (item.data or {}).values()
                )
            ]
        if limit is not None:
            items = items[: max(1, min(limit, ENTITY_RECORDS_BY_TYPE_NAME_LIMIT_MAX))]
        return EntityRecordListResponse(organization_id=organization_id, items=items)

    def resolve_custom_forms(
        self, *, organization_id: str, record: EntityRecordResponse
    ) -> EntityRecordResponse:
        """Fetch the schema of any custom form this record's states are missing.

        Best-effort: a fetch that fails leaves the form absent and the record
        still opens. Only an actual fetch is persisted.
        """
        if self.custom_forms_service_manager is None:
            return record
        try:
            enrolments = self.db_model_service.list_entity_states_for_entity(
                organization_id=organization_id, entity_id=record.entity_id
            )
        except ModularError:
            logger.exception(
                "custom forms: could not read enrolments",
                extra={"entity_id": record.entity_id},
            )
            return record

        resolved = dict(record.custom_form_schema or {})
        changed = False
        for enrolment in enrolments:
            fetched = self.custom_forms_service_manager.resolve_for_record(
                organization_id=organization_id,
                workflow_state_machine_id=enrolment.workflow_id,
                state_key=enrolment.current_state,
                entity_values=record.data or {},
                stored=resolved,
            )
            if fetched is not None:
                resolved = fetched
                changed = True

        if not changed:
            return record
        try:
            self.db_model_service.store_custom_form_schema(
                organization_id=organization_id,
                entity_id=record.entity_id,
                custom_form_schema=resolved,
            )
        except ModularError:
            logger.exception(
                "custom forms: could not store fetched forms",
                extra={"entity_id": record.entity_id},
            )
        return record.model_copy(update={"custom_form_schema": resolved})

    def update_entity_record_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        request: EntityRecordUpdateRequest,
        organization_id: str | None = None,
    ) -> EntityRecordResponse:
        """Authorized wrapper: update entity record after RBAC check.
        Defaults `organization_id` to the actor's org."""
        organization_id = organization_id or self._require_actor_field(actor, "organization_id")
        existing = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        before_data: dict = {}
        requested_changes: dict = dict(request.data or {})
        if existing is not None and IDENTIFIER_FIELD_KEY in requested_changes:
            if self.db_model_service.get_identifier_template(
                organization_id, existing.entity_type_id
            ):
                # Generated identifiers are immutable: silently drop any client
                # attempt to change one (same rule as auto_number locks in
                # patch_entity_data).
                requested_changes.pop(IDENTIFIER_FIELD_KEY, None)
            else:
                # Manual mode: renaming to a taken identifier must fail with a
                # readable 400 here, not a unique-index violation at flush.
                new_identifier = str(
                    requested_changes.get(IDENTIFIER_FIELD_KEY) or ""
                ).strip()
                current_identifier = str(
                    (existing.data or {}).get(IDENTIFIER_FIELD_KEY) or ""
                ).strip()
                if (
                    new_identifier
                    and new_identifier != current_identifier
                    and self.db_model_service.identifier_exists(
                        organization_id, existing.entity_type_id, new_identifier
                    )
                ):
                    raise ValidationError(
                        f"An entity with identifier '{new_identifier}' already exists"
                    )
        due_date_requested = "due_date" in request.model_fields_set
        before_due_date = existing.due_date if existing else None
        if existing:
            self._reject_read_only_field_writes(
                organization_id=organization_id,
                entity_type_id=existing.entity_type_id,
                payload_keys=set(requested_changes.keys()),
            )
            self._reject_reference_field_writes(
                organization_id=organization_id,
                entity_type_id=existing.entity_type_id,
                payload_keys=set(requested_changes.keys()),
                entity_id=entity_id,
            )
            self.guard_write(
                actor,
                organization_id,
                existing.entity_type_id,
                "edit",
                set(request.data.keys()) if request.data else None,
            )
            before_data = dict(existing.data or {})
            merged_data = {**before_data, **requested_changes}
            # Preserve sibling fields (e.g. owner_id); only override data.
            request = request.model_copy(update={"data": merged_data})
        record = self.update_entity_record(
            organization_id=organization_id, entity_id=entity_id, request=request
        )
        if record is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        custom_form_changes = self._store_edited_custom_form_answers(
            organization_id=organization_id,
            entity_id=entity_id,
            existing=existing,
            incoming=request.custom_form_data,
        )
        changed_fields = {
            key: {"before": before_data.get(key), "after": new_val}
            for key, new_val in requested_changes.items()
            if before_data.get(key) != new_val
        }
        changed_fields.update(custom_form_changes)
        if due_date_requested and before_due_date != record.due_date:
            # ISO strings, not date objects — audit metadata is JSONB and the
            # engine has no date-aware json_serializer, so a raw date would fail
            # to serialize and the audit write would be silently rolled back.
            changed_fields["due_date"] = {
                "before": before_due_date.isoformat() if before_due_date else None,
                "after": record.due_date.isoformat() if record.due_date else None,
            }
        if changed_fields:
            self._try_emit_audit_event(
                actor=actor,
                organization_id=organization_id,
                entity_id=entity_id,
                entity_type_id=record.entity_type_id,
                event_type=EntityAuditEventType.UPDATED,
                payload={"changed_fields": changed_fields},
            )
        # Re-fetch the plain row and format via resolve_records_for_actor, same as
        # create (update_entity_record itself is untouched — workflow/manager.py
        # still calls it directly).
        fresh_record = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=record.entity_id
        )
        return self._resolve_single_record_or_deny(
            actor, organization_id, fresh_record, enforce_condition=False
        )

    def _store_custom_form_answers_on_create(
        self, *, organization_id: str, entity_id: str, custom_form_data: dict[str, object] | None
    ) -> None:
        """Best-effort: persist a new record's answers; schema resolves lazily on first read."""
        if not custom_form_data:
            return
        try:
            self.db_model_service.merge_custom_form_data(
                organization_id=organization_id, entity_id=entity_id, values=dict(custom_form_data)
            )
        except ModularError:
            logger.exception(
                "custom form answers at create: could not store entity=%s", entity_id
            )
            return
        logger.info(
            "custom form answers stored at create: entity=%s keys=%d",
            entity_id,
            len(custom_form_data),
        )

    def _store_edited_custom_form_answers(
        self,
        *,
        organization_id: str,
        entity_id: str,
        existing,
        incoming: dict[str, object] | None,
    ) -> dict[str, dict[str, object]]:
        """Merge edited custom form answers, and report them for the audit event.

        Only keys the record's stored schema declares are accepted: these are
        not published-schema fields, so nothing else validates them, and an
        actor with record write access could otherwise persist any key at all.
        """
        if not incoming:
            return {}
        if self.custom_forms_service_manager is None:
            logger.error("custom form answers: manager dependency is not configured")
            raise ServiceError("custom forms manager dependency is not configured")

        allowed = self.custom_forms_service_manager.answer_keys_for_record(
            custom_form_schema=getattr(existing, "custom_form_schema", None)
        )
        unknown = sorted(set(incoming) - allowed)
        if unknown:
            logger.warning(
                "custom form answers rejected: entity=%s keys=%s", entity_id, unknown
            )
            raise ValidationError(
                f"custom form answers name fields this form does not declare: "
                f"{', '.join(unknown)}"
            )

        before = dict(getattr(existing, "custom_form_data", None) or {})
        values = {key: value for key, value in incoming.items() if before.get(key) != value}
        if not values:
            return {}
        self.db_model_service.merge_custom_form_data(
            organization_id=organization_id, entity_id=entity_id, values=values
        )
        return {key: {"before": before.get(key), "after": value} for key, value in values.items()}

    def _notify_assignment_if_needed(
        self,
        *,
        actor: dict[str, object],
        organization_id: str,
        record: EntityRecordResponse,
        previous_assignee_id: str | None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Emit an in-app notification when an entity's assignee changes.

        Mirrors the tasks-module assignment pattern: fire only on an actual
        change, skip self-assignment, and never let a notification failure
        block the update."""
        if self.notifications_service_manager is None:
            return
        new_assignee_id = record.assignee_id
        if not new_assignee_id or new_assignee_id == previous_assignee_id:
            return
        actor_id = actor_str(actor, "user_id") or None
        if new_assignee_id == actor_id:
            return
        try:
            entity_type_name = (
                self.db_model_service.get_entity_type_name_by_id(
                    organization_id=organization_id,
                    entity_type_id=record.entity_type_id,
                )
                or record.entity_type_id
            )
            entity_label = str(
                (record.data or {}).get(IDENTIFIER_FIELD_KEY) or entity_type_name
            )
            link = self._build_entity_link(
                organization_id=organization_id, entity_id=record.entity_id
            )
            actor_name = ""
            if self.user_service_manager is not None:
                try:
                    actor_name = self.user_service_manager.get_actor_display_info(actor)[0] or ""
                except Exception as exc:
                    logger.debug("actor display info lookup failed for assignment email: %s", exc)
            self.notifications_service_manager.create_assignment_notification(
                organization_id=organization_id,
                recipient_id=new_assignee_id,
                entity_id=record.entity_id,
                entity_type=entity_type_name,
                entity_label=entity_label,
                actor_id=actor_id,
                actor_name=actor_name,
                link=link,
                background_tasks=background_tasks,
            )
        except (ServiceError, ValidationError) as exc:
            logger.warning("Failed to create assignment notification: %s", exc)
        except Exception as exc:
            logger.exception("Unexpected error creating assignment notification: %s", exc)

    def _build_entity_link(self, *, organization_id: str, entity_id: str) -> str | None:
        """Best-effort deep link to the entity in its workflow pipeline. Returns
        None when the entity is not enrolled in any workflow."""
        try:
            states = self.db_model_service.list_entity_states_for_entity(
                organization_id=organization_id,
                entity_id=entity_id,
            )
        except PersistenceError as exc:
            logger.warning(
                "entity link lookup failed (best-effort, non-fatal): %s", exc,
                extra={"organization_id": organization_id, "entity_id": entity_id},
            )
            return None
        except Exception as exc:
            logger.exception("Unexpected error building entity link: %s", exc)
            return None
        if not states:
            return None
        workflow_id = states[0].workflow_id
        if not workflow_id:
            return None
        return f"/pipeline/{workflow_id}?entity={entity_id}"

    def set_entity_assignee_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        assignee_id: str | None,
        organization_id: str | None = None,
        *,
        assign_to_originator: bool = False,
        assignment_source: AssignmentSource = AssignmentSource.API,
        action_run_id: str | None = None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> EntityRecordResponse:
        """Assign an entity to a user, or clear the assignment (`assignee_id=None`).

        Requires entity `edit` permission for every assignment, including to
        yourself; a system actor bypasses the check. `assign_to_originator`
        resolves the target from the record's creation history instead of the
        caller. Assigning the current holder is a no-op: no write, notification
        or history row."""
        organization_id = organization_id or self._require_actor_field(actor, "organization_id")
        existing = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        if existing is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        self.guard_write(actor, organization_id, existing.entity_type_id, "edit")
        if assign_to_originator:
            assignee_id = self._resolve_assignable_originator(organization_id, entity_id)
        previous_assignee_id = existing.assignee_id
        if assignee_id != previous_assignee_id:
            self._write_assignee_change(
                actor=actor,
                organization_id=organization_id,
                entity_id=entity_id,
                previous_assignee_id=previous_assignee_id,
                assignee_id=assignee_id,
                assign_to_originator=assign_to_originator,
                assignment_source=assignment_source,
                action_run_id=action_run_id,
                background_tasks=background_tasks,
            )
        return self._assignee_response(actor, organization_id, entity_id)

    def _write_assignee_change(
        self,
        *,
        actor: dict[str, object],
        organization_id: str,
        entity_id: str,
        previous_assignee_id: str | None,
        assignee_id: str | None,
        assign_to_originator: bool,
        assignment_source: AssignmentSource,
        action_run_id: str | None,
        background_tasks: BackgroundTaskScheduler | None,
    ) -> None:
        """Persist an assignee change, then notify the assignee and record it."""
        record = self.db_model_service.set_entity_assignee(
            organization_id=organization_id,
            entity_id=entity_id,
            assignee_id=assignee_id,
        )
        if record is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        response = self._entity_record_response_with_inherited(record)
        self._notify_assignment_if_needed(
            actor=actor,
            organization_id=organization_id,
            record=response,
            previous_assignee_id=previous_assignee_id,
            background_tasks=background_tasks,
        )
        self._try_emit_audit_event(
            actor=actor,
            organization_id=organization_id,
            entity_id=entity_id,
            entity_type_id=response.entity_type_id,
            event_type=EntityAuditEventType.ASSIGNEE_CHANGED,
            payload=self._assignment_audit_payload(
                previous_assignee_id=previous_assignee_id,
                new_assignee_id=assignee_id,
                assign_to_originator=assign_to_originator,
                assignment_source=assignment_source,
                action_run_id=action_run_id,
            ),
        )

    def _assignee_response(
        self, actor: dict[str, object], organization_id: str, entity_id: str
    ) -> EntityRecordResponse:
        """Re-read the row and format it under the actor's field permissions."""
        fresh_record = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        return self._resolve_single_record_or_deny(
            actor, organization_id, fresh_record, enforce_condition=False
        )

    @staticmethod
    def _assignment_audit_payload(
        *,
        previous_assignee_id: str | None,
        new_assignee_id: str | None,
        assign_to_originator: bool,
        assignment_source: AssignmentSource,
        action_run_id: str | None,
    ) -> dict[str, object]:
        """Build the `ENTITY_ASSIGNEE_CHANGED` payload.

        `action_run_id` is omitted entirely unless a workflow action made the
        change."""
        payload: dict[str, object] = {
            AssignmentAuditKey.PREVIOUS_ASSIGNEE_ID: previous_assignee_id,
            AssignmentAuditKey.NEW_ASSIGNEE_ID: new_assignee_id,
            AssignmentAuditKey.ASSIGNMENT_MODE: (
                AssignmentMode.ORIGINATOR if assign_to_originator else AssignmentMode.MANUAL
            ),
            AssignmentAuditKey.ASSIGNMENT_SOURCE: assignment_source,
        }
        if action_run_id:
            payload[AssignmentAuditKey.ACTION_RUN_ID] = action_run_id
        return payload

    def _find_entity_originator(self, organization_id: str, entity_id: str) -> str | None:
        """Return the id of the user who created this record, or None.

        The single definition of "originator": the actor on the earliest
        `ENTITY_CREATED` audit event with a human actor. None means nobody
        human created the record (system- or agent-created); a read failure
        raises rather than reporting None.

        Callers must authorize the record first — this does no access check of
        its own beyond scoping the read to `organization_id`."""
        return self.audit_service_manager.find_entity_originator(
            organization_id=organization_id,
            entity_id=entity_id,
            event_type=str(EntityAuditEventType.CREATED),
            actor_type=str(ActorType.USER),
        )

    def _resolve_assignable_originator(self, organization_id: str, entity_id: str) -> str:
        """Return the id of the user who created this record, or reject the request.

        Checks the originator for assignability. Raises `ValidationError` when
        no such creator exists or they cannot be assigned; runs before the
        write, so the current assignee is left untouched."""
        originator_id = self._find_entity_originator(organization_id, entity_id)
        if not originator_id:
            raise ValidationError(
                ORIGINATOR_NOT_FOUND_MESSAGE,
                code=AssignmentRejection.ORIGINATOR_NOT_FOUND,
            )
        candidate = self.user_service_manager.get_org_member_assignability(
            originator_id, organization_id
        )
        if candidate.verdict is OrgMembershipVerdict.NOT_FOUND:
            raise ValidationError(
                ORIGINATOR_USER_MISSING_MESSAGE,
                code=AssignmentRejection.ORIGINATOR_USER_MISSING,
            )
        if candidate.verdict is OrgMembershipVerdict.SUSPENDED:
            raise ValidationError(
                originator_suspended_message(candidate.full_name),
                code=AssignmentRejection.ORIGINATOR_SUSPENDED,
            )
        if candidate.verdict is OrgMembershipVerdict.INACTIVE_ACCOUNT:
            raise ValidationError(
                originator_inactive_account_message(candidate.full_name),
                code=AssignmentRejection.ORIGINATOR_INACTIVE_ACCOUNT,
            )
        if not candidate.is_assignable:
            raise ValidationError(
                ORIGINATOR_NOT_A_MEMBER_MESSAGE,
                code=AssignmentRejection.ORIGINATOR_NOT_A_MEMBER,
            )
        return originator_id

    def archive_entity_record_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        organization_id: str | None = None,
    ) -> EntityRecordResponse:
        """Authorized wrapper: archive entity record after RBAC check.
        Defaults `organization_id` to the actor's org."""
        organization_id = organization_id or self._require_actor_field(actor, "organization_id")
        existing = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        if existing:
            self.guard_write(actor, organization_id, existing.entity_type_id, "delete")
        record = self.archive_entity_record(organization_id=organization_id, entity_id=entity_id)
        if record is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        self._try_emit_audit_event(
            actor=actor,
            organization_id=organization_id,
            entity_id=entity_id,
            entity_type_id=record.entity_type_id,
            event_type=EntityAuditEventType.ARCHIVED,
            payload={},
        )
        # Re-fetch and format via resolve_records_for_actor, same as create/update.
        # include_archived=True: the record we just archived is otherwise invisible
        # to the default fetch.
        fresh_record = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id, include_archived=True
        )
        return self._resolve_single_record_or_deny(
            actor, organization_id, fresh_record, enforce_condition=False
        )

    def restore_entity_record_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        organization_id: str | None = None,
        data: dict | None = None,
        owner_id: str | None = None,
    ) -> EntityRecordResponse:
        """Authorized wrapper: clear archived_at on a previously archived entity.
        Defaults `organization_id` to the actor's org. Optionally refreshes
        data/owner. 404 if no entity exists for the id."""
        organization_id = organization_id or self._require_actor_field(actor, "organization_id")
        existing = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        if existing:
            self.guard_write(actor, organization_id, existing.entity_type_id, "edit")
        record = self.restore_entity_record(
            organization_id=organization_id,
            entity_id=entity_id,
            data=data,
            owner_id=owner_id,
        )
        if record is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        self._try_emit_audit_event(
            actor=actor,
            organization_id=organization_id,
            entity_id=entity_id,
            entity_type_id=record.entity_type_id,
            event_type=EntityAuditEventType.RESTORED,
            payload={},
        )
        # Re-fetch and format via resolve_records_for_actor, same as create/update.
        fresh_record = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        return self._resolve_single_record_or_deny(
            actor, organization_id, fresh_record, enforce_condition=False
        )

    def get_entity_with_states_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        organization_id: str | None = None,
        include_archived: bool = False,
    ) -> EntityWithStatesResponse:
        """Authorized wrapper: fetch an entity together with every workflow
        enrollment row attached to it. Defaults `organization_id` to the
        actor's org. Replaces the legacy combined `EntityState` shape from
        the workflow controller."""
        organization_id = organization_id or self._require_actor_field(actor, "organization_id")
        record = self.db_model_service.get_entity_record_by_id(
            organization_id=organization_id,
            entity_id=entity_id,
            include_archived=include_archived,
        )
        if record is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        entity = self._resolve_single_record_or_deny(
            actor, organization_id, record, enforce_condition=True
        )
        # Relation-inherited values are an overlay, never stored on the row, so
        # they have to be composed here or the detail view shows only the
        # record's own fields. Write paths strip these keys again, so the
        # overlay cannot be round-tripped back into `data`.
        entity.data = self._compose_entity_response_data(
            organization_id=organization_id,
            entity_type_id=record.entity_type_id,
            entity_id=record.entity_id,
            data=entity.data or {},
        )
        try:
            state_rows = self.db_model_service.list_entity_states_for_entity(
                organization_id=organization_id,
                entity_id=entity_id,
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("get_entity_with_states_for_actor failed loading states: %s", exc)
            raise ServiceError(f"Unable to load entity states: {exc}") from exc
        states = [self._entity_state_response(row) for row in state_rows]
        entity = self.resolve_custom_forms(organization_id=organization_id, record=entity)
        return EntityWithStatesResponse(
            entity=entity,
            states=states,
            originator_id=self._find_entity_originator(organization_id, entity_id),
        )

    # ── EntityRelation (graph edges) ────────────────────────────────────────
    #
    # Only actor-gated entry points are exposed. There are no pure (un-
    # authorized) variants on this resource. The broader "auth-as-controller-
    # dependency" sweep (tracked in state_machine_rewrite.md §11) will pull
    # the same shape across entity_records / entity_types.

    def create_entity_relation_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        request: EntityRelationCreateRequest,
    ) -> EntityRelationResponse:
        return self.relationships_service.create_for_actor(actor, entity_id, request)

    def list_entity_relations_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        direction: str = "both",
        relation_type: str | None = None,
    ) -> EntityRelationListResponse:
        return self.relationships_service.list_for_actor(
            actor, entity_id, direction=direction, relation_type=relation_type
        )

    def list_related_files_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
    ) -> RelatedEntityFileListResponse:
        return self.relationships_service.list_related_files_for_actor(actor, entity_id)

    def delete_entity_relation_for_actor(
        self,
        actor: dict[str, object],
        relation_id: str,
    ) -> EntityRelationResponse:
        return self.relationships_service.delete_for_actor(actor, relation_id)

    # ── EntityState (workflow enrollments) ──────────────────────────────────
    #
    # No public CRUD surface yet. The workflow engine writes via `enroll_entity`
    # (called from create_entity_for_actor after the actor has already been
    # authorized for the workflow). Reads are exposed via actor-gated methods
    # for the upcoming GET /entities/{id}/enrollments endpoint.

    def _enroll_entity(
        self,
        *,
        organization_id: str,
        entity_id: str,
        workflow_id: str,
        current_state: str,
        sla_due_at: datetime | None = None,
    ) -> EntityStateResponse:
        """Internal write: register an entity in a workflow. Caller must have
        already authorized the request (typically the workflow manager)."""
        try:
            record = self.db_model_service.enroll_entity_in_workflow(
                organization_id=organization_id,
                entity_id=entity_id,
                workflow_id=workflow_id,
                current_state=current_state,
                sla_due_at=sla_due_at,
            )
            return self._entity_state_response(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError) as exc:
            logger.warning(
                "_enroll_entity failed: %s",
                exc,
                extra={"organization_id": organization_id, "entity_id": entity_id, "workflow_id": workflow_id},
            )
            raise
        except ValueError as exc:
            logger.warning(
                "_enroll_entity failed: %s",
                exc,
                extra={"organization_id": organization_id, "entity_id": entity_id, "workflow_id": workflow_id},
            )
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            logger.warning(
                "_enroll_entity failed: %s",
                exc,
                extra={"organization_id": organization_id, "entity_id": entity_id, "workflow_id": workflow_id},
            )
            raise ServiceError(f"Unable to enroll entity: {exc}") from exc

    def list_entity_states_for_actor(
        self,
        actor: dict[str, object],
        entity_id: str,
        workflow_id: str | None = None,
    ) -> EntityStateListResponse:
        """Authorized wrapper: list workflow enrollments for an entity after RBAC check."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            records = self.db_model_service.list_entity_states_for_entity(
                organization_id=organization_id,
                entity_id=entity_id,
                workflow_id=workflow_id,
            )
            scope = self.roles_manager.get_workflow_access_scope(actor)
            workflow_service = getattr(self.roles_manager, "workflow_service_manager", None)
            if scope is not None and workflow_service is not None:
                records = [
                    record
                    for record in records
                    if (
                        machine := workflow_service.workflow_db.get_state_machine_by_row_id(
                            organization_id=organization_id,
                            row_id=record.workflow_id,
                        )
                    ) is not None
                    and machine.machine_name in scope
                ]
            items = [self._entity_state_response(record) for record in records]
            return EntityStateListResponse(
                organization_id=organization_id, entity_id=entity_id, items=items
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("list_entity_states_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to list entity states: {exc}") from exc

    def get_entity_state_for_actor(
        self,
        actor: dict[str, object],
        state_id: str,
    ) -> EntityStateResponse:
        """Authorized wrapper: fetch a single workflow enrollment after RBAC check."""
        organization_id = self._require_actor_field(actor, "organization_id")
        try:
            record = self.db_model_service.get_entity_state_by_id(
                organization_id=organization_id, state_id=state_id
            )
            if record is None:
                raise NotFoundError(f"entity state '{state_id}' not found")
            scope = self.roles_manager.get_workflow_access_scope(actor)
            workflow_service = getattr(self.roles_manager, "workflow_service_manager", None)
            if scope is not None and workflow_service is not None:
                machine = workflow_service.workflow_db.get_state_machine_by_row_id(
                    organization_id=organization_id,
                    row_id=record.workflow_id,
                )
                if machine is None or machine.machine_name not in scope:
                    raise NotFoundError(f"entity state '{state_id}' not found")
            return self._entity_state_response(record)
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("get_entity_state_for_actor failed: %s", exc)
            raise ServiceError(f"Unable to fetch entity state: {exc}") from exc

    def _transition_entity_state(
        self,
        *,
        organization_id: str,
        state_id: str,
        expected_state_version: int,
        next_state: str,
        state_entered_at: datetime,
        last_transition_at: datetime,
        sla_due_at: datetime | None = None,
    ) -> EntityStateResponse | None:
        """Internal: optimistic-lock state transition. Returns updated state
        or None on version conflict. Caller (workflow engine) has already
        authorized the actor."""
        try:
            record = self.db_model_service.transition_entity_state(
                organization_id=organization_id,
                state_id=state_id,
                expected_state_version=expected_state_version,
                next_state=next_state,
                state_entered_at=state_entered_at,
                last_transition_at=last_transition_at,
                sla_due_at=sla_due_at,
            )
            if record is None:
                return None
            return self._entity_state_response(record)
        except (ConflictError, ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.debug("_transition_entity_state failed: %s", exc)
            raise ServiceError(f"Unable to transition entity state: {exc}") from exc

    # ── Audit events ─────────────────────────────────────────────────────────
    #
    # Entity CRUD writes to the unified `audit_events` table (backend/audit).
    # Reads happen exclusively through `GET /audit-events`; this module has no
    # read path of its own.

    def _try_emit_audit_event(
        self,
        *,
        actor: dict[str, object],
        organization_id: str,
        entity_id: str,
        entity_type_id: str,
        event_type: EntityAuditEventType,
        payload: dict,
    ) -> None:
        """Best-effort audit event emit — resolve actor identity and entity type, write to audit_events.

        Failures are caught and logged as warnings so they never block the
        primary operation that triggered the emit.
        """
        entity_type_name: str | None = None
        try:
            entity_type_name = self.db_model_service.get_entity_type_name_by_id(
                organization_id=organization_id,
                entity_type_id=entity_type_id,
            )
        except Exception as e:
            logger.debug(
                "entity type name lookup failed for audit emit",
                extra={"entity_id": entity_id, "error": str(e)},
                exc_info=True,
            )
        actor_name: str | None = None
        actor_role: str | None = None
        try:
            actor_name, actor_role = self.user_service_manager.get_actor_display_info(actor)
        except Exception as e:
            logger.debug(
                "actor display info lookup failed for audit emit",
                extra={"entity_id": entity_id, "error": str(e)},
                exc_info=True,
            )
        try:
            actor_id = actor_str(actor, "user_id") or None
            self.audit_service_manager.emit_audit_event(
                AuditEventInput(
                    organization_id=organization_id,
                    metadata_type=AuditMetadataType.ENTITY,
                    entity_type=entity_type_name,
                    entity_id=entity_id,
                    event_type=str(event_type),
                    actor_type=str(actor.get("actor_type") or ActorType.USER),
                    actor_id=actor_id,
                    actor_name=actor_name,
                    actor_role=actor_role,
                    user_id=actor_id,
                    source=str(AuditEventSource.API),
                    event_metadata=payload,
                )
            )
        except Exception as e:
            logger.warning(
                "entity audit emit failed",
                extra={
                    "event_type": str(event_type),
                    "entity_id": entity_id,
                    "org_id": organization_id,
                    "error": str(e),
                },
                exc_info=True,
            )

    def _emit_entity_event(
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
    ) -> None:
        """Best-effort audit event emit for callers outside the 5 CRUD paths
        (workflow transitions/enrollment/tasks, forms, background jobs).

        Same name and signature these callers already use — only the
        destination changed, from the retired `entity_events` table to the
        unified `audit_events` table. Failures are caught and logged as
        warnings so they never block the primary operation that triggered
        the emit.
        """

        entity_type_name: str | None = None
        try:
            entity = self.db_model_service.get_entity_record_by_id(
                organization_id=organization_id, entity_id=entity_id, include_archived=True
            )
            if entity is not None:
                entity_type_name = self.db_model_service.get_entity_type_name_by_id(
                    organization_id=organization_id, entity_type_id=entity.entity_type_id
                )
        except Exception as e:
            logger.debug(
                "entity type name lookup failed for audit emit",
                extra={"entity_id": entity_id, "error": str(e)},
                exc_info=True,
            )
        try:
            self.audit_service_manager.emit_audit_event(
                AuditEventInput(
                    organization_id=organization_id,
                    metadata_type=AuditMetadataType.ENTITY,
                    entity_type=entity_type_name,
                    entity_id=entity_id,
                    event_type=str(event_type),
                    actor_type=str(actor_type),
                    actor_id=actor_id,
                    actor_name=actor_name,
                    actor_role=actor_role,
                    user_id=actor_id,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    source=str(AuditEventSource.API),
                    event_metadata=payload or {},
                )
            )
        except Exception as e:
            logger.warning(
                "entity audit emit failed",
                extra={
                    "event_type": str(event_type),
                    "entity_id": entity_id,
                    "org_id": organization_id,
                    "error": str(e),
                },
                exc_info=True,
            )

    @staticmethod
    def _entity_state_response(record: EntityStateRecord) -> EntityStateResponse:
        """Map an internal state record to the public response shape."""
        return EntityStateResponse(
            state_id=record.state_id,
            organization_id=record.organization_id,
            entity_id=record.entity_id,
            workflow_id=record.workflow_id,
            current_state=record.current_state,
            state_version=record.state_version,
            state_entered_at=record.state_entered_at,
            last_transition_at=record.last_transition_at,
            sla_due_at=record.sla_due_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _entity_relation_response(record: EntityRelation) -> EntityRelationResponse:
        """Map an internal relation record to the public response shape."""
        return EntityRelationResponse(
            relation_id=record.relation_id,
            organization_id=record.organization_id,
            from_entity_id=record.from_entity_id,
            to_entity_id=record.to_entity_id,
            relation_type=record.relation_type,
            relation_metadata=(
                dict(record.relation_metadata) if record.relation_metadata is not None else None
            ),
            created_at=record.created_at,
        )

    @staticmethod
    def _entity_record_response(record: EntityRecord) -> EntityRecordResponse:
        """Map an internal entity record to the public response shape."""
        return EntityRecordResponse(
            entity_id=record.entity_id,
            organization_id=record.organization_id,
            entity_type_id=record.entity_type_id,
            data=dict(record.data),
            custom_form_schema=dict(record.custom_form_schema or {}),
            custom_form_data=dict(record.custom_form_data or {}),
            owner_id=record.owner_id,
            assignee_id=record.assignee_id,
            due_date=record.due_date,
            created_at=record.created_at,
            updated_at=record.updated_at,
            archived_at=record.archived_at,
        )

    @staticmethod
    def _entity_type_record_response(record: EntityType) -> EntityTypeRecordResponse:
        """Map an internal entity type to the public response shape."""
        return EntityTypeRecordResponse(
            entity_type_id=record.entity_type_id,
            organization_id=record.organization_id,
            name=record.name,
            description=record.description,
            schema_definition=dict(record.schema_definition),
            version=record.version,
            is_active=record.is_active,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _entity_type_relation_response(record: EntityTypeRelation) -> EntityTypeRelationResponse:
        return EntityTypeRelationResponse(
            relation_def_id=record.relation_def_id,
            organization_id=record.organization_id,
            from_entity_type_id=record.from_entity_type_id,
            to_entity_type_id=record.to_entity_type_id,
            relation_name=record.relation_name,
            relation_type=record.relation_type,
            relation_metadata=record.relation_metadata,
            created_at=record.created_at,
            updated_at=record.updated_at,
            deleted_at=record.deleted_at,
        )

    def upsert_form_config_for_actor(
        self,
        actor: dict[str, object],
        request: UpsertFormConfigRequest,
    ) -> FormConfigResponse:
        """Authorized wrapper: upsert a form config after RBAC check."""
        organization_id = request.organization_id or self._require_actor_field(
            actor, "organization_id"
        )
        self._authorize_actor_operation(actor, "metadata", "write", organization_id)
        normalized_request = UpsertFormConfigRequest(
            organization_id=organization_id,
            form_key=request.form_key,
            fields=list(request.fields),
            version=request.version,
        )
        return self.upsert_form_config(normalized_request)

    def get_form_config_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        form_key: str,
    ) -> FormConfigResponse:
        """Authorized wrapper: fetch a form config after RBAC check."""
        self._authorize_actor_operation(actor, "metadata", "read", organization_id)
        response = self.get_form_config(organization_id=organization_id, form_key=form_key)
        if response is None:
            raise NotFoundError("form config not found")
        return response

    def _authorize_actor_operation(
        self,
        actor: dict[str, object],
        resource: str,
        action: str,
        organization_id: str,
    ) -> None:
        """Reject the call if `organization_id` doesn't match the actor's own org.

        Only meaningful where `organization_id` can come from something other
        than the actor itself — a client-supplied wire-payload field (create
        entity type/relation-declaration/entity-record, upsert form config) or
        a hard external parameter (`get_form_config_for_actor`)."""
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_organization_id:
            raise AuthorizationError("Forbidden organization scope")

    def _apply_field_permissions(
        self,
        db: Session,
        actor: dict[str, object],
        org_id: str,
        entity_type_name: str,
        response: EntityRecordResponse,
    ) -> EntityRecordResponse:
        """Strip hidden fields and mask masked fields; None = bypass, [] = deny all, list = allowed fields.

        Inherited fields (sourced from a different entity type via a relation
        declaration) are resolved separately, against their real source field's
        permission — never against a row configured on this (target) entity type
        for the field's synthetic name. See `InheritedFieldPermissionsService`."""
        if actor.get("actor_type", "").lower() == "system":
            return response
        user_id = self._require_actor_field(actor, "user_id")
        visible = self.roles_manager.get_visible_fields(db, user_id, org_id, entity_type_name)
        masked = self.roles_manager.get_masked_fields(db, user_id, org_id, entity_type_name)
        if visible is None and not masked:
            return response

        field_sources = self.inherited_field_permissions.get_field_sources(
            org_id, response.entity_type_id
        )
        data = dict(response.data)
        if field_sources:
            data = self.inherited_field_permissions.apply(
                db, user_id, org_id, data, field_sources
            )
        if visible is not None:
            data = {
                k: v
                for k, v in data.items()
                if k == IDENTIFIER_FIELD_KEY or k in visible or k in field_sources
            }
        for field in masked:
            if field != IDENTIFIER_FIELD_KEY and field in data and field not in field_sources:
                data[field] = MASKED_FIELD_VALUE
        response.data = data
        return response

    def _validate_field_write_permissions(
        self,
        db: Session,
        actor: dict[str, object],
        org_id: str,
        entity_type_name: str,
        payload_fields: set[str],
    ) -> None:
        """Raise if payload contains fields not in the actor's editable list."""
        if actor.get("actor_type", "").lower() == "system":
            return
        user_id = self._require_actor_field(actor, "user_id")
        editable = self.roles_manager.get_editable_fields(db, user_id, org_id, entity_type_name)
        if editable is None:
            return
        disallowed = payload_fields - set(editable) - {IDENTIFIER_FIELD_KEY}
        if disallowed:
            raise AuthorizationError(f"Not allowed to edit fields: {', '.join(sorted(disallowed))}")

    def _check_entity_permission(
        self,
        db: Session,
        actor: dict[str, object],
        org_id: str,
        entity_type_name: str,
        action: str,
    ) -> list[EntityConditionSpec]:
        """Check entity-level permission; no-op if actor is system.

        Returns the read-narrowing condition(s) attached to the granting role(s) (entity
        field permission filter) — empty means unconditional access. Only `guard_read`
        evaluates the returned conditions against a specific record; other callers
        (guard_write, list/view entity-type checks) call this for the allow/deny
        decision only and ignore the return value, unaffected by this feature."""
        if actor.get("actor_type", "").lower() == "system":
            return []
        user_id = self._require_actor_field(actor, "user_id")
        result = self.roles_manager.evaluate_entity_access(
            db, user_id, org_id, entity_type_name, action
        )
        if not result.allowed:
            raise AuthorizationError(f"Not allowed to perform '{action}' on '{entity_type_name}'")
        return result.conditions

    def verify_entity_type_view_permission(
        self,
        actor: dict[str, object],
        organization_id: str,
        entity_type_id: str,
    ) -> None:
        """Resolve entity type name and check actor view permission. Public entry point
        for cross-module callers (e.g. workflow manager) that must not call the private
        `_check_entity_permission` directly."""
        with self.db_model_service._db_session() as db:
            entity_type_name = self.db_model_service.get_entity_type_name_by_id(
                organization_id=organization_id, entity_type_id=entity_type_id, db=db
            )
            if entity_type_name:
                self._check_entity_permission(db, actor, organization_id, entity_type_name, "view")

    def guard_read(
        self,
        actor: dict[str, object],
        org_id: str,
        entity_type_id: str,
        record: EntityRecordResponse,
        *,
        enforce_condition: bool = True,
    ) -> EntityRecordResponse:
        """Resolve entity type, check view permission (including any entity field
        permission filter condition), apply field filtering.

        `enforce_condition=False` is for callers formatting the response of an
        already-authorized WRITE (e.g. `update_entity_record_for_actor`,
        `set_entity_assignee_for_actor` reusing this method purely for its field-masking
        step) — this feature governs reads only, so a write's own response must never be
        blocked by the actor's read condition, even though the entity-type view check and
        field masking still apply exactly as before."""
        with self.db_model_service._db_session() as db:
            entity_type_name = self.db_model_service.get_entity_type_name_by_id(
                organization_id=org_id, entity_type_id=entity_type_id, db=db
            )
            if entity_type_name:
                conditions = self._check_entity_permission(db, actor, org_id, entity_type_name, "view")
                if (
                    enforce_condition
                    and not self._record_satisfies_any_condition(conditions, record)
                ):
                    raise AuthorizationError("You do not have permission to view this record.")
                record = self._apply_field_permissions(db, actor, org_id, entity_type_name, record)
        return record

    @staticmethod
    def _record_satisfies_any_condition(
        conditions: list[EntityConditionSpec], record: EntityRecordResponse
    ) -> bool:
        """True if there's no condition to satisfy, or at least one condition is
        satisfied (most-permissive-role-wins). Thin wrapper over the shared
        `common.protocols` implementation — every read surface (this module, audit
        event reads, etc.) evaluates conditions the exact same way."""
        return record_satisfies_any_condition(conditions, record.data, entity_id=record.entity_id)

    @staticmethod
    def _resolve_and_compare(condition: EntityConditionSpec, record: EntityRecordResponse) -> bool:
        """Evaluate one entity permission read condition against a record. Thin wrapper
        over the shared `common.protocols` implementation."""
        return resolve_and_compare(condition, record.data, entity_id=record.entity_id)

    def guard_write(
        self,
        actor: dict[str, object],
        org_id: str,
        entity_type_id: str,
        action: str,
        fields: set[str] | None = None,
    ) -> None:
        """Resolve entity type, check write permission, validate fields if provided."""
        with self.db_model_service._db_session() as db:
            entity_type_name = self.db_model_service.get_entity_type_name_by_id(
                organization_id=org_id, entity_type_id=entity_type_id, db=db
            )
            if entity_type_name:
                self._check_entity_permission(db, actor, org_id, entity_type_name, action)
                if fields:
                    self._validate_field_write_permissions(
                        db, actor, org_id, entity_type_name, fields
                    )

    @staticmethod
    def _resolve_identity_service(dependencies: tuple[object, ...]) -> object | None:
        """Return the configured auth service or raise if unwired."""
        for dependency in dependencies:
            if hasattr(dependency, "check_access"):
                return dependency
        return None

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field_name: str) -> str:
        """Pull a required field off the actor payload, raising 400 on absence."""
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"Missing actor field: {field_name}")
        return value

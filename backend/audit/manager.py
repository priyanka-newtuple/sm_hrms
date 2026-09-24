"""Business logic manager for unified audit events."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from common.auth import actor_str
from common.enums import AuditMetadataType, ModuleStatus
from common.logger import logger
from common.protocols import MASKED_FIELD_VALUE, RolesServiceProtocol, record_satisfies_any_condition
from audit.db_models import AuditEventsModelService
from audit.models.interface import (
    AUDIT_EVENT_TYPES,
    AuditEventInput,
    AuditEventRecord,
    AuditEventType,
    AuditMetadataKey,
)
from audit.models.response import AuditConstantsResponse, AuditEventListResponse, AuditEventResponse
from entities.models.interface import IDENTIFIER_FIELD_KEY
from exceptions import AuthorizationError, NotFoundError, ServiceError, ValidationError


class AuditServiceManager:
    """Orchestration layer for audit_events — reads, appends, and actor lookups."""

    def __init__(
        self,
        db_model_service: AuditEventsModelService,
        roles_manager: RolesServiceProtocol | None = None,
        entities_service: Any = None,
    ) -> None:
        self.db = db_model_service
        self.roles_manager = roles_manager
        self.entities_service = entities_service
        self.module_name = "audit"
        self._started = False

    def start(self) -> None:
        """Mark the manager as started."""
        self._started = True

    def stop(self) -> None:
        """Idempotent shutdown hook."""
        self._started = False

    def get_status(self) -> dict[str, object]:
        return {"module": self.module_name, "status": ModuleStatus.READY.value, "started": self._started}

    def emit_audit_event(self, event: AuditEventInput) -> AuditEventRecord | None:
        """Append one audit row, returning the record or None on failure.

        Best-effort: a failed audit write returns None rather than raising, so
        it never breaks the operation that triggered it.
        """
        return self.db.emit_audit_event(**event.model_dump())

    def find_entity_originator(
        self, *, organization_id: str, entity_id: str, event_type: str, actor_type: str
    ) -> str | None:
        """Return the user id of the actor on a record's earliest matching event.

        Resolves who originally created a record. None means no matching event;
        a read failure raises.
        """
        return self.db.find_earliest_event_actor_id(
            organization_id=organization_id,
            entity_id=entity_id,
            event_type=event_type,
            actor_type=actor_type,
        )

    def list_audit_events_for_actor(
        self,
        actor: dict[str, object],
        *,
        entity_id: str | None = None,
        entity_ids: list[str] | None = None,
        user_id: str | None = None,
        actor_type: str | None = None,
        metadata_type: str | list[str] | None = None,
        event_type: str | list[str] | None = None,
        date_from: date | datetime | None = None,
        date_to: date | datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditEventListResponse:
        """List audit events for the actor's org (optionally entity-scoped), validating
        ``metadata_type`` against ``AuditMetadataType`` before hitting the DB.

        ``metadata_type`` accepts a single value or a list; every value must match
        `AuditMetadataType`, or the whole request is rejected (fail closed — a request
        with one bad value alongside good ones is not silently narrowed to the good
        ones, since that would hide the same typo this validation exists to catch).
        An empty list (`[]`) isn't reachable via the HTTP layer — a URL can't express
        "zero values for a repeated query param" — so it's only ever passed by an
        internal caller in Python; it has no invalid elements to reject, so it falls
        through to the existing `list_for_*_paginated` behavior of treating `[]` the
        same as "no filter."
        """
        organization_id = actor_str(actor, "organization_id")
        if not organization_id:
            raise ValidationError("actor organization_id is required")
        self._validate_metadata_type(metadata_type)
        date_from_at, date_to_at = self._normalize_date_window(date_from, date_to)

        try:
            if entity_id:
                self._check_entity_scope(actor, organization_id, entity_id)
                items_raw, total = self.db.list_for_entity_paginated(
                    organization_id=organization_id,
                    entity_id=entity_id,
                    metadata_type=metadata_type,
                    event_type=event_type,
                    user_id=user_id,
                    date_from=date_from_at,
                    date_to=date_to_at,
                    limit=limit,
                    offset=offset,
                )
            else:
                items_raw, total = self.db.list_for_org_paginated(
                    organization_id=organization_id,
                    metadata_type=metadata_type,
                    event_type=event_type,
                    user_id=user_id,
                    actor_type=actor_type,
                    entity_ids=entity_ids,
                    date_from=date_from_at,
                    date_to=date_to_at,
                    limit=limit,
                    offset=offset,
                )
            items = [self._convert_audit_record_to_response(r) for r in items_raw]
            self._attach_entity_identifiers(items, organization_id)
            self._mask_entity_updated_items(items, actor, organization_id)
            return AuditEventListResponse(
                items=items,
                total=total,
                entity_id=entity_id,
            )
        except (ValidationError, AuthorizationError, NotFoundError):
            raise
        except Exception as exc:
            logger.exception("list_audit_events_for_actor failed")
            raise ServiceError("Unable to list audit events") from exc

    @staticmethod
    def _normalize_date_window(
        date_from: date | datetime | None,
        date_to: date | datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        """Convert date filters to a half-open UTC datetime window."""
        if isinstance(date_from, datetime):
            start_at = date_from
        elif isinstance(date_from, date):
            start_at = datetime.combine(date_from, time.min, tzinfo=UTC)
        else:
            start_at = None

        if isinstance(date_to, datetime):
            end_at = date_to
        elif isinstance(date_to, date):
            end_at = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        else:
            end_at = None

        if start_at and end_at and start_at >= end_at:
            raise ValidationError("date_from must be on or before date_to")
        return start_at, end_at

    @staticmethod
    def _validate_metadata_type(metadata_type: str | list[str] | None) -> None:
        """Reject any `metadata_type` value(s) not in `AuditMetadataType`.

        Fails closed on a mixed valid/invalid list rather than silently dropping
        the invalid entries, so a typo can't quietly narrow results with no signal
        to the caller. This is the single validation choke point for both the
        `GET /audit-events` HTTP path and internal callers (e.g. dashboard's
        activity widget) that call this manager directly with raw strings.
        """
        if metadata_type is None:
            return
        values = metadata_type if isinstance(metadata_type, list) else [metadata_type]
        valid_values = set(AuditMetadataType.list())
        invalid_values = sorted({value for value in values if value not in valid_values})
        if invalid_values:
            raise ValidationError(
                f"Invalid metadata_type value(s): {', '.join(invalid_values)}. "
                f"Valid values: {', '.join(AuditMetadataType.list())}"
            )

    def _check_entity_scope(
        self,
        actor: dict[str, object],
        organization_id: str,
        entity_id: str,
    ) -> None:
        """404 if the entity doesn't exist in the actor's org; 403 if the actor
        lacks "view" permission on the entity's type, or if the actor's granting
        role(s) have a read condition (entity field permission filter) that this
        specific entity doesn't satisfy — an entity a role can't view directly
        must not be readable via its audit trail either, same generic denial as
        a direct entity read.

        No-op beyond the existence check for a system actor — mirrors the
        entities module's own (now-deleted) `_check_entity_permission`.
        `entities_service` and `roles_manager` are required
        dependencies of this manager; a `None` here is a wiring bug in
        `main.py`, not a runtime condition to degrade gracefully around.
        """
        entity = self.entities_service.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id, include_archived=True
        )
        if entity is None:
            raise NotFoundError(f"entity record '{entity_id}' not found")
        if str(actor.get("actor_type") or "").lower() == "system":
            return
        user_id = actor_str(actor, "user_id")
        if not user_id:
            raise ValidationError("Missing actor field: user_id")
        entity_type_name = self.entities_service.get_entity_type_name_by_id(
            organization_id=organization_id, entity_type_id=entity.entity_type_id
        )
        if not entity_type_name:
            return
        access = self.db.check_entity_view_permission(
            roles_manager=self.roles_manager,
            user_id=user_id,
            organization_id=organization_id,
            entity_type_name=entity_type_name,
            action="view",
        )
        if not access.allowed:
            raise AuthorizationError(f"Not allowed to perform 'view' on '{entity_type_name}'")
        if not record_satisfies_any_condition(access.conditions, entity.data, entity_id=entity.entity_id):
            raise AuthorizationError("You do not have permission to view this record.")

    def _attach_entity_identifiers(
        self,
        items: list[AuditEventResponse],
        organization_id: str,
    ) -> None:
        """Fill `entity_identifier` on rows that reference an entity record.

        One batched lookup per page, scoped to the actor's org. Archived records
        are included — an audit trail must still name a record that was since
        archived. Rows whose entity is gone (hard-deleted, or an id from another
        org) keep `entity_identifier=None`; the caller falls back to `entity_id`.

        Identifier resolution is skipped when no row references an entity, or
        when the manager was constructed without an entities service — the
        listing still returns, callers fall back to `entity_id`.
        """
        entity_ids = {item.entity_id for item in items if item.entity_id}
        if not entity_ids or self.entities_service is None:
            return
        records = self.entities_service.list_entity_records_by_ids(
            organization_id=organization_id, entity_ids=entity_ids, include_archived=True
        )
        identifiers = {
            record.entity_id: (record.data or {}).get(IDENTIFIER_FIELD_KEY) for record in records
        }
        archived = {record.entity_id for record in records if record.archived_at is not None}
        for item in items:
            if item.entity_id:
                item.entity_identifier = identifiers.get(item.entity_id)
                item.entity_archived = item.entity_id in archived

    def _mask_entity_updated_items(
        self,
        items: list[AuditEventResponse],
        actor: dict[str, object],
        organization_id: str,
    ) -> None:
        """Redact `changed_fields` on ENTITY_UPDATED rows per the actor's field permissions.

        Mutates `items` in place. Full before/after values are always stored on
        write; masking is applied fresh on every read against the current viewer,
        so permission changes take effect immediately without rewriting history.
        Rows whose `entity_type` couldn't be resolved at write time are redacted
        entirely rather than passed through unmasked — masking must fail closed.
        `roles_manager` is a required dependency of this manager; a `None`
        here is a wiring bug in `main.py`, not a condition to degrade around.
        """
        user_id = actor_str(actor, "user_id") or None
        if not user_id:
            return
        updated_items = [
            item
            for item in items
            if item.metadata_type == AuditMetadataType.ENTITY.value
            and item.event_type == AuditEventType.ENTITY_UPDATED
            and isinstance(item.metadata.get(AuditMetadataKey.CHANGED_FIELDS), dict)
        ]
        if not updated_items:
            return
        for item in updated_items:
            changed_fields = item.metadata[AuditMetadataKey.CHANGED_FIELDS]
            if not item.entity_type:
                item.metadata[AuditMetadataKey.CHANGED_FIELDS] = {
                    field_key: {"before": MASKED_FIELD_VALUE, "after": MASKED_FIELD_VALUE}
                    for field_key in changed_fields
                }
                continue
            item.metadata[AuditMetadataKey.CHANGED_FIELDS] = self._mask_changed_fields(
                user_id, organization_id, item.entity_type, changed_fields
            )

    def _mask_changed_fields(
        self,
        user_id: str,
        org_id: str,
        entity_type_name: str,
        changed_fields: dict[str, object],
    ) -> dict[str, object]:
        """Apply field-level visibility and masking to a changed_fields diff.

        Three-state model per field:
        - Not in visible_fields: remove key entirely
        - In masked_fields: keep key, replace before/after with MASKED_FIELD_VALUE
        - Otherwise: return full before/after values
        """
        visible, masked = self.db.get_visible_and_masked_fields(
            roles_manager=self.roles_manager,
            user_id=user_id,
            organization_id=org_id,
            entity_type_name=entity_type_name,
        )
        result: dict[str, object] = {}
        for field_key, diff in changed_fields.items():
            if visible is not None and field_key not in visible:
                continue
            if field_key in (masked or []):
                result[field_key] = {"before": MASKED_FIELD_VALUE, "after": MASKED_FIELD_VALUE}
            else:
                result[field_key] = diff
        return result

    def get_constants(self) -> AuditConstantsResponse:
        return AuditConstantsResponse(
            metadata_types=AuditMetadataType.list(),
            event_types=AUDIT_EVENT_TYPES,
        )

    @staticmethod
    def _convert_audit_record_to_response(record) -> AuditEventResponse:
        return AuditEventResponse(
            id=record.id,
            organization_id=record.organization_id,
            metadata_type=record.metadata_type,
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            user_id=record.user_id,
            event_type=record.event_type,
            actor_type=record.actor_type,
            actor_id=record.actor_id,
            actor_name=record.actor_name,
            actor_role=record.actor_role,
            correlation_id=record.correlation_id,
            source=record.source,
            before_state=record.before_state,
            after_state=record.after_state,
            metadata=dict(record.metadata or {}),
            event_timestamp=record.event_timestamp,
        )

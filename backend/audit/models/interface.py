"""Interface models and contracts for unified audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from common.data_model import ExtendedStrEnum
from common.enums import AuditMetadataType

_AUDIT_EVENT_TYPES: dict[AuditMetadataType, list[str]] = {
    AuditMetadataType.ENTITY: [
        "STATE_TRANSITIONED",
        "ENTITY_ENROLLED",
        "TASK_EXECUTED",
        "ACTION_STARTED",
        "ACTION_COMPLETED",
        "ACTION_FAILED",
        "ACTION_RETRY_SCHEDULED",
        "ACTION_WAITING_EXTERNAL",
        "ACTION_ALERT",
        "ACTION_NO_TRIGGER",
        "ACTION_CHAIN_SKIPPED",
        "ACTION_CHAIN_STOPPED",
        "ACTION_FORM_SUBMITTED",
        "COMMENT_CREATED",
        "COMMENT_UPDATED",
        "COMMENT_ARCHIVED",
        "REPLY_CREATED",
        "REPLY_ARCHIVED",
        "COMMENT_LIKED",
        "COMMENT_UNLIKED",
        "ENTITY_CREATED",
        "ENTITY_UPDATED",
        "ENTITY_ASSIGNEE_CHANGED",
        "ENTITY_ARCHIVED",
        "ENTITY_RESTORED",
        "GRID_FORM_INSTANCE_UPDATED",
        "GRID_FORM_INSTANCE_POPULATED",
    ],
    AuditMetadataType.TRANSITION: [
        "TRANSITION_SUCCEEDED",
        "TRANSITION_BLOCKED",
        "TRANSITION_CONFLICT",
    ],
    AuditMetadataType.AUTH: [
        "AUTH_LOGIN_SUCCESS",
        "AUTH_LOGIN_FAILED",
        "AUTH_LOGOUT",
        "AUTH_REGISTER",
        "AUTH_PASSWORD_CHANGED",
        "AUTH_GOOGLE_LOGIN",
        "AUTH_GOOGLE_LOGIN_FAILED",
        "AUTH_GOOGLE_ACCOUNT_LINKED",
        "AUTH_PASSWORD_RESET_REQUESTED",
        "AUTH_ACCOUNT_DEACTIVATED",
        "AUTH_ACCOUNT_REACTIVATED",
        "AUTH_USER_APPROVED",
        "AUTH_USER_REJECTED",
        "AUTH_USER_SUSPENDED",
    ],
    AuditMetadataType.SCHEDULE: [
        "SCHEDULE_CREATED",
        "SCHEDULE_UPDATED",
        "SCHEDULE_TARGET_ADDED",
        "SCHEDULE_RUN_REQUESTED",
        "SCHEDULE_RUN_QUEUED",
    ],
}

AUDIT_EVENT_TYPES: dict[str, list[str]] = {
    metadata_type.value: event_types for metadata_type, event_types in _AUDIT_EVENT_TYPES.items()
}


class AuditEventType(ExtendedStrEnum):
    """Event type constants the audit module branches on directly (e.g. masking gates).

    Not exhaustive — most event type strings only ever flow through as opaque
    values sourced from `AUDIT_EVENT_TYPES`. This only holds the ones manager-layer
    logic needs to compare against by name.
    """

    ENTITY_UPDATED = "ENTITY_UPDATED"


class AuditMetadataKey(ExtendedStrEnum):
    """Well-known keys inside the `metadata` JSONB payload."""

    CHANGED_FIELDS = "changed_fields"


# Narrower than `metadata_type=entity`, which also carries action, enrollment
# and comment events.
LOGS_EVENT_TYPES: tuple[str, ...] = (
    "ENTITY_CREATED",
    "ENTITY_UPDATED",
    "ENTITY_ASSIGNEE_CHANGED",
    "ENTITY_ARCHIVED",
)


class AuditEventInput(PydanticBaseModel):
    """One audit event to append — the write-side counterpart to `AuditEventRecord`.

    Mirrors the columns a caller may set, minus the ones the database owns
    (`id`, `event_timestamp`). Cross-module callers build this instead of
    passing loose keywords, so a missing or mistyped field fails where the
    event is constructed rather than inside the persistence layer.
    """

    organization_id: str
    metadata_type: AuditMetadataType
    event_type: str
    actor_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    user_id: str | None = None
    actor_id: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    source: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    before_state: str | None = None
    after_state: str | None = None
    event_metadata: dict[str, Any] | None = None


class AuditEventRecord(PydanticBaseModel):
    """One row in `audit.audit_events` — the unified audit log.

    Captures entity events, transition attempts, auth events, comments, and
    actions. Distinguished by `metadata_type` and `event_type`.
    """

    id: str
    organization_id: str
    metadata_type: AuditMetadataType
    entity_type: str | None = None
    entity_id: str | None = None
    user_id: str | None = None
    event_type: str
    actor_type: str
    actor_id: str | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    source: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    before_state: str | None = None
    after_state: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    event_timestamp: datetime | None = None

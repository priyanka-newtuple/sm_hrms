"""Executor: generic signal executor that runs steps from config_json.

Supports notify, email, and trigger step types. Adding a new signal type
requires only new config — no new executor or action_kind needed.
"""

from __future__ import annotations

import json
from typing import Any

from audit.db_models import AuditEventModel
from common.enums import AuditMetadataType
from common.logger import logger
from entities.db_models import EntityRecordModel
from executor.executors.base import fail, get_field
from executor.models.interface import (
    BaseExecutor,
    ExecutorData,
    ExecutorDefinition,
    ExecutorInput,
    ExecutorResponse,
)
from user.db_models import User

STEP_TYPE_NOTIFY = "notify"
STEP_TYPE_EMAIL = "email"
RECIPIENT_ENTITY_CREATOR = "entity_creator"


class SignalExecutor(BaseExecutor):
    """Generic signal executor — reads behavior from config_json steps array."""

    def __init__(
        self,
        mail_service: Any = None,
        database_service_manager: Any = None,
        config: Any = None,
        notifications_service: Any = None,
    ) -> None:
        self._mail = mail_service
        self._database_service_manager = database_service_manager
        self._config = config
        self._notifications = notifications_service

    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="signal.fire",
            description="Generic signal executor. Runs notify/email/trigger steps from config.",
            supported_outcomes=["completed", "no_recipient_found", "failed"],
        )

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        """Execute all signal steps defined in the config for the given entity."""
        try:
            org_id = get_field(input_payload.fields, "org_id") or ""
            entity_id = input_payload.entity_id
            steps = self._parse_steps(input_payload.fields)
            if not steps:
                return fail("no steps defined in signal config")
            executed = self._run_steps(steps, entity_id, org_id, input_payload.entity_type, db)
            if executed == 0:
                return ExecutorResponse(
                    success=True,
                    message="No steps executed — recipient not found",
                    data=ExecutorData(outcome="no_recipient_found", fields={}, meta={}),
                )
            return ExecutorResponse(
                success=True,
                message=f"Signal executed {executed} step(s)",
                data=ExecutorData(outcome="completed", fields={}, meta={"steps_executed": executed}),
            )
        except Exception as exc:
            logger.error("signal.fire executor failed entity=%s error=%s", input_payload.entity_id, exc)
            return fail(str(exc))

    def _parse_steps(self, fields: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse the steps array from the raw config field."""
        raw = get_field(fields, "_raw_config") or "{}"
        try:
            config = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("signal.fire: failed to parse config_json: %s", exc)
            config = {}
        return config.get("steps", [])

    def _run_steps(self, steps: list[dict[str, Any]], entity_id: str, org_id: str, entity_type: str, db: Any) -> int:
        """Execute all steps and return count of successfully executed steps."""
        executed = 0
        for step in steps:
            try:
                recipient = self._resolve_recipient(step.get("recipient", ""), entity_id, org_id, db)
                if not recipient:
                    logger.warning("signal.fire: could not resolve recipient '%s' for entity %s",
                                   step.get("recipient", ""), entity_id)
                    continue
                if self._execute_step(step, recipient, entity_id, org_id, entity_type, db):
                    executed += 1
            except Exception as exc:
                logger.error("signal.fire: step failed entity=%s error=%s", entity_id, exc)
        return executed

    def _execute_step(self, step: dict[str, Any], recipient: dict[str, Any], entity_id: str, org_id: str, entity_type: str, db: Any) -> bool:
        """Execute a single step. Returns True if step ran successfully."""
        try:
            step_type = step.get("type", "")
            if step_type == STEP_TYPE_NOTIFY and self._notifications and db:
                workflow_id = step.get("workflow_id", "")
                link = f"/pipeline/{workflow_id}?entity={entity_id}" if workflow_id else ""
                self._notifications.create_notification(
                    db=db,
                    organization_id=org_id,
                    recipient_id=str(recipient.get("id", "")),
                    notification_type=step.get("notification_type", "system"),
                    entity_id=entity_id,
                    entity_type=entity_type,
                    actor_id=None,
                    actor_name=None,
                    title=step.get("title", ""),
                    body=step.get("body", ""),
                    link=link,
                )
                return True
            if step_type == STEP_TYPE_EMAIL and self._mail and db:
                return self._send_email(step, recipient, org_id, db)
        except Exception as exc:
            logger.error("signal.fire: _execute_step failed entity=%s step_type=%s error=%s",
                         entity_id, step.get("type", ""), exc)
        return False

    def _send_email(self, step: dict[str, Any], recipient: dict[str, Any], org_id: str, db: Any) -> bool:
        """Send email for a step. Returns True if sent."""
        try:
            email = recipient.get("email", "")
            if not email:
                return False
            name = recipient.get("full_name", "") or "there"
            body_html = step.get("body_html", "") or (
                f"<p>Hi {name},</p><p>{step.get('body', '')}</p>"
            )
            self._mail.send_email(db=db, org_id=org_id, to=email,
                                  subject=step.get("subject", ""), body_html=body_html)
            return True
        except Exception as exc:
            logger.error("signal.fire: _send_email failed to=%s error=%s",
                         recipient.get("email", ""), exc)
            return False

    def _resolve_recipient(self, recipient_spec: str | None, entity_id: str, org_id: str, db: Any) -> dict[str, Any] | None:
        """Resolve recipient spec to a user dict."""
        if not recipient_spec or not db:
            return None
        try:
            if recipient_spec == RECIPIENT_ENTITY_CREATOR:
                return self._resolve_entity_creator(entity_id, org_id, db)
        except Exception as exc:
            logger.warning("signal.fire: failed to resolve recipient '%s': %s", recipient_spec, exc)
        return None

    def _resolve_entity_creator(self, entity_id: str, org_id: str, db: Any) -> dict[str, Any] | None:
        """Resolve entity creator via owner_id, falling back to first entity audit event."""
        try:
            entity = db.query(EntityRecordModel).filter_by(entity_id=entity_id, organization_id=org_id).first()
            user_id = entity.owner_id if entity and entity.owner_id else None
            if not user_id:
                event = (
                    db.query(AuditEventModel)
                    .filter_by(entity_id=entity_id, organization_id=org_id,
                               metadata_type=AuditMetadataType.ENTITY.value)
                    .order_by(AuditEventModel.event_timestamp.asc())
                    .first()
                )
                user_id = event.actor_id if event and event.actor_id else None
            if not user_id:
                return None
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return None
            return {
                "id": str(user.id),
                "email": str(user.email) if user.email else "",
                "full_name": str(user.full_name) if getattr(user, "full_name", None) else "",
            }
        except Exception as exc:
            logger.error("signal.fire: _resolve_entity_creator failed entity=%s error=%s", entity_id, exc)
            return None

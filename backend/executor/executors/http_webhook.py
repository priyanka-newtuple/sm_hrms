"""Executor: call an external system via an approved connector (webhook.http)."""

from __future__ import annotations

from typing import Any

from audit.db_models import AuditEventsModelService
from common.enums import AuditMetadataType
from common.logger import logger
from connectors.db_models import ConnectorsModelService
from connectors.manager import ConnectorCallResult, run_connector_call
from connectors.models.interface import ConnectorStatus
from custom_forms.models.interface import (
    CUSTOM_FORM_RESPONSE_META_KEY,
    CUSTOM_FORM_WRITEBACK_TARGET,
    WRITEBACK_TARGET_META_KEY,
)
from executor.executors.base import fail, get_field
from executor.models.interface import (
    BaseExecutor,
    ExecutorData,
    ExecutorDefinition,
    ExecutorInput,
    ExecutorResponse,
    ExecutorValue,
    ValueKind,
)
from roles.db_models import RolesModelService


class HttpWebhookExecutor(BaseExecutor):
    """Run an approved HTTP connector when an entity enters a state."""

    def __init__(
        self,
        mail_service: Any = None,
        database_service_manager: Any = None,
        config: Any = None,
        notifications_service: Any = None,
    ) -> None:
        self._database_service_manager = database_service_manager
        self._config = config
        self._connectors = ConnectorsModelService(database_service_manager)
        self._audit = AuditEventsModelService(database_service_manager)
        self._notifications = notifications_service
        self._roles = RolesModelService() if database_service_manager else None

    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="webhook.http",
            description="Call an external system via an approved HTTP connector.",
            supported_outcomes=["success", "failed"],
        )

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        """Resolve the connector, make the call, and map the response back onto the entity."""
        try:
            fields = input_payload.fields
            org_id = get_field(fields, "org_id")
            connector_id = get_field(fields, "connector_id")
            if not org_id or not connector_id:
                return fail("missing required field: org_id or connector_id")

            contract = self._connectors.get_connector(connector_id, org_id)
            if contract is None:
                return fail(f"connector '{connector_id}' not found")
            if contract.status == ConnectorStatus.DISABLED:
                return fail(f"connector '{connector_id}' is disabled")

            secrets = self._connectors.get_decrypted_secrets(connector_id, org_id)
            field_values = {key: _field_text(value) for key, value in fields.items()}
            # run_id is stable across retries → de-dupes delivery via the Idempotency-Key header.
            result = run_connector_call(
                contract=contract,
                secrets=secrets,
                field_values=field_values,
                idempotency_key=get_field(fields, "run_id"),
            )

            self._emit_audit(
                org_id=org_id,
                entity_id=input_payload.entity_id,
                entity_type=(contract.entity_types[0] if contract.entity_types else None),
                connector_id=connector_id,
                connector_name=contract.name,
                run_id=get_field(fields, "run_id"),
                result=result,
            )

            if result.status_code in (401, 403):
                self._notify_auth_error(db=db, org_id=org_id, connector_id=connector_id, connector_name=contract.name)

            return self._to_response(
                result,
                writeback_target=get_field(fields, "writeback_target") or "entity",
            )
        except Exception as exc:
            logger.exception(f"webhook.http executor failed entity={input_payload.entity_id}")
            return fail(f"webhook execution error: {exc}")

    def _notify_auth_error(
        self, *, db: Any, org_id: str, connector_id: str, connector_name: str
    ) -> None:
        """Notify users with connector:write that credentials have expired. Never raises."""
        if self._notifications is None or self._roles is None:
            return
        try:
            user_ids = self._roles.get_users_with_permission(db, org_id, "connector:write")
            self._notifications.notify_connector_auth_error(
                db=db,
                organization_id=org_id,
                connector_id=connector_id,
                connector_name=connector_name,
                user_ids=user_ids,
            )
        except Exception:
            logger.exception(f"connector auth-error notification failed connector={connector_id}")

    def _emit_audit(
        self,
        *,
        org_id: str,
        entity_id: str,
        entity_type: str | None,
        connector_id: str,
        connector_name: str,
        run_id: str | None,
        result: Any,
    ) -> None:
        """Write an ACTION_COMPLETED or ACTION_FAILED audit event. Never raises."""
        try:
            event_type = "ACTION_COMPLETED" if result.ok else "ACTION_FAILED"
            metadata: dict[str, Any] = {
                "connector_id": connector_id,
                "connector_name": connector_name,
                "status_code": result.status_code,
            }
            if not result.ok and result.error:
                metadata["error"] = result.error
            if result.ok and result.mapped_fields:
                # Log only the field names written back, not the values (may be sensitive).
                metadata["fields_written"] = list(result.mapped_fields.keys())

            self._audit.emit_audit_event(
                organization_id=org_id,
                metadata_type=AuditMetadataType.ENTITY,
                event_type=event_type,
                actor_type="system",
                entity_id=entity_id,
                entity_type=entity_type,
                source="connector",
                correlation_id=run_id,
                event_metadata=metadata,
            )
        except Exception:
            logger.exception(f"connector audit emit failed entity={entity_id} connector={connector_id}")

    @staticmethod
    def _to_response(
        result: ConnectorCallResult,
        writeback_target: str = "entity",
    ) -> ExecutorResponse:
        """Convert a connector call result into a normalized executor response."""
        if not result.ok:
            return ExecutorResponse(
                success=False,
                message=result.error or "connector call failed",
                data=ExecutorData(
                    outcome="failed",
                    fields={},
                    meta={"status_code": result.status_code, "error": result.error},
                ),
            )
        meta: dict[str, Any] = {"status_code": result.status_code}
        if writeback_target == CUSTOM_FORM_WRITEBACK_TARGET:
            meta[WRITEBACK_TARGET_META_KEY] = CUSTOM_FORM_WRITEBACK_TARGET
            meta[CUSTOM_FORM_RESPONSE_META_KEY] = result.response_json
            return ExecutorResponse(
                success=True,
                message="connector call succeeded",
                data=ExecutorData(outcome="success", fields={}, meta=meta),
            )
        mapped = {key: _to_executor_value(value) for key, value in result.mapped_fields.items()}
        return ExecutorResponse(
            success=True,
            message="connector call succeeded",
            data=ExecutorData(outcome="success", fields=mapped, meta=meta),
        )


def _field_text(value: Any) -> str:
    """Return the string form of an executor field value for placeholder resolution."""
    return str(value.value) if hasattr(value, "value") else str(value)


def _to_executor_value(value: Any) -> ExecutorValue:
    """Wrap a response value in the typed ExecutorValue matching its Python type."""
    if value is None:
        return ExecutorValue(kind=ValueKind.NULL, value=None)
    if isinstance(value, bool):
        return ExecutorValue(kind=ValueKind.BOOLEAN, value=value)
    if isinstance(value, (int, float)):
        return ExecutorValue(kind=ValueKind.NUMBER, value=value)
    if isinstance(value, dict):
        return ExecutorValue(kind=ValueKind.JSON, value=value)
    if isinstance(value, list):
        return ExecutorValue(kind=ValueKind.LIST, value=value)
    return ExecutorValue(kind=ValueKind.TEXT, value=str(value))

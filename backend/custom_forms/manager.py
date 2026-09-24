"""Resolve a record's custom forms.

A dynamic method is a method version with a connector and no fields. It fetches
a form's schema from that connector, once per record (once per state reached, for
a method pinned to several states of one workflow), into
`entities.custom_form_schema` keyed by method id. The answers live beside it in
`entities.custom_form_data`, one flat key per answer (`mapping.value_key`).

Fetching never blocks a record: a connector that fails leaves the form absent.
"""

from __future__ import annotations

from typing import Any

from common.auth import actor_str
from common.logger import logger
from custom_forms.models.interface import (
    MODULE_NAME,
    ConnectorsProtocol,
    EntitiesDbProtocol,
    MethodLibraryDbProtocol,
    WorkflowDbProtocol,
)
from custom_forms.models.response import ConnectorFormPreviewResponse
from custom_forms.services.mapping import (
    answer_keys,
    schema_without_values,
    values_from_sources,
)
from custom_forms.services.payload import validate_grid_payload
from exceptions import AuthorizationError, ModularError, NotFoundError, ValidationError

# Mark which workflow state a cached schema was resolved for, so a method pinned
# to several states of one workflow (the Form Configurator's shared sentinel)
# refetches when that workflow reaches a new one. An entry without the markers
# keeps today's fetch-once behaviour.
RESOLVED_WORKFLOW_KEY = "_resolved_workflow_id"
RESOLVED_STATE_KEY = "_resolved_state_key"


class CustomFormsServiceManager:
    """Fetch, validate and store the forms a record's dynamic methods provide."""

    def __init__(
        self,
        workflow_db_model_service: WorkflowDbProtocol | None = None,
        method_library_db_model_service: MethodLibraryDbProtocol | None = None,
        connectors_service_manager: ConnectorsProtocol | None = None,
        entities_db_model_service: EntitiesDbProtocol | None = None,
    ) -> None:
        self.workflow_db = workflow_db_model_service
        self.method_library_db = method_library_db_model_service
        self.connectors_service_manager = connectors_service_manager
        self.entities_db = entities_db_model_service
        self.module_name = MODULE_NAME
        self._started = False

    def start(self) -> None:
        """Mark the module as started."""
        self._started = True

    def stop(self) -> None:
        """Mark the module as stopped."""
        self._started = False

    def connector_ids_for_state(
        self, *, organization_id: str, workflow_state_machine_id: str, state_key: str
    ) -> dict[str, str]:
        """Which dynamic methods apply here, as {method_id: connector_id}."""
        if self.workflow_db is None or self.method_library_db is None:
            return {}
        found: dict[str, str] = {}
        try:
            pins = self.workflow_db.list_method_pins(
                organization_id=organization_id,
                workflow_state_machine_id=workflow_state_machine_id,
            )
        except ModularError:
            logger.exception("custom forms: could not read method pins")
            return {}

        for pinned_state, method_id, version_id in pins:
            if pinned_state != state_key:
                continue
            connector_id = self._connector_id_for_version(organization_id, version_id)
            if connector_id:
                found[method_id] = connector_id
        return found

    def resolve_for_record(
        self,
        *,
        organization_id: str,
        workflow_state_machine_id: str,
        state_key: str,
        entity_values: dict[str, Any] | None,
        stored: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Fill in any missing form, returning what to store or None."""
        wanted = self.connector_ids_for_state(
            organization_id=organization_id,
            workflow_state_machine_id=workflow_state_machine_id,
            state_key=state_key,
        )
        if not wanted:
            return None

        current = dict(stored or {})
        changed = False
        for method_id, connector_id in wanted.items():
            cached = current.get(method_id)
            if self._serves_state(cached, workflow_state_machine_id, state_key):
                continue
            form = self._fetch_form(
                organization_id=organization_id,
                connector_id=connector_id,
                entity_values=entity_values,
            )
            if form is None:
                # An earlier state's form must not stand in for this one: drop it
                # so the form reads as absent until a fetch succeeds.
                if isinstance(cached, dict) and RESOLVED_STATE_KEY in cached:
                    del current[method_id]
                    changed = True
                continue
            current[method_id] = {
                **schema_without_values(form),
                RESOLVED_WORKFLOW_KEY: workflow_state_machine_id,
                RESOLVED_STATE_KEY: state_key,
            }
            changed = True
        return current if changed else None

    @staticmethod
    def _serves_state(cached: Any, workflow_state_machine_id: str, state_key: str) -> bool:
        """Whether a stored schema may serve this workflow state without a refetch: unmarked
        entries and another enrolment's form always do, a marked one only on its own state."""
        if not isinstance(cached, dict):
            return bool(cached)
        if RESOLVED_STATE_KEY not in cached:
            return True
        if cached.get(RESOLVED_WORKFLOW_KEY) != workflow_state_machine_id:
            return True
        return cached.get(RESOLVED_STATE_KEY) == state_key

    def answer_keys_for_record(
        self, *, custom_form_schema: dict[str, Any] | None
    ) -> set[str]:
        """Every answer key the record's stored schemas declare."""
        keys: set[str] = set()
        for schema in (custom_form_schema or {}).values():
            if isinstance(schema, dict):
                keys |= answer_keys(schema)
        return keys

    def apply_connector_data(
        self, *, organization_id: str, entity_id: str, fetched: Any
    ) -> tuple[list[str], list[str]]:
        """Fill this record's custom form answers from a results body.

        Returns (written_keys, unresolved_sources) for the audit trail. The
        answers are ordinary data fields, and a key already holding a value is
        left alone, so a figure someone entered is never overwritten by a later
        run of the same action.
        """
        if self.entities_db is None:
            logger.error("custom form write-back: entities service is not wired")
            raise ValidationError("custom forms: entities service is not wired")

        record = self.entities_db.get_entity_record_by_id(
            organization_id=organization_id, entity_id=entity_id
        )
        schemas = (record.custom_form_schema if record else None) or {}
        if not schemas:
            logger.warning(
                "custom form write-back: entity %s has no form schema to fill", entity_id
            )
            return [], []

        existing = dict(record.custom_form_data or {}) if record else {}
        values: dict[str, Any] = {}
        unresolved: list[str] = []
        for schema in schemas.values():
            if not isinstance(schema, dict):
                continue
            resolved, misses = values_from_sources(schema, fetched, existing)
            values.update(resolved)
            unresolved.extend(misses)

        if values:
            self.entities_db.merge_custom_form_data(
                organization_id=organization_id, entity_id=entity_id, values=values
            )
        logger.info(
            "custom form write-back: entity=%s wrote=%d unresolved=%d",
            entity_id,
            len(values),
            len(unresolved),
        )
        return sorted(values), unresolved

    def resolve_connector_form_for_actor(
        self,
        actor: dict[str, Any],
        organization_id: str,
        method_version_id: str,
        entity_values: dict[str, Any] | None,
    ) -> ConnectorFormPreviewResponse:
        """Preview one dynamic method version's connector form before any record exists.

        Keyed by the method version rather than a raw connector id, so preview
        only ever runs a connector that is actually wired to a dynamic form —
        the same check `connector_ids_for_state` already applies on read.
        """
        self._authorize(actor, organization_id)
        connector_id = self._connector_id_for_version(organization_id, method_version_id)
        if connector_id is None:
            raise NotFoundError(f"method version '{method_version_id}' has no connector to preview")
        form = self._fetch_form(
            organization_id=organization_id,
            connector_id=connector_id,
            entity_values=entity_values,
        )
        if form is None:
            raise NotFoundError(f"connector '{connector_id}' returned no usable form")
        return ConnectorFormPreviewResponse(form=schema_without_values(form))

    def _connector_id_for_version(self, organization_id: str, version_id: str) -> str | None:
        """The connector on one method version, when that version has no fields."""
        try:
            fields = self.method_library_db.list_version_fields(
                organization_id=organization_id, method_version_id=version_id
            )
        except ModularError:
            logger.exception(f"custom forms: could not read fields of version {version_id}")
            return None
        if fields:
            return None
        version = self._version(organization_id, version_id)
        connector_id = getattr(version, "connector_id", None) if version else None
        return str(connector_id) if connector_id else None

    def _version(self, organization_id: str, version_id: str) -> Any:
        """One method version, or None when it cannot be read."""
        try:
            return self.method_library_db.get_version(
                organization_id=organization_id, version_id=version_id
            )
        except ModularError:
            logger.exception(f"custom forms: could not read version {version_id}")
            return None

    def _fetch_form(
        self,
        *,
        organization_id: str,
        connector_id: str,
        entity_values: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Call one connector for one record and validate what comes back."""
        if self.connectors_service_manager is None:
            logger.error("custom forms: connectors manager dependency is not configured")
            return None
        placeholders = {
            str(key): str(value)
            for key, value in (entity_values or {}).items()
            if value is not None and not isinstance(value, (dict, list))
        }
        try:
            result = self.connectors_service_manager.run_for_entity(
                organization_id=organization_id,
                connector_id=connector_id,
                entity_values=placeholders,
            )
        except ModularError:
            logger.exception(f"custom forms: connector {connector_id} call failed")
            return None
        if result is None or not getattr(result, "ok", False):
            error = getattr(result, "error", None) if result is not None else "no result"
            logger.warning(
                f"custom forms: connector {connector_id} returned no usable form: {error}"
            )
            return None
        try:
            return validate_grid_payload(result.response_json)
        except ValidationError as exc:
            logger.error(
                f"custom forms: connector {connector_id} returned an invalid form: {exc}"
            )
            return None

    def _authorize(self, actor: dict[str, Any], organization_id: str) -> None:
        """Ensure the actor may operate within the requested organization scope."""
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_organization_id:
            logger.error(
                f"custom forms org scope mismatch actor_org={actor_organization_id} requested_org={organization_id}"
            )
            raise AuthorizationError("Forbidden organization scope")

    @staticmethod
    def _require_actor_field(actor: dict[str, Any], field_name: str) -> str:
        value = actor_str(actor, field_name)
        if not value:
            logger.error(f"actor missing required field: {field_name}")
            raise AuthorizationError(f"Actor missing required field: {field_name}")
        return value

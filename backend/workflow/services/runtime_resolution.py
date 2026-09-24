"""Resolve which workflow definition and entity state a runtime request is actually operating on.

This capability answers "what is true right now" and nothing else: no authorization, no
mutation, no evaluation, no audit. Those stay in `workflow/manager.py`, which sequences them.

The rule worth stating plainly, because everything else here exists to serve it: an entity
enrolled in a workflow keeps running the exact definition it was enrolled into. A newer active
version does not pull in-flight records forward — their current state may not even exist in the
new definition. The active version is only a fallback, for when there is no usable enrolled row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.logger import logger
from exceptions import NotFoundError, ValidationError
from workflow.models.interface import (
    UNENROLLED_PLACEHOLDER_STATE,
    EntityState,
    EntityTypeSentinel,
)

if TYPE_CHECKING:
    from entities.manager import EntitiesServiceManager
    from workflow.db_models import WorkflowModelService
    from workflow.models.interface import StateMachineRecord


class RuntimeResolutionService:
    """Resolves workflow versions, entity types and entity-state context for runtime requests."""

    def __init__(
        self,
        workflow_db: WorkflowModelService,
        entities_service_manager: EntitiesServiceManager,
    ) -> None:
        """Store the workflow definition reader and the entities module's public read API."""
        self.workflow_db = workflow_db
        self.entities_service_manager = entities_service_manager

    # ── workflow version resolution ──────────────────────────────────────────

    def resolve_runtime_workflow(
        self,
        organization_id: str,
        machine_name: str,
        entity_state: EntityState | None,
        enrolled_machine: StateMachineRecord | None = None,
    ) -> StateMachineRecord:
        """Resolve the workflow version a runtime request should execute against.

        `enrolled_machine` lets a caller that already loaded the enrolled workflow row pass it in
        rather than have it read a second time in the same request.
        """
        if entity_state is not None and entity_state.workflow_id:
            enrolled = enrolled_machine or self.workflow_db.get_state_machine_by_row_id(
                organization_id=organization_id, row_id=entity_state.workflow_id
            )
            if enrolled is not None:
                return enrolled
        resolved_name = entity_state.machine_name if entity_state else machine_name
        machine = self.workflow_db.get_active_state_machine(
            organization_id=organization_id, machine_name=resolved_name
        )
        if machine is None:
            logger.warning(
                "active workflow not found: %s",
                resolved_name,
                extra={"organization_id": organization_id, "machine_name": resolved_name},
            )
            raise NotFoundError(f"active workflow '{resolved_name}' was not found")
        return machine

    # ── entity type resolution ───────────────────────────────────────────────

    def resolve_entity_type_id(self, organization_id: str, entity_type_name: str) -> str:
        """Look up entity_type_id from the canonical registry by display name.

        Returns "" for the unassigned placeholder — workflows can be saved without configuring a
        real entity type, and viewing them should not crash. Callers must handle the empty-string
        sentinel as "no entity type bound".
        """
        if not entity_type_name or entity_type_name == EntityTypeSentinel.UNASSIGNED:
            return ""
        record = self.entities_service_manager.get_entity_type_record(
            organization_id=organization_id, name=entity_type_name
        )
        if record is None:
            logger.warning(
                "entity_type not registered: %s",
                entity_type_name,
                extra={"organization_id": organization_id, "entity_type_name": entity_type_name},
            )
            raise ValidationError(
                f"entity_type '{entity_type_name}' is not registered "
                f"for organization '{organization_id}'"
            )
        return record.entity_type_id

    def lookup_entity_type_name(self, organization_id: str, entity_type_id: str) -> str:
        """Reverse-lookup the registry name for an entity_type_id, or "" when unknown."""
        return (
            self.entities_service_manager.get_entity_type_name(
                organization_id=organization_id, entity_type_id=entity_type_id
            )
            or ""
        )

    # ── entity state hydration ───────────────────────────────────────────────
    #
    # Both entry points below share `_hydrate`, on purpose: they previously duplicated the
    # build and silently disagreed, the write path omitting owner_id, assignee_id and
    # archived_at from an otherwise identical view. Keep them sharing one core.

    def hydrate_entity_state(
        self,
        organization_id: str,
        entity_id: str,
        *,
        include_archived: bool = False,
    ) -> EntityState | None:
        """Build a denormalized `EntityState` view from runtime tables.

        Returns None when the runtime entity does not exist, or when it is archived and
        `include_archived` is False. When the entity exists but is not enrolled in any workflow,
        returns a placeholder view with `machine_name=""` / `current_state="CREATED"` to mirror
        the legacy unenrolled-but-tracked semantic. Archived rows always carry `archived_at` so
        callers can render a banner.
        """
        view, _state_id, _workflow_id, _machine = self._hydrate(
            organization_id, entity_id, include_archived=include_archived
        )
        return view

    def hydrate_transition_context(
        self,
        organization_id: str,
        entity_id: str,
        *,
        workflow_id: str | None = None,
    ) -> tuple[EntityState | None, str | None, str | None, StateMachineRecord | None]:
        """Hydrate for a write, returning `(view, state_id, workflow_id, enrolled_machine)`.

        Transition writes need the view (for code paths reading `current_state`/`data`), the
        synthetic state_id (for the optimistic-lock UPDATE on `runtime.entity_state`), and the
        enrolled workflow record, which this already read to fill in machine name and version.
        Handing that record back lets `resolve_runtime_workflow` skip a second fetch of the same
        row in the same request.
        """
        return self._hydrate(organization_id, entity_id, workflow_id=workflow_id)

    def _hydrate(
        self,
        organization_id: str,
        entity_id: str,
        *,
        include_archived: bool = False,
        workflow_id: str | None = None,
    ) -> tuple[EntityState | None, str | None, str | None, StateMachineRecord | None]:
        """Read the entity, its enrollments and its type name, and build the state view.

        Returns `(view, state_id, workflow_id, enrolled_machine)`; the three identifiers are
        None when the entity is enrolled nowhere. The first enrollment row is treated as the
        primary one, which is what `workflow_id` narrows when an entity sits in several.
        """
        record = self.entities_service_manager.get_entity_record(
            organization_id=organization_id,
            entity_id=entity_id,
            include_archived=include_archived,
        )
        if record is None:
            return None, None, None, None

        states = self.entities_service_manager.list_entity_states_for_entity(
            organization_id=organization_id, entity_id=entity_id, workflow_id=workflow_id
        )
        entity_type_name = self.lookup_entity_type_name(organization_id, record.entity_type_id)

        common = self._record_fields(record, entity_type_name, organization_id)

        if not states:
            return self._unenrolled_view(common), None, None, None

        primary = states[0]
        machine = self.workflow_db.get_state_machine_by_row_id(
            organization_id=organization_id, row_id=primary.workflow_id
        )
        return (
            self._enrolled_view(primary, machine, common),
            primary.state_id,
            primary.workflow_id,
            machine,
        )

    @staticmethod
    def _record_fields(
        record: object, entity_type_name: str, organization_id: str
    ) -> dict[str, object]:
        """The view fields that come from the entity record, whatever its enrollment state.

        Shared by both views on purpose: the write path used to omit owner_id, assignee_id and
        archived_at, so the same entity read differently depending on which path asked.
        """
        return {
            "entity_id": record.entity_id,
            "entity_type": entity_type_name,
            "organization_id": organization_id,
            "owner_id": record.owner_id,
            "assignee_id": record.assignee_id,
            "due_date": record.due_date,
            "data": dict(record.data),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "archived_at": record.archived_at,
        }

    @staticmethod
    def _unenrolled_view(common: dict[str, object]) -> EntityState:
        """The synthetic view for an entity that exists but is enrolled nowhere."""
        return EntityState(
            machine_name="",
            machine_version=0,
            current_state=UNENROLLED_PLACEHOLDER_STATE,
            state_version=0,
            state_entered_at=None,
            last_transition_at=None,
            sla_due_at=None,
            **common,
        )

    @staticmethod
    def _enrolled_view(
        primary: object, machine: StateMachineRecord | None, common: dict[str, object]
    ) -> EntityState:
        """The view for an enrolled entity, from its state row and enrolled workflow.

        A missing `machine` is not an error here: the enrolled row can outlive the workflow
        version it points at, and the caller decides what to do about that.
        """
        return EntityState(
            machine_name=machine.machine_name if machine else "",
            machine_version=machine.version if machine else 0,
            workflow_id=primary.workflow_id,
            current_state=primary.current_state,
            state_version=primary.state_version,
            state_entered_at=primary.state_entered_at,
            last_transition_at=primary.last_transition_at,
            sla_due_at=primary.sla_due_at,
            **common,
        )

"""Business logic manager for action definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from common.enums import ModuleStatus
from exceptions import NotFoundError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from actions.db_models import ActionsModelService


class ActionsServiceManager:
    """Read-only manager for action definitions and action runs.

    Stateless — each method receives the per-request DB session as a parameter.
    Sessions are owned and closed by the controller.
    """

    def __init__(
        self,
        actions_db_model_service: ActionsModelService,
        database_service_manager: Any = None,
        config: Any = None,
        auth_service_manager: Any = None,
        *dependencies: Any,
    ) -> None:
        """Store the DB model service; unused dependencies accepted for interface compatibility."""
        _ = database_service_manager, config, auth_service_manager, dependencies
        self.db = actions_db_model_service
        self.module_name = "actions"
        self._started = False

    def start(self) -> None:
        """Mark the service as started."""
        self._started = True

    def stop(self) -> None:
        """Mark the service as stopped."""
        self._started = False

    def get_status(self) -> dict[str, object]:
        """Return the current module status."""
        return {
            "module": self.module_name,
            "status": ModuleStatus.READY.value,
            "started": self._started,
        }

    # ── Action Definitions ────────────────────────────────────────────────────

    def list_action_definitions(
        self, db: Session, org_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return action definitions visible to the given org (global + org-scoped)."""
        return self.db.list_action_definitions(db, org_id=org_id)

    def get_action_definition_by_kind(self, db: Session, kind: str) -> dict[str, Any]:
        """Return a single action definition by kind, raising NotFoundError if missing."""
        row = self.db.get_action_definition_by_kind(db, kind)
        if row is None:
            raise NotFoundError(f"action definition '{kind}' not found")
        return row

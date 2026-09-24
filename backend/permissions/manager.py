"""Business logic manager for the global permission catalog."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from common.logger import logger
from exceptions import PersistenceError, ServiceError
from permissions.models.response import PermissionRead

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from permissions.db_models import Permission, PermissionsModelService


class PermissionsServiceManager:
    """Orchestrate permission catalog reads.

    Stateless — each method receives the per-request DB session as a parameter.
    Sessions are owned and closed by the controller.
    """

    def __init__(
        self,
        permissions_db_model_service: PermissionsModelService,
        database_service_manager: Any = None,
        config: Any = None,
        auth_service_manager: Any = None,
    ) -> None:
        _ = database_service_manager, config, auth_service_manager
        if permissions_db_model_service is None:
            raise ServiceError("permissions persistence dependency is not configured")
        self.db = permissions_db_model_service
        self.module_name = "permissions"
        self._started = False

    def start(self) -> None:
        """Mark the service as started."""
        self._started = True

    def stop(self) -> None:
        """Mark the service as stopped."""
        self._started = False

    # ── Response builder ──────────────────────────────────────────────────────

    @staticmethod
    def _to_read(permission: Permission) -> PermissionRead:
        """Convert a Permission ORM object to a PermissionRead response model."""
        return PermissionRead(
            id=permission.id,
            key=permission.key,
            resource=permission.resource,
            action=permission.action,
            description=permission.description,
            is_system=permission.is_system,
        )

    # ── Catalog ───────────────────────────────────────────────────────────────

    def list_permissions(self, db: Session) -> list[PermissionRead]:
        """Return the seeded backend permission catalog."""
        try:
            permissions = self.db.list_permissions(db)
            return [self._to_read(p) for p in permissions]
        except PersistenceError:
            raise
        except Exception as exc:
            logger.exception(f"permissions.manager.list_permissions failed: {exc}")
            raise ServiceError(f"Unable to list permissions: {exc}")

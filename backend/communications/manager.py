"""Business logic manager for communications."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from common.auth import actor_str
from common.enums import ModuleStatus, NotificationChannel, NotificationStatus
from communications.models.request import NotificationCreateRequest
from communications.models.response import (
    CollaborationStatusResponse,
    NotificationCreateResponse,
)
from exceptions import AuthorizationError, ServiceError, ValidationError

if TYPE_CHECKING:
    from auth.models.response import AccessCheckResponse
    from communications.db_models import CommunicationsModelService
    from database.manager import DatabaseServiceManager


class AuthAccessService(Protocol):
    def check_access(self, payload: dict[str, object]) -> AccessCheckResponse:
        """Return an authorization decision for the given payload."""
        ...


class CommunicationsServiceManager:
    """Collaboration orchestration service."""

    def __init__(
        self,
        communications_db_model_service: CommunicationsModelService,
        database_service_manager: DatabaseServiceManager | None,
        config: object | None,
        auth_service_manager: AuthAccessService | None = None,
        *dependencies: object,
    ) -> None:
        self.communications_db_model_service = communications_db_model_service
        self.db_model_service = communications_db_model_service
        self.model_service = communications_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.dependencies = list(dependencies)
        self.module_name = "communications"
        self._started = False
        self.auth_service_manager = auth_service_manager or self._resolve_identity_service(
            dependencies
        )

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_status(self) -> CollaborationStatusResponse:
        return CollaborationStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    def create_notification(
        self,
        request: NotificationCreateRequest | dict[str, object],
    ) -> NotificationCreateResponse:
        try:
            notification_request = (
                request
                if isinstance(request, NotificationCreateRequest)
                else NotificationCreateRequest.model_validate(request)
            )
            record = self.db_model_service.create_notification(notification_request)
            return NotificationCreateResponse(
                notification_id=record.notification_id,
                recipient_id=record.recipient_id,
                organization_id=record.organization_id,
                template=record.template,
                status=NotificationStatus(record.status),
                channel=NotificationChannel(record.channel),
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except Exception as exc:
            raise ServiceError(f"Unable to create notification: {exc}") from exc

    def create_notification_for_actor(
        self,
        actor: dict[str, object],
        request: NotificationCreateRequest,
    ) -> NotificationCreateResponse:
        organization_id = request.organization_id or self._require_actor_field(
            actor, "organization_id"
        )
        self._authorize_actor_operation(actor, "notification", "write", organization_id)
        normalized_request = NotificationCreateRequest(
            recipient_id=request.recipient_id,
            organization_id=organization_id,
            template=request.template,
            payload=dict(request.payload),
        )
        return self.create_notification(normalized_request)

    def _authorize_actor_operation(
        self,
        actor: dict[str, object],
        resource: str,
        action: str,
        organization_id: str,
    ) -> None:
        actor_organization_id = self._require_actor_field(actor, "organization_id")
        if organization_id != actor_organization_id:
            raise AuthorizationError("Forbidden organization scope")

    @staticmethod
    def _resolve_identity_service(dependencies: tuple[object, ...]) -> AuthAccessService | None:
        for dependency in dependencies:
            if hasattr(dependency, "check_access"):
                return cast("AuthAccessService", dependency)
        return None

    @staticmethod
    def _require_actor_field(actor: dict[str, object], field_name: str) -> str:
        value = actor_str(actor, field_name)
        if not value:
            raise ValidationError(f"Missing actor field: {field_name}")
        return value

"""Integrations REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from common.auth import require_permission
from common.logger import logger, tracer
from common.utils import raise_http_error
from exceptions import NotFoundError
from integrations.models.request import (
    ConnectIntegrationRequest,
    ListCalendarEventsRequest,
    ScheduleCalendarEventRequest,
    SendTestEmailRequest,
    SetCapabilityDefaultRequest,
    UpsertOrganizationIntegrationRequest,
    ValidateOrganizationIntegrationRequest,
)
from integrations.models.response import (
    CalendarEventResponse,
    CalendarEventsListResponse,
    CapabilityDefaultResponse,
    CapabilityDefaultsListResponse,
    IntegrationConnectionResponse,
    IntegrationConnectionsListResponse,
    IntegrationDefinitionsListResponse,
    IntegrationsCalendarStatusResponse,
    IntegrationValidationResponse,
    OrganizationIntegrationResponse,
    OrganizationIntegrationsListResponse,
    TestEmailResponse,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from integrations.manager import IntegrationsServiceManager
    from mail.manager import MailServiceManager

IntegrationReadActor = Annotated[dict[str, object], Depends(require_permission("integration", "read"))]
IntegrationWriteActor = Annotated[dict[str, object], Depends(require_permission("integration", "write"))]


class IntegrationsRestController:
    """Implements integrations REST controller."""

    def __init__(
        self,
        integrations_service_manager: IntegrationsServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        self.integrations_service_manager = integrations_service_manager
        self.manager = integrations_service_manager
        self.database_service_manager = database_service_manager
        self.current_db = (
            database_service_manager.postgres_db_service()
            if database_service_manager and hasattr(database_service_manager, "postgres_db_service")
            else None
        )
        self.current_db_engine = getattr(self.current_db, "engine", None)
        self.auth_service_manager = auth_service_manager
        # Back-linked in the composition root after the mail manager is built,
        # so the test-email route can reuse the shared email send path.
        self.mail_service_manager: MailServiceManager | None = None

    def _get_db(self):
        """Yield a request-scoped SQLAlchemy session bound to the shared Postgres engine."""
        engine = self.database_service_manager.postgres_db_service().engine
        session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "IntegrationsRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Prepare the integrations REST controller."""
        route_dependencies = self._route_dependencies(security)
        get_db = self._get_db

        @app.get(
            "/integrations/status",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=IntegrationsCalendarStatusResponse,
            dependencies=route_dependencies,
        )
        def status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.status"):
                try:
                    logger.info("integrations status requested", extra={"request_id": request_id})
                    return self.integrations_service_manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "status"))

        @app.get(
            "/integrations_calendar/status",
            status_code=status.HTTP_200_OK,
            tags=["integrations_calendar"],
            response_model=IntegrationsCalendarStatusResponse,
            dependencies=route_dependencies,
        )
        def legacy_status_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.legacy_status"):
                try:
                    logger.info(
                        "integrations_calendar status requested", extra={"request_id": request_id}
                    )
                    return self.integrations_service_manager.get_status()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "legacy_status"))

        @app.get(
            "/integrations/definitions",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=IntegrationDefinitionsListResponse,
            dependencies=route_dependencies,
        )
        def list_definitions_endpoint(request: Request):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.list_definitions"):
                try:
                    logger.info(
                        "integrations definitions requested", extra={"request_id": request_id}
                    )
                    return self.integrations_service_manager.list_definitions()
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_definitions"))

        @app.get(
            "/integrations/organizations/{organization_id}",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=OrganizationIntegrationsListResponse,
            dependencies=route_dependencies,
        )
        def list_organization_integrations_endpoint(
            request: Request,
            organization_id: str,
            actor: IntegrationReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.list_org_integrations"):
                try:
                    logger.info("integrations org list requested", extra={"request_id": request_id})
                    return (
                        self.integrations_service_manager.list_organization_integrations_for_actor(
                            actor,
                            organization_id,
                        )
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "list_organization_integrations")
                    )

        @app.get(
            "/integrations/organizations/{organization_id}/defaults",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=CapabilityDefaultsListResponse,
            dependencies=route_dependencies,
        )
        def list_capability_defaults_endpoint(
            request: Request,
            organization_id: str,
            actor: IntegrationReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.list_defaults"):
                try:
                    logger.info("integrations defaults requested", extra={"request_id": request_id})
                    return self.integrations_service_manager.list_capability_defaults_for_actor(
                        actor, organization_id
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "list_capability_defaults")
                    )

        @app.put(
            "/integrations/organizations/{organization_id}/defaults/{capability}",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=CapabilityDefaultResponse,
            dependencies=route_dependencies,
        )
        def set_capability_default_endpoint(
            request: Request,
            organization_id: str,
            capability: str,
            payload: SetCapabilityDefaultRequest,
            actor: IntegrationWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.set_default"):
                try:
                    logger.info("integrations set_default", extra={"request_id": request_id})
                    return self.integrations_service_manager.set_capability_default_for_actor(
                        actor,
                        organization_id,
                        capability,
                        payload,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "set_capability_default"))

        @app.get(
            "/integrations/organizations/{organization_id}/{provider}",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=OrganizationIntegrationResponse,
            dependencies=route_dependencies,
        )
        def get_organization_integration_endpoint(
            request: Request,
            organization_id: str,
            provider: str,
            actor: IntegrationReadActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.get_org_integration"):
                try:
                    logger.info("integrations org get requested", extra={"request_id": request_id})
                    response = (
                        self.integrations_service_manager.get_organization_integration_for_actor(
                            actor,
                            organization_id,
                            provider,
                        )
                    )
                    if response is None:
                        raise NotFoundError("Integration not found")
                    return response
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "get_organization_integration")
                    )

        @app.put(
            "/integrations/organizations/{organization_id}/{provider}",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=OrganizationIntegrationResponse,
            dependencies=route_dependencies,
        )
        def upsert_organization_integration_endpoint(
            request: Request,
            organization_id: str,
            provider: str,
            payload: UpsertOrganizationIntegrationRequest,
            actor: IntegrationWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.upsert_org_integration"):
                try:
                    logger.info("integrations org upsert", extra={"request_id": request_id})
                    return (
                        self.integrations_service_manager.upsert_organization_integration_for_actor(
                            actor,
                            organization_id,
                            provider,
                            payload,
                        )
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "upsert_organization_integration")
                    )

        @app.delete(
            "/integrations/organizations/{organization_id}/{provider}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["integrations"],
            dependencies=route_dependencies,
        )
        def delete_organization_integration_endpoint(
            request: Request,
            organization_id: str,
            provider: str,
            actor: IntegrationWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.delete_org_integration"):
                try:
                    logger.info("integrations org delete", extra={"request_id": request_id})
                    deleted = (
                        self.integrations_service_manager.delete_organization_integration_for_actor(
                            actor,
                            organization_id,
                            provider,
                        )
                    )
                    if not deleted:
                        raise NotFoundError("Integration not found")
                    return None
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "delete_organization_integration")
                    )

        @app.post(
            "/integrations/organizations/{organization_id}/{provider}/validate",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=IntegrationValidationResponse,
            dependencies=route_dependencies,
        )
        def validate_organization_integration_endpoint(
            request: Request,
            organization_id: str,
            provider: str,
            payload: ValidateOrganizationIntegrationRequest,
            actor: IntegrationWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.validate_org_integration"):
                try:
                    logger.info("integrations org validate", extra={"request_id": request_id})
                    return self.integrations_service_manager.validate_organization_integration_for_actor(
                        actor,
                        organization_id,
                        provider,
                        payload,
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "validate_organization_integration")
                    )

        @app.post(
            "/integrations/organizations/{organization_id}/{provider}/test-email",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=TestEmailResponse,
            dependencies=route_dependencies,
        )
        def send_test_email_endpoint(
            request: Request,
            organization_id: str,
            provider: str,
            payload: SendTestEmailRequest,
            actor: IntegrationWriteActor,
            db: Session = Depends(get_db),
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.send_test_email"):
                try:
                    logger.info("integrations send test email", extra={"request_id": request_id})
                    normalized_provider = self.integrations_service_manager.authorize_test_email(
                        actor, organization_id, provider
                    )
                    if self.mail_service_manager is None:
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Email service is not available",
                        )
                    # If the form sent config/secrets, test ad-hoc against those
                    # (secrets blank on edit fall back to the saved ones); else
                    # use the org's saved configuration.
                    if payload.config or payload.secrets:
                        merged_secrets = self.integrations_service_manager.merged_secrets_for(
                            organization_id, normalized_provider, payload.config, payload.secrets
                        )
                        return self.mail_service_manager.send_test_email(
                            db,
                            organization_id,
                            payload.to_email,
                            provider=normalized_provider,
                            config=payload.config,
                            secrets=merged_secrets,
                        )
                    return self.mail_service_manager.send_test_email(
                        db,
                        organization_id,
                        payload.to_email,
                        provider=normalized_provider,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "send_test_email"))

        @app.post(
            "/integrations/connect",
            status_code=status.HTTP_201_CREATED,
            tags=["integrations"],
            response_model=IntegrationConnectionResponse,
            dependencies=route_dependencies,
        )
        def connect_integration_endpoint(
            request: Request,
            connect_request: ConnectIntegrationRequest,
            actor: IntegrationWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.connect"):
                try:
                    logger.info("integrations connect", extra={"request_id": request_id})
                    return self.integrations_service_manager.connect_integration_for_actor(
                        actor, connect_request
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "connect_integration"))

        @app.post(
            "/integrations_calendar/connect",
            status_code=status.HTTP_201_CREATED,
            tags=["integrations_calendar"],
            response_model=IntegrationConnectionResponse,
            dependencies=route_dependencies,
        )
        def legacy_connect_integration_endpoint(
            request: Request,
            connect_request: ConnectIntegrationRequest,
            actor: IntegrationWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.legacy_connect"):
                try:
                    logger.info("integrations_calendar connect", extra={"request_id": request_id})
                    return self.integrations_service_manager.connect_integration_for_actor(
                        actor, connect_request
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "legacy_connect_integration")
                    )

        @app.get(
            "/integrations/accounts/{organization_id}",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=IntegrationConnectionsListResponse,
            dependencies=route_dependencies,
        )
        def list_integrations_endpoint(
            request: Request,
            organization_id: str,
            actor: IntegrationReadActor,
            user_id: str | None = None,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.list_accounts"):
                try:
                    logger.info("integrations list_accounts", extra={"request_id": request_id})
                    return self.integrations_service_manager.list_integrations_for_actor(
                        actor, organization_id, user_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_integrations"))

        @app.get(
            "/integrations_calendar/accounts/{organization_id}",
            status_code=status.HTTP_200_OK,
            tags=["integrations_calendar"],
            response_model=IntegrationConnectionsListResponse,
            dependencies=route_dependencies,
        )
        def legacy_list_integrations_endpoint(
            request: Request,
            organization_id: str,
            actor: IntegrationReadActor,
            user_id: str | None = None,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.legacy_list_accounts"):
                try:
                    logger.info(
                        "integrations_calendar list_accounts", extra={"request_id": request_id}
                    )
                    return self.integrations_service_manager.list_integrations_for_actor(
                        actor, organization_id, user_id
                    )
                except Exception as exc:
                    raise_http_error(
                        exc, self._error_context(request_id, "legacy_list_integrations")
                    )

        # TODO(modular-integrations): Move calendar event execution endpoints out of
        # integrations. Keep this route only as a compatibility surface until a
        # dedicated calendar/scheduling execution module owns event creation.
        @app.post(
            "/integrations/events/schedule",
            status_code=status.HTTP_201_CREATED,
            tags=["integrations"],
            response_model=CalendarEventResponse,
            dependencies=route_dependencies,
        )
        def schedule_event_endpoint(
            request: Request,
            event_request: ScheduleCalendarEventRequest,
            actor: IntegrationWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.schedule_event"):
                try:
                    logger.info("integrations schedule_event", extra={"request_id": request_id})
                    return self.integrations_service_manager.schedule_event_for_actor(
                        actor, event_request
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "schedule_event"))

        # TODO(modular-integrations): Remove this legacy alias when calendar/scheduling
        # execution is extracted from integrations.
        @app.post(
            "/integrations_calendar/events/schedule",
            status_code=status.HTTP_201_CREATED,
            tags=["integrations_calendar"],
            response_model=CalendarEventResponse,
            dependencies=route_dependencies,
        )
        def legacy_schedule_event_endpoint(
            request: Request,
            event_request: ScheduleCalendarEventRequest,
            actor: IntegrationWriteActor,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.legacy_schedule_event"):
                try:
                    logger.info(
                        "integrations_calendar schedule_event", extra={"request_id": request_id}
                    )
                    return self.integrations_service_manager.schedule_event_for_actor(
                        actor, event_request
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "legacy_schedule_event"))

        # TODO(modular-integrations): Move calendar event read endpoints out of
        # integrations. Keep this route only as a compatibility surface until a
        # dedicated calendar/scheduling execution module owns event listing.
        @app.get(
            "/integrations/events",
            status_code=status.HTTP_200_OK,
            tags=["integrations"],
            response_model=CalendarEventsListResponse,
            dependencies=route_dependencies,
        )
        def list_events_endpoint(
            request: Request,
            organization_id: str,
            actor: IntegrationReadActor,
            provider: str | None = None,
            user_id: str | None = None,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.list_events"):
                try:
                    logger.info("integrations list_events", extra={"request_id": request_id})
                    return self.integrations_service_manager.list_events_for_actor(
                        actor,
                        ListCalendarEventsRequest(
                            organization_id=organization_id,
                            provider=provider,
                            user_id=user_id,
                        ),
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_events"))

        # TODO(modular-integrations): Remove this legacy alias when calendar/scheduling
        # execution is extracted from integrations.
        @app.get(
            "/integrations_calendar/events",
            status_code=status.HTTP_200_OK,
            tags=["integrations_calendar"],
            response_model=CalendarEventsListResponse,
            dependencies=route_dependencies,
        )
        def legacy_list_events_endpoint(
            request: Request,
            organization_id: str,
            actor: IntegrationReadActor,
            provider: str | None = None,
            user_id: str | None = None,
        ):
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("IntegrationsController.legacy_list_events"):
                try:
                    logger.info(
                        "integrations_calendar list_events", extra={"request_id": request_id}
                    )
                    return self.integrations_service_manager.list_events_for_actor(
                        actor,
                        ListCalendarEventsRequest(
                            organization_id=organization_id,
                            provider=provider,
                            user_id=user_id,
                        ),
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "legacy_list_events"))

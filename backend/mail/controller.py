"""Mail REST controller."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import sessionmaker

from common.auth import require_permission
from common.logger import tracer
from common.utils import raise_http_error
from mail.manager import inbound_email_service

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.params import Depends as DependsParam
    from sqlalchemy.orm import Session

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from mail.manager import MailServiceManager

MailReadActor = Annotated[dict[str, object], Depends(require_permission("email_config", "read"))]
MailWriteActor = Annotated[dict[str, object], Depends(require_permission("email_config", "write"))]
MailTemplateReadActor = Annotated[dict[str, object], Depends(require_permission("email_template", "read"))]
MailTemplateWriteActor = Annotated[dict[str, object], Depends(require_permission("email_template", "write"))]


def build_inbound_email_router(
    session_factory: Callable[[], Session],
    webhook_secret: str = "",
) -> APIRouter:
    """Build the inbound email webhook router."""
    inbound_router = APIRouter(prefix="/api/inbound-email", tags=["inbound-email"])

    def get_db():
        """Yield a request-scoped SQLAlchemy session for inbound webhook handling."""
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    @inbound_router.post("/webhook")
    async def inbound_email_webhook(
        request: Request,
        db: Session = Depends(get_db),
    ):
        """Validate the webhook token and hand the inbound payload to the mail service."""
        if webhook_secret:
            token = request.headers.get("X-Webhook-Token")
            if token != webhook_secret:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid webhook token",
                )

        payload = await request.json()
        return await inbound_email_service.process_inbound_email(db, payload)

    return inbound_router


class MailRestController:
    """Mail configuration controller."""

    def __init__(
        self,
        mail_service_manager: MailServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        """Store the mail manager and optional shared services used by the controller."""
        _ = auth_service_manager
        self.manager = mail_service_manager
        self._database_service_manager = database_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        """Wrap an optional security dependency in the list shape FastAPI expects."""
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        """Build structured error metadata for controller exception handling."""
        return {
            "request_id": request_id,
            "controller": "MailRestController",
            "operation": operation,
        }

    def _get_db(self):
        """Yield a request-scoped SQLAlchemy session bound to the shared Postgres engine."""
        engine = self._database_service_manager.postgres_db_service().engine
        session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register all mail configuration, template, and test routes on the app router."""
        route_dependencies = self._route_dependencies(security)
        get_db = self._get_db

        @app.get(
            "/email-templates",
            status_code=status.HTTP_200_OK,
            tags=["email-templates"],
            dependencies=route_dependencies,
        )
        def list_email_templates(
            request: Request,
            actor: MailTemplateReadActor,
            action_kind: str | None = None,
            db: Session = Depends(get_db),
        ):
            """List email templates visible to the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MailController.list_email_templates"):
                try:
                    return self.manager.list_email_templates(db, str(actor["organization_id"]), action_kind=action_kind)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list_email_templates"))

        @app.get(
            "/email-templates/variables",
            status_code=status.HTTP_200_OK,
            tags=["email-templates"],
            dependencies=route_dependencies,
        )
        def get_template_variables(
            request: Request,
            action_kind: str,
            actor: MailTemplateReadActor,
        ):
            """Return available template variables for a given action kind."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MailController.get_template_variables"):
                try:
                    return self.manager.get_template_variables(action_kind)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_template_variables"))

        @app.post(
            "/email-templates",
            status_code=status.HTTP_201_CREATED,
            tags=["email-templates"],
            dependencies=route_dependencies,
        )
        def create_email_template(
            request: Request,
            actor: MailTemplateWriteActor,
            payload: dict = Body(default={}),
            db: Session = Depends(get_db),
        ):
            """Create a new email template for the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MailController.create_email_template"):
                try:
                    return self.manager.create_email_template(
                        db, str(actor["organization_id"]), payload
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create_email_template"))

        @app.get(
            "/email-templates/{template_id}",
            status_code=status.HTTP_200_OK,
            tags=["email-templates"],
            dependencies=route_dependencies,
        )
        def get_email_template(
            request: Request,
            template_id: str,
            actor: MailTemplateReadActor,
            db: Session = Depends(get_db),
        ):
            """Return one email template by its template identifier."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MailController.get_email_template"):
                try:
                    return self.manager.get_email_template(
                        db, str(actor["organization_id"]), template_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "get_email_template"))

        @app.put(
            "/email-templates/{template_id}",
            status_code=status.HTTP_200_OK,
            tags=["email-templates"],
            dependencies=route_dependencies,
        )
        def update_email_template(
            request: Request,
            template_id: str,
            actor: MailTemplateWriteActor,
            payload: dict = Body(default={}),
            db: Session = Depends(get_db),
        ):
            """Update an email template. System templates require a superadmin."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MailController.update_email_template"):
                try:
                    return self.manager.update_email_template(
                        db, str(actor["organization_id"]), template_id, payload, actor=actor
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "update_email_template"))

        @app.delete(
            "/email-templates/{template_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["email-templates"],
            dependencies=route_dependencies,
        )
        def delete_email_template(
            request: Request,
            template_id: str,
            actor: MailTemplateWriteActor,
            db: Session = Depends(get_db),
        ):
            """Delete an email template owned by the actor's organization."""
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("MailController.delete_email_template"):
                try:
                    self.manager.delete_email_template(
                        db, str(actor["organization_id"]), template_id
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "delete_email_template"))

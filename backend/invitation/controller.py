"""Invitation REST controller — organization invitation endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status

from common.auth import require_permission
from common.deps import get_db
from common.logger import logger, tracer
from common.utils import raise_http_error
from invitation.models.request import InvitationAcceptRequest, InvitationCreateRequest
from invitation.models.response import (
    AcceptInvitationResponse,
    InvitationResponse,
    InvitationValidationResponse,
)

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager
    from invitation.manager import InvitationServiceManager

InvitationWriteActor = Annotated[dict[str, object], Depends(require_permission("user", "write"))]


class InvitationRestController:
    """Invitation management controller.

    Handles creating, listing, validating, accepting, resending, and revoking
    organization invitations. Admin-only except for public validate/accept endpoints.
    """

    def __init__(
        self,
        invitation_service_manager: InvitationServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_manager: AuthServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_manager
        self.manager = invitation_service_manager

    @staticmethod
    def _route_dependencies(security: DependsParam | None) -> list[DependsParam] | None:
        return [security] if security else None

    @staticmethod
    def _error_context(request_id: str, operation: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "controller": "InvitationRestController",
            "operation": operation,
        }

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """Register invitation routes on the provided router."""
        route_dependencies = self._route_dependencies(security)

        @app.get(
            "/invitations/validate",
            response_model=InvitationValidationResponse,
            tags=["invitations"],
        )
        def validate_invitation(
            request: Request,
            token: str = Query(...),
            db: Any = Depends(get_db),
        ) -> InvitationValidationResponse:
            """Validate an invitation token.

            Public endpoint — no authentication required.

            Args:
                request: Incoming FastAPI request.
                token: URL-safe invitation token from the invite email.
                db: Injected database session.

            Returns:
                InvitationValidationResponse with valid flag and metadata.

            Raises:
                HTTPException: 500 on service error, database error, or persistence error.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("InvitationController.validate"):
                try:
                    logger.info("invitations.validate", extra={"request_id": request_id})
                    return self.manager.validate_token(db, token)
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "validate"))

        @app.post(
            "/invitations/accept",
            response_model=AcceptInvitationResponse,
            tags=["invitations"],
        )
        def accept_invitation(
            request: Request,
            payload: InvitationAcceptRequest,
            db: Any = Depends(get_db),
        ) -> AcceptInvitationResponse:
            """Accept an invitation and create or add user to the organization.

            Public endpoint — no authentication required.

            Args:
                payload: Token plus optional full_name and password for new users.
                db: Injected database session.

            Returns:
                AcceptInvitationResponse with the user_id.

            Raises:
                HTTPException 404: Invitation not found.
                HTTPException 400: Validation error (expired, already accepted, etc.).
                HTTPException 500: Service error, database error, or persistence error.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("InvitationController.accept"):
                try:
                    logger.info("invitations.accept", extra={"request_id": request_id})
                    return self.manager.accept_invitation(
                        db,
                        token=payload.token,
                        full_name=payload.full_name,
                        password=payload.password,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "accept"))

        @app.post(
            "/invitations",
            response_model=InvitationResponse,
            status_code=status.HTTP_201_CREATED,
            tags=["invitations"],
            dependencies=route_dependencies,
        )
        def create_invitation(
            request: Request,
            payload: InvitationCreateRequest,
            actor: InvitationWriteActor,
            db: Any = Depends(get_db),
        ) -> InvitationResponse:
            """Create and send an organization invitation. Admin only.

            Args:
                request: Incoming FastAPI request.
                payload: Email and role for the invitee.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: Injected database session.

            Returns:
                InvitationResponse for the created invitation.

            Raises:
                HTTPException 400: Validation error (duplicate, invalid role, etc.).
                HTTPException 500: Service error, database error, or persistence error.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("InvitationController.create"):
                try:
                    logger.info("invitations.create", extra={"request_id": request_id})
                    return self.manager.create_invitation(
                        db,
                        organization_id=str(actor.get("organization_id", "")),
                        email=str(payload.email),
                        role=payload.role,
                        invited_by_user_id=str(actor.get("user_id", "")),
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "create"))

        @app.get(
            "/invitations",
            response_model=list[InvitationResponse],
            tags=["invitations"],
            dependencies=route_dependencies,
        )
        def list_invitations(
            request: Request,
            actor: InvitationWriteActor,
            status_filter: str | None = Query(default=None, alias="status"),
            db: Any = Depends(get_db),
        ) -> list[InvitationResponse]:
            """List invitations for the current organization. Admin only.

            Args:
                request: Incoming FastAPI request.
                status_filter: Optional status to filter by (pending/accepted/expired/revoked).
                db: Injected database session.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).

            Returns:
                List of InvitationResponse objects.

            Raises:
                HTTPException 500: Service error, database error, or persistence error.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("InvitationController.list"):
                try:
                    logger.info("invitations.list", extra={"request_id": request_id})
                    return self.manager.list_invitations(
                        db,
                        organization_id=str(actor.get("organization_id", "")),
                        status=status_filter,
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "list"))

        @app.post(
            "/invitations/{invitation_id}/resend",
            response_model=InvitationResponse,
            tags=["invitations"],
            dependencies=route_dependencies,
        )
        def resend_invitation(
            request: Request,
            invitation_id: str,
            actor: InvitationWriteActor,
            db: Any = Depends(get_db),
        ) -> InvitationResponse:
            """Resend an invitation email with a new token and extended expiry. Admin only.

            Args:
                request: Incoming FastAPI request.
                invitation_id: UUID of the invitation.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: Injected database session.

            Returns:
                Updated InvitationResponse.

            Raises:
                HTTPException 404: Invitation not found.
                HTTPException 400: Invitation is not pending.
                HTTPException 500: Service error, database error, or persistence error.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("InvitationController.resend"):
                try:
                    logger.info("invitations.resend", extra={"request_id": request_id})
                    return self.manager.resend_invitation(
                        db,
                        invitation_id,
                        organization_id=str(actor.get("organization_id", "")),
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "resend"))

        @app.post(
            "/invitations/{invitation_id}/revoke",
            response_model=InvitationResponse,
            tags=["invitations"],
            dependencies=route_dependencies,
        )
        def revoke_invitation(
            request: Request,
            invitation_id: str,
            actor: InvitationWriteActor,
            db: Any = Depends(get_db),
        ) -> InvitationResponse:
            """Revoke a pending invitation. Admin only.

            Args:
                request: Incoming FastAPI request.
                invitation_id: UUID of the invitation.
                actor: Current authenticated actor (must have one of ADMIN_ALLOWED_ROLES).
                db: Injected database session.

            Returns:
                Updated InvitationResponse with revoked status.

            Raises:
                HTTPException 404: Invitation not found.
                HTTPException 400: Invitation is not pending.
                HTTPException 500: Service error, database error, or persistence error.
            """
            request_id = getattr(request.state, "request_id", "unknown")
            with tracer.start_as_current_span("InvitationController.revoke"):
                try:
                    logger.info("invitations.revoke", extra={"request_id": request_id})
                    return self.manager.revoke_invitation(
                        db,
                        invitation_id,
                        organization_id=str(actor.get("organization_id", "")),
                    )
                except Exception as exc:
                    raise_http_error(exc, self._error_context(request_id, "revoke"))

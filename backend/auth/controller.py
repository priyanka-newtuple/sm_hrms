"""Auth REST controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.models.interface import ActorContext
from auth.models.request import (
    ForgotPasswordRequest,
    GoogleAuthCallback,
    MicrosoftAuthCallback,
    MicrosoftIdTokenLogin,
    ResetPasswordRequest,
    TokenRefresh,
    UserLogin,
)
from auth.models.response import (
    GoogleAuthUrl,
    MessageResponse,
    MicrosoftAuthUrl,
    MicrosoftTokenResponse,
    PendingOrgRegistrationResponse,
    RegistrationResponse,
    TokenResponse,
)
from common.deps import get_db
from common.utils import raise_http_error
from user.models.request import UserCreate, UserCreateWithOrg
from user.models.response import UserRead

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from auth.manager import AuthServiceManager
    from database.manager import DatabaseServiceManager


class AuthRestController:
    """Auth REST controller — receives the manager via constructor, registers routes via prepare()."""

    def __init__(
        self,
        auth_service_manager: AuthServiceManager,
        database_service_manager: DatabaseServiceManager | None = None,
        auth_service_provider: AuthServiceManager | None = None,
    ) -> None:
        _ = database_service_manager, auth_service_provider
        self.manager = auth_service_manager

    def prepare(self, app: APIRouter) -> None:
        http_bearer = HTTPBearer()
        auth_router = APIRouter(prefix="/auth", tags=["auth"])

        def get_current_user(
            credentials: HTTPAuthorizationCredentials = Security(http_bearer),
            db: Session = Depends(get_db),
        ) -> Any:
            try:
                return self.manager.resolve_current_user(credentials.credentials, db)
            except Exception as exc:
                raise_http_error(
                    exc,
                    {"controller": "AuthRestController", "operation": "resolve_current_user"},
                )

        # ── Registration ──────────────────────────────────────────────────────

        @auth_router.post(
            "/register",
            response_model=TokenResponse | RegistrationResponse,
            status_code=status.HTTP_201_CREATED,
            responses={
                201: {"description": "User created and immediately active"},
                202: {
                    "description": "User created but pending approval",
                    "model": RegistrationResponse,
                },
            },
        )
        def register(
            payload: UserCreate,
            background_tasks: BackgroundTasks,
            db: Any = Depends(get_db),
        ) -> TokenResponse | RegistrationResponse:
            """Register a new local user with automatic organization assignment."""
            try:
                result, http_status = self.manager.register(
                    payload, db, background_tasks=background_tasks
                )
                if http_status == 202:
                    return JSONResponse(
                        content=result.model_dump(), status_code=status.HTTP_202_ACCEPTED
                    )
                return result
            except Exception as exc:
                raise_http_error(exc, {"controller": "AuthRestController", "operation": "register"})

        @auth_router.post(
            "/register-with-org",
            response_model=PendingOrgRegistrationResponse,
            status_code=status.HTTP_201_CREATED,
            deprecated=True,
        )
        def register_with_organization(
            payload: UserCreateWithOrg,
            background_tasks: BackgroundTasks,
            db: Any = Depends(get_db),
        ) -> PendingOrgRegistrationResponse:
            """Register a new user and create a new organization (deprecated)."""
            try:
                return self.manager.register_with_org(
                    payload, db, background_tasks=background_tasks
                )
            except Exception as exc:
                raise_http_error(
                    exc,
                    {"controller": "AuthRestController", "operation": "register_with_org"},
                )

        # ── Login / Logout ────────────────────────────────────────────────────

        @auth_router.post("/login", response_model=TokenResponse)
        def login(payload: UserLogin, db: Any = Depends(get_db)) -> TokenResponse:
            """Login with email and password."""
            try:
                return self.manager.login(payload, db)
            except Exception as exc:
                raise_http_error(exc, {"controller": "AuthRestController", "operation": "login"})

        @auth_router.post("/refresh", response_model=TokenResponse)
        def refresh_token(payload: TokenRefresh, db: Any = Depends(get_db)) -> TokenResponse:
            """Refresh access token using a refresh token."""
            try:
                return self.manager.refresh_token(payload, db)
            except Exception as exc:
                raise_http_error(
                    exc, {"controller": "AuthRestController", "operation": "refresh_token"}
                )

        @auth_router.post("/logout", response_model=MessageResponse)
        def logout(payload: TokenRefresh, db: Any = Depends(get_db)) -> MessageResponse:
            """Logout and revoke refresh token."""
            try:
                return self.manager.logout(payload, db)
            except Exception as exc:
                raise_http_error(exc, {"controller": "AuthRestController", "operation": "logout"})

        # ── Google OAuth ──────────────────────────────────────────────────────

        @auth_router.get("/google/url", response_model=GoogleAuthUrl)
        def get_google_auth_url(redirect_uri: str | None = None) -> GoogleAuthUrl:
            """Get Google OAuth authorization URL."""
            try:
                return self.manager.get_google_auth_url(redirect_uri)
            except Exception as exc:
                raise_http_error(
                    exc,
                    {"controller": "AuthRestController", "operation": "get_google_auth_url"},
                )

        @auth_router.post(
            "/google/callback",
            response_model=TokenResponse | RegistrationResponse,
            responses={
                200: {"description": "User authenticated successfully"},
                202: {
                    "description": "User created but pending approval",
                    "model": RegistrationResponse,
                },
            },
        )
        async def google_callback(
            payload: GoogleAuthCallback,
            background_tasks: BackgroundTasks,
            db: Any = Depends(get_db),
        ) -> TokenResponse | RegistrationResponse:
            """Exchange Google auth code for tokens."""
            try:
                result, http_status = await self.manager.google_callback(
                    payload, db, background_tasks=background_tasks
                )
                if http_status == 202:
                    return JSONResponse(
                        content=result.model_dump(), status_code=status.HTTP_202_ACCEPTED
                    )
                return result
            except Exception as exc:
                raise_http_error(
                    exc, {"controller": "AuthRestController", "operation": "google_callback"}
                )

        @auth_router.get("/microsoft/url", response_model=MicrosoftAuthUrl)
        def get_microsoft_auth_url(redirect_uri: str | None = None) -> MicrosoftAuthUrl:
            """Get Microsoft OAuth authorization URL and signed state."""
            try:
                return self.manager.get_microsoft_auth_url(redirect_uri)
            except Exception as exc:
                raise_http_error(
                    exc,
                    {"controller": "AuthRestController", "operation": "get_microsoft_auth_url"},
                )

        @auth_router.post(
            "/microsoft/callback",
            response_model=MicrosoftTokenResponse | RegistrationResponse,
            responses={
                200: {"description": "User authenticated successfully"},
                202: {
                    "description": "User created but pending approval",
                    "model": RegistrationResponse,
                },
            },
        )
        async def microsoft_callback(
            payload: MicrosoftAuthCallback,
            background_tasks: BackgroundTasks,
            db: Session = Depends(get_db),
        ) -> MicrosoftTokenResponse | RegistrationResponse:
            """Exchange Microsoft auth code for id_token and app user context."""
            try:
                result, http_status = await self.manager.microsoft_callback(
                    payload, db, background_tasks=background_tasks
                )
                if http_status == 202:
                    return JSONResponse(
                        content=result.model_dump(), status_code=status.HTTP_202_ACCEPTED
                    )
                return result
            except Exception as exc:
                raise_http_error(
                    exc,
                    {"controller": "AuthRestController", "operation": "microsoft_callback"},
                )

        @auth_router.post(
            "/microsoft/id-token-login",
            response_model=MicrosoftTokenResponse | RegistrationResponse,
            responses={
                200: {"description": "User authenticated successfully"},
                202: {
                    "description": "User created but pending approval",
                    "model": RegistrationResponse,
                },
            },
        )
        async def microsoft_id_token_login(
            payload: MicrosoftIdTokenLogin,
            background_tasks: BackgroundTasks,
            db: Session = Depends(get_db),
        ) -> MicrosoftTokenResponse | RegistrationResponse:
            """Log in using a Microsoft ID token a client already obtained from
            its own Microsoft sign-in — no separate authorization-code round
            trip. Requires the token's audience to match this deployment's
            configured Microsoft client_id."""
            try:
                result, http_status = await self.manager.microsoft_id_token_login(
                    payload.id_token, db, background_tasks=background_tasks
                )
                if http_status == 202:
                    return JSONResponse(
                        content=result.model_dump(), status_code=status.HTTP_202_ACCEPTED
                    )
                return result
            except Exception as exc:
                raise_http_error(
                    exc,
                    {"controller": "AuthRestController", "operation": "microsoft_id_token_login"},
                )

        # ── Pending / Remind ──────────────────────────────────────────────────

        @auth_router.post("/remind-admin", response_model=MessageResponse)
        def remind_admin(
            payload: UserLogin,
            background_tasks: BackgroundTasks,
            db: Any = Depends(get_db),
        ) -> MessageResponse:
            """Send a reminder to org admins that a user is still pending approval."""
            try:
                return self.manager.remind_admin(payload, db, background_tasks=background_tasks)
            except Exception as exc:
                raise_http_error(
                    exc, {"controller": "AuthRestController", "operation": "remind_admin"}
                )

        # ── Current user ──────────────────────────────────────────────────────

        @auth_router.get("/me", response_model=UserRead)
        def get_current_user_info(
            current_user: Any = Depends(get_current_user),
        ) -> UserRead:
            """Get current user information."""
            try:
                return self.manager.get_me(current_user)
            except Exception as exc:
                raise_http_error(exc, {"controller": "AuthRestController", "operation": "get_me"})

        # ── Password reset ────────────────────────────────────────────────────

        @auth_router.post("/forgot-password", response_model=MessageResponse)
        def forgot_password(
            payload: ForgotPasswordRequest, db: Any = Depends(get_db)
        ) -> MessageResponse:
            """Request a password reset link (always returns generic message)."""
            try:
                return self.manager.forgot_password(payload, db)
            except Exception as exc:
                raise_http_error(
                    exc, {"controller": "AuthRestController", "operation": "forgot_password"}
                )

        @auth_router.post("/reset-password", response_model=MessageResponse)
        def reset_password(
            payload: ResetPasswordRequest, db: Any = Depends(get_db)
        ) -> MessageResponse:
            """Reset password using token from forgot-password email."""
            try:
                return self.manager.reset_password(payload, db)
            except Exception as exc:
                raise_http_error(
                    exc, {"controller": "AuthRestController", "operation": "reset_password"}
                )

        # ── RBAC / Status ─────────────────────────────────────────────────────

        @auth_router.get("/status")
        def auth_status():
            """Return auth module health status."""
            return self.manager.get_status()

        @auth_router.post("/check")
        def check_access(
            resource: str,
            action: str,
            current_user: Any = Depends(get_current_user),
            organization_id: str | None = None,
            db: Any = Depends(get_db),
        ):
            """Check if the current user has a specific resource:action permission."""
            try:
                actor = ActorContext(
                    user_id=current_user.id,
                    organization_id=current_user.organization_id or "",
                    roles=[current_user.role] if current_user.role else [],
                )
                return self.manager.check_access(
                    actor=actor,
                    resource=resource,
                    action=action,
                    organization_id=organization_id,
                    db=db,
                )
            except Exception as exc:
                raise_http_error(
                    exc, {"controller": "AuthRestController", "operation": "check_access"}
                )

        app.include_router(auth_router, tags=["auth"])

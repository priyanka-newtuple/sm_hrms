"""Business logic manager for the auth module.

AuthServiceManager is instantiated once (stateless) and injected into
AuthRestController. Each method owns its own DB session via SessionLocal,
keeping all database concerns out of the controller layer.
"""

from __future__ import annotations

import base64
import hashlib
import html as html_mod
import re
import secrets
import warnings
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlparse
from uuid import uuid4

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from jose import JWTError, jwt
from starlette import status

from auth.db_models import (
    ApprovalType,
    AuthDBOperations,
    AuthEventType,
    AuthModelService,
    AuthService,
    OrgModelService,
    UserCreationResult,
)
from auth.models.interface import INVITE_PENDING_MESSAGE, ActorContext, PermissionSpec
from auth.models.request import (
    AccessCheckRequest,
    ForgotPasswordRequest,
    GoogleAuthCallback,
    MicrosoftAuthCallback,
    ResetPasswordRequest,
    TokenRefresh,
    UserLogin,
)
from auth.models.response import (
    AccessCheckResponse,
    GoogleAuthUrl,
    IdentityAccessStatusResponse,
    MessageResponse,
    MicrosoftAuthUrl,
    MicrosoftTokenResponse,
    PendingOrgRegistrationResponse,
    RegistrationResponse,
    TokenResponse,
)
from common.configuration import Configuration
from common.logger import logger
from common.security import (
    create_password_reset_token,
    decode_password_reset_token,
    decode_token,
    hash_password,
    verify_password,
)
from exceptions import (
    ConflictError,
    MicrosoftOAuthError,
    NotFoundError,
    ValidationError,
)
from mail.manager import email_service
from mail.models.interface import EmailActionKind
from user.db_models import (
    AuthType as ModularAuthType,
)
from user.db_models import (
    OrganizationStatus,
    UserModelService,
    UserRole,
    UserStatus,
)
from user.models.response import UserPublic, UserRead
from roles.models.request import RoleCreateRequest, RolePermissionCreate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from common.protocols import BackgroundTaskScheduler
    from invitation.manager import InvitationServiceManager
    from user.models.request import UserCreate, UserCreateWithOrg

# Shared in-memory RBAC store (process-scoped singleton)
_rbac_store = AuthModelService()

EMAIL_KIND_PASSWORD_RESET = EmailActionKind.PASSWORD_RESET.value


def get_correlation_id() -> str:
    """Return a request correlation id for auth event logging."""
    return uuid4().hex


class MicrosoftOAuthService:
    SCOPE = "openid profile email offline_access User.Read"
    # Microsoft Entra ID signs v2.0 ID tokens with RSA keys from JWKS.
    # Keep algorithm pinned to RS256 instead of env-driven to avoid insecure/misconfigured alg values.
    ALGORITHM = "RS256"
    _configuration: Configuration | None = None

    @classmethod
    def configure(cls, configuration: Configuration) -> None:
        cls._configuration = configuration

    @classmethod
    def _oauth_configuration(cls):
        if cls._configuration is None:
            raise MicrosoftOAuthError("Microsoft OAuth is not configured")
        return cls._configuration._configuration.microsoft_oauth_configuration

    @classmethod
    def enabled(cls) -> bool:
        return bool(cls._oauth_configuration().enabled)

    @classmethod
    def client_id(cls) -> str:
        return str(cls._oauth_configuration().client_id).strip()

    @classmethod
    def tenant_id(cls) -> str:
        return str(cls._oauth_configuration().tenant_id).strip()

    @classmethod
    def client_secret(cls) -> str:
        return str(cls._oauth_configuration().client_secret).strip()

    @classmethod
    def redirect_uri(cls) -> str:
        return str(cls._oauth_configuration().redirect_uri).strip()

    @classmethod
    def has_client_secret(cls) -> bool:
        """True only when a client secret is configured (else we use PKCE)."""
        return bool(cls.client_secret())

    @classmethod
    def use_pkce(cls) -> bool:
        """Use the public-client (PKCE) flow whenever no real client secret is set."""
        return not cls.has_client_secret()

    @classmethod
    def is_configured(cls) -> bool:
        # Secret is intentionally NOT required — without one we fall back to PKCE.
        return bool(cls.enabled() and cls.client_id() and cls.tenant_id())

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """Return (code_verifier, code_challenge) for an S256 PKCE exchange."""
        verifier = secrets.token_urlsafe(64)  # ~86 chars, within RFC 7636's 43–128
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return verifier, challenge

    @classmethod
    def _tenant_base_url(cls) -> str:
        return f"https://login.microsoftonline.com/{cls.tenant_id()}"

    @classmethod
    def _issuer(cls) -> str:
        return f"{cls._tenant_base_url()}/v2.0"

    @classmethod
    def _authorize_url(cls) -> str:
        return f"{cls._tenant_base_url()}/oauth2/v2.0/authorize"

    @classmethod
    def _token_url(cls) -> str:
        return f"{cls._tenant_base_url()}/oauth2/v2.0/token"

    @classmethod
    def _jwks_url(cls) -> str:
        return f"{cls._tenant_base_url()}/discovery/v2.0/keys"

    @classmethod
    def _state_secret(cls) -> str:
        return str(cls._oauth_configuration().state_secret)

    @classmethod
    def _state_ttl_seconds(cls) -> int:
        ttl = int(getattr(cls._oauth_configuration(), "state_ttl_seconds", 600))
        return ttl if ttl > 0 else 600

    @classmethod
    def generate_state(cls, redirect_uri: str | None = None) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "provider": "microsoft",
            "nonce": secrets.token_urlsafe(16),
            "iat": now,
            "exp": now + timedelta(seconds=cls._state_ttl_seconds()),
        }
        if redirect_uri:
            payload["redirect_uri"] = redirect_uri
        return jwt.encode(payload, cls._state_secret(), algorithm="HS256")

    @classmethod
    def verify_state(cls, state: str, redirect_uri: str | None = None) -> dict[str, Any]:
        try:
            payload = jwt.decode(state, cls._state_secret(), algorithms=["HS256"])
        except JWTError as exc:
            logger.exception("Microsoft OAuth state verification failed")
            raise MicrosoftOAuthError("Invalid state token") from exc

        if payload.get("provider") != "microsoft":
            raise MicrosoftOAuthError("Invalid state provider")

        state_redirect_uri = payload.get("redirect_uri")
        if redirect_uri and state_redirect_uri and state_redirect_uri != redirect_uri:
            raise MicrosoftOAuthError("State redirect URI mismatch")
        return payload

    @classmethod
    def build_authorization_url(
        cls, state: str, redirect_uri: str | None = None, code_challenge: str | None = None
    ) -> str:
        if not cls.is_configured():
            raise MicrosoftOAuthError("Microsoft OAuth is not configured")
        final_redirect_uri = redirect_uri or cls.redirect_uri()
        params = {
            "client_id": cls.client_id(),
            "response_type": "code",
            "redirect_uri": final_redirect_uri,
            "response_mode": "query",
            "scope": cls.SCOPE,
            "state": state,
            "prompt": "select_account",
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{cls._authorize_url()}?{urlencode(params)}"

    @classmethod
    async def exchange_code_for_tokens(
        cls,
        code: str,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        if not cls.is_configured():
            logger.error("Microsoft token exchange attempted while OAuth is not configured")
            raise MicrosoftOAuthError("Microsoft OAuth is not configured")
        final_redirect_uri = redirect_uri or cls.redirect_uri()

        data = {
            "client_id": cls.client_id(),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": final_redirect_uri,
        }
        # Public-client (PKCE) flow: prove possession via code_verifier, never a secret.
        if code_verifier:
            data["code_verifier"] = code_verifier
        elif cls.has_client_secret():
            data["client_secret"] = cls.client_secret()
        else:
            raise MicrosoftOAuthError(
                "Microsoft token exchange requires a client secret or a PKCE verifier"
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(cls._token_url(), data=data)
        if response.status_code != 200:
            logger.error(
                "Microsoft token exchange failed with non-200 response",
                extra={"status_code": response.status_code},
            )
            raise MicrosoftOAuthError("Microsoft token exchange failed")
        payload = response.json()
        if not payload.get("id_token"):
            logger.error("Microsoft token exchange response missing id_token")
            raise MicrosoftOAuthError("Microsoft response missing id_token")
        return payload

    @staticmethod
    def _ensure_bytes(value: str | bytes) -> bytes:
        return value.encode("utf-8") if isinstance(value, str) else value

    @classmethod
    def _decode_jwk_value(cls, value: str | bytes) -> int:
        decoded = base64.urlsafe_b64decode(cls._ensure_bytes(value) + b"==")
        return int.from_bytes(decoded, "big")

    @classmethod
    def _pem_from_jwk(cls, jwk_key: dict[str, str]) -> bytes:
        return (
            RSAPublicNumbers(
                n=cls._decode_jwk_value(jwk_key["n"]),
                e=cls._decode_jwk_value(jwk_key["e"]),
            )
            .public_key(default_backend())
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    @classmethod
    def _select_jwk(cls, jwks: dict[str, Any], kid: str) -> dict[str, str] | None:
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return {
                    "kty": str(key.get("kty", "")),
                    "kid": str(key.get("kid", "")),
                    "use": str(key.get("use", "")),
                    "n": str(key.get("n", "")),
                    "e": str(key.get("e", "")),
                }
        return None

    @classmethod
    def validate_id_token(cls, id_token: str) -> dict[str, Any]:
        if not cls.is_configured():
            raise MicrosoftOAuthError("Microsoft OAuth is not configured")
        try:
            with httpx.Client(timeout=15.0) as client:
                jwks_response = client.get(cls._jwks_url())
        except Exception as exc:
            raise MicrosoftOAuthError("Failed to fetch Microsoft JWKS") from exc

        if jwks_response.status_code != 200:
            raise MicrosoftOAuthError("Failed to fetch Microsoft JWKS")
        jwks = jwks_response.json()

        try:
            header = jwt.get_unverified_header(id_token)
            kid = str(header.get("kid") or "")
            if not kid:
                raise MicrosoftOAuthError("Microsoft token missing kid")
            jwk_key = cls._select_jwk(jwks, kid)
            if not jwk_key:
                raise MicrosoftOAuthError("No matching Microsoft signing key")
            public_key = cls._pem_from_jwk(jwk_key)
            claims = jwt.decode(
                id_token,
                public_key,
                algorithms=[cls.ALGORITHM],
                audience=cls.client_id(),
                issuer=cls._issuer(),
                options={"require_exp": True},
            )
        except JWTError as exc:
            logger.exception("Microsoft id_token validation failed")
            raise MicrosoftOAuthError("Invalid or expired Microsoft token") from exc

        expected_tid = cls.tenant_id()
        token_tid = str(claims.get("tid") or "")
        if expected_tid and token_tid != expected_tid:
            raise MicrosoftOAuthError("Microsoft token tenant mismatch")
        return claims

    @staticmethod
    def extract_identity(claims: dict[str, Any]) -> tuple[str, str, str, str | None]:
        microsoft_id = str(claims.get("oid") or claims.get("sub") or "").strip()
        email = (
            str(claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "")
            .strip()
            .lower()
        )
        full_name = str(claims.get("name") or email.split("@")[0] or "").strip()
        avatar = str(claims.get("picture")).strip() if claims.get("picture") else None
        if not microsoft_id:
            raise MicrosoftOAuthError("Microsoft token missing user identifier")
        if not email:
            raise MicrosoftOAuthError("Microsoft token missing email")
        return microsoft_id, email, full_name, avatar


class AuthServiceManager:
    """Stateless auth business logic manager.

    Instantiated once and injected into AuthRestController.
    Each method receives a per-request SQLAlchemy Session.
    """

    def __init__(
        self,
        rbac: AuthModelService | None = None,
        db_manager: Any = None,
        config: Any = None,
        roles_db_service: Any = None,
        audit_events_service: Any = None,
    ) -> None:
        self.rbac = rbac or _rbac_store
        self.invitation_service_manager: InvitationServiceManager | None = None
        self.db_manager = db_manager
        self.config = config
        self.roles_db_service = roles_db_service
        self.audit_events_service = audit_events_service
        self.notifications_manager = None
        self._mail_service_manager = None
        if isinstance(config, Configuration):
            MicrosoftOAuthService.configure(config)

    # ── PKCE verifier storage (Redis, keyed by the round-tripping state) ─────────

    @staticmethod
    def _render_email_template(text: str, values: dict[str, str]) -> str:
        for key, value in values.items():
            text = text.replace(f"{{{{{key}}}}}", value)
        return text

    @staticmethod
    def _pkce_key(state: str) -> str:
        return f"msoauth:pkce:{hashlib.sha256(state.encode()).hexdigest()}"

    def _pkce_redis(self) -> Any:
        """Return the Redis client used to bridge the PKCE verifier across the
        authorize → callback round-trip, or None if Redis is unavailable."""
        try:
            return self.db_manager.redis_db_service().redis_client
        except Exception:
            logger.exception("PKCE verifier store (Redis) is unavailable")
            return None

    def _stash_pkce_verifier(self, state: str, verifier: str) -> None:
        client = self._pkce_redis()
        if client is None:
            raise MicrosoftOAuthError("PKCE verifier store is unavailable")
        client.set(
            self._pkce_key(state),
            verifier,
            ex=MicrosoftOAuthService._state_ttl_seconds(),
        )

    def _pop_pkce_verifier(self, state: str) -> str | None:
        client = self._pkce_redis()
        if client is None:
            return None
        key = self._pkce_key(state)
        verifier = client.get(key)
        client.delete(key)
        return verifier

    # ── Microsoft Entra role sync ───────────────────────────────────────────────
    #
    # Entra tells us *who* a user is (their app-role values); the platform owns
    # *what* a role can do. On each login we read the `roles` claim, ensure a
    # matching RBAC role exists (auto-created read-only, never a system role), and
    # reconcile the user's sync-managed assignments to exactly match the claim.

    # Marks role assignments created by Entra sync so reconciliation only ever
    # grants/revokes its own rows and never touches manually-assigned roles.
    MICROSOFT_SYNC_ASSIGNED_BY = "microsoft_sync"

    # Read-only baseline granted to an auto-created role. View-only, no admin/
    # sensitive surfaces — an admin grants write/transition permissions later.
    READ_ONLY_BASELINE_PERMISSIONS = (
        "entity_record:read",
        "workflow:read",
        "comment:read",
        "file:read",
        "form:read",
        "projection:read",
    )

    def _create_readonly_role(self, db: Session, org_id: str, value: str) -> Any:
        """Create a read-only, non-system RBAC role for an Entra app-role value."""
        payload = RoleCreateRequest(
            name=value,
            display_name=value,
            description=(
                f"Auto-created from Microsoft Entra app role '{value}'. "
                "Read-only baseline — an admin can grant additional permissions."
            ),
            priority=0,
            permissions=[
                RolePermissionCreate(permission_key=key)
                for key in self.READ_ONLY_BASELINE_PERMISSIONS
            ],
        )
        try:
            return self.roles_db_service.create_role(db, org_id, payload)
        except ValidationError:
            # Lost a create race (or it already exists) — fetch the existing one.
            return self.roles_db_service.get_role_by_name(db, org_id, value)

    def _reconcile_microsoft_roles(
        self, db: Session, user: Any, org: Any, role_values: list[str]
    ) -> bool:
        """Make the user's sync-managed RBAC roles exactly match the Entra claim.

        Auto-creates missing roles (read-only), grants newly-matched roles and
        revokes ones the directory no longer asserts. Returns True if at least
        one role matched (used to skip manual approval).
        """
        org_id = getattr(org, "id", None)
        if not (self.roles_db_service and org_id):
            return False

        matched_role_ids: set[str] = set()
        for raw in role_values:
            value = (raw or "").strip()
            if not value:
                continue
            role = self.roles_db_service.get_role_by_name(db, org_id, value)
            if role is None:
                role = self._create_readonly_role(db, org_id, value)
            if role is not None:
                matched_role_ids.add(role.id)

        current = self.roles_db_service.get_user_roles(db, user.id, org_id)
        current_sync_ids = {
            a.role_id for a in current if a.assigned_by == self.MICROSOFT_SYNC_ASSIGNED_BY
        }

        for role_id in matched_role_ids - current_sync_ids:
            self.roles_db_service.assign_role_to_user(
                db, user.id, org_id, role_id, assigned_by=self.MICROSOFT_SYNC_ASSIGNED_BY
            )
        for role_id in current_sync_ids - matched_role_ids:
            try:
                self.roles_db_service.remove_user_role(db, user.id, org_id, role_id)
            except NotFoundError:
                # Already unassigned (e.g. concurrent login revoked it) — the
                # reconcile goal "role not assigned" is satisfied, so skip.
                logger.debug(
                    "Sync revoke skipped: role already unassigned",
                    extra={"user_id": user.id, "role_id": role_id},
                )

        self._mirror_primary_role_to_legacy(db, user, org_id)
        return bool(matched_role_ids)

    def _mirror_primary_role_to_legacy(self, db: Session, user: Any, org_id: str) -> None:
        """Mirror the user's highest-priority RBAC role name into the legacy
        ``user.role`` column so display and legacy callers reflect the effective
        role.

        Priority ordering (superadmin=1000, admin=100, viewer=10, auto-created=0)
        guarantees a system role is never downgraded by a read-only synced role —
        so legacy-column lookups for admins/superadmins keep working.
        """
        try:
            roles = self.roles_db_service.get_user_roles_with_permissions(db, user.id, org_id)
        except Exception:
            logger.exception("Failed to read RBAC roles while mirroring legacy role")
            return
        if not roles:
            return
        primary = max(roles, key=lambda r: ((r.priority or 0), r.name or ""))
        new_legacy = (primary.name or "")[:32]
        if new_legacy and user.role != new_legacy:
            user.role = new_legacy
            db.commit()
            db.refresh(user)

    # ── Registration ──────────────────────────────────────────────────────────

    def register(
        self,
        payload: UserCreate,
        db: Session,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> tuple[TokenResponse | RegistrationResponse, int]:
        """Register a user, unless an unaccepted invitation is already waiting for them."""
        if self.config and not self.config._configuration.app_settings.allow_registration:
            raise PermissionError("Registration is disabled")

        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        if AuthDBOperations.find_pending_invitation(db, payload.email):
            raise ConflictError(INVITE_PENDING_MESSAGE)

        if auth_service.get_user_by_email(payload.email):
            raise ConflictError("Email already registered")

        if OrgModelService.is_public_email_domain(payload.email) and not payload.organization_name:
            raise ValidationError(
                "Organization name is required for public email domains "
                "(gmail.com, outlook.com, etc.)"
            )

        result = auth_service.create_local_user(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
            organization_name=payload.organization_name,
        )

        user = result.user
        org = result.organization

        auth_service.log_auth_event(
            event_type=AuthEventType.REGISTER,
            user_id=user.id,
            email=user.email,
            payload={
                "role": user.role,
                "auth_type": user.auth_type,
                "status": user.status,
                "approval_type": result.approval_type.value,
                "is_new_org": result.is_new_org,
                "organization_name": org.name if org else None,
            },
            organization_id=user.organization_id,
        )

        if result.approval_type == ApprovalType.ACTIVE:
            access_token, refresh_token = auth_service.create_tokens(user)
            auth_service.update_last_login(user)
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                user=UserPublic.model_validate(user),
            ), 201

        if result.approval_type == ApprovalType.PENDING_ORG_ADMIN:
            self._notify_admins_new_user(
                db, user.email, user.full_name, user.organization_id,
                background_tasks=background_tasks,
            )
            return RegistrationResponse(
                message="Your account is pending approval from your organization administrator.",
                user_id=user.id,
                organization_id=org.id if org else "",
                organization_name=org.name if org else "",
                approval_type=result.approval_type.value,
                is_new_organization=False,
            ), 202

        # PENDING_PLATFORM
        self._notify_superadmins_new_org(
            db, org.name if org else "", user.email, user.full_name,
            background_tasks=background_tasks,
        )
        return RegistrationResponse(
            message=(
                "Your organization request is pending platform approval. "
                "You will be notified when approved."
            ),
            user_id=user.id,
            organization_id=org.id if org else "",
            organization_name=org.name if org else "",
            approval_type=result.approval_type.value,
            is_new_organization=result.is_new_org,
        ), 202

    def register_with_org(
        self,
        payload: UserCreateWithOrg,
        db: Session,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> PendingOrgRegistrationResponse:
        """Deprecated — use register() with organization_name."""
        warnings.warn(
            "register-with-org is deprecated. Use /auth/register with organization_name.",
            DeprecationWarning,
            stacklevel=2,
        )

        if self.config and not self.config._configuration.app_settings.allow_registration:
            raise PermissionError("Registration is disabled")

        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        existing = auth_service.get_user_by_email(payload.email)
        if existing:
            if existing.organization_id:
                existing_org = OrgModelService.get_organization(db, existing.organization_id)
                if existing_org and existing_org.status == OrganizationStatus.PENDING.value:
                    raise ConflictError(
                        "You already have a pending organization request. "
                        "Please wait for it to be approved or rejected."
                    )
            raise ConflictError("Email already registered")

        slug = OrgModelService.slugify(payload.organization_name)
        if payload.organization_slug:
            slug = payload.organization_slug
        base_slug, counter = slug, 1
        while OrgModelService.get_organization_by_slug(db, slug) is not None:
            slug = f"{base_slug}-{counter}"
            counter += 1

        org, user = AuthDBOperations.create_pending_org_with_admin(
            db=db,
            org_name=payload.organization_name,
            slug=slug,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
        )

        auth_service.log_auth_event(
            event_type=AuthEventType.REGISTER,
            user_id=user.id,
            email=user.email,
            payload={
                "role": user.role,
                "auth_type": user.auth_type,
                "status": user.status,
                "organization_id": org.id,
                "organization_name": org.name,
                "registration_type": "with_org",
            },
            organization_id=org.id,
        )

        self._notify_superadmins_new_org(
            db, org.name, user.email, user.full_name, background_tasks=background_tasks
        )

        return PendingOrgRegistrationResponse(
            message="Organization request submitted. You will be notified when approved.",
            user_id=user.id,
            organization_id=org.id,
            organization_name=org.name,
            status="pending_org_approval",
        )

    # ── Login / Logout ────────────────────────────────────────────────────────

    def login(self, payload: UserLogin, db: Session) -> TokenResponse:
        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        user, error_reason = auth_service.authenticate_local(payload.email, payload.password)

        if not user:
            auth_service.log_auth_event(
                event_type=AuthEventType.LOGIN_FAILED,
                email=payload.email,
                payload={"reason": error_reason or "unknown"},
            )
            _messages = {
                "not_found": "Invalid email or password",
                "wrong_auth_type": "Please sign in with Google",
                "invalid_password": "Invalid email or password",
                "pending_approval": (
                    "Your account is pending approval. "
                    "Please wait for an admin to approve your access."
                ),
                "suspended": "Your account has been suspended. Please contact an administrator.",
                "rejected": "Your account access request was denied. Please contact an administrator.",
                "inactive": "Your account is inactive. Please contact an administrator.",
            }
            detail = _messages.get(error_reason or "", "Invalid email or password")
            is_status_error = error_reason in (
                "pending_approval",
                "suspended",
                "rejected",
                "inactive",
            )
            exc = ValidationError(detail)
            exc.status_code = 403 if is_status_error else 401  # type: ignore[attr-defined]
            raise exc

        auth_service.log_auth_event(
            event_type=AuthEventType.LOGIN_SUCCESS,
            user_id=user.id,
            email=user.email,
            payload={"auth_type": user.auth_type},
            organization_id=user.organization_id,
        )

        access_token, refresh_token = auth_service.create_tokens(user)
        auth_service.update_last_login(user)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserPublic.model_validate(user),
        )

    def refresh_token(self, payload: TokenRefresh, db: Session) -> TokenResponse:
        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        result = auth_service.refresh_access_token(payload.refresh_token)
        if not result:
            exc = ValidationError("Invalid or expired refresh token")
            exc.status_code = 401  # type: ignore[attr-defined]
            raise exc

        access_token, new_refresh_token, user = result

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            user=UserPublic.model_validate(user),
        )

    def logout(self, payload: TokenRefresh, db: Session) -> MessageResponse:
        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        token_payload = decode_token(payload.refresh_token)
        user_id = token_payload.get("sub") if token_payload else None

        organization_id = None
        if user_id:
            user = auth_service.get_user_by_id(user_id)
            if user:
                organization_id = user.organization_id

        auth_service.revoke_refresh_token(payload.refresh_token)

        auth_service.log_auth_event(
            event_type=AuthEventType.LOGOUT,
            user_id=user_id,
            organization_id=organization_id,
        )

        return MessageResponse(message="Successfully logged out")

    # ── Google OAuth ──────────────────────────────────────────────────────────

    def get_google_auth_url(self, redirect_uri: str | None = None) -> GoogleAuthUrl:
        if not (self.config and self.config._configuration.google_oauth_configuration.client_id):
            raise ValidationError("Google OAuth is not configured")
        auth_service = AuthService(None, self.config, audit_events_service=self.audit_events_service)  # type: ignore[arg-type]
        return GoogleAuthUrl(url=auth_service.get_google_auth_url(redirect_uri))

    def get_microsoft_auth_url(self, redirect_uri: str | None = None) -> MicrosoftAuthUrl:
        if not MicrosoftOAuthService.is_configured():
            exc = ValidationError("Microsoft OAuth is not configured")
            exc.status_code = 503  # type: ignore[attr-defined]
            raise exc

        final_redirect_uri = redirect_uri or MicrosoftOAuthService.redirect_uri()
        parsed = urlparse(final_redirect_uri)
        # Native mobile clients redirect through a custom app URI scheme
        # (e.g. "myapp://auth/callback") rather than http(s) — RFC 3986 (§3.1)
        # allows any scheme matching ALPHA *( ALPHA / DIGIT / "+" / "-" / "." ).
        is_web_scheme = parsed.scheme in {"http", "https"}
        is_custom_app_scheme = bool(re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.-]*", parsed.scheme))
        if not (is_web_scheme or is_custom_app_scheme) or not parsed.netloc:
            exc = ValidationError("Invalid redirect URI")
            exc.status_code = 400  # type: ignore[attr-defined]
            raise exc

        state = MicrosoftOAuthService.generate_state(final_redirect_uri)

        code_challenge: str | None = None
        if MicrosoftOAuthService.use_pkce():
            verifier, code_challenge = MicrosoftOAuthService.generate_pkce_pair()
            self._stash_pkce_verifier(state, verifier)

        url = MicrosoftOAuthService.build_authorization_url(
            state=state,
            redirect_uri=final_redirect_uri,
            code_challenge=code_challenge,
        )
        return MicrosoftAuthUrl(url=url, state=state)

    async def google_callback(
        self,
        payload: GoogleAuthCallback,
        db: Session,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> tuple[TokenResponse | RegistrationResponse, int]:
        google_oauth_config = (
            self.config._configuration.google_oauth_configuration if self.config else None
        )
        if not (
            google_oauth_config
            and google_oauth_config.client_id
            and google_oauth_config.client_secret
        ):
            raise ValidationError("Google OAuth is not configured")

        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        try:
            result = await auth_service.authenticate_google(
                code=payload.code,
                redirect_uri=payload.redirect_uri,
            )
        except ValueError as exc:
            auth_service.log_auth_event(
                event_type=AuthEventType.GOOGLE_LOGIN_FAILED,
                payload={"reason": str(exc)},
            )
            raise ValidationError(str(exc)) from exc

        if not result:
            auth_service.log_auth_event(
                event_type=AuthEventType.GOOGLE_LOGIN_FAILED,
                payload={"reason": "authentication_failed"},
            )
            raise ValidationError("Google authentication failed")

        user = result.user
        org = result.organization

        if result.approval_type != ApprovalType.ACTIVE:
            pending_inv = AuthDBOperations.find_pending_invitation(db, user.email)
            if pending_inv:
                try:
                    accepted = self.invitation_service_manager.accept_invitation(db, pending_inv.token)
                    activated_user = UserModelService().get_by_id(db, accepted.user_id)
                    if activated_user:
                        user = activated_user
                        if user.organization_id:
                            org = OrgModelService.get_organization(db, user.organization_id)
                        result = UserCreationResult(
                            user=user,
                            organization=org,
                            is_new_org=result.is_new_org,
                            approval_type=ApprovalType.ACTIVE,
                        )
                except Exception:
                    logger.error(
                        "auto-accept invitation failed for %s — user will remain in pending state",
                        user.email,
                    )

        auth_service.log_auth_event(
            event_type=AuthEventType.GOOGLE_LOGIN,
            user_id=user.id,
            email=user.email,
            payload={
                "auth_type": user.auth_type,
                "approval_type": result.approval_type.value,
                "is_new_org": result.is_new_org,
            },
            organization_id=user.organization_id,
        )

        if result.approval_type == ApprovalType.ACTIVE:
            access_token, refresh_token = auth_service.create_tokens(user)
            auth_service.update_last_login(user)
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                user=UserPublic.model_validate(user),
            ), 200

        if result.approval_type == ApprovalType.PENDING_ORG_ADMIN:
            self._notify_admins_new_user(
                db, user.email, user.full_name, user.organization_id,
                background_tasks=background_tasks,
            )
            return RegistrationResponse(
                message="Your account is pending approval from your organization administrator.",
                user_id=user.id,
                organization_id=org.id if org else "",
                organization_name=org.name if org else "",
                approval_type=result.approval_type.value,
                is_new_organization=False,
            ), 202

        # PENDING_PLATFORM
        self._notify_superadmins_new_org(
            db, org.name if org else "", user.email, user.full_name,
            background_tasks=background_tasks,
        )
        return RegistrationResponse(
            message=(
                "Your organization request is pending platform approval. "
                "You will be notified when approved."
            ),
            user_id=user.id,
            organization_id=org.id if org else "",
            organization_name=org.name if org else "",
            approval_type=result.approval_type.value,
            is_new_organization=result.is_new_org,
        ), 202

    async def microsoft_callback(
        self,
        payload: MicrosoftAuthCallback,
        db: Session,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> tuple[MicrosoftTokenResponse | RegistrationResponse, int]:
        if not MicrosoftOAuthService.is_configured():
            exc = ValidationError("Microsoft OAuth is not configured")
            exc.status_code = 503  # type: ignore[attr-defined]
            raise exc

        auth_service = AuthService(db, roles_db_service=self.roles_db_service, audit_events_service=self.audit_events_service)
        correlation_id = get_correlation_id()
        final_redirect_uri = payload.redirect_uri or MicrosoftOAuthService.redirect_uri()

        try:
            MicrosoftOAuthService.verify_state(payload.state, redirect_uri=final_redirect_uri)
            code_verifier: str | None = None
            if MicrosoftOAuthService.use_pkce():
                code_verifier = self._pop_pkce_verifier(payload.state)
                if not code_verifier:
                    raise MicrosoftOAuthError(
                        "Missing or expired PKCE verifier for this login attempt"
                    )
            token_payload = await MicrosoftOAuthService.exchange_code_for_tokens(
                code=payload.code,
                redirect_uri=final_redirect_uri,
                code_verifier=code_verifier,
            )
            claims = MicrosoftOAuthService.validate_id_token(str(token_payload["id_token"]))
        except MicrosoftOAuthError as exc:
            self._log_microsoft_auth_failure(auth_service, exc, correlation_id)
            raise self._microsoft_oauth_http_error(exc) from exc

        return self._complete_microsoft_login(
            claims=claims,
            db=db,
            auth_service=auth_service,
            correlation_id=correlation_id,
            id_token=str(token_payload["id_token"]),
            access_token=token_payload.get("access_token"),
            expires_in=token_payload.get("expires_in"),
            background_tasks=background_tasks,
        )

    async def microsoft_id_token_login(
        self,
        id_token: str,
        db: Session,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> tuple[MicrosoftTokenResponse | RegistrationResponse, int]:
        """Log in (or provision) a user from a Microsoft ID token obtained
        elsewhere — e.g. a client app's own, already-completed Microsoft
        sign-in — instead of running our own separate authorization-code
        round trip. Validates the token exactly as `microsoft_callback` does
        (same signing-key/audience/tenant checks), then shares its
        provisioning/role-sync/response logic. Requires the token's `aud`
        to match this deployment's configured client_id, which holds as
        long as the caller's own Microsoft sign-in used the same Azure App
        Registration as this SM instance."""
        if not MicrosoftOAuthService.is_configured():
            exc = ValidationError("Microsoft OAuth is not configured")
            exc.status_code = status.HTTP_503_SERVICE_UNAVAILABLE  # type: ignore[attr-defined]
            raise exc

        auth_service = AuthService(db, roles_db_service=self.roles_db_service, audit_events_service=self.audit_events_service)
        correlation_id = get_correlation_id()

        try:
            claims = MicrosoftOAuthService.validate_id_token(id_token)
        except MicrosoftOAuthError as exc:
            self._log_microsoft_auth_failure(auth_service, exc, correlation_id)
            raise self._microsoft_oauth_http_error(exc) from exc

        return self._complete_microsoft_login(
            claims=claims,
            db=db,
            auth_service=auth_service,
            correlation_id=correlation_id,
            id_token=id_token,
            access_token=None,
            expires_in=None,
            background_tasks=background_tasks,
        )

    def _log_microsoft_auth_failure(
        self, auth_service: AuthService, exc: MicrosoftOAuthError, correlation_id: str
    ) -> None:
        auth_service.log_auth_event(
            event_type=AuthEventType.LOGIN_FAILED,
            payload={"reason": str(exc), "provider": "microsoft"},
            correlation_id=correlation_id,
        )

    def _microsoft_oauth_http_error(self, exc: MicrosoftOAuthError) -> ValidationError:
        err = ValidationError(str(exc))
        detail = str(exc).lower()
        if "configured" in detail:
            err.status_code = status.HTTP_503_SERVICE_UNAVAILABLE  # type: ignore[attr-defined]
        elif "tenant" in detail:
            err.status_code = status.HTTP_403_FORBIDDEN  # type: ignore[attr-defined]
        elif "state" in detail or "exchange" in detail or "missing" in detail:
            err.status_code = status.HTTP_400_BAD_REQUEST  # type: ignore[attr-defined]
        elif "expired" in detail or "token" in detail or "signing key" in detail:
            err.status_code = status.HTTP_401_UNAUTHORIZED  # type: ignore[attr-defined]
        else:
            err.status_code = status.HTTP_400_BAD_REQUEST  # type: ignore[attr-defined]
        return err

    def _ensure_user_and_org(
        self,
        *,
        microsoft_id: str,
        email: str,
        full_name: str,
        avatar_url: str | None,
        db: Session,
    ) -> UserCreationResult:
        """Resolve (or create) the local user/org for this Microsoft identity,
        auto-accepting any pending invitation for their email so a directory
        sign-in isn't stuck behind a separate manual invite-acceptance step."""
        result = self._authenticate_or_create_microsoft_identity(
            microsoft_id=microsoft_id,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            db=db,
        )
        if result.approval_type == ApprovalType.ACTIVE:
            return result

        pending_inv = AuthDBOperations.find_pending_invitation(db, result.user.email)
        if not pending_inv:
            return result

        try:
            accepted = self.invitation_service_manager.accept_invitation(db, pending_inv.token)
            activated_user = UserModelService().get_by_id(db, accepted.user_id)
        except Exception:
            logger.error(
                "auto-accept invitation failed for %s — user will remain in pending state",
                result.user.email,
            )
            return result

        if not activated_user:
            return result

        org = result.organization
        if activated_user.organization_id:
            org = AuthDBOperations.get_organization(db, activated_user.organization_id)
        return UserCreationResult(
            user=activated_user,
            organization=org,
            is_new_org=result.is_new_org,
            approval_type=ApprovalType.ACTIVE,
        )

    def _sync_roles_and_approval(
        self, db: Session, result: UserCreationResult, ms_roles: list[Any]
    ) -> UserCreationResult:
        """Sync Entra app-roles into RBAC. Fail-open: a sync error must never
        block a successfully authenticated login."""
        try:
            matched = self._reconcile_microsoft_roles(db, result.user, result.organization, ms_roles)
        except Exception:
            logger.exception(
                "Microsoft role reconciliation failed; login proceeds without role sync",
                extra={"user_id": result.user.id},
            )
            return result

        if not matched or result.approval_type == ApprovalType.ACTIVE:
            return result

        # A directory-assigned role authorizes the user — skip manual approval.
        user = result.user
        user.status = UserStatus.ACTIVE.value  # is_active is derived from status by the DB
        db.commit()
        db.refresh(user)
        return UserCreationResult(
            user=user,
            organization=result.organization,
            is_new_org=result.is_new_org,
            approval_type=ApprovalType.ACTIVE,
        )

    def _log_microsoft_login_success(
        self, auth_service: AuthService, result: UserCreationResult, correlation_id: str
    ) -> None:
        user = result.user
        auth_service.log_auth_event(
            event_type=AuthEventType.LOGIN_SUCCESS,
            user_id=user.id,
            email=user.email,
            payload={
                "provider": "microsoft",
                "auth_type": user.auth_type,
                "approval_type": result.approval_type.value,
                "is_new_org": result.is_new_org,
            },
            correlation_id=correlation_id,
            organization_id=user.organization_id,
        )

    def _active_login_response(
        self,
        auth_service: AuthService,
        user: object,
        id_token: str,
        access_token: str | None,
        expires_in: int | None,
    ) -> tuple[MicrosoftTokenResponse, int]:
        app_access_token, app_refresh_token = auth_service.create_tokens(user)
        auth_service.update_last_login(user)
        return MicrosoftTokenResponse(
            id_token=id_token,
            access_token=access_token,
            expires_in=expires_in,
            user=UserPublic.model_validate(user),
            app_access_token=app_access_token,
            app_refresh_token=app_refresh_token,
        ), 200

    def _pending_org_admin_response(
        self,
        db: Session,
        result: UserCreationResult,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> tuple[RegistrationResponse, int]:
        user = result.user
        org = result.organization
        self._notify_admins_new_user(
            db, user.email, user.full_name, user.organization_id,
            background_tasks=background_tasks,
        )
        return RegistrationResponse(
            message="Your account is pending approval from your organization administrator.",
            user_id=user.id,
            organization_id=org.id if org else "",
            organization_name=org.name if org else "",
            approval_type=result.approval_type.value,
            is_new_organization=False,
        ), 202

    def _pending_platform_response(
        self,
        db: Session,
        result: UserCreationResult,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> tuple[RegistrationResponse, int]:
        user = result.user
        org = result.organization
        self._notify_superadmins_new_org(
            db, org.name if org else "", user.email, user.full_name,
            background_tasks=background_tasks,
        )
        return RegistrationResponse(
            message=(
                "Your organization request is pending platform approval. "
                "You will be notified when approved."
            ),
            user_id=user.id,
            organization_id=org.id if org else "",
            organization_name=org.name if org else "",
            approval_type=result.approval_type.value,
            is_new_organization=result.is_new_org,
        ), 202

    def _build_auth_response(
        self,
        *,
        db: Session,
        auth_service: AuthService,
        result: UserCreationResult,
        correlation_id: str,
        id_token: str,
        access_token: str | None,
        expires_in: int | None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> tuple[MicrosoftTokenResponse | RegistrationResponse, int]:
        self._log_microsoft_login_success(auth_service, result, correlation_id)

        if result.approval_type == ApprovalType.ACTIVE:
            return self._active_login_response(
                auth_service, result.user, id_token, access_token, expires_in
            )
        if result.approval_type == ApprovalType.PENDING_ORG_ADMIN:
            return self._pending_org_admin_response(db, result, background_tasks=background_tasks)
        return self._pending_platform_response(db, result, background_tasks=background_tasks)

    def _complete_microsoft_login(
        self,
        *,
        claims: dict[str, Any],
        db: Session,
        auth_service: AuthService,
        correlation_id: str,
        id_token: str,
        access_token: str | None,
        expires_in: int | None,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> tuple[MicrosoftTokenResponse | RegistrationResponse, int]:
        microsoft_id, email, full_name, avatar_url = MicrosoftOAuthService.extract_identity(
            claims
        )
        result = self._ensure_user_and_org(
            microsoft_id=microsoft_id,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            db=db,
        )
        result = self._sync_roles_and_approval(db, result, claims.get("roles") or [])
        return self._build_auth_response(
            db=db,
            auth_service=auth_service,
            result=result,
            correlation_id=correlation_id,
            id_token=id_token,
            access_token=access_token,
            expires_in=expires_in,
            background_tasks=background_tasks,
        )

    # ── Pending / Remind ──────────────────────────────────────────────────────

    def resolve_current_user(self, token: str, db: Session) -> object:
        """Resolve current user from app JWT or Microsoft id_token."""
        payload = decode_token(token)
        if payload and payload.get("type") == "access":
            user_id = str(payload.get("sub") or "").strip()
            user = AuthDBOperations.get_user_by_id(db, user_id) if user_id else None
            if not user:
                exc = ValidationError("User not found")
                exc.status_code = 401  # type: ignore[attr-defined]
                raise exc
            if not user.is_active:
                exc = ValidationError("User account is inactive")
                exc.status_code = 403  # type: ignore[attr-defined]
                raise exc
            return user

        try:
            claims = MicrosoftOAuthService.validate_id_token(token)
            microsoft_id, email, _full_name, _avatar = MicrosoftOAuthService.extract_identity(
                claims
            )
        except MicrosoftOAuthError as exc:
            err = ValidationError("Invalid or expired token")
            err.status_code = 401  # type: ignore[attr-defined]
            raise err from exc

        user = AuthDBOperations.get_user_by_microsoft_id(db, microsoft_id)
        if not user:
            user = AuthDBOperations.get_user_by_email(db, email)
            if user and not user.microsoft_id:
                user.microsoft_id = microsoft_id
                db.commit()
                db.refresh(user)

        if not user:
            exc = ValidationError("User not registered")
            exc.status_code = 403  # type: ignore[attr-defined]
            raise exc
        if not user.is_active:
            exc = ValidationError("User account is inactive")
            exc.status_code = 403  # type: ignore[attr-defined]
            raise exc
        return user

    def _authenticate_or_create_microsoft_identity(
        self,
        microsoft_id: str,
        email: str,
        full_name: str,
        avatar_url: str | None,
        db: Session,
    ) -> UserCreationResult:
        user = AuthDBOperations.get_user_by_microsoft_id(db, microsoft_id)
        if user:
            user.full_name = full_name
            user.avatar_url = avatar_url
            db.commit()
            db.refresh(user)
            org = (
                AuthDBOperations.get_organization(db, user.organization_id)
                if user.organization_id
                else None
            )
            approval_type = ApprovalType.ACTIVE
            if not user.is_active:
                approval_type = (
                    ApprovalType.PENDING_PLATFORM
                    if org and org.status == OrganizationStatus.PENDING.value
                    else ApprovalType.PENDING_ORG_ADMIN
                )
            return UserCreationResult(
                user=user, organization=org, is_new_org=False, approval_type=approval_type
            )

        existing_user = AuthDBOperations.get_user_by_email(db, email)
        if existing_user:
            existing_user.microsoft_id = microsoft_id
            existing_user.full_name = full_name
            existing_user.avatar_url = avatar_url
            if existing_user.auth_type == ModularAuthType.LOCAL.value:
                existing_user.auth_type = ModularAuthType.MICROSOFT.value
            db.commit()
            db.refresh(existing_user)
            org = (
                AuthDBOperations.get_organization(db, existing_user.organization_id)
                if existing_user.organization_id
                else None
            )
            approval_type = ApprovalType.ACTIVE
            if not existing_user.is_active:
                approval_type = (
                    ApprovalType.PENDING_PLATFORM
                    if org and org.status == OrganizationStatus.PENDING.value
                    else ApprovalType.PENDING_ORG_ADMIN
                )
            return UserCreationResult(
                user=existing_user, organization=org, is_new_org=False, approval_type=approval_type
            )

        is_new_org = False
        if OrgModelService.is_public_email_domain(email):
            org = OrgModelService.get_organization_for_email(db, email)
            if org is None:
                raise MicrosoftOAuthError(
                    "Microsoft sign-in with public email domains requires an organization. "
                    "Please sign up with your company email or request an invitation."
                )
            organization_id = org.id
        else:
            org, is_new_org = OrgModelService.get_or_create_organization_for_email(
                db,
                email,
                organization_name=None,
                requested_by_user_id=None,
            )
            organization_id = org.id

        is_first = AuthDBOperations.count_users_in_org(db, organization_id) == 0
        org_is_pending = org and org.status == OrganizationStatus.PENDING.value

        if org_is_pending:
            status = UserStatus.PENDING.value
            role = UserRole.ADMIN.value if is_first else UserRole.VIEWER.value
            approval_type = ApprovalType.PENDING_PLATFORM
        elif is_first:
            status = UserStatus.ACTIVE.value
            role = UserRole.ADMIN.value
            approval_type = ApprovalType.ACTIVE
        else:
            status = UserStatus.PENDING.value
            role = UserRole.VIEWER.value
            approval_type = ApprovalType.PENDING_ORG_ADMIN

        new_user = AuthDBOperations.create_microsoft_user(
            db=db,
            email=email,
            full_name=full_name,
            microsoft_id=microsoft_id,
            avatar_url=avatar_url,
            role=role,
            status=status,
            organization_id=organization_id,
        )

        if is_new_org and org:
            org.requested_by_user_id = new_user.id
            db.commit()
            db.refresh(org)
            db.refresh(new_user)
        else:
            db.commit()
            db.refresh(new_user)

        if is_first:
            auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)
            auth_service._assign_admin_role_to_first_user(new_user.id, organization_id)

        return UserCreationResult(
            user=new_user,
            organization=org,
            is_new_org=is_new_org,
            approval_type=approval_type,
        )

    def remind_admin(
        self,
        payload: UserLogin,
        db: Session,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> MessageResponse:
        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        user = auth_service.get_user_by_email(payload.email)
        if not user:
            raise NotFoundError("User not found")

        if (
            user.auth_type == "local"
            and user.hashed_password
            and not verify_password(payload.password, user.hashed_password)
        ):
            exc = ValidationError("Invalid credentials")
            exc.status_code = 401  # type: ignore[attr-defined]
            raise exc

        if user.status != UserStatus.PENDING.value:
            raise ValidationError("Your account is not pending approval")

        self._notify_admins_new_user(
            db, user.email, user.full_name, user.organization_id,
            background_tasks=background_tasks,
        )

        auth_service.log_auth_event(
            event_type=AuthEventType.LOGIN_FAILED,
            user_id=user.id,
            email=user.email,
            payload={"reason": "reminder_sent", "action": "remind_admin"},
            organization_id=user.organization_id,
        )

        return MessageResponse(message="A reminder has been sent to your administrator")

    # ── Current user ──────────────────────────────────────────────────────────

    def get_me(self, user: object) -> UserRead:
        return UserRead.model_validate(user)

    # ── Password reset ────────────────────────────────────────────────────────

    def forgot_password(self, payload: ForgotPasswordRequest, db: Session) -> MessageResponse:
        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        generic_msg = "If an account exists with that email, a reset link has been sent."

        user = auth_service.get_user_by_email(payload.email)
        if not user or user.auth_type == "google" or not user.hashed_password:
            return MessageResponse(message=generic_msg)

        token = create_password_reset_token(user.id, user.hashed_password)
        reset_url = f"{self.config._configuration.app_settings.frontend_url.rstrip('/') if self.config else ''}/reset-password?token={token}"
        user_name = user.full_name or user.email.split("@")[0]

        body_html = (
            f"<html><body style='margin:0;padding:0;background:#f5f5f5;"
            f"font-family:-apple-system,sans-serif;'>"
            f"<div style='max-width:600px;margin:0 auto;padding:20px;'>"
            f"<div style='background:#fff;border-radius:8px;padding:24px;"
            f"box-shadow:0 1px 3px rgba(0,0,0,.1);'>"
            f"<h2 style='color:#0047AB;'>Reset Your Password</h2>"
            f"<p>Hi {html_mod.escape(user_name)},</p>"
            f"<p>We received a request to reset your password.</p>"
            f"<a href='{reset_url}' style='display:inline-block;background:#0047AB;"
            f"color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;"
            f"font-weight:500;'>Reset Password</a>"
            f"<p style='font-size:13px;color:#999;margin-top:20px;'>"
            f"This link expires in 1 hour.</p>"
            f"</div></div></body></html>"
        )
        subject = "Reset your password"

        mail = self._mail_service_manager or email_service
        values = {
            "user_name": html_mod.escape(user_name),
            "reset_url": html_mod.escape(reset_url, quote=True),
        }
        template = mail.get_default_email_template_for_kind(
            db, user.organization_id or "", EMAIL_KIND_PASSWORD_RESET
        )
        if template:
            subject = self._render_email_template(template["subject"], values)
            body_html = self._render_email_template(template["body_html"], values)

        mail.send_email(
            db=db,
            org_id=user.organization_id or "",
            to=user.email,
            subject=subject,
            body_html=body_html,
        )

        auth_service.log_auth_event(
            event_type=AuthEventType.PASSWORD_RESET_REQUESTED,
            user_id=user.id,
            email=user.email,
            organization_id=user.organization_id,
        )

        return MessageResponse(message=generic_msg)

    def reset_password(self, payload: ResetPasswordRequest, db: Session) -> MessageResponse:
        auth_service = AuthService(db, self.config, self.roles_db_service, self.audit_events_service)

        token_data = decode_password_reset_token(payload.token)
        if not token_data:
            raise ValidationError("Invalid or expired reset link. Please request a new one.")

        user_id = token_data.get("sub")
        token_phash = token_data.get("phash")
        if not user_id or not token_phash:
            raise ValidationError("Invalid or expired reset link. Please request a new one.")

        user = auth_service.get_user_by_id(user_id)
        if not user or not user.hashed_password:
            raise ValidationError("Invalid or expired reset link. Please request a new one.")

        current_phash = hashlib.sha256(user.hashed_password.encode()).hexdigest()[:16]
        if current_phash != token_phash:
            raise ValidationError(
                "This reset link has already been used. Please request a new one."
            )

        AuthDBOperations.update_user_password(db, user, hash_password(payload.new_password))

        auth_service.revoke_all_user_tokens(user.id)

        auth_service.log_auth_event(
            event_type=AuthEventType.PASSWORD_CHANGED,
            user_id=user.id,
            email=user.email,
            payload={"method": "reset_token"},
            organization_id=user.organization_id,
        )

        return MessageResponse(message="Password has been reset successfully.")

    # ── RBAC ──────────────────────────────────────────────────────────────────

    def get_status(self) -> IdentityAccessStatusResponse:
        return IdentityAccessStatusResponse(module="auth", status="ready", started=True)

    def check_access(
        self,
        actor: ActorContext | AccessCheckRequest | dict[str, object],
        resource: str | None = None,
        action: str | None = None,
        organization_id: str | None = None,
        db: Session | None = None,
    ) -> AccessCheckResponse:
        if isinstance(actor, AccessCheckRequest):
            payload = actor
        elif isinstance(actor, dict) and resource is None and action is None:
            payload = AccessCheckRequest.model_validate(actor)
        else:
            if isinstance(actor, ActorContext):
                actor_context = actor
            elif isinstance(actor, dict):
                actor_context = ActorContext.model_validate(actor)
            else:
                raise ValidationError("Invalid actor payload")
            if not resource or not action:
                raise ValidationError("resource and action are required")
            payload = AccessCheckRequest(actor=actor_context, resource=resource, action=action, organization_id=organization_id)

        actor_context = payload.actor
        permission = PermissionSpec(resource=payload.resource, action=payload.action)
        org_id = payload.organization_id or actor_context.organization_id

        if org_id and org_id != actor_context.organization_id:
            return AccessCheckResponse(allowed=False, reason="actor organization does not match requested organization", evaluated_permission=permission.key())

        if db is not None and self.roles_db_service is not None:
            try:
                result = self.roles_db_service.check_permission(db, actor_context.user_id, org_id, permission.key())
                return AccessCheckResponse(allowed=result.allowed, reason=result.reason, evaluated_permission=result.permission_key)
            except Exception as exc:
                logger.warning(f"DB permission check failed: {exc}")

        return AccessCheckResponse(allowed=False, reason="permission service unavailable", evaluated_permission=permission.key())

    def _notify_admins_new_user(
        self,
        db: Session,
        new_user_email: str,
        new_user_name: str,
        organization_id: str,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Notify org admins when a new user registers, using the notifications manager."""
        if self.notifications_manager is None:
            logger.warning("_notify_admins_new_user: notifications_manager not set, skipping")
            return
        try:
            from user.db_models import User, UserRole, UserStatus

            admins = (
                db.query(User)
                .filter(
                    User.organization_id == organization_id,
                    User.role == UserRole.ADMIN.value,
                    User.status == UserStatus.ACTIVE.value,
                )
                .all()
            )
            admin_emails = [u.email for u in admins if u.email]
            self.notifications_manager.notify_admins_new_user(
                db=db,
                organization_id=organization_id,
                new_user_email=new_user_email,
                new_user_name=new_user_name,
                admin_emails=admin_emails,
                background_tasks=background_tasks,
            )
        except Exception as exc:
            logger.warning(f"_notify_admins_new_user failed: {exc}")

    def _notify_superadmins_new_org(
        self,
        db: Session,
        org_name: str,
        requester_email: str,
        requester_name: str,
        background_tasks: BackgroundTaskScheduler | None = None,
    ) -> None:
        """Notify superadmins when a new org is requested, using the notifications manager."""
        if self.notifications_manager is None:
            logger.warning("_notify_superadmins_new_org: notifications_manager not set, skipping")
            return
        try:
            from auth.db_models import PLATFORM_ORG_ID
            from user.db_models import User, UserRole, UserStatus

            superadmins = (
                db.query(User)
                .filter(
                    User.organization_id == PLATFORM_ORG_ID,
                    User.role == UserRole.ADMIN.value,
                    User.status == UserStatus.ACTIVE.value,
                )
                .all()
            )
            superadmin_emails = [u.email for u in superadmins if u.email]
            self.notifications_manager.notify_superadmins_new_org(
                db=db,
                org_name=org_name,
                requester_email=requester_email,
                requester_name=requester_name,
                superadmin_emails=superadmin_emails,
                platform_org_id=PLATFORM_ORG_ID,
                background_tasks=background_tasks,
            )
        except Exception as exc:
            logger.warning(f"_notify_superadmins_new_org failed: {exc}")

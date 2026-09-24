"""Business logic manager for organizations."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from common.logger import logger
from common.security import hash_password
from exceptions import ConflictError, NotFoundError, ValidationError
from organizations.db_models import OrganizationStatus
from organizations.models.response import (
    OrganizationListResponse,
    OrganizationRead,
    OrganizationUserListResponse,
    OrganizationWithRequester,
    PendingOrganizationListResponse,
    ProvisionResult,
    ProvisionStatus,
)
from user.models.response import UserRead

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from organizations.db_models import OrganizationsModelService
    from organizations.models.request import PlatformUserCreate


class OrganizationsServiceManager:
    """Organization orchestration service.

    Stateless — each method receives the per-request DB session as a parameter.
    Sessions are owned and closed by the controller.
    """

    def __init__(
        self,
        organizations_db_model_service: OrganizationsModelService,
        database_service_manager: Any = None,
        config: Any = None,
        roles_service_manager: Any = None,
        filehandler_service_manager: Any = None,
    ) -> None:
        self.db = organizations_db_model_service
        self.roles = roles_service_manager
        self.filehandler = filehandler_service_manager
        self.module_name = "organizations"
        self._started = False

    def bind_filehandler(self, filehandler_service_manager: Any) -> None:
        """Bind organization default-file-type provisioning after service construction."""
        self.filehandler = filehandler_service_manager

    def _provision_default_file_types(self, organization_id: str) -> None:
        """Idempotently provision system file types for an active organization."""
        if self.filehandler is None:
            logger.warning(
                "Filehandler is not wired; default file types were not provisioned for org %s",
                organization_id,
            )
            return
        self.filehandler.seed_file_types(organization_id)

    def start(self) -> None:
        """Mark the service as started."""
        self._started = True

    def stop(self) -> None:
        """Mark the service as stopped."""
        self._started = False

    # ── Response builder ──────────────────────────────────────────────────────

    @staticmethod
    def _org_to_read(org: Any) -> OrganizationRead:
        """Convert an ORM organization object to an OrganizationRead response model."""
        return OrganizationRead(
            id=org.id,
            name=org.name,
            slug=org.slug,
            logo_url=getattr(org, "logo_url", None),
            domain=getattr(org, "domain", None),
            settings=getattr(org, "settings", None),
            status=getattr(org, "status", None),
            requested_by_user_id=getattr(org, "requested_by_user_id", None),
            created_at=getattr(org, "created_at", None),
            updated_at=getattr(org, "updated_at", None),
        )

    def get_current(self, db: Session, org_id: str) -> OrganizationRead:
        """Return the organization for the given org_id, raising NotFoundError if missing."""
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")
        return self._org_to_read(org)

    def create_organization(
        self,
        db: Session,
        *,
        name: str,
        slug: str | None = None,
        domain: str | None = None,
        settings: dict[str, Any] | None = None,
        logo_url: str | None = None,
    ) -> OrganizationRead:
        """Create an active organization and provision its default roles and file types."""
        org = self.db.create(
            db,
            name=name,
            slug=slug,
            domain=domain,
            settings=settings,
            logo_url=logo_url,
            status=OrganizationStatus.ACTIVE,
        )
        if self.roles is not None:
            try:
                self.roles.db_model_service.ensure_default_roles(db, str(org.id))
            except Exception as exc:
                logger.error(f"Failed to seed default roles for org {org.id}: {exc}", exc_info=True)
        self._provision_default_file_types(str(org.id))
        return self._org_to_read(org)

    def list_organizations(
        self,
        db: Session,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> OrganizationListResponse:
        """Return a paginated list of organizations, optionally filtered by status."""
        status_enum = OrganizationStatus(status) if status else None
        orgs = self.db.list(db, status=status_enum, limit=limit, offset=offset)
        items = [self._org_to_read(o) for o in orgs]
        return OrganizationListResponse(items=items, total=len(items))

    def get_organization(self, db: Session, org_id: str) -> OrganizationRead:
        """Return a single organization by ID."""
        return self.get_current(db, org_id)

    def update_organization(
        self,
        db: Session,
        org_id: str,
        *,
        name: str | None = None,
        domain: str | None = None,
        settings: dict[str, Any] | None = None,
        logo_url: str | None = None,
        status: str | None = None,
    ) -> OrganizationRead:
        """Update fields on an existing organization, raising NotFoundError if missing."""
        status_enum = OrganizationStatus(status) if status else None
        org = self.db.update(
            db,
            org_id,
            name=name,
            domain=domain,
            settings=settings,
            logo_url=logo_url,
            status=status_enum,
        )
        if not org:
            raise NotFoundError("Organization not found")
        return self._org_to_read(org)

    def rename_current_org(self, db: Session, org_id: str, name: str) -> OrganizationRead:
        """Rename an organization, rejecting if the name is already taken by another org."""
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")

        existing = self.db.get_by_name(db, name)
        if existing and str(existing.id) != str(org_id):
            raise ConflictError("Organization name already taken")

        updated = self.db.update(db, org_id, name=name)
        if not updated:
            raise NotFoundError("Organization not found")
        return self._org_to_read(updated)

    def list_pending(
        self,
        db: Session,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PendingOrganizationListResponse:
        """Return pending organizations with requester details for superadmin review."""
        orgs = self.db.list_pending(db, limit=limit, offset=offset)
        items: list[OrganizationWithRequester] = []
        for org in orgs:
            record = OrganizationWithRequester(
                id=str(org.id),
                name=str(org.name),
                slug=str(org.slug),
                logo_url=getattr(org, "logo_url", None),
                domain=getattr(org, "domain", None),
                settings=getattr(org, "settings", None),
                status=getattr(org, "status", None),
                requested_by_user_id=getattr(org, "requested_by_user_id", None),
                created_at=getattr(org, "created_at", None),
                updated_at=getattr(org, "updated_at", None),
            )
            requester_id = getattr(org, "requested_by_user_id", None)
            if requester_id:
                user = self.db.get_user(db, str(requester_id))
                if user:
                    record.requester_email = getattr(user, "email", None)
                    record.requester_name = getattr(user, "full_name", None)
            items.append(record)
        return PendingOrganizationListResponse(items=items, total=len(items))

    def approve_organization(self, db: Session, org_id: str) -> OrganizationRead:
        """Approve a pending organization, transitioning its status to active."""
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")
        if org.status != OrganizationStatus.PENDING.value:
            return self._org_to_read(org)
        approved = self.db.approve_org(db, org_id)
        if not approved:
            raise NotFoundError("Organization not found after approval")
        if self.roles is not None:
            try:
                roles = self.roles.db_model_service.ensure_default_roles(db, org_id)
                requester_id = getattr(approved, "requested_by_user_id", None)
                if requester_id:
                    admin_role = next((r for r in roles if r.name == "admin"), None)
                    if admin_role:
                        self.roles.db_model_service.assign_role_to_user(db, str(requester_id), org_id, admin_role.id)
            except Exception as exc:
                logger.error(f"Failed to seed roles on org approval for org {org_id}: {exc}", exc_info=True)
        self._provision_default_file_types(org_id)
        return self._org_to_read(approved)

    def reject_organization(self, db: Session, org_id: str) -> OrganizationRead:
        """Reject a pending organization, transitioning its status to rejected."""
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")
        if org.status != OrganizationStatus.PENDING.value:
            return self._org_to_read(org)
        rejected = self.db.reject_org(db, org_id)
        if not rejected:
            raise NotFoundError("Organization not found after rejection")
        return self._org_to_read(rejected)

    def delete_organization(self, db: Session, org_id: str, *, protected_ids: set[str]) -> None:
        """Delete an organization and its users, blocking deletion of protected orgs."""
        if str(org_id) in protected_ids:
            raise ValidationError("Cannot delete protected organization")
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")
        self.db.delete_with_users(db, org_id)

    def list_org_users(
        self,
        db: Session,
        *,
        org_id: str,
        status_filter: str | None,
        limit: int,
        offset: int,
    ) -> OrganizationUserListResponse:
        """Return a paginated list of users belonging to the given organization."""
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")
        users, total = self.db.list_users(
            db,
            org_id=org_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset,
        )
        items = [UserRead.model_validate(u) for u in users]
        return OrganizationUserListResponse(items=items, total=total)

    def create_org_user(self, db: Session, *, org_id: str, payload: PlatformUserCreate) -> UserRead:
        """Create a new user in the organization or add an existing user as a member."""
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")

        existing = self.db.get_user_by_email(db, str(payload.email))
        if existing:
            membership = self.db.get_membership(db, user_id=str(existing.id), org_id=org_id)
            if membership:
                raise ValidationError(
                    f"User {payload.email} is already a member of this organization"
                )
            self.db.add_membership(
                db,
                user_id=str(existing.id),
                org_id=org_id,
                role=str(payload.role),
                status=str(payload.status),
            )
            self._assign_rbac_role(db, user_id=str(existing.id), org_id=org_id, role=str(payload.role))
            return UserRead.model_validate(existing)

        placeholder_password = secrets.token_urlsafe(32)
        user = self.db.create_user(
            db,
            email=str(payload.email),
            full_name=str(payload.full_name),
            role=str(payload.role),
            status=str(payload.status),
            organization_id=org_id,
            hashed_password=hash_password(placeholder_password),
        )
        self.db.add_membership(
            db,
            user_id=str(user.id),
            org_id=org_id,
            role=str(payload.role),
            status=str(payload.status),
        )
        self._assign_rbac_role(db, user_id=str(user.id), org_id=org_id, role=str(payload.role))
        return UserRead.model_validate(user)

    def _assign_rbac_role(self, db: Session, *, user_id: str, org_id: str, role: str) -> None:
        """Mirror the membership role into user_roles — the token reads roles from there.
        Failure is logged, not raised, since the membership is already persisted."""
        if self.roles is None:
            logger.warning(
                f"organizations._assign_rbac_role: roles manager not wired, skipping RBAC assignment for user {user_id} in org {org_id}"
            )
            return
        try:
            self.roles.assign_role_by_name(db, user_id, org_id, role)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"Failed to assign RBAC role '{role}' to user {user_id} in org {org_id}: {exc}"
            )

    def delete_org_user(self, db: Session, *, org_id: str, user_id: str) -> None:
        """Remove a user from the organization, deleting them entirely if it is their primary org."""
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")
        user = self.db.get_user(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        membership = self.db.get_membership(db, user_id=user_id, org_id=org_id)
        belongs_via_primary = str(getattr(user, "organization_id", "")) == str(org_id)
        if not membership and not belongs_via_primary:
            raise NotFoundError("User not found in this organization")
        self.db.remove_membership(db, user_id=user_id, org_id=org_id)
        self.db.remove_user_org_roles(db, user_id=user_id, org_id=org_id)
        if belongs_via_primary:
            self.db.delete_user(db, user_id=user_id)

    def provision_tenant(
        self, db: Session, *, org_id: str, create_sample_job: bool = False
    ) -> ProvisionResult:
        """Provision default resources (RBAC roles, etc.) for a tenant organization."""
        result = ProvisionResult(organization_id=org_id, success=False)
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")

        try:
            if self.roles is not None:
                roles = self.roles.db_model_service.ensure_default_roles(db, org_id)
                result.rbac_roles_created = len(roles)
            else:
                logger.warning(f"provision_tenant: roles service not wired, skipping role seeding for org {org_id}")
        except Exception as exc:
            result.errors.append(f"RBAC role provisioning failed: {exc}")

        if create_sample_job:
            result.errors.append("Sample job provisioning not implemented in modular backend yet")

        result.success = not result.errors
        result.provisioned_at = datetime.now(UTC)
        return result

    def get_provision_status(self, db: Session, *, org_id: str) -> ProvisionStatus:
        """Return the current provisioning status for the given organization."""
        org = self.db.get_by_id(db, org_id)
        if not org:
            raise NotFoundError("Organization not found")
        has_rbac = self.db.has_rbac_roles(db, org_id)
        return ProvisionStatus(
            organization_id=org_id,
            fully_provisioned=False,
            has_entity_types=False,
            has_picklists=False,
            has_form_schemas=False,
            has_document_types=False,
            has_funnels=False,
            has_view_definitions=False,
            has_agent_definitions=False,
            has_rbac_roles=has_rbac,
            entity_type_count=0,
            picklist_count=0,
            form_schema_count=0,
            document_type_count=0,
            funnel_count=0,
        )

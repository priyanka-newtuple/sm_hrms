"""Business logic manager for the user module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from common.logger import logger
from common.security import create_access_token
from exceptions import AuthorizationError, NotFoundError, ValidationError
from user.db_models import UserRole, UserStatus
from user.models.interface import OrgMemberAssignability, OrgMembershipVerdict
from user.models.response import (
    UserOrganizationRead,
    UserOrganizationsResponse,
    UserResponse,
    UserSearchResult,
)

@runtime_checkable
class RolesServiceProtocol(Protocol):
    def get_user_roles_with_permissions(self, db: Any, user_id: str, org_id: str) -> list[Any]: ...


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from common.configuration import Configuration
    from database.manager import DatabaseServiceManager
    from user.db_models import FieldPermission, Role, User, UserModelService


class UserServiceManager:
    """Stateless user management business logic.

    Instantiated once and injected into UserRestController.
    Each method receives the per-request DB session as a parameter.
    """

    def __init__(
        self,
        user_model_service: UserModelService,
        database_service_manager: DatabaseServiceManager | None = None,
        config: Configuration | None = None,
        roles_db_service: RolesServiceProtocol | None = None,
    ) -> None:
        self.db_service = user_model_service
        self.roles_db_service = roles_db_service
        self.module_name = "user"
        self._started = False

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_users(
        self,
        db: Session,
        organization_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserResponse]:
        users = self.db_service.list_all(
            db, organization_id=organization_id, status=status, limit=limit, offset=offset
        )
        responses = [UserResponse.model_validate(u) for u in users]
        if organization_id:
            # Show the org-scoped membership role and status, not the primary-org
            # account mirror — suspension is per-org (user_organizations.status).
            memberships = self.db_service.get_memberships_map(
                db, organization_id, [r.id for r in responses]
            )
            for resp in responses:
                membership = memberships.get(resp.id)
                if membership is not None:
                    resp.role = str(membership.role)
                resp.status = self._effective_org_status(
                    resp.status, str(membership.status) if membership is not None else None
                )
        return responses

    def list_pending(self, db: Session, organization_id: str | None = None) -> list[UserResponse]:
        users = self.db_service.list_pending(db, organization_id=organization_id)
        return [UserResponse.model_validate(u) for u in users]

    def _require_same_org(self, db: Session, user_id: str, organization_id: str | None) -> None:
        """Raise NotFoundError if organization_id is set and user_id isn't a member of it.

        Cross-tenant targets must 404 (not 403) so callers can't distinguish
        "wrong org" from "doesn't exist" and enumerate other tenants' users.
        """
        if organization_id and not self.db_service.is_member_of_org(db, user_id, organization_id):
            raise NotFoundError("User not found")

    def get_user(self, db: Session, user_id: str, organization_id: str | None = None) -> UserResponse:
        user = self.db_service.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        self._require_same_org(db, user_id, organization_id)
        response = UserResponse.model_validate(user)
        if organization_id:
            membership = self.db_service.get_membership(db, user_id, organization_id)
            response.status = self._effective_org_status(
                response.status, membership.status if membership else None
            )
        return response

    def get_user_display_info(self, user_id: str) -> tuple[str | None, str | None]:
        """Return (full_name, role) for a user — used by audit emitters to snapshot actor identity."""
        return self.db_service.fetch_display_info(user_id)

    def get_org_member_assignability(
        self, user_id: str, organization_id: str
    ) -> OrgMemberAssignability:
        """Report whether a user can be handed work in an organization.

        Assignable requires an explicit membership row in that organization and
        an active status on both the account and the membership. A matching
        primary organization does not count.
        """
        if not user_id:
            return OrgMemberAssignability(
                user_id=user_id, full_name="", verdict=OrgMembershipVerdict.NOT_FOUND
            )
        found = self.db_service.fetch_user_with_membership(user_id, organization_id)
        if found is None:
            return OrgMemberAssignability(
                user_id=user_id, full_name="", verdict=OrgMembershipVerdict.NOT_FOUND
            )
        user, membership = found
        if membership is None:
            verdict = OrgMembershipVerdict.NOT_A_MEMBER
        else:
            verdict = self._assignability_verdict(
                self._effective_org_status(user.status, membership.status)
            )
        return OrgMemberAssignability(
            user_id=user_id, full_name=user.full_name or "", verdict=verdict
        )

    @staticmethod
    def _assignability_verdict(effective_status: str) -> OrgMembershipVerdict:
        """Translate an effective org-scoped status into an assignability verdict."""
        if effective_status == UserStatus.ACTIVE.value:
            return OrgMembershipVerdict.ASSIGNABLE
        if effective_status == UserStatus.SUSPENDED.value:
            return OrgMembershipVerdict.SUSPENDED
        return OrgMembershipVerdict.INACTIVE_ACCOUNT

    def get_actor_display_info(self, actor: dict[str, object]) -> tuple[str | None, str | None]:
        """Return (actor_name, actor_role) for audit snapshot given an actor dict.

        System actors carry their identity in the dict itself.
        Human actors are resolved via a point-in-time DB lookup.
        """
        if str(actor.get("actor_type") or "").lower() == "system":
            return str(actor.get("actor_name") or "System"), str(actor.get("actor_role") or "SYSTEM")
        user_id = str(actor.get("user_id") or "")
        return self.db_service.fetch_display_info(user_id)

    # ── Mutations ─────────────────────────────────────────────────────────────

    def approve_user(self, db: Session, user_id: str, organization_id: str | None = None) -> UserResponse:
        user = self.db_service.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        self._require_same_org(db, user_id, organization_id)
        if user.status != UserStatus.PENDING.value:
            raise ValidationError(f"User is not pending (current status: {user.status})")
        updated = self.db_service.set_status(db, user_id, UserStatus.ACTIVE.value)
        if self.roles_db_service is not None and updated.organization_id:
            try:
                self.db_service.ensure_default_roles(db, updated.organization_id)
                viewer_role = self.db_service.get_role_by_name(db, updated.organization_id, UserRole.VIEWER.value)
                if viewer_role:
                    self.db_service.assign_role_to_user(db, user_id, updated.organization_id, viewer_role.id)
            except Exception:
                pass
        return UserResponse.model_validate(updated)

    def reject_user(self, db: Session, user_id: str, organization_id: str | None = None) -> UserResponse:
        user = self.db_service.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        self._require_same_org(db, user_id, organization_id)
        if user.status != UserStatus.PENDING.value:
            raise ValidationError(f"User is not pending (current status: {user.status})")
        updated = self.db_service.set_status(db, user_id, UserStatus.REJECTED.value)
        return UserResponse.model_validate(updated)

    def update_role(
        self,
        db: Session,
        user_id: str,
        role: str,
        organization_id: str | None = None,
        caller_user_id: str | None = None,
    ) -> UserResponse:
        """Change the user's role within one org: membership row + RBAC assignment.
        The legacy users.role column is only touched when it mirrors this org."""
        user = self.db_service.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        org_id = organization_id or str(user.organization_id or "")
        if not org_id:
            raise ValidationError("No organization context for role update")
        self._require_same_org(db, user_id, org_id if organization_id else None)

        self.db_service.ensure_default_roles(db, org_id)
        target_role = self.db_service.get_role_by_name(db, org_id, role)
        if target_role is None:
            raise ValidationError(f"Unknown role '{role}' for this organization")

        if caller_user_id and user_id == caller_user_id:
            caller_roles = self.db_service.get_user_roles(db, caller_user_id, org_id)
            caller_priority = max((r.priority for r in caller_roles), default=-1)
            if target_role.priority >= caller_priority:
                raise AuthorizationError("You cannot grant yourself a role at or above your current rank")

        self.db_service.set_membership_role(db, user_id, org_id, role)
        self._sync_rbac_role(db, user_id, org_id, role)
        if str(user.organization_id or "") == org_id:
            user = self.db_service.set_role(db, user_id, role) or user
        response = UserResponse.model_validate(user)
        response.role = role
        return response

    def _sync_rbac_role(self, db: Session, user_id: str, org_id: str, role: str) -> None:
        """Replace the user's RBAC assignments in the org with the new role."""
        if self.roles_db_service is None:
            return
        try:
            self.db_service.ensure_default_roles(db, org_id)
            new_role = self.db_service.get_role_by_name(db, org_id, role)
            if new_role is None:
                logger.warning(f"update_role: role '{role}' not found in org {org_id}, skipping RBAC sync")
                return
            for assigned in self.db_service.get_user_roles(db, user_id, org_id):
                if str(assigned.id) != str(new_role.id):
                    self.db_service.remove_role_from_user(db, user_id, org_id, str(assigned.id))
            self.db_service.assign_role_to_user(db, user_id, org_id, str(new_role.id))
        except Exception as exc:
            logger.warning(f"RBAC role sync failed for user {user_id} in org {org_id}: {exc}")

    def suspend_user(
        self, db: Session, user_id: str, current_user_id: str, organization_id: str | None = None
    ) -> UserResponse:
        """Suspend a user's membership in one organization (not the whole account)."""
        if user_id == current_user_id:
            raise ValidationError("You cannot suspend yourself")
        user = self.db_service.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        self._require_same_org(db, user_id, organization_id)
        org_id = organization_id or str(user.organization_id or "")
        self._transition_membership_status(
            db, user_id, org_id,
            UserStatus.ACTIVE.value, UserStatus.SUSPENDED.value,
            "User is not an active member of this organization",
        )
        return self._org_scoped_response(db, user, org_id)

    def reactivate_user(self, db: Session, user_id: str, organization_id: str | None = None) -> UserResponse:
        """Reactivate a user's suspended membership in one organization."""
        user = self.db_service.get_by_id(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        self._require_same_org(db, user_id, organization_id)
        org_id = organization_id or str(user.organization_id or "")
        self._transition_membership_status(
            db, user_id, org_id,
            UserStatus.SUSPENDED.value, UserStatus.ACTIVE.value,
            "User is not a suspended member of this organization",
        )
        return self._org_scoped_response(db, user, org_id)

    def _transition_membership_status(
        self, db: Session, user_id: str, org_id: str,
        expected_status: str, target_status: str, error_message: str,
    ) -> None:
        """Move the membership from expected_status to target_status, raising
        ValidationError if it is missing or not in expected_status."""
        membership = self.db_service.get_membership(db, user_id, org_id)
        if membership is None or membership.status != expected_status:
            raise ValidationError(error_message)
        self.db_service.set_membership_status(db, user_id, org_id, target_status)

    def _org_scoped_response(self, db: Session, user: User, org_id: str) -> UserResponse:
        """Build a UserResponse whose status reflects the org membership once the
        account is active."""
        response = UserResponse.model_validate(user)
        membership = self.db_service.get_membership(db, user.id, org_id)
        response.status = self._effective_org_status(
            response.status, membership.status if membership else None
        )
        return response

    @staticmethod
    def _effective_org_status(account_status: str, membership_status: str | None) -> str:
        """Status to show in an org-scoped view. The account lifecycle status
        (pending/rejected) takes precedence so signup approvals stay visible;
        once the account is active, the per-org membership status is shown
        (this is where suspension lives)."""
        if account_status != UserStatus.ACTIVE.value:
            return account_status
        return membership_status or account_status

    def get_my_organizations(self, db: Session, current_user: User) -> UserOrganizationsResponse:
        return self.get_my_organizations_by_id(
            db, current_user.id, {"organization_id": current_user.organization_id}
        )

    def get_my_organizations_by_id(
        self, db: Session, user_id: str, actor: dict
    ) -> UserOrganizationsResponse:
        current_org_id = actor.get("organization_id")
        current_user = self.db_service.get_by_id(db, user_id)
        if not current_user:
            raise NotFoundError("User not found")
        memberships = self.db_service.get_organizations_for_user(db, user_id)
        orgs = [
            UserOrganizationRead(
                id=membership.id,
                organization_id=org.id,
                organization_name=org.name,
                organization_slug=org.slug,
                organization_domain=org.domain,
                organization_logo_url=org.logo_url,
                organization_status=org.status,
                role=membership.role,
                status=membership.status,
                is_current=org.id == current_org_id,
            )
            for membership, org in memberships
        ]
        # Fallback — legacy users may have users.organization_id set without a user_organizations row.
        seen_ids = {o.organization_id for o in orgs}
        if current_user.organization_id and current_user.organization_id not in seen_ids:
            primary = self.db_service.get_organization_by_id(db, current_user.organization_id)
            if primary:
                orgs.append(
                    UserOrganizationRead(
                        id=None,
                        organization_id=primary.id,
                        organization_name=primary.name,
                        organization_slug=primary.slug,
                        organization_domain=primary.domain,
                        organization_logo_url=primary.logo_url,
                        organization_status=primary.status,
                        role=current_user.role,
                        status=current_user.status,
                        is_current=True,
                    )
                )
        return UserOrganizationsResponse(
            organizations=orgs,
            current_organization_id=current_org_id,
        )

    def switch_organization(
        self, db: Session, current_user: User, organization_id: str
    ) -> tuple[str, str]:
        """Switch the user's active org and mint a fresh access token.

        The access token embeds organization_id as a claim; without re-issuing it,
        downstream tenancy-scoped endpoints would continue to read the old org.
        Refresh token is left untouched (it has no org_id claim).
        """
        self.db_service.switch_organization(db, current_user, organization_id)
        org = self.db_service.get_organization_by_id(db, organization_id)
        org_name = str(org.name) if org else organization_id
        roles: list[str] = []
        if self.roles_db_service is not None:
            try:
                if getattr(current_user, "role", None) == UserRole.SUPERADMIN.value:
                    self.roles_db_service.ensure_superadmin_role_in_org(
                        db, current_user.id, organization_id
                    )
                assigned_roles = self.roles_db_service.get_user_roles_with_permissions(
                    db, current_user.id, organization_id
                )
                if not assigned_roles and getattr(current_user, "role", None):
                    # No RBAC assignment in the target org would mean an empty
                    # roles claim and 403s everywhere — mirror the membership role.
                    role_obj = self.roles_db_service.get_role_by_name(
                        db, organization_id, str(current_user.role)
                    )
                    if role_obj:
                        self.roles_db_service.assign_role_to_user(
                            db, current_user.id, organization_id, role_obj.id
                        )
                        assigned_roles = self.roles_db_service.get_user_roles_with_permissions(
                            db, current_user.id, organization_id
                        )
                if assigned_roles:
                    roles = [r.name for r in assigned_roles]
            except Exception as exc:
                logger.warning(f"Failed to load roles for org switch (user={current_user.id} org={organization_id}): {exc}")
        access_token = create_access_token(
            subject=current_user.id,
            organization_id=organization_id,
            roles=roles,
        )
        return org_name, access_token

    def search_users(
        self, db: Session, query: str, organization_id: str, limit: int = 10
    ) -> list[UserSearchResult]:
        users = self.db_service.search_users(
            db, query=query, organization_id=organization_id, limit=limit
        )
        return [
            UserSearchResult(id=user.id, email=user.email, full_name=user.full_name, avatar_url=user.avatar_url, role=user.role)
            for user in users
        ]

    def get_stats(self, db: Session, organization_id: str) -> dict:
        return self.db_service.get_stats(db, organization_id)

    # ── Permissions ───────────────────────────────────────────────────────────

    def get_user_role_names(self, db: Session, user_id: str, org_id: str) -> list[str]:
        return [r.name for r in self.db_service.get_user_roles(db, user_id, org_id)]

    def get_user_primary_role(self, db: Session, user_id: str, org_id: str) -> Role | None:
        roles = self.db_service.get_user_roles(db, user_id, org_id)
        return max(roles, key=lambda r: r.priority) if roles else None

    def has_permission(
        self, db: Session, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        roles = self.db_service.get_user_roles(db, user_id, org_id)
        if not roles:
            return self._fallback_legacy_check(db, user_id, action)
        return any(
            (perm.entity_type in (entity_type, "*")) and perm.action == action and perm.allowed
            for role in roles
            for perm in role.permissions
        )

    def get_field_permissions(
        self, db: Session, user_id: str, org_id: str, entity_type: str
    ) -> dict[str, FieldPermission]:
        roles = self.db_service.get_user_roles(db, user_id, org_id)
        if not roles:
            return {}
        field_perms = self.db_service.get_field_permissions_for_roles(
            db, [r.id for r in roles], entity_type
        )
        merged: dict[str, FieldPermission] = {}
        for fp in field_perms:
            existing = merged.get(fp.field_name)
            if (
                existing is None
                or (fp.can_view and not existing.can_view)
                or (fp.can_edit and not existing.can_edit)
                or (not fp.mask_value and existing.mask_value)
            ):
                merged[fp.field_name] = fp
        return merged

    def filter_entity_data(
        self, db: Session, user_id: str, org_id: str, entity_type: str, data: dict
    ) -> dict:
        field_perms = self.get_field_permissions(db, user_id, org_id, entity_type)
        if not field_perms:
            return data
        filtered = {}
        for field_name, value in data.items():
            fp = field_perms.get(field_name)
            if fp is None:
                filtered[field_name] = value
            elif fp.can_view:
                filtered[field_name] = self._mask_value(value) if fp.mask_value else value
        return filtered

    def get_editable_fields(
        self, db: Session, user_id: str, org_id: str, entity_type: str
    ) -> set[str] | None:
        field_perms = self.get_field_permissions(db, user_id, org_id, entity_type)
        if not field_perms:
            return None
        non_editable = {fn for fn, fp in field_perms.items() if not fp.can_edit}
        return non_editable or None

    def get_user_permissions_summary(self, db: Session, user_id: str, org_id: str) -> dict:
        roles = self.db_service.get_user_roles(db, user_id, org_id)
        if not roles:
            return {"roles": [], "entity_permissions": {}, "field_permissions": {}}

        entity_perms: dict[str, dict[str, bool]] = {}
        for role in roles:
            for perm in role.permissions:
                entity_fields = entity_perms.setdefault(perm.entity_type, {})
                if perm.allowed:
                    entity_fields[perm.action] = True
                elif perm.action not in entity_fields:
                    entity_fields[perm.action] = False

        field_perms_db = self.db_service.get_all_field_permissions_for_roles(
            db, [r.id for r in roles]
        )
        field_perms: dict[str, dict[str, dict]] = {}
        for fp in field_perms_db:
            entity_fields = field_perms.setdefault(fp.entity_type, {})
            existing = entity_fields.get(fp.field_name)
            if existing is None:
                entity_fields[fp.field_name] = {
                    "can_view": fp.can_view,
                    "can_edit": fp.can_edit,
                    "mask_value": fp.mask_value,
                }
            else:
                existing["can_view"] |= fp.can_view
                existing["can_edit"] |= fp.can_edit
                existing["mask_value"] &= fp.mask_value

        return {
            "roles": [
                {
                    "id": r.id,
                    "name": r.name,
                    "display_name": r.display_name,
                    "priority": r.priority,
                    "color": r.color,
                    "is_system": r.is_system,
                }
                for r in roles
            ],
            "entity_permissions": entity_perms,
            "field_permissions": field_perms,
        }

    @staticmethod
    def _mask_value(value: object) -> str:
        if value is None:
            return "***"
        if isinstance(value, str):
            if "@" in value:
                parts = value.split("@")
                return f"{parts[0][0]}***@{parts[1]}" if len(parts) == 2 else "***"
            if len(value) > 4:
                return value[:2] + "***"
            return "***"
        return "***"

    def _fallback_legacy_check(self, db: Session, user_id: str, action: str) -> bool:
        """Fallback for users without RBAC roles using the legacy User.role field."""
        user = self.db_service.get_by_id(db, user_id)
        if not user:
            return False
        if user.role == UserRole.ADMIN.value:
            return True
        if user.role == UserRole.VIEWER.value:
            return action == "view"
        return False

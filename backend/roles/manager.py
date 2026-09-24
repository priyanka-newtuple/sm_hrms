"""Business logic manager for RBAC roles."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from common.auth import build_actor_context
from common.condition_values import parse_membership_values
from common.deps import get_db
from common.enums import DefaultRole, WorkflowPermissionKey
from common.logger import logger
from common.protocols import EntityAccessCheck, EntityConditionSpec, EntityReadPolicy
from exceptions import NotFoundError, PersistenceError, ServiceError, ValidationError
from roles.db_models import Role, RolesModelService
from roles.models.interface import (
    EntityConditionOperator,
    EntityConditionValueSource,
    PermissionCheckResult,
)
from roles.models.request import (
    EntityPermissionCreate,
    EntityReadFilter,
    FieldPermissionCreate,
    RoleCreateRequest,
    RoleDuplicateRequest,
    RoleUpdateRequest,
    TransitionPermissionCreate,
    UserRoleSetRequest,
    WorkflowPermissionCreate,
)
from roles.models.response import (
    EntityPermissionRead,
    FieldPermissionRead,
    PermissionsSummary,
    RoleListItem,
    RolePermissionRead,
    RoleRead,
    RoleSummary,
    TransitionPermissionRead,
    UserRoleRead,
    WorkflowPermissionRead,
)

_DEFAULT_ROLE_VALUES = frozenset(r.value for r in DefaultRole)
from roles.db_models import Role, UserRoleAssignment


class RolesServiceManager:
    """Orchestrate role CRUD, user role assignment, and permission summary APIs."""

    def __init__(
        self,
        roles_db_model_service: RolesModelService,
        database_service_manager: Any = None,
        config: Any = None,
        auth_service_manager: Any = None,
        *dependencies,
    ) -> None:
        """Description:
            Initialize the roles manager with its persistence dependency and optional wiring parameters.

        Args:
            roles_db_model_service: Roles DB/persistence service.
            database_service_manager: Unused legacy/wiring parameter (kept for consistency).
            config: Unused legacy/wiring parameter (kept for consistency).
            auth_service_manager: Unused legacy/wiring parameter (kept for consistency).
            *dependencies: Extra optional dependencies (unused).

        Returns:
            None

        Raises:
            ServiceError: If the persistence dependency is not configured.
        """
        super().__init__()
        _ = config, auth_service_manager, dependencies
        if roles_db_model_service is None:
            raise ServiceError("roles persistence dependency is not configured")
        self.db_model_service = roles_db_model_service
        self.database_service_manager = database_service_manager
        self.workflow_service_manager: Any = None
        self.module_name = "roles"
        self._started = False

    def start(self) -> None:
        """Description:
            Mark the manager as started (used by app lifespan wiring).

        Args:
            None

        Returns:
            None

        Raises:
            None
        """
        self._started = True

    def stop(self) -> None:
        """Description:
            Mark the manager as stopped (used by app lifespan wiring).

        Args:
            None

        Returns:
            None

        Raises:
            None
        """
        self._started = False

    # ── Mapping helpers ─────────────────────────────────────────────────────

    def _to_role_read(self, db: Session, role: Role) -> RoleRead:
        """Description:
            Map a Role ORM object into the API response model.

        Args:
            db: SQLAlchemy session.
            role: Role ORM instance.

        Returns:
            RoleRead response model.

        Raises:
            PersistenceError: If role assignment counting fails.
        """
        user_count = self.db_model_service.count_role_assignments(db, role.id, role.organization_id)
        return RoleRead(
            id=role.id,
            organization_id=role.organization_id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            is_system=role.is_system,
            priority=int(role.priority),
            color=role.color,
            permissions=[
                RolePermissionRead(permission_key=p.permission_key)
                for p in role.permissions
                if p.permission_key is not None
            ],
            entity_permissions=[
                EntityPermissionRead(
                    id=p.id,
                    entity_type=p.entity_type,
                    action=p.action,
                    allowed=bool(p.allowed),
                    entity_field=p.entity_field,
                    operator=p.operator,
                    value_source=p.value_source,
                    condition_value=p.condition_value,
                    read_filter=(
                        EntityReadFilter.model_validate(p.read_filter)
                        if getattr(p, "read_filter", None) is not None
                        else None
                    ),
                )
                for p in role.permissions
                if p.entity_type is not None and p.permission_key is None
            ],
            field_permissions=[
                FieldPermissionRead(
                    id=fp.id,
                    entity_type=fp.entity_type,
                    field_name=fp.field_name,
                    can_view=bool(fp.can_view),
                    can_edit=bool(fp.can_edit),
                    mask_value=bool(fp.mask_value),
                )
                for fp in role.field_permissions
            ],
            transition_permissions=[
                TransitionPermissionRead(
                    id=tp.id,
                    machine_name=str(tp.machine_name),
                    transition_key=str(tp.transition_key),
                )
                for tp in role.transition_permissions
            ],
            workflow_permissions=[
                WorkflowPermissionRead(id=wp.id, machine_name=str(wp.machine_name))
                for wp in role.workflow_permissions
            ],
            user_count=int(user_count),
            created_at=role.created_at,
            updated_at=role.updated_at,
        )

    def _validate_entity_permissions(
        self, db: Session, org_id: str, entries: list[EntityPermissionCreate]
    ) -> None:
        seen: set[tuple[str, str]] = set()
        for ep in entries:
            key = (ep.entity_type, ep.action)
            if key in seen:
                raise ValidationError(f"Duplicate entity permission: ({ep.entity_type}, {ep.action})")
            seen.add(key)
            if not self.db_model_service.entity_type_exists(db, org_id, ep.entity_type):
                raise ValidationError(f"Unknown entity type '{ep.entity_type}' for this organization")
            self._validate_entity_condition(db, org_id, ep)

    def _validate_entity_condition(
        self, db: Session, org_id: str, ep: EntityPermissionCreate
    ) -> None:
        """Validate an entity permission's optional read condition at save time (entity
        field permission filter) — rejects unknown fields/operators/value sources up
        front so a bad condition can never be discovered later at check time."""
        if ep.read_filter is not None:
            if ep.action != "view":
                raise ValidationError("Read filters are only supported on view permissions.")
            if any(
                value is not None
                for value in (ep.entity_field, ep.operator, ep.value_source, ep.condition_value)
            ):
                raise ValidationError("Provide read_filter or a legacy condition, not both.")
            fields = self.db_model_service.get_entity_type_schema_fields(db, org_id, ep.entity_type)
            for condition in ep.read_filter.conditions:
                if not condition.entity_field.strip() or not condition.condition_value.strip():
                    raise ValidationError("Every condition needs a field and a non-empty value.")
                self._validate_membership_value(condition.operator, condition.condition_value)
                if fields is None or not self._schema_has_field(fields, condition.entity_field):
                    raise ValidationError(
                        f"The field '{condition.entity_field}' does not exist on entity type '{ep.entity_type}'."
                    )
            return
        condition_fields = (ep.entity_field, ep.operator, ep.condition_value)
        if all(f is None for f in condition_fields):
            return
        if any(f is None for f in condition_fields):
            raise ValidationError(
                "entity_field, operator, and condition_value must all be provided together, "
                "or all omitted."
            )
        if ep.operator not in EntityConditionOperator.list():
            raise ValidationError(f"'{ep.operator}' is not a supported comparison operator.")
        if ep.value_source is not None and ep.value_source != EntityConditionValueSource.LITERAL.value:
            raise ValidationError(f"'{ep.value_source}' is not a supported condition value source.")
        self._validate_membership_value(ep.operator, ep.condition_value)
        fields = self.db_model_service.get_entity_type_schema_fields(db, org_id, ep.entity_type)
        if fields is None or not self._schema_has_field(fields, ep.entity_field):
            raise ValidationError(
                f"The field '{ep.entity_field}' does not exist on entity type '{ep.entity_type}'."
            )

    @staticmethod
    def _validate_membership_value(operator: str, value: str) -> None:
        if operator in {"in", "not_in"} and not parse_membership_values(value):
            raise ValidationError("Enter at least one non-empty comma-separated value.")
        if operator in {"==", "!="} and "," in value:
            raise ValidationError(
                "Commas are not allowed with 'Equals' or 'Not equals'. "
                "Use 'Is one of' or 'Is not one of' to match multiple values."
            )

    @staticmethod
    def _schema_has_field(fields: list[dict], field_name: str) -> bool:
        return any((f.get("id") or f.get("field") or f.get("name")) == field_name for f in fields)

    def _validate_permission_keys(self, db: Session, keys: list[str]) -> None:
        if not keys:
            return
        if self.db_model_service._permissions_svc is None:
            return
        for key in keys:
            if not self.db_model_service._permissions_svc.get_by_key(db, key):
                raise ValidationError(f"Unknown permission key '{key}'")

    def _validate_transition_permissions(
        self, db: Session, org_id: str, entries: list[TransitionPermissionCreate]
    ) -> None:
        """Reject unknown workflows/transitions and duplicate (machine_name, transition_key) pairs."""
        seen: set[tuple[str, str]] = set()
        for entry in entries:
            key = (entry.machine_name, entry.transition_key)
            if key in seen:
                raise ValidationError(f"Duplicate transition permission: ({entry.machine_name}, {entry.transition_key})")
            seen.add(key)
            if self.workflow_service_manager is None:
                continue
            machine = self.workflow_service_manager.get_state_machine_by_name(org_id, entry.machine_name)
            if machine is None:
                raise ValidationError(f"Unknown workflow '{entry.machine_name}' for this organization")
            # valid_keys = [t.key for t in machine.definition.transitions]
            # if entry.transition_key not in valid_keys:
            #     raise ValidationError(f"Unknown transition key '{entry.transition_key}' in workflow '{entry.machine_name}'")

    def _validate_workflow_permissions(
        self, org_id: str, entries: list[WorkflowPermissionCreate]
    ) -> None:
        """Validate a non-empty, duplicate-free workflow allow-list."""
        seen: set[str] = set()
        for entry in entries:
            if entry.machine_name in seen:
                raise ValidationError(f"Duplicate workflow permission: {entry.machine_name}")
            seen.add(entry.machine_name)
            if self.workflow_service_manager is not None and (
                self.workflow_service_manager.get_state_machine_by_name(org_id, entry.machine_name) is None
            ):
                raise ValidationError(f"Unknown workflow '{entry.machine_name}' for this organization")

    @staticmethod
    def _validate_transition_workflow_scope(
        workflows: list, transitions: list
    ) -> None:
        allowed = {entry.machine_name for entry in workflows}
        outside = sorted({entry.machine_name for entry in transitions} - allowed)
        if allowed and outside:
            raise ValidationError(
                f"Transition permissions require workflow access: {', '.join(outside)}"
            )

    @staticmethod
    def _prune_transitions_to_workflow_scope(workflows: list, transitions: list) -> list:
        """Drop stale transition grants when an admin submits a narrowed workflow scope."""
        allowed = {entry.machine_name for entry in workflows}
        if not allowed:
            return list(transitions)
        return [entry for entry in transitions if entry.machine_name in allowed]

    def _validate_field_permissions(
        self, db: Session, org_id: str, entries: list[FieldPermissionCreate]
    ) -> None:
        seen: set[tuple[str, str]] = set()
        for fp in entries:
            key = (fp.entity_type, fp.field_name)
            if key in seen:
                raise ValidationError(f"Duplicate field permission: ({fp.entity_type}, {fp.field_name})")
            seen.add(key)
            if not self.db_model_service.entity_type_exists(db, org_id, fp.entity_type):
                raise ValidationError(f"Unknown entity type '{fp.entity_type}' for this organization")
            # if not self.db_model_service.entity_field_exists(db, org_id, fp.entity_type, fp.field_name):
            #     raise ValidationError(f"Unknown field '{fp.field_name}' on entity type '{fp.entity_type}'")

    def _ensure_default_roles(self, db: Session, organization_id: str) -> None:
        """Description:
            Ensure system roles exist for the organization.

        Args:
            db: SQLAlchemy session.
            organization_id: Organization id.

        Returns:
            None

        Raises:
            PersistenceError: If the persistence layer cannot ensure defaults.
        """
        self.db_model_service.ensure_default_roles(db, organization_id)

    def _validate_org_membership(self, db: Session, user_id: str, organization_id: str) -> None:
        """Raise NotFoundError or ValidationError if user does not belong to the org.

        Checks the real user_organizations membership, not just the primary-org
        column, so genuine multi-org members aren't rejected in their non-primary orgs.
        """
        user = self.db_model_service.get_user(db, user_id)
        if not user:
            raise NotFoundError("User not found")
        if str(user.organization_id) == str(organization_id):
            return
        if self.db_model_service.get_user_org_membership(db, user_id, organization_id) is None:
            raise ValidationError("User does not belong to this organization")

    # ── Role CRUD ───────────────────────────────────────────────────────────

    def list_roles(self, db: Session, organization_id: str) -> list[RoleListItem]:
        """Description:
            List all roles (system + custom) for an organization.

        Args:
            db: SQLAlchemy session.
            organization_id: Organization id.

        Returns:
            List of role list items.

        Raises:
            PersistenceError: If reads fail.
        """
        self._ensure_default_roles(db, organization_id)
        roles = self.db_model_service.list_roles(db, organization_id)
        items: list[RoleListItem] = []
        for role in roles:
            user_count = self.db_model_service.count_role_assignments(db, role.id, organization_id)
            items.append(
                RoleListItem(
                    id=role.id,
                    name=role.name,
                    display_name=role.display_name,
                    description=role.description,
                    is_system=role.is_system,
                    priority=int(role.priority),
                    color=role.color,
                    user_count=int(user_count),
                    created_at=role.created_at,
                )
            )
        return items

    def get_role(
        self, db: Session, role_id: str, organization_id: str, actor_roles: list[str] | None = None
    ) -> RoleRead:
        """Description:
            Get a role by id scoped to the organization.
            Superadmin can fetch roles from any organization.

        Args:
            db: SQLAlchemy session.
            role_id: Role id.
            organization_id: Organization id.
            actor_roles: Actor's roles for superadmin bypass.

        Returns:
            RoleRead for the requested role.

        Raises:
            NotFoundError: If the role does not exist in the org.
            PersistenceError: If reads fail.
        """
        is_superadmin = DefaultRole.SUPERADMIN.value in (actor_roles or [])
        if is_superadmin:
            role = self.db_model_service.get_role_by_id(db, role_id)
        else:
            role = self.db_model_service.get_role(db, role_id, organization_id)
        if not role:
            raise NotFoundError("Role not found")
        return self._to_role_read(db, role)

    def create_role(self, db: Session, organization_id: str, payload: RoleCreateRequest) -> RoleRead:
        """Description:
            Create a new custom role for the organization.

        Args:
            db: SQLAlchemy session.
            organization_id: Organization id.
            payload: Role creation request.

        Returns:
            Newly created role.

        Raises:
            ValidationError: If a role with the same name already exists.
            PersistenceError: If persistence operations fail.
        """
        self._ensure_default_roles(db, organization_id)
        existing = self.db_model_service.get_role_by_name(db, organization_id, payload.name)
        if existing:
            raise ValidationError(f"Role with name '{payload.name}' already exists")
        self._validate_permission_keys(db, [p.permission_key for p in payload.permissions])
        self._validate_entity_permissions(db, organization_id, payload.entity_permissions)
        self._validate_field_permissions(db, organization_id, payload.field_permissions)
        self._validate_transition_permissions(db, organization_id, payload.transition_permissions)
        self._validate_workflow_permissions(organization_id, payload.workflow_permissions)
        self._validate_transition_workflow_scope(
            payload.workflow_permissions, payload.transition_permissions
        )
        role = self.db_model_service.create_role(db, organization_id, payload)
        return self._to_role_read(db, role)

    def update_role(self, db: Session, role_id: str, organization_id: str, payload: RoleUpdateRequest, actor_roles: list[str] | None = None) -> RoleRead:
        """Description:
            Update role fields and (optionally) replace its permissions.

        Args:
            db: SQLAlchemy session.
            role_id: Role id.
            organization_id: Organization id.
            payload: Role update request.

        Returns:
            Updated role.

        Raises:
            NotFoundError: If the role does not exist.
            ValidationError: If the update violates business rules.
            PersistenceError: If persistence operations fail.
        """
        role = self.db_model_service.get_role(db, role_id, organization_id)
        if not role:
            raise NotFoundError("Role not found")
        is_superadmin = DefaultRole.SUPERADMIN.value in (actor_roles or [])
        if role.is_system and not is_superadmin:
            if payload.priority is not None:
                raise ValidationError("Cannot change priority of system roles")
            if payload.permissions is not None:
                raise ValidationError("Cannot change permissions of system roles")
            if payload.entity_permissions is not None:
                raise ValidationError("Cannot change entity permissions of system roles")
            if payload.field_permissions is not None:
                raise ValidationError("Cannot change field permissions of system roles")
            if payload.workflow_permissions is not None:
                raise ValidationError("Cannot change workflow permissions of system roles")
        if payload.permissions is not None:
            self._validate_permission_keys(db, [p.permission_key for p in payload.permissions])
        if payload.entity_permissions is not None:
            self._validate_entity_permissions(db, organization_id, payload.entity_permissions)
        if payload.field_permissions is not None:
            self._validate_field_permissions(db, organization_id, payload.field_permissions)
        effective_transitions = (
            payload.transition_permissions
            if payload.transition_permissions is not None
            else role.transition_permissions
        )
        if payload.workflow_permissions is not None:
            effective_transitions = self._prune_transitions_to_workflow_scope(
                payload.workflow_permissions, effective_transitions
            )
            if payload.transition_permissions is not None:
                payload = payload.model_copy(
                    update={"transition_permissions": effective_transitions}
                )
        if payload.transition_permissions is not None:
            self._validate_transition_permissions(db, organization_id, payload.transition_permissions)
        if payload.workflow_permissions is not None:
            self._validate_workflow_permissions(organization_id, payload.workflow_permissions)
        self._validate_transition_workflow_scope(
            payload.workflow_permissions if payload.workflow_permissions is not None else role.workflow_permissions,
            effective_transitions,
        )
        updated = self.db_model_service.update_role(db, role, payload)
        return self._to_role_read(db, updated)

    def get_workflow_access_scope(self, actor: dict[str, object]) -> set[str] | None:
        """Resolve the actor's workflow allow-list.

        None means unrestricted, empty set means denied outright, otherwise
        the specific set of allowed machine names. `roles/db_models.py`
        only supplies the raw role/permission rows (one batched read) —
        the RBAC decision (is_system bypass, workflow:read grant, scope
        accumulation) is made here."""
        if str(actor.get("actor_type") or "").lower() == "system":
            return None
        roles, permissions, workflow_permissions = self.db_model_service.get_workflow_access_rows(
            actor.get("user_id", ""), actor.get("organization_id", "")
        )
        if not roles:
            return set()
        granted_role_ids = {
            p.role_id
            for p in permissions
            if p.allowed and p.permission_key == WorkflowPermissionKey.READ
        }
        scoped_machines_by_role: dict[str, set[str]] = {}
        for wp in workflow_permissions:
            scoped_machines_by_role.setdefault(wp.role_id, set()).add(str(wp.machine_name))

        allowed: set[str] = set()
        has_workflow_reader = False
        for role in roles:
            if not (role.is_system or role.id in granted_role_ids):
                continue
            has_workflow_reader = True
            role_scope = scoped_machines_by_role.get(role.id)
            if role.is_system or not role_scope:
                return None
            allowed.update(role_scope)
        return allowed if has_workflow_reader else set()

    def check_permission_for_actor(
        self, actor: dict[str, object], permission_key: str
    ) -> PermissionCheckResult:
        """Whether the actor's role(s) grant `permission_key`, evaluated
        fresh every call against the real DB — no caching. `system`-typed
        actors bypass unconditionally, same convention as
        `get_workflow_access_scope`. Fails closed: any DB/session error
        propagates (`PersistenceError`) rather than being swallowed into
        an allow."""
        if str(actor.get("actor_type") or "").lower() == "system":
            return PermissionCheckResult.allow(permission_key)
        return self.db_model_service.check_permission_self_managed(
            actor.get("user_id", ""), actor.get("organization_id", ""), permission_key
        )

    def delete_role(self, db: Session, role_id: str, organization_id: str) -> None:
        """Description:
            Delete a custom role if allowed (not system, no assignments).

        Args:
            db: SQLAlchemy session.
            role_id: Role id.
            organization_id: Organization id.

        Returns:
            None

        Raises:
            NotFoundError: If the role does not exist.
            ValidationError: If the role is system or has user assignments.
            PersistenceError: If persistence operations fail.
        """
        role = self.db_model_service.get_role(db, role_id, organization_id)
        if not role:
            raise NotFoundError("Role not found")
        if role.is_system:
            raise ValidationError("Cannot delete system roles")
        user_count = self.db_model_service.count_role_assignments(db, role.id, organization_id)
        if user_count > 0:
            raise ValidationError(
                f"Cannot delete role '{role.display_name}' - {user_count} user(s) assigned. Reassign users first."
            )
        self.db_model_service.delete_role(db, role)

    def duplicate_role(self, db: Session, role_id: str, organization_id: str, payload: RoleDuplicateRequest) -> RoleRead:
        """Description:
            Duplicate an existing role under a new name.

        Args:
            db: SQLAlchemy session.
            role_id: Source role id.
            organization_id: Organization id.
            payload: Role duplication request.

        Returns:
            Newly duplicated role.

        Raises:
            NotFoundError: If the source role does not exist.
            ValidationError: If the target name already exists.
            PersistenceError: If persistence operations fail.
        """
        source = self.db_model_service.get_role(db, role_id, organization_id)
        if not source:
            raise NotFoundError("Source role not found")
        existing = self.db_model_service.get_role_by_name(db, organization_id, payload.name)
        if existing:
            raise ValidationError(f"Role with name '{payload.name}' already exists")
        duplicated = self.db_model_service.duplicate_role(db, source, organization_id, payload)
        return self._to_role_read(db, duplicated)

    # ── User role assignment ────────────────────────────────────────────────

    def get_user_roles(self, db: Session, user_id: str, organization_id: str) -> list[UserRoleRead]:
        """Description:
            List a user's role assignments (RBAC) within the organization.

        Args:
            db: SQLAlchemy session.
            user_id: User id.
            organization_id: Organization id.

        Returns:
            List of user role reads (assignment + role metadata).

        Raises:
            PersistenceError: If persistence operations fail.
        """
        assignments = self.db_model_service.get_user_roles(db, user_id, organization_id)
        result: list[UserRoleRead] = []
        for assignment in assignments:
            role = self.db_model_service.get_role(db, assignment.role_id, organization_id)
            if not role:
                continue
            result.append(
                UserRoleRead(
                    id=assignment.id,
                    user_id=assignment.user_id,
                    organization_id=assignment.organization_id,
                    role_id=assignment.role_id,
                    role_name=role.name,
                    role_display_name=role.display_name,
                    role_color=role.color,
                    role_is_system=role.is_system,
                    assigned_at=assignment.assigned_at,
                    assigned_by=assignment.assigned_by,
                )
            )
        return result

    def set_user_role(
        self,
        db: Session,
        user_id: str,
        organization_id: str,
        payload: UserRoleSetRequest,
        *,
        assigned_by: str,
    ) -> UserRoleRead:
        """Description:
            Replace the user's role assignments with a single role in the organization.

        Args:
            db: SQLAlchemy session.
            user_id: User id.
            organization_id: Organization id.
            payload: Role assignment request.
            assigned_by: Actor user id performing the assignment.

        Returns:
            The created role assignment read.

        Raises:
            NotFoundError: If the user or role does not exist.
            PersistenceError: If persistence operations fail.
        """
        role = self._require_user_and_role(db, user_id, organization_id, payload.role_id)

        assignment = self.db_model_service.set_user_role(
            db,
            user_id=user_id,
            organization_id=organization_id,
            payload=payload,
            assigned_by=assigned_by,
        )

        self.db_model_service.update_user_org_role(db, user_id, organization_id, role.name)

        return self._to_user_role_read(assignment, role)

    def add_user_role(
        self,
        db: Session,
        user_id: str,
        organization_id: str,
        payload: UserRoleSetRequest,
        *,
        assigned_by: str,
    ) -> UserRoleRead:
        """Grant one more role to the user, keeping every role they already hold (idempotent)."""
        role = self._require_user_and_role(db, user_id, organization_id, payload.role_id)

        assignment = self.db_model_service.assign_role_to_user(
            db, user_id, organization_id, role.id, assigned_by=assigned_by
        )

        # Mirror the highest-priority role, not the one just granted, so adding a
        # site role never demotes an admin's membership label (same rule as the
        # Microsoft role sync's `_mirror_primary_role_to_legacy`).
        held = self.db_model_service.get_user_roles_with_permissions(db, user_id, organization_id)
        primary = max(held, key=lambda r: ((r.priority or 0), r.name or ""))
        self.db_model_service.update_user_org_role(db, user_id, organization_id, primary.name)

        return self._to_user_role_read(assignment, role)

    def _require_user_and_role(self, db: Session, user_id: str, organization_id: str, role_id: str) -> Role:
        """Resolve the role to grant, raising NotFoundError if the user or role is missing."""
        if not self.db_model_service.get_user(db, user_id):
            raise NotFoundError("User not found")
        role = self.db_model_service.get_role(db, role_id, organization_id)
        if not role:
            raise NotFoundError("Role not found in this organization")
        return role

    @staticmethod
    def _to_user_role_read(assignment: UserRoleAssignment, role: Role) -> UserRoleRead:
        """Shape one role assignment plus its role into the API read model."""
        return UserRoleRead(
            id=assignment.id,
            user_id=assignment.user_id,
            organization_id=assignment.organization_id,
            role_id=assignment.role_id,
            role_name=role.name,
            role_display_name=role.display_name,
            role_color=role.color,
            role_is_system=role.is_system,
            assigned_at=assignment.assigned_at,
            assigned_by=assignment.assigned_by,
        )

    def make_actor_dependency(self, allowed_roles: list[str]):
        """Return a FastAPI dependency that validates the actor's roles.

        For READ-level gates (allowed_roles includes 'viewer'), custom roles that
        exist in the org's roles table are also accepted alongside the hardcoded
        DefaultRole values. ADMIN and SUPERADMIN gates are always strictly hardcoded.

        Args:
            allowed_roles: List of role name strings that are permitted.

        Returns:
            A FastAPI-compatible dependency callable.
        """
        required_roles = {str(r).strip().lower() for r in allowed_roles if str(r).strip()}
        check_custom = DefaultRole.VIEWER.value in required_roles
        db_service = self.db_model_service

        def dep(request: Request, db: Any = Depends(get_db)) -> dict:
            actor = build_actor_context(request)
            if not required_roles:
                return actor
            actor_roles = set(actor["roles"])
            if not actor_roles.isdisjoint(required_roles):
                return actor
            if check_custom:
                custom_roles = actor_roles - _DEFAULT_ROLE_VALUES
                org_id = str(actor.get("organization_id") or "").strip()
                if custom_roles and org_id:
                    try:
                        for role_name in custom_roles:
                            if db_service.get_role_by_name(db, org_id, role_name):
                                return actor
                    except PersistenceError as exc:
                        logger.warning(f"Custom role validation failed: {exc}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        return dep

    def assign_role_by_name(
        self, db: Session, user_id: str, organization_id: str, role_name: str
    ) -> None:
        """Assign a role to a user by role name within an organization.

        Silently skips if the role name does not exist in this org — covers
        legacy DefaultRole values that are not seeded into the roles table.

        Args:
            db: SQLAlchemy session.
            user_id: User id.
            organization_id: Organization id.
            role_name: Role name string (e.g. "ba", "admin").
        """
        role = self.db_model_service.get_role_by_name(db, organization_id, role_name)
        if not role:
            self.db_model_service.ensure_default_roles(db, organization_id)
            role = self.db_model_service.get_role_by_name(db, organization_id, role_name)
        if not role:
            logger.warning(
                f"assign_role_by_name: role '{role_name}' not found in org {organization_id} after seeding, skipping"
            )
            return
        self.db_model_service.assign_role_to_user(db, user_id, organization_id, role.id)

    def remove_user_role(self, db: Session, user_id: str, organization_id: str, role_id: str) -> None:
        """Description:
            Remove a specific role assignment from a user.

        Args:
            db: SQLAlchemy session.
            user_id: User id.
            organization_id: Organization id.
            role_id: Role id.

        Returns:
            None

        Raises:
            NotFoundError: If the user or role assignment is not found.
            ValidationError: If the user does not belong to the organization.
            PersistenceError: If persistence operations fail.
        """
        self._validate_org_membership(db, user_id, organization_id)
        self.db_model_service.remove_user_role(db, user_id, organization_id, role_id)

    # ── Permission evaluation ──────────────────────────────────────────────

    def check_permission(
        self, db: Session, user_id: str, organization_id: str, permission_key: str
    ) -> PermissionCheckResult:
        """Evaluate whether a user has a permission in an organization.

        Args:
            db: SQLAlchemy session.
            user_id: User id.
            organization_id: Organization id.
            permission_key: Permission key to check (e.g. 'role:read').

        Returns:
            PermissionCheckResult with allowed/denied and reason.

        Raises:
            PersistenceError: If the database query fails.
        """
        return self.db_model_service.check_permission(db, user_id, organization_id, permission_key)

    def get_visible_fields(
        self, db: Session, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        """None = system bypass; [] = deny all (no perms configured); list = explicit visible fields."""
        roles = self.db_model_service.get_user_roles_with_permissions(db, user_id, org_id)
        if not roles:
            return []
        for role in roles:
            if role.is_system:
                return None
        fps = self.db_model_service.get_field_permissions_for_roles(db, [r.id for r in roles], entity_type)
        if not fps:
            return []
        return [str(fp.field_name) for fp in fps if fp.can_view]

    def get_editable_fields(
        self, db: Session, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None:
        """None = system bypass; [] = deny all (no perms configured); list = explicitly editable fields."""
        roles = self.db_model_service.get_user_roles_with_permissions(db, user_id, org_id)
        if not roles:
            return []
        for role in roles:
            if role.is_system:
                return None
        fps = self.db_model_service.get_field_permissions_for_roles(db, [r.id for r in roles], entity_type)
        if not fps:
            return []
        return [str(fp.field_name) for fp in fps if fp.can_edit]

    def get_masked_fields(
        self, db: Session, user_id: str, org_id: str, entity_type: str
    ) -> list[str]:
        """Return list of field names that should be masked (shown as ***)."""
        roles = self.db_model_service.get_user_roles_with_permissions(db, user_id, org_id)
        if not roles:
            return []
        for role in roles:
            if role.is_system:
                return []
        fps = self.db_model_service.get_field_permissions_for_roles(db, [r.id for r in roles], entity_type)
        return [str(fp.field_name) for fp in fps if fp.can_view and fp.mask_value]

    def check_entity_permission(
        self, db: Session, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool:
        """Return True if user has permission to perform action on entity_type in org."""
        return self.db_model_service.check_entity_permission(db, user_id, org_id, entity_type, action)

    def evaluate_entity_access(
        self, db: Session, user_id: str, org_id: str, entity_type: str, action: str
    ) -> EntityAccessCheck:
        """Return allowed/denied plus any read-narrowing conditions (entity field
        permission filter) for the granting role(s). Used by `entities/manager.py`'s
        `guard_read` to filter individual records; `check_entity_permission` above stays
        the plain bool contract other callers (audit module, tests) already depend on."""
        return self.db_model_service.evaluate_entity_access(db, user_id, org_id, entity_type, action)

    def resolve_entity_read_policies(
        self,
        db: Session,
        user_id: str,
        org_id: str,
        entity_types: set[str],
    ) -> dict[str, EntityReadPolicy]:
        """Compile all list-page entity policies with two set-based lookups."""
        roles = self.db_model_service.get_user_roles_with_permissions(db, user_id, org_id)
        if not roles:
            return {}
        if any(role.is_system for role in roles):
            return {name: EntityReadPolicy() for name in entity_types}
        role_ids = [role.id for role in roles]
        field_permissions = self.db_model_service.get_field_permissions_for_roles_and_types(
            db, role_ids, entity_types
        )
        fields_by_type: dict[str, list[Any]] = {}
        for permission in field_permissions:
            fields_by_type.setdefault(permission.entity_type, []).append(permission)

        policies: dict[str, EntityReadPolicy] = {}
        for entity_type in entity_types:
            conditions: list[EntityConditionSpec] = []
            unconditional = False
            allowed = False
            for role in roles:
                for permission in role.permissions:
                    if (
                        permission.permission_key is None
                        and permission.entity_type == entity_type
                        and permission.action == "view"
                        and permission.allowed
                    ):
                        allowed = True
                        condition = EntityConditionSpec.from_permission(permission)
                        if condition is not None:
                            conditions.append(condition)
                        else:
                            unconditional = True
            if not allowed:
                continue
            field_rules = fields_by_type.get(entity_type, [])
            policies[entity_type] = EntityReadPolicy(
                conditions=[] if unconditional else conditions,
                visible_fields={rule.field_name for rule in field_rules if rule.can_view},
                masked_fields={
                    rule.field_name for rule in field_rules if rule.can_view and rule.mask_value
                },
            )
        return policies

    def cascade_workflow_publish(
        self,
        org_id: str,
        machine_name: str,
        old_definition: Any,
        new_definition: Any,
    ) -> None:
        """Cascade transition permission changes on workflow publish — detects renames and deletes."""
        old_list = old_definition.transitions
        new_list = new_definition.transitions
        old_transitions = {t.key: (t.from_state, t.to_state) for t in old_list}
        new_transitions = {t.key: (t.from_state, t.to_state) for t in new_list}
        removed_keys = set(old_transitions.keys()) - set(new_transitions.keys())
        added_keys = set(new_transitions.keys()) - set(old_transitions.keys())
        new_by_route = {v: k for k, v in new_transitions.items() if k in added_keys}

        renames: list[tuple[str, str]] = []
        unmatched_old: list[tuple[int, str]] = []
        for old_key in removed_keys:
            route = old_transitions[old_key]
            if route in new_by_route:
                renames.append((old_key, new_by_route[route]))
            else:
                old_idx = next(i for i, t in enumerate(old_list) if t.key == old_key)
                unmatched_old.append((old_idx, old_key))

        true_deletes: list[str] = []
        if len(old_list) == len(new_list) and unmatched_old:
            unmatched_new_by_idx = {i: t.key for i, t in enumerate(new_list)
                                     if t.key in added_keys and t.key not in {k for _, k in renames}}
            for old_idx, old_key in unmatched_old:
                if old_idx in unmatched_new_by_idx:
                    renames.append((old_key, unmatched_new_by_idx[old_idx]))
                else:
                    true_deletes.append(old_key)
        else:
            true_deletes.extend(old_key for _, old_key in unmatched_old)

        if not renames and not true_deletes:
            return
        valid_keys = list(set(new_transitions.keys()) | {new_key for _, new_key in renames})
        self.db_model_service.sync_transition_permissions_on_publish(
            org_id=org_id, machine_name=machine_name, renames=renames, valid_keys=valid_keys
        )

    # ── Effective permissions ──────────────────────────────────────────────

    def _guard_permissions_access(
        self,
        db: Session,
        user_id: str,
        organization_id: str,
        actor_user_id: str,
        actor_org_id: str,
        actor_roles: list[str] | None,
    ) -> None:
        """Raise if the actor is not allowed to inspect the target user's permissions."""
        if actor_user_id == user_id:
            return
        if actor_org_id != organization_id:
            raise ValidationError("Cannot inspect permissions across organizations")
        actor_role_set = {r.lower() for r in (actor_roles or [])}
        if not actor_role_set.intersection({DefaultRole.ADMIN.value, DefaultRole.SUPERADMIN.value, DefaultRole.OWNER.value}):
            raise ValidationError("Only admins can inspect other users' permissions")
        self._validate_org_membership(db, user_id, organization_id)

    def _aggregate_permission_keys(self, db: Session, roles: list) -> set[str]:
        """Return merged catalog permission keys across all assigned roles."""
        permission_keys: set[str] = set()
        for role in roles:
            if role.is_system:
                if self.db_model_service._permissions_svc is not None:
                    catalog = self.db_model_service._permissions_svc.list_permissions(db)
                    permission_keys.update(p.key for p in catalog)
            else:
                for perm in role.permissions:
                    if perm.allowed and perm.permission_key:
                        permission_keys.add(perm.permission_key)
        return permission_keys

    def _aggregate_entity_permissions(
        self, db: Session, roles: list
    ) -> list[EntityPermissionRead]:
        """Return merged entity-level permissions as a flat list across all assigned roles.

        System roles get all actions on all entity types.
        For custom roles, union logic applies — allowed if any role grants it.
        """
        all_actions = {"view", "create", "edit", "delete"}
        merged: dict[tuple[str, str], bool] = {}

        for role in roles:
            if role.is_system:
                try:
                    entity_types = self.db_model_service.list_all_entity_types(db)
                    for et in entity_types:
                        for action in all_actions:
                            merged[(et, action)] = True
                except Exception:
                    pass
                continue

            for perm in role.permissions:
                if perm.entity_type is None or perm.permission_key is not None:
                    continue
                key = (perm.entity_type, perm.action)
                if perm.allowed:
                    merged[key] = True
                elif key not in merged:
                    merged[key] = False

        return [
            EntityPermissionRead(id="", entity_type=et, action=action, allowed=allowed)
            for (et, action), allowed in merged.items()
        ]

    def _aggregate_field_permissions(self, db: Session, roles: list) -> list[FieldPermissionRead]:
        """Return merged field permissions as a flat list across all assigned roles."""
        field_perms_db = self.db_model_service.get_all_field_permissions_for_roles(db, [r.id for r in roles])
        merged: dict[tuple[str, str], FieldPermissionRead] = {}
        for fp in field_perms_db:
            key = (fp.entity_type, fp.field_name)
            existing = merged.get(key)
            if existing is None:
                merged[key] = FieldPermissionRead(
                    id=fp.id,
                    entity_type=fp.entity_type,
                    field_name=fp.field_name,
                    can_view=bool(fp.can_view),
                    can_edit=bool(fp.can_edit),
                    mask_value=bool(fp.mask_value),
                )
            else:
                existing.can_view = existing.can_view or bool(fp.can_view)
                existing.can_edit = existing.can_edit or bool(fp.can_edit)
                existing.mask_value = existing.mask_value and bool(fp.mask_value)
        return list(merged.values())

    def _aggregate_transition_permissions(
        self, roles: list
    ) -> list[TransitionPermissionRead]:
        """Merge transition permissions across roles. Returns [] for system roles (frontend derives from is_system)."""
        seen: set[tuple[str, str]] = set()
        result: list[TransitionPermissionRead] = []
        for role in roles:
            if role.is_system:
                return []
            for tp in role.transition_permissions:
                key = (str(tp.machine_name), str(tp.transition_key))
                if key not in seen:
                    seen.add(key)
                    result.append(TransitionPermissionRead(
                        id=str(tp.id),
                        machine_name=str(tp.machine_name),
                        transition_key=str(tp.transition_key),
                    ))
        return result

    def get_effective_permissions(
        self,
        db: Session,
        user_id: str,
        organization_id: str,
        actor_user_id: str,
        actor_org_id: str,
        actor_roles: list[str] | None = None,
    ) -> PermissionsSummary:
        """Return effective permission catalog keys for a user in an org."""
        self._guard_permissions_access(db, user_id, organization_id, actor_user_id, actor_org_id, actor_roles)
        roles = self.db_model_service.get_user_roles_with_permissions(db, user_id, organization_id)
        transition_perms = self._aggregate_transition_permissions(roles)
        return PermissionsSummary(
            user_id=user_id,
            organization_id=organization_id,
            roles=[
                RoleSummary(
                    id=r.id,
                    name=r.name,
                    display_name=r.display_name,
                    priority=int(r.priority),
                    color=r.color,
                    is_system=r.is_system,
                )
                for r in roles
            ],
            permissions=sorted(self._aggregate_permission_keys(db, roles)),
            entity_permissions=self._aggregate_entity_permissions(db, roles),
            field_permissions=self._aggregate_field_permissions(db, roles),
            transition_permissions=transition_perms,
        )

    # ── Permissions summary ────────────────────────────────────────────────

    def get_permissions_summary(self, db: Session, user_id: str, organization_id: str) -> PermissionsSummary:
        """Description:
            Return merged entity + field permissions for the user in the organization.

        Args:
            db: SQLAlchemy session.
            user_id: User id.
            organization_id: Organization id.

        Returns:
            PermissionsSummary for the user.

        Raises:
            PersistenceError: If persistence operations fail.
        """
        roles = self.db_model_service.get_user_roles_with_permissions(db, user_id, organization_id)
        if not roles:
            return PermissionsSummary(roles=[], entity_permissions=[], field_permissions=[])

        transition_perms = self._aggregate_transition_permissions(roles)
        return PermissionsSummary(
            user_id=None,
            organization_id=None,
            roles=[
                RoleSummary(
                    id=r.id,
                    name=r.name,
                    display_name=r.display_name,
                    priority=int(r.priority),
                    color=r.color,
                    is_system=r.is_system,
                )
                for r in roles
            ],
            permissions=sorted(self._aggregate_permission_keys(db, roles)),
            entity_permissions=self._aggregate_entity_permissions(db, roles),
            field_permissions=self._aggregate_field_permissions(db, roles),
            transition_permissions=transition_perms,
        )

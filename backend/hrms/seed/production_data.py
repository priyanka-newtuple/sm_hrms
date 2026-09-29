"""Idempotently install production reference data and the first administrator."""

from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import delete, select

from hrms.authz.enums import RoleName
from hrms.config import get_settings
from hrms.database import AsyncSessionLocal
from hrms.models.employee import Employee
from hrms.models.enums import EmploymentType
from hrms.models.role import Role, RoleFeaturePermission, RolePermissionKey
from hrms.models.user import User
from hrms.seed.permission_matrix import FEATURE_PERMISSIONS, ROLE_DESCRIPTIONS, ROLE_PERMISSION_KEYS
from hrms.services.reference_data_service import ensure_reference_data


async def sync_roles_and_permissions(db) -> dict[RoleName, Role]:
    """Make database authorization data match the version shipped with the app."""
    roles: dict[RoleName, Role] = {}
    for role_name in RoleName:
        role = (await db.execute(select(Role).where(Role.name == role_name.value))).scalar_one_or_none()
        if role is None:
            role = Role(name=role_name.value, description=ROLE_DESCRIPTIONS[role_name])
            db.add(role)
            await db.flush()
        else:
            role.description = ROLE_DESCRIPTIONS[role_name]
        roles[role_name] = role

        expected_features = FEATURE_PERMISSIONS[role_name]
        existing_permissions = {
            item.feature_key: item
            for item in (
                await db.execute(select(RoleFeaturePermission).where(RoleFeaturePermission.role_id == role.id))
            ).scalars()
        }
        for feature_key, (actions, scope, profile) in expected_features.items():
            permission = existing_permissions.get(feature_key)
            if permission is None:
                db.add(
                    RoleFeaturePermission(
                        role_id=role.id,
                        feature_key=feature_key,
                        actions=actions,
                        record_scope=scope,
                        data_profile=profile,
                    )
                )
            else:
                permission.actions = actions
                permission.record_scope = scope
                permission.data_profile = profile

        await db.execute(delete(RolePermissionKey).where(RolePermissionKey.role_id == role.id))
        db.add_all(
            RolePermissionKey(role_id=role.id, permission_key=permission_key)
            for permission_key in ROLE_PERMISSION_KEYS[role_name]
        )

    await db.flush()
    return roles


async def ensure_bootstrap_superadmin(db, super_admin_role: Role) -> None:
    settings = get_settings()
    email = settings.BOOTSTRAP_SUPERADMIN_EMAIL.strip().lower()
    if not email:
        raise RuntimeError("BOOTSTRAP_SUPERADMIN_EMAIL must be set for a production deployment")
    if not email.endswith(f"@{settings.ALLOWED_EMAIL_DOMAIN.lower()}"):
        raise RuntimeError("BOOTSTRAP_SUPERADMIN_EMAIL must belong to ALLOWED_EMAIL_DOMAIN")

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None:
        employee = (await db.execute(select(Employee).where(Employee.user_id == user.id))).scalar_one_or_none()
        if employee is None:
            raise RuntimeError(f"Bootstrap user {email} exists without an employee record")
        return

    first_name = settings.BOOTSTRAP_SUPERADMIN_FIRST_NAME.strip()
    last_name = settings.BOOTSTRAP_SUPERADMIN_LAST_NAME.strip()
    if not first_name or not last_name:
        raise RuntimeError("BOOTSTRAP_SUPERADMIN_FIRST_NAME and BOOTSTRAP_SUPERADMIN_LAST_NAME must be set")

    user = User(email=email)
    db.add(user)
    await db.flush()
    db.add(
        Employee(
            user_id=user.id,
            role_id=super_admin_role.id,
            employee_code=settings.BOOTSTRAP_SUPERADMIN_EMPLOYEE_CODE,
            first_name=first_name,
            last_name=last_name,
            work_email=email,
            department="Leadership",
            designation="Chief Executive Officer",
            date_joined=date.today(),
            employment_type=EmploymentType.FULL_TIME,
        )
    )


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_reference_data(db)
        roles = await sync_roles_and_permissions(db)
        await ensure_bootstrap_superadmin(db, roles[RoleName.SUPER_ADMIN])
        await db.commit()
    print("Production roles, permissions, reference data, and bootstrap administrator are ready.")


if __name__ == "__main__":
    asyncio.run(main())

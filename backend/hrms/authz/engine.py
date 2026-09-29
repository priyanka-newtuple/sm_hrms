from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.enums import (
    Action,
    DataProfile,
    FeatureKey,
    PermissionKey,
    RecordScope,
    expand_actions,
)
from hrms.models.employee import Employee
from hrms.models.role import RoleFeaturePermission, RolePermissionKey


class AuthzEngine:
    """
    Reads permission grants from the database (seeded verbatim from the
    permissions spreadsheet) rather than hardcoding role checks. One instance
    is created per request via the `get_authz_engine` dependency.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_grant(self, role_id: uuid.UUID, feature: FeatureKey) -> RoleFeaturePermission | None:
        result = await self.db.execute(
            select(RoleFeaturePermission).where(
                RoleFeaturePermission.role_id == role_id,
                RoleFeaturePermission.feature_key == feature,
            )
        )
        return result.scalar_one_or_none()

    async def has_permission(self, employee: Employee, feature: FeatureKey, action: Action) -> bool:
        grant = await self._get_grant(employee.role_id, feature)
        if grant is None:
            return False
        return action in expand_actions(grant.actions)

    async def get_scope(self, employee: Employee, feature: FeatureKey) -> RecordScope:
        grant = await self._get_grant(employee.role_id, feature)
        return grant.record_scope if grant else RecordScope.NONE

    async def get_data_profile(self, employee: Employee, feature: FeatureKey) -> DataProfile:
        grant = await self._get_grant(employee.role_id, feature)
        return grant.data_profile if grant else DataProfile.NONE

    async def has_permission_key(self, employee: Employee, key: PermissionKey) -> bool:
        result = await self.db.execute(
            select(RolePermissionKey).where(
                RolePermissionKey.role_id == employee.role_id,
                RolePermissionKey.permission_key == key,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_all_feature_grants(self, employee: Employee) -> dict[FeatureKey, RoleFeaturePermission]:
        """Used by /auth/me to hand the frontend a precomputed permission set for UI gating."""
        result = await self.db.execute(select(RoleFeaturePermission).where(RoleFeaturePermission.role_id == employee.role_id))
        return {row.feature_key: row for row in result.scalars().all()}

    async def get_all_permission_keys(self, employee: Employee) -> set[PermissionKey]:
        result = await self.db.execute(select(RolePermissionKey).where(RolePermissionKey.role_id == employee.role_id))
        return {row.permission_key for row in result.scalars().all()}

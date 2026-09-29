from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_current_employee
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.models.role import Role
from hrms.schemas.employee import RoleOut

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _employee: Employee = Depends(get_current_employee),
):
    """Any authenticated user can see the list of role names (needed for assignment UI)."""
    result = await db.execute(select(Role).order_by(Role.name))
    return result.scalars().all()

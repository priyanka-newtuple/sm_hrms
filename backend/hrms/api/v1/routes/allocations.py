from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_authz_engine, require_permission
from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey
from hrms.core.pagination import Page
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.schemas.allocation import (
    AllocationCreate,
    AllocationPreview,
    AllocationUpdate,
    AllocationWriteResult,
)
from hrms.services import allocation_service

router = APIRouter(prefix="/allocations", tags=["allocations"])
FEATURE = FeatureKey.ALLOCATIONS


@router.get("", response_model=Page)
async def list_allocations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    employee_id: uuid.UUID | None = Query(None),
    project_id: uuid.UUID | None = Query(None),
    active_on: date | None = Query(None),
    include_cancelled: bool = Query(False),
    overallocated_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    items, total = await allocation_service.list_allocations(
        db,
        engine,
        current_employee,
        offset=(page - 1) * page_size,
        limit=page_size,
        employee_id=employee_id,
        project_id=project_id,
        active_on=active_on,
        include_cancelled=include_cancelled,
        overallocated_only=overallocated_only,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/options")
async def allocation_options(
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(require_permission(FEATURE, Action.CREATE)),
):
    from sqlalchemy import select

    from hrms.authz.enums import RecordScope
    from hrms.authz.scope_filters import managed_project_ids_subquery
    from hrms.models.enums import ALLOCATABLE_PROJECT_STATUSES, EmploymentStatus
    from hrms.models.project import Project

    people = (
        await db.execute(
            select(Employee).where(Employee.employment_status == EmploymentStatus.ACTIVE).order_by(Employee.first_name)
        )
    ).scalars()
    query = select(Project).where(Project.approval_status == "approved", Project.status.in_(ALLOCATABLE_PROJECT_STATUSES))
    if await engine.get_scope(actor, FEATURE) != RecordScope.ALL:
        query = query.where(Project.id.in_(managed_project_ids_subquery(actor.id)))
    projects = (await db.execute(query.order_by(Project.name))).scalars()
    from hrms.services.reference_data_service import project_role_options

    return {
        "employees": [{"id": e.id, "label": e.full_name} for e in people],
        "projects": [{"id": p.id, "label": p.name} for p in projects],
        "project_roles": await project_role_options(db),
    }


@router.post("/preview")
async def preview_allocation(
    payload: AllocationPreview,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(require_permission(FEATURE, Action.CREATE)),
):
    return await allocation_service.preview_allocation(db, engine, actor, payload)


@router.get("/{allocation_id}")
async def get_allocation(
    allocation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    return await allocation_service.get_allocation(db, engine, current_employee, allocation_id)


@router.post("", response_model=AllocationWriteResult, status_code=201)
async def create_allocation(
    payload: AllocationCreate,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.CREATE)),
):
    """
    Returns the saved allocation plus a capacity verdict. Exceeding 100% is a
    warning (`over_allocated: true`), not a rejection — see AllocationWriteResult.
    """
    return await allocation_service.create_allocation(db, engine, current_employee, payload)


@router.patch("/{allocation_id}", response_model=AllocationWriteResult)
async def update_allocation(
    allocation_id: uuid.UUID,
    payload: AllocationUpdate,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.EDIT)),
):
    return await allocation_service.update_allocation(db, engine, current_employee, allocation_id, payload)


@router.post("/{allocation_id}/cancel")
async def cancel_allocation(
    allocation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.EDIT)),
):
    """
    Allocations are cancelled, never deleted, so the record of who was booked on
    what survives. Replaces the previous `DELETE /allocations/{id}`.
    """
    return await allocation_service.cancel_allocation(db, engine, current_employee, allocation_id)

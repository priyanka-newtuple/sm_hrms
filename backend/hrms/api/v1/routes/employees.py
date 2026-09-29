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
from hrms.schemas.allocation import CapacityOut
from hrms.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    OffboardingReadiness,
    OffboardRequest,
)
from hrms.services import allocation_service, employee_service

router = APIRouter(prefix="/employees", tags=["employees"])

FEATURE = FeatureKey.EMPLOYEE_DIRECTORY
OFFBOARDING = FeatureKey.EMPLOYEE_OFFBOARDING


@router.get("/form-options")
async def employee_form_options(
    db: AsyncSession = Depends(get_db),
    _employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    from hrms.services.reference_data_service import workforce_options

    return await workforce_options(db)


@router.get("", response_model=Page)
async def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: str | None = Query(None),
    department: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    items, total = await employee_service.list_employees(
        db,
        engine,
        current_employee,
        offset=(page - 1) * page_size,
        limit=page_size,
        search=search,
        department=department,
        status=status,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{employee_id}")
async def get_employee(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    return await employee_service.get_employee(db, engine, current_employee, employee_id)


@router.post("", status_code=201)
async def create_employee(
    payload: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.CREATE)),
):
    return await employee_service.create_employee(db, engine, current_employee, payload)


@router.patch("/{employee_id}")
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.EDIT)),
):
    return await employee_service.update_employee(db, engine, current_employee, employee_id, payload)


@router.get("/{employee_id}/allocations", response_model=Page)
async def employee_allocations(
    employee_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    include_cancelled: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FeatureKey.ALLOCATIONS, Action.VIEW)),
):
    items, total = await allocation_service.list_allocations(
        db,
        engine,
        current_employee,
        offset=(page - 1) * page_size,
        limit=page_size,
        employee_id=employee_id,
        include_cancelled=include_cancelled,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{employee_id}/capacity", response_model=CapacityOut)
async def employee_capacity(
    employee_id: uuid.UUID,
    on: date | None = Query(None, description="Defaults to today"),
    db: AsyncSession = Depends(get_db),
    _employee: Employee = Depends(require_permission(FeatureKey.ALLOCATIONS, Action.VIEW)),
):
    return await allocation_service.employee_capacity(db, employee_id, on or date.today())


@router.get("/{employee_id}/offboarding-readiness", response_model=OffboardingReadiness)
async def offboarding_readiness(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _employee: Employee = Depends(require_permission(OFFBOARDING, Action.VIEW)),
):
    return await employee_service.offboarding_readiness(db, employee_id)


@router.post("/{employee_id}/offboard")
async def offboard_employee(
    employee_id: uuid.UUID,
    payload: OffboardRequest,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(OFFBOARDING, Action.EDIT)),
):
    return await employee_service.offboard_employee(db, engine, current_employee, employee_id, payload)


@router.post("/{employee_id}/reactivate")
async def reactivate_employee(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.EDIT)),
):
    return await employee_service.reactivate_employee(db, engine, current_employee, employee_id)

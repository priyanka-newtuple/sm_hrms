from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_authz_engine, require_permission
from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey
from hrms.core.pagination import Page
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.models.enums import ProjectStatus
from hrms.schemas.project import (
    CustomerCreate,
    CustomerUpdate,
    ProjectCreate,
    ProjectUpdate,
)
from hrms.services import allocation_service, project_service

router = APIRouter(tags=["projects"])

CUSTOMERS = FeatureKey.CUSTOMERS
PROJECTS = FeatureKey.PROJECTS
ALLOCATIONS = FeatureKey.ALLOCATIONS


# --------------------------------------------------------------------------- customers


@router.get("/customers", response_model=Page)
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: str | None = Query(None),
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(CUSTOMERS, Action.VIEW)),
):
    items, total = await project_service.list_customers(
        db,
        engine,
        current_employee,
        offset=(page - 1) * page_size,
        limit=page_size,
        search=search,
        include_archived=include_archived,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(CUSTOMERS, Action.VIEW)),
):
    return await project_service.get_customer(db, engine, current_employee, customer_id)


@router.post("/customers", status_code=201)
async def create_customer(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(CUSTOMERS, Action.CREATE)),
):
    return await project_service.create_customer(db, engine, current_employee, payload)


@router.patch("/customers/{customer_id}")
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(CUSTOMERS, Action.EDIT)),
):
    return await project_service.update_customer(db, engine, current_employee, customer_id, payload)


@router.post("/customers/{customer_id}/archive")
async def archive_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(CUSTOMERS, Action.EDIT)),
):
    return await project_service.archive_customer(db, engine, current_employee, customer_id)


@router.get("/customers/{customer_id}/projects", response_model=Page)
async def customer_projects(
    customer_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(PROJECTS, Action.VIEW)),
):
    items, total = await project_service.list_projects(
        db,
        engine,
        current_employee,
        offset=(page - 1) * page_size,
        limit=page_size,
        customer_id=customer_id,
        include_archived=include_archived,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


# --------------------------------------------------------------------------- projects


@router.get("/projects", response_model=Page)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: str | None = Query(None),
    status: ProjectStatus | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(PROJECTS, Action.VIEW)),
):
    items, total = await project_service.list_projects(
        db,
        engine,
        current_employee,
        offset=(page - 1) * page_size,
        limit=page_size,
        search=search,
        status=status,
        customer_id=customer_id,
        include_archived=include_archived,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(PROJECTS, Action.VIEW)),
):
    return await project_service.get_project(db, engine, current_employee, project_id)


@router.post("/projects", status_code=201)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(PROJECTS, Action.CREATE)),
):
    return await project_service.create_project(db, engine, current_employee, payload)


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(PROJECTS, Action.EDIT)),
):
    return await project_service.update_project(db, engine, current_employee, project_id, payload)


@router.post("/projects/{project_id}/archive")
async def archive_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(PROJECTS, Action.EDIT)),
):
    return await project_service.archive_project(db, engine, current_employee, project_id)


@router.get("/projects/{project_id}/allocations", response_model=Page)
async def project_allocations(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    include_cancelled: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(ALLOCATIONS, Action.VIEW)),
):
    items, total = await allocation_service.list_allocations(
        db,
        engine,
        current_employee,
        offset=(page - 1) * page_size,
        limit=page_size,
        project_id=project_id,
        include_cancelled=include_cancelled,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)

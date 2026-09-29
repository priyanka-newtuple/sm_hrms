from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_authz_engine, get_current_employee
from hrms.authz.engine import AuthzEngine
from hrms.core.pagination import Page
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.schemas.onboarding import TaskCompleteIn
from hrms.schemas.work import ReassignIn, WorkAllocationIn, WorkAssetIn, WorkItem
from hrms.services import onboarding_service, work_service

router = APIRouter(prefix="/work", tags=["my-work"])


@router.get("", response_model=Page)
async def inbox(
    view: Literal["todo", "waiting", "completed"] = "todo",
    kind: Literal["action", "approval"] | None = None,
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.inbox(db, engine, actor, view, page, page_size, kind)


@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.summary(db, engine, actor)


@router.get("/tasks/{task_id}", response_model=WorkItem)
async def detail(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.detail(db, engine, actor, task_id)


@router.get("/documents/{document_id}", response_model=WorkItem)
async def document_detail(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.document_detail(db, engine, actor, document_id)


@router.post("/tasks/{task_id}/complete", response_model=WorkItem)
async def complete(
    task_id: UUID,
    payload: TaskCompleteIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    task, _ = await work_service.load_task(db, engine, actor, task_id, write=True)
    await onboarding_service.complete_task(db, engine, actor, task.onboarding_record_id, task_id, payload)
    return await work_service.detail(db, engine, actor, task_id)


@router.get("/tasks/{task_id}/assets")
async def assets(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.asset_options(db, engine, actor, task_id)


@router.post("/tasks/{task_id}/assets", response_model=WorkItem)
async def assign_asset(
    task_id: UUID,
    payload: WorkAssetIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.assign_asset(db, engine, actor, task_id, payload)


@router.get("/tasks/{task_id}/projects")
async def projects(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.project_options(db, engine, actor, task_id)


@router.get("/tasks/{task_id}/project-roles")
async def project_roles(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.project_role_options(db, engine, actor, task_id)


@router.post("/tasks/{task_id}/allocation")
async def allocate(
    task_id: UUID,
    payload: WorkAllocationIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.allocate(db, engine, actor, task_id, payload)


@router.get("/tasks/{task_id}/assignees")
async def assignees(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.assignee_options(db, engine, actor, task_id)


@router.post("/tasks/{task_id}/reassign", response_model=WorkItem)
async def reassign(
    task_id: UUID,
    payload: ReassignIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.reassign(db, engine, actor, task_id, payload)


@router.post("/tasks/{task_id}/allocation-preview")
async def allocation_preview(
    task_id: UUID,
    payload: WorkAllocationIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await work_service.allocation_preview(db, engine, actor, task_id, payload)

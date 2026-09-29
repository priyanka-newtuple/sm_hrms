from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_authz_engine, get_current_employee, require_permission
from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.models.enums import CustomerStatus, EmploymentStatus
from hrms.models.project import Customer
from hrms.schemas.project_approval import ProjectDecisionIn, ProjectVersionIn
from hrms.services import project_approval_service as service

router = APIRouter(tags=["project-approvals"])


@router.get("/project-creation-options")
async def creation_options(
    db: AsyncSession = Depends(get_db), actor: Employee = Depends(require_permission(FeatureKey.PROJECTS, Action.CREATE))
):
    # Deliberately minimal pickers: creating a project does not grant customer
    # account data or organization-wide employee profile access.
    customers = (
        await db.execute(
            select(Customer.id, Customer.code, Customer.name)
            .where(Customer.status != CustomerStatus.ARCHIVED)
            .order_by(Customer.name)
        )
    ).all()
    people = (
        await db.execute(
            select(Employee.id, Employee.first_name, Employee.last_name)
            .where(Employee.employment_status == EmploymentStatus.ACTIVE)
            .order_by(Employee.first_name)
        )
    ).all()
    return {
        "customers": [{"id": c.id, "label": f"{c.code} — {c.name}"} for c in customers],
        "employees": [{"id": p.id, "label": f"{p.first_name} {p.last_name}"} for p in people],
    }


@router.get("/project-approvals/{request_id}")
async def detail(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await service.detail(db, engine, actor, request_id)


@router.post("/project-approvals/{request_id}/submit")
async def submit(
    request_id: UUID,
    payload: ProjectVersionIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await service.submit(db, engine, actor, request_id, payload.version)


@router.post("/project-approvals/{request_id}/withdraw")
async def withdraw(
    request_id: UUID,
    payload: ProjectVersionIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await service.withdraw(db, engine, actor, request_id, payload.version)


@router.post("/project-approvals/{request_id}/decision")
async def decide(
    request_id: UUID,
    payload: ProjectDecisionIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    actor: Employee = Depends(get_current_employee),
):
    return await service.decide(db, engine, actor, request_id, payload)

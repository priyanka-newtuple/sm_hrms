from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_current_employee, require_permission
from hrms.authz.enums import Action, FeatureKey
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.schemas.hr_content import HolidayContentIn, JobDescriptionIn, JobOpeningIn, LearningEventIn, PolicyIn
from hrms.services import hr_cockpit_service as service

router = APIRouter(prefix="/hr-cockpit", tags=["hr-cockpit"])


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db), actor: Employee = Depends(require_permission(FeatureKey.HR_COCKPIT, Action.VIEW))):
    return await service.dashboard(db, actor)


@router.post("/policies", status_code=201)
async def create_policy(payload: PolicyIn, db: AsyncSession = Depends(get_db), actor: Employee = Depends(get_current_employee)):
    return await service.create_policy(db, actor, payload)


@router.post("/learning-events", status_code=201)
async def create_event(payload: LearningEventIn, db: AsyncSession = Depends(get_db), actor: Employee = Depends(get_current_employee)):
    return await service.create_event(db, actor, payload)


@router.post("/job-descriptions", status_code=201)
async def create_jd(payload: JobDescriptionIn, db: AsyncSession = Depends(get_db), actor: Employee = Depends(get_current_employee)):
    return await service.create_jd(db, actor, payload)


@router.post("/openings", status_code=201)
async def create_opening(payload: JobOpeningIn, db: AsyncSession = Depends(get_db), actor: Employee = Depends(get_current_employee)):
    return await service.create_opening(db, actor, payload)


@router.post("/holidays", status_code=201)
async def create_holiday(payload: HolidayContentIn, db: AsyncSession = Depends(get_db), actor: Employee = Depends(get_current_employee)):
    return await service.create_holiday(db, actor, payload)


@router.post("/{kind}/{item_id}/submit")
async def submit(kind: str, item_id: UUID, db: AsyncSession = Depends(get_db), actor: Employee = Depends(get_current_employee)):
    return await service.submit_content(db, actor, kind, item_id)


@router.post("/{kind}/{item_id}/{decision}")
async def decide(kind: str, item_id: UUID, decision: str, db: AsyncSession = Depends(get_db), actor: Employee = Depends(get_current_employee)):
    return await service.approve_or_publish(db, actor, kind, item_id, decision)

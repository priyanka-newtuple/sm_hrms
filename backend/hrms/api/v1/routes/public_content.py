from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_current_employee
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.schemas.hr_content import ReferralIn
from hrms.services import hr_cockpit_service as service

router = APIRouter(prefix="/public/content", tags=["public-content"])

@router.get("/policies")
async def policies(db: AsyncSession = Depends(get_db)): return await service.public_policies(db)

@router.get("/learning-events")
async def events(db: AsyncSession = Depends(get_db)): return await service.public_events(db)

@router.get("/openings")
async def openings(db: AsyncSession = Depends(get_db)): return await service.public_openings(db)

@router.get("/holidays")
async def holidays(db: AsyncSession = Depends(get_db)): return await service.public_holidays(db)

@router.post("/openings/{opening_id}/referrals", status_code=201)
async def refer(opening_id: UUID, payload: ReferralIn, db: AsyncSession = Depends(get_db), actor: Employee = Depends(get_current_employee)):
    return await service.refer(db, actor, opening_id, payload)

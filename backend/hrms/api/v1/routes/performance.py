from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_current_employee, require_permission
from hrms.authz.enums import Action, FeatureKey
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.schemas.performance import (
    AcknowledgeIn,
    CalibrationIn,
    CycleIn,
    DecisionIn,
    FeedbackIn,
    GoalIn,
    ManagerReviewIn,
    SelfReviewIn,
)
from hrms.services import performance_service

router = APIRouter(prefix="/performance", tags=["performance"])
FEATURE = FeatureKey.PERFORMANCE_MANAGEMENT


@router.get("/dashboard")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    return await performance_service.dashboard(db, actor)


@router.get("/cycles")
async def cycles(
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    return await performance_service.cycles(db, actor)


@router.post("/cycles", status_code=201)
async def create_cycle(
    payload: CycleIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.create_cycle(db, actor, payload)


@router.put("/cycles/{cycle_id}")
async def update_cycle(
    cycle_id: UUID,
    payload: CycleIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.update_cycle(db, actor, cycle_id, payload)


@router.post("/cycles/{cycle_id}/submit")
async def submit_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.submit_cycle(db, actor, cycle_id)


@router.post("/cycles/{cycle_id}/decision")
async def decide_cycle(
    cycle_id: UUID,
    payload: DecisionIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.approve_cycle(db, actor, cycle_id, payload)


@router.get("/reviews/{review_id}")
async def review_detail(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.review_detail(db, actor, review_id)


@router.post("/reviews/{review_id}/goals", status_code=201)
async def create_goal(
    review_id: UUID,
    payload: GoalIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.create_goal(db, actor, review_id, payload)


@router.put("/goals/{goal_id}")
async def update_goal(
    goal_id: UUID,
    payload: GoalIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.update_goal(db, actor, goal_id, payload)


@router.post("/reviews/{review_id}/goals/submit")
async def submit_goals(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.submit_goals(db, actor, review_id)


@router.post("/reviews/{review_id}/goals/decision")
async def decide_goals(
    review_id: UUID,
    payload: DecisionIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.decide_goals(db, actor, review_id, payload)


@router.post("/reviews/{review_id}/self-review")
async def self_review(
    review_id: UUID,
    payload: SelfReviewIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.submit_self_review(db, actor, review_id, payload)


@router.post("/reviews/{review_id}/manager-review")
async def manager_review(
    review_id: UUID,
    payload: ManagerReviewIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.submit_manager_review(db, actor, review_id, payload)


@router.post("/feedback/{feedback_id}")
async def project_feedback(
    feedback_id: UUID,
    payload: FeedbackIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.submit_feedback(db, actor, feedback_id, payload)


@router.post("/reviews/{review_id}/calibrate")
async def calibrate(
    review_id: UUID,
    payload: CalibrationIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.calibrate(db, actor, review_id, payload)


@router.post("/reviews/{review_id}/publish")
async def publish(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.publish(db, actor, review_id)


@router.post("/reviews/{review_id}/acknowledge")
async def acknowledge(
    review_id: UUID,
    payload: AcknowledgeIn,
    db: AsyncSession = Depends(get_db),
    actor: Employee = Depends(get_current_employee),
):
    return await performance_service.acknowledge(db, actor, review_id, payload)

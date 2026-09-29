from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from hrms.authz.enums import RoleName
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from hrms.models.allocation import Allocation
from hrms.models.employee import Employee
from hrms.models.enums import COMMITTED_ALLOCATION_STATUSES, EmploymentStatus
from hrms.models.performance import PerformanceCycle, PerformanceGoal, PerformanceReview, ProjectFeedback

HR_OWNERS = {RoleName.HR_FULL.value, RoleName.SUPER_ADMIN.value}


def _is_hr_owner(actor: Employee) -> bool:
    return actor.role.name in HR_OWNERS


def _cycle_out(row: PerformanceCycle) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "goal_due_date": row.goal_due_date,
        "self_review_due_date": row.self_review_due_date,
        "manager_review_due_date": row.manager_review_due_date,
        "status": row.status,
        "created_by_name": row.created_by.full_name if row.created_by else None,
        "approved_by_name": row.approved_by.full_name if row.approved_by else None,
    }


def _goal_out(row: PerformanceGoal) -> dict:
    return {
        "id": row.id,
        "cycle_id": row.cycle_id,
        "employee_id": row.employee_id,
        "title": row.title,
        "description": row.description,
        "category": row.category,
        "measurement": row.measurement,
        "weight": row.weight,
        "target_date": row.target_date,
        "progress": row.progress,
        "evidence": row.evidence,
        "status": row.status,
        "manager_comment": row.manager_comment,
        "version": row.version,
    }


def _feedback_out(row: ProjectFeedback) -> dict:
    return {
        "id": row.id,
        "review_id": row.review_id,
        "project_id": row.project_id,
        "project_name": row.project.name,
        "employee_name": row.review.employee.full_name,
        "status": row.status,
        "rating": row.rating,
        "contribution": row.contribution,
        "collaboration": row.collaboration,
        "submitted_at": row.submitted_at,
    }


def _review_out(row: PerformanceReview, *, include_private: bool) -> dict:
    data = {
        "id": row.id,
        "cycle": _cycle_out(row.cycle),
        "employee_id": row.employee_id,
        "employee_name": row.employee.full_name,
        "manager_id": row.manager_id,
        "manager_name": row.manager.full_name if row.manager else "Super Admin",
        "status": row.status,
        "self_summary": row.self_summary,
        "self_rating": row.self_rating,
        "goals": [_goal_out(goal) for goal in getattr(row, "goals", [])],
        "project_feedback": [_feedback_out(item) for item in row.feedback] if include_private else [],
        "published_at": row.published_at,
        "acknowledged_at": row.acknowledged_at,
        "employee_comment": row.employee_comment,
    }
    if include_private or row.status in ("published", "acknowledged"):
        data.update(
            manager_summary=row.manager_summary,
            manager_rating=row.manager_rating,
            calibration_comment=row.calibration_comment,
            calibrated_rating=row.calibrated_rating,
            final_rating=row.final_rating,
            calibrated_by_name=row.calibrated_by.full_name if row.calibrated_by else None,
        )
    return data


def _review_query():
    return select(PerformanceReview).options(
        selectinload(PerformanceReview.cycle).selectinload(PerformanceCycle.created_by),
        selectinload(PerformanceReview.cycle).selectinload(PerformanceCycle.approved_by),
        selectinload(PerformanceReview.employee),
        selectinload(PerformanceReview.manager),
        selectinload(PerformanceReview.calibrated_by),
        selectinload(PerformanceReview.feedback).selectinload(ProjectFeedback.project),
        selectinload(PerformanceReview.feedback).selectinload(ProjectFeedback.review).selectinload(PerformanceReview.employee),
    )


async def _load_review(db, review_id) -> PerformanceReview:
    row = (await db.execute(_review_query().where(PerformanceReview.id == review_id))).scalar_one_or_none()
    if row is None:
        raise NotFound("Performance review not found")
    goals = list(
        (
            await db.execute(
                select(PerformanceGoal)
                .where(PerformanceGoal.cycle_id == row.cycle_id, PerformanceGoal.employee_id == row.employee_id)
                .order_by(PerformanceGoal.created_at)
            )
        ).scalars()
    )
    row.goals = goals
    return row


async def cycles(db, actor: Employee) -> list[dict]:
    query = select(PerformanceCycle).options(
        selectinload(PerformanceCycle.created_by), selectinload(PerformanceCycle.approved_by)
    )
    if not _is_hr_owner(actor):
        query = query.where(PerformanceCycle.status.notin_(["draft", "pending_approval"]))
    rows = (await db.execute(query.order_by(PerformanceCycle.start_date.desc()))).scalars()
    return [_cycle_out(row) for row in rows]


async def create_cycle(db, actor: Employee, payload) -> dict:
    if not _is_hr_owner(actor):
        raise PermissionDenied("Only HR Full or Super Admin can create performance cycles.")
    row = PerformanceCycle(**payload.model_dump(), created_by_id=actor.id)
    db.add(row)
    await db.flush()
    await record_audit(db, actor_id=actor.user_id, action="create", entity_type="performance_cycle", entity_id=str(row.id))
    await db.commit()
    row = (
        await db.execute(
            select(PerformanceCycle)
            .options(selectinload(PerformanceCycle.created_by), selectinload(PerformanceCycle.approved_by))
            .where(PerformanceCycle.id == row.id)
        )
    ).scalar_one()
    return _cycle_out(row)


async def update_cycle(db, actor: Employee, cycle_id, payload) -> dict:
    row = await db.get(PerformanceCycle, cycle_id, with_for_update=True)
    if row is None:
        raise NotFound("Performance cycle not found")
    if row.created_by_id != actor.id or not _is_hr_owner(actor):
        raise PermissionDenied("Only the cycle owner can edit this cycle.")
    if row.status != "draft":
        raise Conflict("Only a draft cycle can be edited.")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    await db.commit()
    return {"id": row.id, "status": row.status}


async def submit_cycle(db, actor: Employee, cycle_id) -> dict:
    row = await db.get(PerformanceCycle, cycle_id, with_for_update=True)
    if row is None:
        raise NotFound("Performance cycle not found")
    if not _is_hr_owner(actor) or row.created_by_id != actor.id:
        raise PermissionDenied("Only the cycle owner can submit it.")
    if row.status != "draft":
        raise Conflict("Only a draft cycle can be submitted.")
    row.status = "pending_approval"
    await db.commit()
    return {"id": row.id, "status": row.status}


async def approve_cycle(db, actor: Employee, cycle_id, payload) -> dict:
    if actor.role.name != RoleName.SUPER_ADMIN.value:
        raise PermissionDenied("Only Super Admin can approve a performance cycle.")
    row = await db.get(PerformanceCycle, cycle_id, with_for_update=True)
    if row is None:
        raise NotFound("Performance cycle not found")
    if row.created_by_id == actor.id:
        raise PermissionDenied("The cycle author cannot approve the same cycle.")
    if row.status != "pending_approval":
        raise Conflict("This cycle is not waiting for approval.")
    if payload.decision == "changes_requested":
        if not payload.comment:
            raise ValidationFailed("A comment is required when requesting changes.")
        row.status = "draft"
        row.description = f"{row.description or ''}\nReview note: {payload.comment}".strip()
    else:
        row.status = "open"
        row.approved_by_id = actor.id
        row.approved_at = datetime.now(UTC)
        employees = list(
            (await db.execute(select(Employee).where(Employee.employment_status == EmploymentStatus.ACTIVE))).scalars()
        )
        for employee in employees:
            db.add(
                PerformanceReview(
                    cycle_id=row.id,
                    employee_id=employee.id,
                    manager_id=employee.reports_to_id,
                )
            )
    await record_audit(
        db,
        actor_id=actor.user_id,
        action=f"performance_cycle_{payload.decision}",
        entity_type="performance_cycle",
        entity_id=str(row.id),
        diff={"comment": payload.comment},
    )
    await db.commit()
    return {"id": row.id, "status": row.status}


async def dashboard(db, actor: Employee) -> dict:
    cycle_rows = await cycles(db, actor)
    review_query = _review_query().where(PerformanceReview.employee_id == actor.id)
    my_rows = list((await db.execute(review_query.order_by(PerformanceReview.created_at.desc()))).scalars())
    for row in my_rows:
        row.goals = list(
            (
                await db.execute(
                    select(PerformanceGoal).where(
                        PerformanceGoal.cycle_id == row.cycle_id, PerformanceGoal.employee_id == row.employee_id
                    )
                )
            ).scalars()
        )
    team_query = _review_query()
    if _is_hr_owner(actor):
        team_query = team_query.where(PerformanceReview.employee_id != actor.id)
    else:
        second_level_managers = select(Employee.id).where(Employee.reports_to_id == actor.id)
        team_query = team_query.where(
            or_(PerformanceReview.manager_id == actor.id, PerformanceReview.manager_id.in_(second_level_managers))
        )
    team_rows = list((await db.execute(team_query.order_by(PerformanceReview.created_at.desc()))).scalars())
    for row in team_rows:
        row.goals = list(
            (
                await db.execute(
                    select(PerformanceGoal).where(
                        PerformanceGoal.cycle_id == row.cycle_id, PerformanceGoal.employee_id == row.employee_id
                    )
                )
            ).scalars()
        )
    feedback_rows = list(
        (
            await db.execute(
                select(ProjectFeedback)
                .options(
                    selectinload(ProjectFeedback.project),
                    selectinload(ProjectFeedback.review).selectinload(PerformanceReview.employee),
                )
                .where(ProjectFeedback.reviewer_id == actor.id)
                .order_by(ProjectFeedback.created_at.desc())
            )
        ).scalars()
    )
    return {
        "cycles": cycle_rows,
        "my_reviews": [_review_out(row, include_private=False) for row in my_rows],
        "team_reviews": [_review_out(row, include_private=True) for row in team_rows],
        "feedback_requests": [_feedback_out(row) for row in feedback_rows],
        "can_manage_cycles": _is_hr_owner(actor),
        "can_approve_cycles": actor.role.name == RoleName.SUPER_ADMIN.value,
    }


async def review_detail(db, actor: Employee, review_id) -> dict:
    row = await _load_review(db, review_id)
    allowed = row.employee_id == actor.id or row.manager_id == actor.id or _is_hr_owner(actor)
    if not allowed:
        raise NotFound("Performance review not found")
    return _review_out(row, include_private=row.employee_id != actor.id or row.status in ("published", "acknowledged"))


async def create_goal(db, actor: Employee, review_id, payload) -> dict:
    row = await _load_review(db, review_id)
    if row.employee_id != actor.id:
        raise PermissionDenied("You can only create goals for your own review.")
    if row.cycle.status != "open" or row.status not in ("not_started", "self_draft"):
        raise Conflict("Goals are locked for this review.")
    if not row.cycle.start_date <= payload.target_date <= row.cycle.end_date:
        raise ValidationFailed("The goal target date must fall inside the review cycle.")
    goal = PerformanceGoal(cycle_id=row.cycle_id, employee_id=actor.id, **payload.model_dump())
    db.add(goal)
    row.status = "self_draft"
    await db.commit()
    await db.refresh(goal)
    return _goal_out(goal)


async def update_goal(db, actor: Employee, goal_id, payload) -> dict:
    goal = await db.get(PerformanceGoal, goal_id, with_for_update=True)
    if goal is None:
        raise NotFound("Goal not found")
    if goal.employee_id != actor.id:
        raise PermissionDenied("You can only edit your own goals.")
    if goal.status not in ("draft", "changes_requested"):
        raise Conflict("Only draft or returned goals can be edited.")
    for key, value in payload.model_dump().items():
        setattr(goal, key, value)
    goal.status = "draft"
    goal.manager_comment = None
    goal.version += 1
    await db.commit()
    return _goal_out(goal)


async def submit_goals(db, actor: Employee, review_id) -> dict:
    row = await _load_review(db, review_id)
    if row.employee_id != actor.id:
        raise PermissionDenied("You can only submit your own goals.")
    goals = row.goals
    if not goals or sum(goal.weight for goal in goals) != 100:
        raise ValidationFailed("Goal weights must total exactly 100% before submission.")
    if any(goal.status not in ("draft", "changes_requested") for goal in goals):
        raise Conflict("Goals are already waiting for approval or approved.")
    for goal in goals:
        goal.status = "pending_approval"
    await db.commit()
    return {"review_id": row.id, "status": "pending_approval"}


async def decide_goals(db, actor: Employee, review_id, payload) -> dict:
    row = await _load_review(db, review_id)
    if row.manager_id != actor.id and actor.role.name != RoleName.SUPER_ADMIN.value:
        raise PermissionDenied("Only the reporting manager can review these goals.")
    pending = [goal for goal in row.goals if goal.status == "pending_approval"]
    if not pending:
        raise Conflict("No goals are waiting for approval.")
    if payload.decision == "changes_requested" and not payload.comment:
        raise ValidationFailed("A comment is required when requesting changes.")
    for goal in pending:
        goal.status = "approved" if payload.decision == "approve" else "changes_requested"
        goal.manager_comment = payload.comment
    await db.commit()
    return {"review_id": row.id, "status": payload.decision}


async def _create_feedback_requests(db, review: PerformanceReview) -> None:
    cycle = review.cycle
    allocations = list(
        (
            await db.execute(
                select(Allocation)
                .options(selectinload(Allocation.project))
                .where(
                    Allocation.employee_id == review.employee_id,
                    Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES),
                    Allocation.start_date <= cycle.end_date,
                    or_(Allocation.end_date.is_(None), Allocation.end_date >= cycle.start_date),
                )
            )
        ).scalars()
    )
    for allocation in allocations:
        reviewer_id = allocation.project.project_manager_id
        if reviewer_id and reviewer_id != review.manager_id:
            existing = (
                await db.execute(
                    select(ProjectFeedback.id).where(
                        ProjectFeedback.review_id == review.id,
                        ProjectFeedback.project_id == allocation.project_id,
                        ProjectFeedback.reviewer_id == reviewer_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(ProjectFeedback(review_id=review.id, project_id=allocation.project_id, reviewer_id=reviewer_id))


async def submit_self_review(db, actor: Employee, review_id, payload) -> dict:
    row = await _load_review(db, review_id)
    if row.employee_id != actor.id:
        raise PermissionDenied("You can only submit your own self-review.")
    if row.status not in ("not_started", "self_draft"):
        raise Conflict("This self-review cannot be changed.")
    if not row.goals or sum(goal.weight for goal in row.goals) != 100 or any(goal.status != "approved" for goal in row.goals):
        raise ValidationFailed("All goals must be approved and total 100% before the self-review.")
    row.self_summary = payload.summary
    row.self_rating = payload.rating
    row.status = "submitted_to_manager"
    await _create_feedback_requests(db, row)
    await db.commit()
    return {"id": row.id, "status": row.status, "pending_with": row.manager.full_name if row.manager else "Super Admin"}


async def submit_manager_review(db, actor: Employee, review_id, payload) -> dict:
    row = await _load_review(db, review_id)
    if row.manager_id != actor.id and actor.role.name != RoleName.SUPER_ADMIN.value:
        raise PermissionDenied("Only the reporting manager can complete this review.")
    if row.status != "submitted_to_manager":
        raise Conflict("The employee self-review is not waiting for manager review.")
    row.manager_summary = payload.summary
    row.manager_rating = payload.rating
    row.status = "manager_submitted"
    await db.commit()
    return {"id": row.id, "status": row.status}


async def submit_feedback(db, actor: Employee, feedback_id, payload) -> dict:
    row = (
        await db.execute(
            select(ProjectFeedback)
            .options(
                selectinload(ProjectFeedback.project),
                selectinload(ProjectFeedback.review).selectinload(PerformanceReview.employee),
            )
            .where(ProjectFeedback.id == feedback_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.reviewer_id != actor.id:
        raise NotFound("Feedback request not found")
    if row.status != "pending":
        raise Conflict("This feedback was already submitted.")
    row.rating = payload.rating
    row.contribution = payload.contribution
    row.collaboration = payload.collaboration
    row.status = "submitted"
    row.submitted_at = datetime.now(UTC)
    await db.commit()
    return _feedback_out(row)


async def calibrate(db, actor: Employee, review_id, payload) -> dict:
    row = await _load_review(db, review_id)
    manager_manager_id = None
    if row.manager_id:
        manager = await db.get(Employee, row.manager_id)
        manager_manager_id = manager.reports_to_id if manager else None
    if not _is_hr_owner(actor) and actor.id != manager_manager_id:
        raise PermissionDenied("Only the second-level manager or HR Full can calibrate this review.")
    if row.status != "manager_submitted":
        raise Conflict("The manager review must be submitted before calibration.")
    row.calibrated_rating = payload.rating
    row.calibration_comment = payload.comment
    row.calibrated_by_id = actor.id
    row.status = "calibrated"
    await db.commit()
    return {"id": row.id, "status": row.status}


async def publish(db, actor: Employee, review_id) -> dict:
    if not _is_hr_owner(actor):
        raise PermissionDenied("Only HR Full or Super Admin can publish performance reviews.")
    row = await _load_review(db, review_id)
    if row.status != "calibrated":
        raise Conflict("Only calibrated reviews can be published.")
    row.final_rating = row.calibrated_rating
    row.status = "published"
    row.published_at = datetime.now(UTC)
    await db.commit()
    return {"id": row.id, "status": row.status, "final_rating": row.final_rating}


async def acknowledge(db, actor: Employee, review_id, payload) -> dict:
    row = await _load_review(db, review_id)
    if row.employee_id != actor.id:
        raise PermissionDenied("You can only acknowledge your own review.")
    if row.status != "published":
        raise Conflict("Only a published review can be acknowledged.")
    row.employee_comment = payload.comment
    row.acknowledged_at = datetime.now(UTC)
    row.status = "acknowledged"
    await db.commit()
    return {"id": row.id, "status": row.status}


async def work_items(db, actor: Employee, view: str) -> list:
    from hrms.schemas.work import WorkItem

    items = []
    reviews = list(
        (
            await db.execute(
                _review_query().where(or_(PerformanceReview.employee_id == actor.id, PerformanceReview.manager_id == actor.id))
            )
        ).scalars()
    )
    for review in reviews:
        is_self = review.employee_id == actor.id
        goals = list(
            (
                await db.execute(
                    select(PerformanceGoal).where(
                        PerformanceGoal.cycle_id == review.cycle_id,
                        PerformanceGoal.employee_id == review.employee_id,
                    )
                )
            ).scalars()
        )
        pending_goals = any(goal.status == "pending_approval" for goal in goals)
        approved_goals = (
            bool(goals) and sum(goal.weight for goal in goals) == 100 and all(goal.status == "approved" for goal in goals)
        )
        title = None
        kind = "action"
        due = None
        status = review.status
        if view == "todo" and is_self:
            if review.status in ("not_started", "self_draft") and not approved_goals:
                title, due = "Set and submit performance goals", review.cycle.goal_due_date
            elif review.status in ("not_started", "self_draft") and approved_goals:
                title, due = "Complete your self-review", review.cycle.self_review_due_date
            elif review.status == "published":
                title, due = "Acknowledge your performance review", None
        elif view == "todo" and not is_self:
            kind = "approval"
            if pending_goals:
                title, due = f"Approve goals for {review.employee.full_name}", review.cycle.goal_due_date
            elif review.status == "submitted_to_manager":
                title, due = f"Review {review.employee.full_name}'s performance", review.cycle.manager_review_due_date
        elif (
            view == "waiting"
            and is_self
            and review.status
            in (
                "submitted_to_manager",
                "manager_submitted",
                "calibrated",
            )
        ):
            title = "Performance review awaiting completion"
        elif view == "completed" and is_self and review.status == "acknowledged":
            title = "Performance review acknowledged"
        if title:
            items.append(
                WorkItem(
                    id=review.id,
                    source="performance",
                    kind=kind,
                    title=title,
                    employee_name=review.employee.full_name,
                    department=review.employee.department,
                    status=status,
                    due_date=due,
                    overdue=bool(due and due < datetime.now(UTC).date()),
                    action_type="performance_review",
                    assignee_name=review.manager.full_name if review.manager else "Super Admin",
                    can_act=view == "todo",
                    href="/performance",
                )
            )
    feedback = list(
        (
            await db.execute(
                select(ProjectFeedback)
                .options(
                    selectinload(ProjectFeedback.project),
                    selectinload(ProjectFeedback.review).selectinload(PerformanceReview.employee),
                )
                .where(ProjectFeedback.reviewer_id == actor.id)
            )
        ).scalars()
    )
    for row in feedback:
        if (view == "todo" and row.status == "pending") or (view == "completed" and row.status == "submitted"):
            items.append(
                WorkItem(
                    id=row.id,
                    source="performance",
                    kind="action",
                    title=f"Project feedback for {row.review.employee.full_name}",
                    description=row.project.name,
                    employee_name=row.review.employee.full_name,
                    department=row.review.employee.department,
                    status=row.status,
                    action_type="project_feedback",
                    assignee_name=actor.full_name,
                    can_act=row.status == "pending",
                    href="/performance",
                )
            )
    if view == "todo" and actor.role.name == RoleName.SUPER_ADMIN.value:
        pending_cycles = list(
            (
                await db.execute(
                    select(PerformanceCycle)
                    .options(selectinload(PerformanceCycle.created_by))
                    .where(
                        PerformanceCycle.status == "pending_approval",
                        PerformanceCycle.created_by_id != actor.id,
                    )
                )
            ).scalars()
        )
        for cycle in pending_cycles:
            items.append(
                WorkItem(
                    id=cycle.id,
                    source="performance",
                    kind="approval",
                    title=f"Approve performance cycle: {cycle.name}",
                    employee_name=cycle.created_by.full_name,
                    department=cycle.created_by.department,
                    status=cycle.status,
                    action_type="performance_cycle_approval",
                    assignee_name=actor.full_name,
                    can_act=True,
                    href="/performance",
                )
            )
    return items

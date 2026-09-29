"""Task-scoped reads and writes. An assignment grants no access to its parent module."""

from datetime import date

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from hrms.authz.enums import Action, FeatureKey, RecordScope
from hrms.authz.scope_filters import apply_employee_scope, managed_project_ids_subquery
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from hrms.models.asset import Asset
from hrms.models.document import EmployeeDocument
from hrms.models.employee import Employee
from hrms.models.enums import (
    ALLOCATABLE_PROJECT_STATUSES,
    TERMINAL_TASK_STATUSES,
    AssetStatus,
    DocumentStatus,
    EmploymentStatus,
    TaskActionType,
    TaskStatus,
)
from hrms.models.onboarding import OnboardingRecord, OnboardingTask
from hrms.models.project import Project, ProjectApprovalRequest
from hrms.schemas.allocation import AllocationCreate
from hrms.schemas.asset import AssetAssignIn
from hrms.schemas.work import WorkItem
from hrms.services import allocation_service, asset_service, onboarding_flow_service, onboarding_service


def task_query():
    return select(OnboardingTask).options(
        selectinload(OnboardingTask.assignee),
        selectinload(OnboardingTask.onboarding_record).selectinload(OnboardingRecord.employee),
    )


def latest_document_predicate():
    newer = aliased(EmployeeDocument)
    return ~exists(
        select(newer.id).where(
            newer.employee_id == EmployeeDocument.employee_id,
            newer.doc_type == EmployeeDocument.doc_type,
            or_(
                newer.created_at > EmployeeDocument.created_at,
                (newer.created_at == EmployeeDocument.created_at) & (newer.id > EmployeeDocument.id),
            ),
        )
    )


def document_query():
    return select(EmployeeDocument).options(selectinload(EmployeeDocument.employee))


async def is_reviewer(engine, actor):
    return await engine.has_permission(actor, FeatureKey.EMPLOYEE_ONBOARDING, Action.MANAGE)


def task_item(task, actor, *, manager=False):
    employee = task.onboarding_record.employee
    description = {
        TaskActionType.ASSET_ASSIGNMENT: "Select an available asset below to record the handover and complete this task.",
        TaskActionType.PROJECT_ALLOCATION: "Choose a project and allocation dates below to complete this task.",
    }.get(task.action_type, task.description)
    return WorkItem(
        id=task.id,
        source="tasks",
        kind="action",
        title=task.title,
        description=description,
        employee_name=employee.full_name,
        department=employee.department,
        date_joined=employee.date_joined,
        workflow_type=task.onboarding_record.workflow_type.value,
        status=task.status.value,
        action_type=task.action_type.value,
        due_date=task.due_date,
        overdue=bool(task.status == TaskStatus.READY and task.due_date and task.due_date < date.today()),
        assignee_name=task.assignee.full_name if task.assignee else "Unassigned — HR action needed",
        note=task.completion_note,
        can_act=task.status == TaskStatus.READY and (task.assignee_employee_id == actor.id or manager),
        payroll_required=task.step_key == "razorpay_account",
        can_reassign=manager and task.status not in TERMINAL_TASK_STATUSES,
        record_id=task.onboarding_record_id if manager else None,
    )


def document_item(doc, actor, reviewer):
    return WorkItem(
        id=doc.id,
        source="documents",
        kind="approval",
        title=f"Review {doc.doc_type.value.replace('_', ' ')}",
        employee_name=doc.employee.full_name,
        department=doc.employee.department,
        date_joined=doc.employee.date_joined,
        status=doc.status.value,
        action_type="document_review",
        assignee_name="HR review queue",
        note=doc.note,
        file_name=doc.file_name,
        can_act=reviewer and doc.status == DocumentStatus.SUBMITTED and actor.id not in (doc.employee_id, doc.uploaded_by_id),
    )


async def queue_queries(engine, actor, view):
    tasks = task_query().where(OnboardingTask.assignee_employee_id == actor.id)
    tasks = tasks.where(
        OnboardingTask.status.in_(
            [TaskStatus.READY] if view == "todo" else [TaskStatus.PENDING] if view == "waiting" else list(TERMINAL_TASK_STATUSES)
        )
    )
    reviewer = await is_reviewer(engine, actor)
    docs = document_query()
    if view != "waiting":
        scope = await engine.get_scope(actor, FeatureKey.EMPLOYEE_ONBOARDING)
        visible_employees = apply_employee_scope(select(Employee.id), scope, actor)
        docs = docs.where(EmployeeDocument.employee_id.in_(visible_employees))
    if view == "todo":
        docs = docs.where(
            EmployeeDocument.status == DocumentStatus.SUBMITTED,
            EmployeeDocument.employee_id != actor.id,
            or_(EmployeeDocument.uploaded_by_id.is_(None), EmployeeDocument.uploaded_by_id != actor.id),
            latest_document_predicate(),
        )
        if not reviewer:
            docs = docs.where(False)
    elif view == "waiting":
        docs = docs.where(
            EmployeeDocument.employee_id == actor.id,
            EmployeeDocument.status == DocumentStatus.SUBMITTED,
            latest_document_predicate(),
        )
    else:
        docs = docs.where(
            EmployeeDocument.verified_by_id == actor.id,
            EmployeeDocument.status.in_([DocumentStatus.VERIFIED, DocumentStatus.REJECTED]),
        )
        if not reviewer:
            docs = docs.where(False)
    return tasks, docs, reviewer


async def inbox(db, engine, actor, view, page, page_size, kind=None):
    from hrms.services import hr_cockpit_service, performance_service, project_approval_service

    tasks, docs, reviewer = await queue_queries(engine, actor, view)
    requests = await project_approval_service.inbox_query(engine, actor, view)
    if kind == "approval":
        requests = requests.where(ProjectApprovalRequest.status.notin_(["draft", "changes_requested"]))
    if kind == "action":
        requests = requests.where(ProjectApprovalRequest.status.in_(["draft", "changes_requested"]))
    if kind == "approval":
        tasks = tasks.where(False)
    if kind == "action":
        docs = docs.where(False)
    performance_items = await performance_service.work_items(db, actor, view)
    hr_items = await hr_cockpit_service.work_items(db, actor, view)
    if kind:
        performance_items = [item for item in performance_items if item.kind == kind]
        hr_items = [item for item in hr_items if item.kind == kind]
    # Merge only the bounded prefix needed for this page; never load all work.
    count = 0
    for query in (tasks, docs, requests):
        count += (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    count += len(performance_items) + len(hr_items)
    take = page * page_size
    task_rows = (
        await db.execute(tasks.order_by(OnboardingTask.due_date.asc().nulls_last(), OnboardingTask.id).limit(take))
    ).scalars()
    doc_rows = (await db.execute(docs.order_by(EmployeeDocument.id).limit(take))).scalars()
    request_rows = (await db.execute(requests.order_by(ProjectApprovalRequest.id).limit(take))).scalars()
    items = [task_item(t, actor) for t in task_rows] + [document_item(d, actor, reviewer) for d in doc_rows]
    items += [project_approval_service.work_item(r, actor) for r in request_rows]
    items += performance_items
    items += hr_items
    items.sort(key=lambda i: (i.due_date or date.max, str(i.id)))
    return {"items": items[(page - 1) * page_size : take], "total": count, "page": page, "page_size": page_size}


async def summary(db, engine, actor):
    tasks, docs, _ = await queue_queries(engine, actor, "todo")
    actions = (await db.execute(select(func.count()).select_from(tasks.subquery()))).scalar_one()
    approvals = (await db.execute(select(func.count()).select_from(docs.subquery()))).scalar_one()
    from hrms.services import hr_cockpit_service, performance_service, project_approval_service

    requests = await project_approval_service.inbox_query(engine, actor, "todo")
    for is_action in (True, False):
        condition = ProjectApprovalRequest.status.in_(["draft", "changes_requested"])
        query = requests.where(condition if is_action else ~condition)
        count = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        if is_action:
            actions += count
        else:
            approvals += count
    for item in await performance_service.work_items(db, actor, "todo"):
        if item.kind == "action":
            actions += 1
        else:
            approvals += 1
    for item in await hr_cockpit_service.work_items(db, actor, "todo"):
        if item.kind == "action": actions += 1
        else: approvals += 1
    return {"actions": actions, "approvals": approvals, "total": actions + approvals}


async def load_task(db, engine, actor, task_id, *, write=False):
    # Read authorization before acquiring a workflow lock. Recheck after the lock
    # to handle an assignment changed concurrently by HR.
    task = (await db.execute(task_query().where(OnboardingTask.id == task_id))).scalar_one_or_none()
    if task is None:
        raise NotFound("Task not found")
    manager = await engine.has_permission(
        actor, onboarding_service.FEATURE_BY_TYPE[task.onboarding_record.workflow_type], Action.MANAGE
    )
    if task.assignee_employee_id != actor.id and not manager:
        raise NotFound("Task not found")
    if manager:
        await onboarding_service.assert_can_manage_record(db, engine, actor, task.onboarding_record)
    if write:
        await db.execute(select(OnboardingRecord.id).where(OnboardingRecord.id == task.onboarding_record_id).with_for_update())
        task = (
            await db.execute(task_query().where(OnboardingTask.id == task_id).execution_options(populate_existing=True))
        ).scalar_one()
        if task.assignee_employee_id != actor.id and not manager:
            raise NotFound("Task not found")
    return task, manager


async def detail(db, engine, actor, task_id):
    task, manager = await load_task(db, engine, actor, task_id)
    return task_item(task, actor, manager=manager)


async def document_detail(db, engine, actor, document_id):
    doc = (await db.execute(document_query().where(EmployeeDocument.id == document_id))).scalar_one_or_none()
    reviewer = await is_reviewer(engine, actor)
    if doc is None or (doc.employee_id != actor.id and not reviewer):
        raise NotFound("Review not found")
    if doc.employee_id != actor.id:
        from hrms.services.document_service import assert_employee_access

        await assert_employee_access(db, engine, actor, doc.employee_id)
    item = document_item(doc, actor, reviewer)
    latest = (
        await db.execute(select(EmployeeDocument.id).where(EmployeeDocument.id == document_id, latest_document_predicate()))
    ).scalar_one_or_none()
    item.can_act = item.can_act and latest is not None
    return item


def require_ready(task, action_type):
    if task.status != TaskStatus.READY:
        raise Conflict("This task is no longer actionable. Refresh My Work.")
    if task.action_type != action_type:
        raise ValidationFailed("This action does not belong to the assigned task.")


async def asset_options(db, engine, actor, task_id):
    task, _ = await load_task(db, engine, actor, task_id)
    require_ready(task, TaskActionType.ASSET_ASSIGNMENT)
    rows = (await db.execute(select(Asset).where(Asset.status == AssetStatus.IN_STOCK).order_by(Asset.name))).scalars()
    return [{"id": a.id, "label": f"{a.asset_tag} — {a.name}"} for a in rows]


async def assign_asset(db, engine, actor, task_id, payload):
    task, _ = await load_task(db, engine, actor, task_id, write=True)
    require_ready(task, TaskActionType.ASSET_ASSIGNMENT)
    await asset_service.assign_asset(
        db,
        actor,
        payload.asset_id,
        AssetAssignIn(
            employee_id=task.onboarding_record.employee_id,
            assigned_date=payload.assigned_date,
            condition_notes=payload.condition_notes,
        ),
    )
    return await detail(db, engine, actor, task_id)


async def project_options(db, engine, actor, task_id):
    task, _ = await load_task(db, engine, actor, task_id)
    require_ready(task, TaskActionType.PROJECT_ALLOCATION)
    if not await engine.has_permission(actor, FeatureKey.ALLOCATIONS, Action.CREATE):
        raise PermissionDenied("Project allocation permission is required. Ask HR to reassign this task.")
    scope = await engine.get_scope(actor, FeatureKey.ALLOCATIONS)
    stmt = select(Project).where(Project.status.in_(ALLOCATABLE_PROJECT_STATUSES), Project.approval_status == "approved")
    if scope == RecordScope.NONE:
        return []
    if scope != RecordScope.ALL:
        stmt = stmt.where(Project.id.in_(managed_project_ids_subquery(actor.id)))
    rows = (await db.execute(stmt.order_by(Project.name))).scalars()
    return [{"id": p.id, "label": p.name} for p in rows]


async def project_role_options(db, engine, actor, task_id):
    task, _ = await load_task(db, engine, actor, task_id)
    require_ready(task, TaskActionType.PROJECT_ALLOCATION)
    if not await engine.has_permission(actor, FeatureKey.ALLOCATIONS, Action.CREATE):
        raise PermissionDenied("Project allocation permission is required.")
    from hrms.services.reference_data_service import project_role_options as options

    return await options(db)


async def allocate(db, engine, actor, task_id, payload):
    task, _ = await load_task(db, engine, actor, task_id, write=True)
    require_ready(task, TaskActionType.PROJECT_ALLOCATION)
    if not await engine.has_permission(actor, FeatureKey.ALLOCATIONS, Action.CREATE):
        raise PermissionDenied("Project allocation permission is required. Ask HR to reassign this task.")
    result = await allocation_service.create_allocation(
        db, engine, actor, AllocationCreate(employee_id=task.onboarding_record.employee_id, **payload.model_dump())
    )
    return {"item": await detail(db, engine, actor, task_id), "over_allocated": result.over_allocated}


async def assignee_options(db, engine, actor, task_id):
    task, _ = await load_task(db, engine, actor, task_id)
    await onboarding_service.assert_can_manage_record(db, engine, actor, task.onboarding_record)
    rows = (
        await db.execute(
            select(Employee).where(Employee.employment_status == EmploymentStatus.ACTIVE).order_by(Employee.first_name)
        )
    ).scalars()
    return [{"id": e.id, "label": e.full_name} for e in rows]


async def reassign(db, engine, actor, task_id, payload):
    task, _ = await load_task(db, engine, actor, task_id, write=True)
    await onboarding_service.assert_can_manage_record(db, engine, actor, task.onboarding_record)
    if task.status in TERMINAL_TASK_STATUSES:
        raise Conflict("Completed tasks cannot be reassigned.")
    if task.action_type in (TaskActionType.EMPLOYEE_PROFILE, TaskActionType.DOCUMENT_COLLECTION, TaskActionType.INVITE_EMPLOYEE):
        raise ValidationFailed("Employee self-service and system tasks cannot be reassigned.")
    if not payload.reason.strip():
        raise ValidationFailed("A reason is required.")
    assignee = await db.get(Employee, payload.employee_id)
    if assignee is None or assignee.employment_status != EmploymentStatus.ACTIVE:
        raise ValidationFailed("Choose an active employee.")
    if task.action_type == TaskActionType.PROJECT_ALLOCATION and not await engine.has_permission(
        assignee, FeatureKey.ALLOCATIONS, Action.CREATE
    ):
        raise ValidationFailed("The assignee needs project allocation permission.")
    previous = task.assignee_employee_id
    task.assignee_employee_id = assignee.id
    task.assignee = assignee
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="reassign",
        entity_type="onboarding_task",
        entity_id=str(task.id),
        diff={"from": str(previous), "to": str(assignee.id), "reason": payload.reason},
    )
    if task.status == TaskStatus.READY and previous != assignee.id:
        await onboarding_flow_service._on_task_ready(db, task.onboarding_record, task, task.onboarding_record.employee)
    await db.commit()
    return await detail(db, engine, actor, task_id)


async def allocation_preview(db, engine, actor, task_id, payload):
    from hrms.schemas.allocation import AllocationPreview

    task, _ = await load_task(db, engine, actor, task_id)
    require_ready(task, TaskActionType.PROJECT_ALLOCATION)
    if not await engine.has_permission(actor, FeatureKey.ALLOCATIONS, Action.CREATE):
        raise PermissionDenied("Project allocation permission is required.")
    proposal = AllocationPreview(
        employee_id=task.onboarding_record.employee_id,
        **payload.model_dump(include={"project_id", "allocation_percent", "start_date", "end_date"}),
    )
    return await allocation_service.preview_allocation(db, engine, actor, proposal)

"""Project approval state machine. Every transition locks the parent project."""

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from hrms.authz.enums import Action, FeatureKey, PermissionKey
from hrms.authz.scope_filters import apply_project_scope
from hrms.authz.serializers import strip_project_fields
from hrms.config import get_settings
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from hrms.models.allocation import Allocation
from hrms.models.employee import Employee
from hrms.models.enums import COMMITTED_ALLOCATION_STATUSES, EmploymentStatus, ProjectStatus
from hrms.models.project import Customer, Project, ProjectApprovalRequest
from hrms.schemas.project import ProjectCreate
from hrms.services import notification_service

FEATURE = FeatureKey.PROJECTS
OPEN_STATES = ("draft", "pending", "changes_requested")
MATERIAL_FIELDS = {
    "name",
    "customer_id",
    "project_manager_id",
    "delivery_manager_id",
    "start_date",
    "end_date",
    "engagement_type",
    "currency",
    "budgeted_hours",
    "budget_amount",
    "billing_rate",
    "revenue",
    "margin_percent",
}


def latest_request(project):
    return max(project.approval_requests, key=lambda r: (r.created_at, str(r.id)), default=None)


def project_values(project):
    return ProjectCreate.model_validate({k: getattr(project, k) for k in ProjectCreate.model_fields}).model_dump(mode="json")


def safe_values(values, keys):
    out = strip_project_fields(dict(values), keys)
    if PermissionKey.VIEW_PROJECT_REVENUE not in keys:
        out.pop("budget_amount", None)
    return out


def request_out(request, keys):
    return {
        "id": str(request.id),
        "project_id": str(request.project_id),
        "kind": request.kind,
        "status": request.status,
        "version": request.version,
        "requested_by_id": str(request.requested_by_id),
        "requester_name": request.requester.full_name,
        "reviewer_name": request.reviewer.full_name if request.reviewer else None,
        "submitted_at": request.submitted_at.isoformat() if request.submitted_at else None,
        "decided_at": request.decided_at.isoformat() if request.decided_at else None,
        "note": request.note,
        "proposed": safe_values(request.proposed, keys),
        "history": [
            {**e, **({"snapshot": safe_values(e["snapshot"], keys)} if "snapshot" in e else {})} for e in request.history
        ],
    }


async def event(db, request, actor, action, note=None, *, snapshot=False):
    entry = {
        "action": action,
        "actor": actor.full_name,
        "actor_id": str(actor.id),
        "at": datetime.now(UTC).isoformat(),
        "version": request.version,
        "note": note,
    }
    if snapshot:
        entry["snapshot"] = dict(request.proposed)
    request.history = [*(request.history or []), entry]
    await record_audit(
        db,
        actor_id=actor.user_id,
        action=f"project_{action}",
        entity_type="project_approval",
        entity_id=str(request.id),
        diff=entry,
    )


async def new_request(db, project, actor, proposed, *, direct=False):
    request = ProjectApprovalRequest(
        project_id=project.id,
        requested_by_id=actor.id,
        kind="initial" if project.approval_status != "approved" else "amendment",
        status="approved" if direct else "draft",
        version=1 if direct else 0,
        proposed=proposed,
        history=[],
    )
    if direct:
        request.kind = "initial"
        request.reviewed_by_id = actor.id
        request.decided_at = datetime.now(UTC)
        request.note = "Created and approved by Super Admin"
    db.add(request)
    await db.flush()
    await event(db, request, actor, "created_and_approved" if direct else "draft_created", request.note, snapshot=direct)
    return request


async def validate_proposal(db, proposed):
    from hrms.services.project_service import _assert_active_employee, _assert_customer_assignable

    payload = ProjectCreate.model_validate(proposed)
    await _assert_customer_assignable(db, payload.customer_id)
    await _assert_active_employee(db, payload.project_manager_id, "project manager")
    if payload.delivery_manager_id:
        await _assert_active_employee(db, payload.delivery_manager_id, "delivery manager")
    return payload


async def lock_project(db, project_id):
    from hrms.repositories import project_repo

    found = (await db.execute(select(Project.id).where(Project.id == project_id).with_for_update())).scalar_one_or_none()
    if found is None:
        raise NotFound("Project not found")
    return (
        await db.execute(
            project_repo.projects_base_query().where(Project.id == project_id).execution_options(populate_existing=True)
        )
    ).scalar_one()


async def assert_operational(db, project_id):
    # Lock through the write transaction so initial approval cannot race usage.
    project = (
        await db.execute(
            select(Project).where(Project.id == project_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if project is None:
        raise NotFound("Project not found")
    if project.approval_status != "approved":
        raise ValidationFailed("This project needs approval before allocations or timesheets can be created.")
    return project


async def query_for_actor(engine, actor):
    scope = await engine.get_scope(actor, FEATURE)
    visible = apply_project_scope(select(Project.id), scope, actor)
    return (
        select(ProjectApprovalRequest)
        .options(
            selectinload(ProjectApprovalRequest.project),
            selectinload(ProjectApprovalRequest.requester),
            selectinload(ProjectApprovalRequest.reviewer),
        )
        .where(ProjectApprovalRequest.project_id.in_(visible))
    )


async def can_review(engine, actor):
    return await engine.has_permission(actor, FEATURE, Action.APPROVE)


async def load_request(db, engine, actor, request_id, *, write=False):
    query = await query_for_actor(engine, actor)
    request = (
        await db.execute(query.where(ProjectApprovalRequest.id == request_id).execution_options(populate_existing=True))
    ).scalar_one_or_none()
    if request is None:
        raise NotFound("Project request not found")
    approver = await can_review(engine, actor)
    owner = actor.id in (request.requested_by_id, request.project.project_manager_id, request.project.delivery_manager_id)
    editor = await engine.has_permission(actor, FEATURE, Action.EDIT)
    if not approver and not (owner and editor):
        raise NotFound("Project request not found")
    if write:
        await lock_project(db, request.project_id)
        request = (
            await db.execute(query.where(ProjectApprovalRequest.id == request_id).execution_options(populate_existing=True))
        ).scalar_one()
        owner = actor.id in (request.requested_by_id, request.project.project_manager_id, request.project.delivery_manager_id)
        if not approver and not (owner and editor):
            raise NotFound("Project request not found")
    return request


async def detail(db, engine, actor, request_id):
    request = await load_request(db, engine, actor, request_id)
    keys = await engine.get_all_permission_keys(actor)
    out = request_out(request, keys)
    project = request.project
    out["project_name"] = project.name
    out["project_code"] = project.code
    out["current"] = safe_values(project_values(project), keys)
    out["can_review"] = request.status == "pending" and request.requested_by_id != actor.id and await can_review(engine, actor)
    out["can_submit"] = request.status in ("draft", "changes_requested") and await engine.has_permission(
        actor, FEATURE, Action.SUBMIT
    )
    out["can_withdraw"] = request.status == "pending" and request.requested_by_id == actor.id
    customer = await db.get(Customer, request.proposed["customer_id"])
    pm = await db.get(Employee, request.proposed["project_manager_id"])
    dm = await db.get(Employee, request.proposed["delivery_manager_id"]) if request.proposed.get("delivery_manager_id") else None
    current_customer = await db.get(Customer, project.customer_id)
    current_pm = await db.get(Employee, project.project_manager_id)
    current_dm = await db.get(Employee, project.delivery_manager_id) if project.delivery_manager_id else None
    out["current_names"] = {
        "customer_id": current_customer.name if current_customer else "Unavailable",
        "project_manager_id": current_pm.full_name if current_pm else "Unavailable",
        "delivery_manager_id": current_dm.full_name if current_dm else "Unassigned",
    }
    out["customer_name"] = customer.name if customer else "Unavailable"
    out["project_manager_name"] = pm.full_name if pm else "Unavailable"
    out["delivery_manager_name"] = dm.full_name if dm else "Unassigned"
    return out


async def notify(db, request, actor, *, submitted):
    # Queue, never send inline. Recipients are checked against current permissions and scope.
    from hrms.authz.engine import AuthzEngine

    recipients = (
        (await db.execute(select(Employee).where(Employee.employment_status == EmploymentStatus.ACTIVE))).scalars()
        if submitted
        else [await db.get(Employee, request.requested_by_id)]
    )
    engine = AuthzEngine(db)
    for recipient in recipients:
        if recipient is None or recipient.id == actor.id:
            continue
        if submitted:
            if not await can_review(engine, recipient):
                continue
            query = await query_for_actor(engine, recipient)
            if (await db.execute(query.where(ProjectApprovalRequest.id == request.id))).scalar_one_or_none() is None:
                continue
        notification_service.queue_email(
            db,
            email_to=recipient.work_email,
            template_key="project_review",
            payload={
                "recipient_name": recipient.first_name,
                "project_name": request.proposed["name"],
                "status": "awaiting approval" if submitted else request.status.replace("_", " "),
                "link": f"{get_settings().FRONTEND_URL}/my-work/projects/{request.id}",
            },
            recipient_employee_id=recipient.id,
        )


async def submit(db, engine, actor, request_id, version):
    if not await engine.has_permission(actor, FEATURE, Action.SUBMIT):
        raise PermissionDenied("You cannot submit project requests.")
    request = await load_request(db, engine, actor, request_id, write=True)
    if request.status not in ("draft", "changes_requested") or request.version != version:
        raise Conflict("The request has changed. Refresh before submitting.")
    await validate_proposal(db, request.proposed)
    request.version += 1
    request.status = "pending"
    request.submitted_at = datetime.now(UTC)
    request.reviewed_by_id = None
    request.decided_at = None
    request.note = None
    if request.kind == "initial":
        request.project.approval_status = "pending"
    await event(db, request, actor, "submitted", snapshot=True)
    await db.flush()
    await notify(db, request, actor, submitted=True)
    await db.commit()
    return await detail(db, engine, actor, request_id)


async def withdraw(db, engine, actor, request_id, version):
    if not await engine.has_permission(actor, FEATURE, Action.SUBMIT):
        raise PermissionDenied("You cannot withdraw project requests.")
    request = await load_request(db, engine, actor, request_id, write=True)
    if request.requested_by_id != actor.id:
        raise PermissionDenied("Only the request's author can withdraw it.")
    if request.status != "pending" or request.version != version:
        raise Conflict("This request is no longer pending. Refresh before continuing.")
    request.status = "draft"
    request.version += 1
    if request.kind == "initial":
        request.project.approval_status = "draft"
    await event(db, request, actor, "withdrawn")
    await db.commit()
    return await detail(db, engine, actor, request_id)


async def decide(db, engine, actor, request_id, payload):
    if not await can_review(engine, actor):
        raise PermissionDenied("Project approval permission is required.")
    request = await load_request(db, engine, actor, request_id, write=True)
    if request.requested_by_id == actor.id:
        raise PermissionDenied("You cannot approve your own submitted request. Super Admin direct creation is the exception.")
    if request.status != "pending" or payload.version != request.version:
        raise Conflict("This request or its version has changed. Refresh before reviewing.")
    if payload.decision != "approve" and not (payload.note and payload.note.strip()):
        raise ValidationFailed("A reason is required for rejection or requested changes.")
    project = request.project
    if payload.decision == "approve":
        proposed = await validate_proposal(db, request.proposed)
        # An amendment cannot invalidate existing commitments.
        if request.kind == "amendment":
            allocations = (
                await db.execute(
                    select(Allocation).where(
                        Allocation.project_id == project.id, Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES)
                    )
                )
            ).scalars()
            for allocation in allocations:
                if allocation.start_date < proposed.start_date or (
                    proposed.end_date and (allocation.end_date is None or allocation.end_date > proposed.end_date)
                ):
                    raise ValidationFailed("Proposed dates exclude existing allocations. Adjust them before approval.")
            changes = proposed.model_dump()
            for field in MATERIAL_FIELDS:
                setattr(project, field, changes[field])
        else:
            project.status = ProjectStatus.PLANNED
            project.approval_status = "approved"
        request.status = "approved"
    else:
        request.status = "rejected" if payload.decision == "reject" else "changes_requested"
        if request.kind == "initial":
            project.approval_status = request.status
    request.note = payload.note.strip() if payload.note else None
    request.reviewed_by_id = actor.id
    request.decided_at = datetime.now(UTC)
    await event(db, request, actor, payload.decision, request.note, snapshot=True)
    await db.flush()
    await notify(db, request, actor, submitted=False)
    await db.commit()
    return await detail(db, engine, actor, request_id)


async def inbox_query(engine, actor, view):
    query = await query_for_actor(engine, actor)
    approver = await can_review(engine, actor)
    if not approver and not await engine.has_permission(actor, FEATURE, Action.EDIT):
        return query.where(False)
    if view == "todo":
        condition = (ProjectApprovalRequest.requested_by_id == actor.id) & ProjectApprovalRequest.status.in_(
            ["draft", "changes_requested"]
        )
        if approver:
            condition = or_(
                condition, (ProjectApprovalRequest.status == "pending") & (ProjectApprovalRequest.requested_by_id != actor.id)
            )
        return query.where(condition)
    if view == "waiting":
        return query.where(ProjectApprovalRequest.requested_by_id == actor.id, ProjectApprovalRequest.status == "pending")
    return query.where(
        ProjectApprovalRequest.status.in_(["approved", "rejected"]),
        or_(ProjectApprovalRequest.requested_by_id == actor.id, ProjectApprovalRequest.reviewed_by_id == actor.id),
    )


def work_item(request, actor):
    from hrms.schemas.work import WorkItem

    is_action = request.status in ("draft", "changes_requested")
    subject = "project amendment" if request.kind == "amendment" else "project"
    return WorkItem(
        id=request.id,
        source="projects",
        kind="action" if is_action else "approval",
        title=f"{'Update' if is_action else 'Review'} {subject} — {request.proposed['name']}",
        employee_name=request.requester.full_name,
        department=request.requester.department,
        date_joined=None,
        workflow_type="projects",
        status=request.status,
        action_type="project_review",
        assignee_name=request.requester.full_name if is_action else "Project approvers",
        note=request.note,
        can_act=request.status == "pending" and request.requested_by_id != actor.id,
    )

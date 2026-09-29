from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey, RecordScope
from hrms.authz.scope_filters import apply_customer_scope, apply_project_scope
from hrms.authz.scope_guard import assert_in_scope
from hrms.authz.serializers import strip_customer_fields, strip_project_fields
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from hrms.models.allocation import Allocation
from hrms.models.employee import Employee
from hrms.models.enums import (
    COMMITTED_ALLOCATION_STATUSES,
    CustomerStatus,
    EmploymentStatus,
    ProjectStatus,
)
from hrms.models.project import Customer, Project
from hrms.repositories import employee_repo, project_repo
from hrms.schemas.project import (
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)

CUSTOMER_FEATURE = FeatureKey.CUSTOMERS
PROJECT_FEATURE = FeatureKey.PROJECTS


# --------------------------------------------------------------------------- helpers


def _serialize_customer(customer: Customer, permission_keys, project_count: int | None = None):
    data = CustomerOut.model_validate(customer).model_dump(mode="json")
    if project_count is not None:
        data["project_count"] = project_count
    return strip_customer_fields(data, permission_keys)


def _serialize_project(
    project: Project, permission_keys, headcount: int | None = None, *, actor=None, editor=False, approver=False, all_scope=False
):
    data = ProjectOut.model_validate(project).model_dump(mode="json")
    if headcount is not None:
        data["allocated_headcount"] = headcount
    data = strip_project_fields(data, permission_keys)
    # budget_amount is commercial too, and rides along with revenue visibility.
    from hrms.authz.enums import PermissionKey

    if PermissionKey.VIEW_PROJECT_REVENUE not in permission_keys:
        data.pop("budget_amount", None)
    if actor is not None:
        from hrms.services.project_approval_service import latest_request, request_out

        request = latest_request(project)
        owner = actor.id in (project.created_by_id, project.project_manager_id, project.delivery_manager_id)
        workflow_visible = approver or (editor and owner)
        data["approval_request"] = request_out(request, permission_keys) if request and workflow_visible else None
        data["can_edit"] = (
            editor
            and (all_scope or actor.id in (project.project_manager_id, project.delivery_manager_id))
            and project.status != ProjectStatus.ARCHIVED
            and not (request and request.status == "pending")
        )
        if project.approval_status != "approved":
            data["can_edit"] = data["can_edit"] and (owner or approver) and project.approval_status != "rejected"
        data["approval_history"] = (
            [request_out(r, permission_keys) for r in project.approval_requests] if workflow_visible else []
        )
    return data


async def workflow_visibility(stmt, engine, actor):
    # Drafts are visible only to their owners and project approvers, even for
    # roles with broad read-only access to operational projects.
    if await engine.has_permission(actor, PROJECT_FEATURE, Action.APPROVE):
        return stmt
    allowed = Project.approval_status == "approved"
    if await engine.has_permission(actor, PROJECT_FEATURE, Action.EDIT):
        allowed = (
            allowed
            | (Project.created_by_id == actor.id)
            | (Project.project_manager_id == actor.id)
            | (Project.delivery_manager_id == actor.id)
        )
    return stmt.where(allowed)


async def serialize_for_actor(db, engine, actor, project, headcount=None):
    return _serialize_project(
        project,
        await engine.get_all_permission_keys(actor),
        headcount,
        actor=actor,
        editor=await engine.has_permission(actor, PROJECT_FEATURE, Action.EDIT),
        approver=await engine.has_permission(actor, PROJECT_FEATURE, Action.APPROVE),
        all_scope=await engine.get_scope(actor, PROJECT_FEATURE) == RecordScope.ALL,
    )


async def assert_project_writer(db, engine, actor, project):
    if not await engine.has_permission(actor, PROJECT_FEATURE, Action.EDIT):
        raise PermissionDenied("Project editing permission is required.")
    scope = await engine.get_scope(actor, PROJECT_FEATURE)
    if scope != RecordScope.ALL and actor.id not in (project.project_manager_id, project.delivery_manager_id):
        raise NotFound("Project not found")
    visible = await workflow_visibility(select(Project.id).where(Project.id == project.id), engine, actor)
    if (await db.execute(visible)).scalar_one_or_none() is None:
        raise NotFound("Project not found")


async def _assert_active_employee(db: AsyncSession, employee_id: uuid.UUID, label: str) -> None:
    employee = await employee_repo.get_by_id(db, employee_id)
    if employee is None:
        raise NotFound(f"{label} not found")
    if employee.employment_status in (EmploymentStatus.OFFBOARDING, EmploymentStatus.OFFBOARDED):
        raise ValidationFailed(f"{employee.full_name} is {employee.employment_status.value} and cannot be assigned as {label}.")


async def _assert_customer_assignable(db: AsyncSession, customer_id: uuid.UUID) -> None:
    customer = await project_repo.get_customer(db, customer_id)
    if customer is None:
        raise NotFound("Customer not found")
    if customer.status == CustomerStatus.ARCHIVED:
        raise ValidationFailed(f"Customer '{customer.name}' is archived.")


# --------------------------------------------------------------------------- customers


async def list_customers(
    db: AsyncSession,
    engine: AuthzEngine,
    current_employee: Employee,
    *,
    offset: int,
    limit: int,
    search: str | None = None,
    include_archived: bool = False,
):
    scope = await engine.get_scope(current_employee, CUSTOMER_FEATURE)
    permission_keys = await engine.get_all_permission_keys(current_employee)
    stmt = apply_customer_scope(project_repo.customers_base_query(), scope, current_employee)
    stmt = project_repo.apply_customer_filters(stmt, search=search, include_archived=include_archived)
    customers, total = await project_repo.list_paginated(db, stmt, offset=offset, limit=limit, order_by=Customer.name)
    return [_serialize_customer(c, permission_keys) for c in customers], total


async def get_customer(db: AsyncSession, engine: AuthzEngine, current_employee: Employee, customer_id: uuid.UUID) -> dict:
    await assert_in_scope(
        db,
        engine,
        current_employee,
        feature=CUSTOMER_FEATURE,
        model=Customer,
        record_id=customer_id,
        scope_filter=apply_customer_scope,
        entity_label="Customer",
    )
    customer = await project_repo.get_customer(db, customer_id)
    if customer is None:
        raise NotFound("Customer not found")
    count = await db.execute(select(func.count()).select_from(Project).where(Project.customer_id == customer_id))
    permission_keys = await engine.get_all_permission_keys(current_employee)
    return _serialize_customer(customer, permission_keys, project_count=count.scalar_one())


async def create_customer(db: AsyncSession, engine: AuthzEngine, actor: Employee, payload: CustomerCreate) -> dict:
    if payload.account_owner_id:
        await _assert_active_employee(db, payload.account_owner_id, "account owner")

    customer = Customer(**payload.model_dump(), code=await project_repo.next_customer_code(db))
    db.add(customer)
    await db.flush()
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="create",
        entity_type="customer",
        entity_id=str(customer.id),
    )
    await db.commit()
    saved = await project_repo.get_customer(db, customer.id)
    return _serialize_customer(saved, await engine.get_all_permission_keys(actor))


async def update_customer(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
) -> dict:
    await assert_in_scope(
        db,
        engine,
        actor,
        feature=CUSTOMER_FEATURE,
        model=Customer,
        record_id=customer_id,
        scope_filter=apply_customer_scope,
        entity_label="Customer",
    )
    customer = await project_repo.get_customer(db, customer_id)
    if customer is None:
        raise NotFound("Customer not found")

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("account_owner_id"):
        await _assert_active_employee(db, changes["account_owner_id"], "account owner")
    if changes.get("status") == CustomerStatus.ARCHIVED:
        await _assert_no_open_projects(db, customer)

    for field, value in changes.items():
        setattr(customer, field, value)
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="update",
        entity_type="customer",
        entity_id=str(customer.id),
        diff=changes,
    )
    await db.commit()
    saved = await project_repo.get_customer(db, customer_id)
    return _serialize_customer(saved, await engine.get_all_permission_keys(actor))


async def _assert_no_open_projects(db: AsyncSession, customer: Customer) -> None:
    open_projects = await project_repo.open_projects_for_customer(db, customer.id)
    if open_projects:
        raise Conflict(
            f"'{customer.name}' still has {len(open_projects)} open project(s). Complete or archive them first.",
            {"projects": [{"id": str(p.id), "code": p.code, "name": p.name, "status": p.status.value} for p in open_projects]},
        )


async def archive_customer(db: AsyncSession, engine: AuthzEngine, actor: Employee, customer_id: uuid.UUID) -> dict:
    await assert_in_scope(
        db,
        engine,
        actor,
        feature=CUSTOMER_FEATURE,
        model=Customer,
        record_id=customer_id,
        scope_filter=apply_customer_scope,
        entity_label="Customer",
    )
    customer = await project_repo.get_customer(db, customer_id)
    if customer is None:
        raise NotFound("Customer not found")
    if customer.status == CustomerStatus.ARCHIVED:
        raise Conflict("Customer is already archived.")
    await _assert_no_open_projects(db, customer)

    customer.status = CustomerStatus.ARCHIVED
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="archive",
        entity_type="customer",
        entity_id=str(customer.id),
    )
    await db.commit()
    saved = await project_repo.get_customer(db, customer_id)
    return _serialize_customer(saved, await engine.get_all_permission_keys(actor))


# --------------------------------------------------------------------------- projects


async def list_projects(
    db: AsyncSession,
    engine: AuthzEngine,
    current_employee: Employee,
    *,
    offset: int,
    limit: int,
    search: str | None = None,
    status: ProjectStatus | None = None,
    customer_id: uuid.UUID | None = None,
    include_archived: bool = False,
):
    scope = await engine.get_scope(current_employee, PROJECT_FEATURE)
    permission_keys = await engine.get_all_permission_keys(current_employee)
    stmt = apply_project_scope(project_repo.projects_base_query(), scope, current_employee)
    stmt = await workflow_visibility(stmt, engine, current_employee)
    stmt = project_repo.apply_project_filters(
        stmt,
        search=search,
        status=status,
        customer_id=customer_id,
        include_archived=include_archived,
    )
    projects, total = await project_repo.list_paginated(db, stmt, offset=offset, limit=limit, order_by=Project.name)
    editor = await engine.has_permission(current_employee, PROJECT_FEATURE, Action.EDIT)
    approver = await engine.has_permission(current_employee, PROJECT_FEATURE, Action.APPROVE)
    return [
        _serialize_project(
            p, permission_keys, actor=current_employee, editor=editor, approver=approver, all_scope=scope == RecordScope.ALL
        )
        for p in projects
    ], total


async def get_project(db: AsyncSession, engine: AuthzEngine, current_employee: Employee, project_id: uuid.UUID) -> dict:
    # Without this the endpoint was an IDOR: an Employee scoped to "Assigned"
    # could read any project by guessing/knowing its id.
    await assert_in_scope(
        db,
        engine,
        current_employee,
        feature=PROJECT_FEATURE,
        model=Project,
        record_id=project_id,
        scope_filter=apply_project_scope,
        entity_label="Project",
    )
    stmt = await workflow_visibility(project_repo.projects_base_query().where(Project.id == project_id), engine, current_employee)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise NotFound("Project not found")
    headcount = await db.execute(
        select(func.count(func.distinct(Allocation.employee_id))).where(
            Allocation.project_id == project_id,
            Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES),
        )
    )
    return await serialize_for_actor(db, engine, current_employee, project, headcount.scalar_one())


async def create_project(db: AsyncSession, engine: AuthzEngine, actor: Employee, payload: ProjectCreate) -> dict:
    await _assert_customer_assignable(db, payload.customer_id)
    await _assert_active_employee(db, payload.project_manager_id, "project manager")
    if payload.delivery_manager_id:
        await _assert_active_employee(db, payload.delivery_manager_id, "delivery manager")

    # Manage-Assigned (a PM) may only create projects they will themselves manage —
    # otherwise the new row would land outside their own scope.
    scope = await engine.get_scope(actor, PROJECT_FEATURE)
    if scope != RecordScope.ALL and payload.project_manager_id != actor.id:
        raise ValidationFailed(
            "Your role can only create projects that you manage. Set yourself as the "
            "project manager, or ask a Delivery Manager to create it."
        )

    from hrms.services import project_approval_service as approvals

    if payload.status != ProjectStatus.PLANNED:
        raise ValidationFailed("New projects start as Planned. Activate them after approval.")
    direct = await engine.has_permission(actor, PROJECT_FEATURE, Action.FULL)
    project = Project(
        **payload.model_dump(),
        code=await project_repo.next_project_code(db),
        approval_status="approved" if direct else "draft",
        created_by_id=actor.id,
    )
    db.add(project)
    await db.flush()
    await approvals.new_request(db, project, actor, payload.model_dump(mode="json"), direct=direct)
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="create",
        entity_type="project",
        entity_id=str(project.id),
    )
    await db.commit()
    saved = await project_repo.get_project(db, project.id)
    return await serialize_for_actor(db, engine, actor, saved)


async def update_project(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    project_id: uuid.UUID,
    payload: ProjectUpdate,
) -> dict:
    from pydantic import ValidationError

    from hrms.services import project_approval_service as approvals

    project = await approvals.lock_project(db, project_id)
    await assert_project_writer(db, engine, actor, project)
    if project.status == ProjectStatus.ARCHIVED:
        raise Conflict("Archived projects cannot be edited.")
    request = approvals.latest_request(project)
    if request and request.status == "pending":
        raise Conflict("This project has a submitted request. Withdraw it before editing.")
    if project.approval_status == "rejected":
        raise Conflict("This project request was rejected. Create a new request.")
    changes = payload.model_dump(exclude_unset=True, mode="json")
    base = approvals.project_values(project)
    if request and request.kind == "amendment" and request.status in ("draft", "changes_requested"):
        if actor.id != request.requested_by_id:
            raise PermissionDenied("Only the amendment's author can edit its draft.")
        base.update(request.proposed)
    try:
        proposed = ProjectCreate.model_validate({**base, **changes})
    except ValidationError as exc:
        raise ValidationFailed("Check required project fields and the date range.") from exc
    await approvals.validate_proposal(db, proposed.model_dump(mode="json"))
    if project.approval_status != "approved" and proposed.status != ProjectStatus.PLANNED:
        raise ValidationFailed("A project must be approved before its delivery status can change.")
    if proposed.status == ProjectStatus.ARCHIVED:
        if request and request.status in approvals.OPEN_STATES:
            raise Conflict("Resolve the project approval request before archiving.")
        await _assert_no_active_allocations(db, project)
    if (await engine.get_scope(actor, PROJECT_FEATURE)) != RecordScope.ALL and proposed.project_manager_id != actor.id:
        raise ValidationFailed("Your role can only manage projects assigned to you.")
    material = any(
        field in changes and changes[field] != approvals.project_values(project)[field] for field in approvals.MATERIAL_FIELDS
    )
    if project.approval_status == "approved" and (material or (request and request.status in ("draft", "changes_requested"))):
        # Stage the amendment; never mutate live commercial/date/ownership values.
        if not request or request.status not in ("draft", "changes_requested"):
            request = await approvals.new_request(db, project, actor, proposed.model_dump(mode="json"))
        else:
            request.proposed = proposed.model_dump(mode="json")
            request.version += 1
        # Routine delivery information is independent of approval and may be updated.
        for field, value in proposed.model_dump().items():
            if field in changes and field not in approvals.MATERIAL_FIELDS:
                setattr(project, field, value)
        await approvals.event(db, request, actor, "draft_updated")
    else:
        for field, value in proposed.model_dump().items():
            setattr(project, field, value)
        if request and project.approval_status != "approved":
            request.proposed = proposed.model_dump(mode="json")
            request.version += 1
            await approvals.event(db, request, actor, "draft_updated")
    await record_audit(
        db, actor_id=actor.user_id, action="update", entity_type="project", entity_id=str(project.id), diff=changes
    )
    await db.commit()
    saved = await project_repo.get_project(db, project_id)
    return await serialize_for_actor(db, engine, actor, saved)


async def _assert_no_active_allocations(db: AsyncSession, project: Project) -> None:
    result = await db.execute(
        select(func.count())
        .select_from(Allocation)
        .where(
            Allocation.project_id == project.id,
            Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES),
        )
    )
    count = result.scalar_one()
    if count:
        raise Conflict(
            f"'{project.name}' still has {count} active allocation(s). Cancel or complete them before archiving.",
            {"active_allocations": count},
        )


async def archive_project(db: AsyncSession, engine: AuthzEngine, actor: Employee, project_id: uuid.UUID) -> dict:
    await assert_in_scope(
        db,
        engine,
        actor,
        feature=PROJECT_FEATURE,
        model=Project,
        record_id=project_id,
        scope_filter=apply_project_scope,
        entity_label="Project",
    )
    from hrms.services import project_approval_service as approvals

    project = await approvals.lock_project(db, project_id)
    await assert_project_writer(db, engine, actor, project)
    request = approvals.latest_request(project)
    if project.approval_status != "approved" or (request and request.status in approvals.OPEN_STATES):
        raise Conflict("Resolve the project approval request before archiving.")
    if project.status == ProjectStatus.ARCHIVED:
        raise Conflict("Project is already archived.")
    await _assert_no_active_allocations(db, project)

    project.status = ProjectStatus.ARCHIVED
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="archive",
        entity_type="project",
        entity_id=str(project.id),
    )
    await db.commit()
    saved = await project_repo.get_project(db, project_id)
    return await serialize_for_actor(db, engine, actor, saved)

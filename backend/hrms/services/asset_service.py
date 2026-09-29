from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import FeatureKey
from hrms.authz.scope_filters import apply_asset_assignment_scope
from hrms.core.audit import record_audit
from hrms.core.exceptions import NotFound, PermissionDenied
from hrms.models.asset import Asset, AssetAssignment
from hrms.models.employee import Employee
from hrms.models.enums import AssetStatus
from hrms.repositories import asset_repo
from hrms.schemas.asset import (
    AssetAssignIn,
    AssetAssignmentOut,
    AssetCreate,
    AssetOut,
    AssetReturnIn,
)

FEATURE = FeatureKey.ASSET_MANAGEMENT


async def list_assets(db: AsyncSession, *, offset: int, limit: int):
    stmt = asset_repo.assets_base_query()
    assets, total = await asset_repo.list_paginated(db, stmt, offset=offset, limit=limit, order_by=Asset.name)
    items = [AssetOut.model_validate(a).model_dump(mode="json") for a in assets]
    return items, total


async def create_asset(db: AsyncSession, actor: Employee, payload: AssetCreate) -> Asset:
    asset = Asset(**payload.model_dump())
    db.add(asset)
    await db.flush()
    await record_audit(db, actor_id=actor.user_id, action="create", entity_type="asset", entity_id=str(asset.id))
    await db.commit()
    await db.refresh(asset, attribute_names=["assignments"])
    return asset


async def assign_asset(db: AsyncSession, actor: Employee, asset_id: uuid.UUID, payload: AssetAssignIn) -> AssetAssignment:
    from hrms.services import onboarding_flow_service

    # Match the task endpoint's workflow -> asset lock order.
    await onboarding_flow_service._open_onboarding_record(db, payload.employee_id)
    asset = (await db.execute(select(Asset).where(Asset.id == asset_id).with_for_update())).scalar_one_or_none()
    if asset is None:
        raise NotFound("Asset not found")
    if asset.status != AssetStatus.IN_STOCK:
        raise PermissionDenied("Only assets in stock can be assigned.")

    assignment = AssetAssignment(
        asset_id=asset_id,
        employee_id=payload.employee_id,
        assigned_date=payload.assigned_date,
        condition_notes=payload.condition_notes,
    )
    asset.status = AssetStatus.ASSIGNED
    db.add(assignment)
    await db.flush()

    # If this employee has an open onboarding with an asset-allocation step,
    # this assignment completes it (and emails the next assignee). No-op otherwise.
    from hrms.models.enums import TaskActionType

    await onboarding_flow_service.auto_complete(
        db,
        employee_id=payload.employee_id,
        action_type=TaskActionType.ASSET_ASSIGNMENT,
        actor=actor,
        entity_type="asset_assignment",
        entity_id=assignment.id,
    )

    await record_audit(
        db,
        actor_id=actor.user_id,
        action="assign",
        entity_type="asset_assignment",
        entity_id=str(assignment.id),
    )
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def return_asset(db: AsyncSession, actor: Employee, assignment_id: uuid.UUID, payload: AssetReturnIn) -> AssetAssignment:
    assignment = await db.get(AssetAssignment, assignment_id)
    if assignment is None:
        raise NotFound("Assignment not found")
    assignment.returned_date = payload.returned_date
    if payload.condition_notes:
        assignment.condition_notes = payload.condition_notes

    asset = await asset_repo.get_asset(db, assignment.asset_id)
    asset.status = AssetStatus.IN_STOCK
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="return",
        entity_type="asset_assignment",
        entity_id=str(assignment.id),
    )
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def employee_asset_history(db: AsyncSession, engine: AuthzEngine, current_employee: Employee, employee_id: uuid.UUID):
    scope = await engine.get_scope(current_employee, FEATURE)
    stmt = apply_asset_assignment_scope(asset_repo.assignments_base_query(), scope, current_employee)
    stmt = stmt.where(AssetAssignment.employee_id == employee_id).order_by(AssetAssignment.assigned_date.desc())
    result = await db.execute(stmt)
    assignments = result.scalars().all()
    return [AssetAssignmentOut.model_validate(a).model_dump(mode="json") for a in assignments]

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_authz_engine, require_permission
from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey
from hrms.core.pagination import Page
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.schemas.asset import (
    AssetAssignIn,
    AssetAssignmentOut,
    AssetCreate,
    AssetOut,
    AssetReturnIn,
)
from hrms.services import asset_service

router = APIRouter(tags=["assets"])
FEATURE = FeatureKey.ASSET_MANAGEMENT


@router.get("/assets", response_model=Page)
async def list_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    items, total = await asset_service.list_assets(db, offset=(page - 1) * page_size, limit=page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/assets", response_model=AssetOut, status_code=201)
async def create_asset(
    payload: AssetCreate,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.CREATE)),
):
    return await asset_service.create_asset(db, current_employee, payload)


@router.post("/assets/{asset_id}/assign", response_model=AssetAssignmentOut, status_code=201)
async def assign_asset(
    asset_id: uuid.UUID,
    payload: AssetAssignIn,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.EDIT)),
):
    return await asset_service.assign_asset(db, current_employee, asset_id, payload)


@router.post("/asset-assignments/{assignment_id}/return", response_model=AssetAssignmentOut)
async def return_asset(
    assignment_id: uuid.UUID,
    payload: AssetReturnIn,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.EDIT)),
):
    return await asset_service.return_asset(db, current_employee, assignment_id, payload)


@router.get("/employees/{employee_id}/assets", response_model=list[AssetAssignmentOut])
async def employee_asset_history(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    return await asset_service.employee_asset_history(db, engine, current_employee, employee_id)

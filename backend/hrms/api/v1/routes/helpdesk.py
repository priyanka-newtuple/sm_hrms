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
from hrms.schemas.helpdesk import HelpdeskCategoryOut, TicketCreate, TicketOut, TicketUpdate
from hrms.services import helpdesk_service

router = APIRouter(prefix="/helpdesk", tags=["helpdesk"])
FEATURE = FeatureKey.HELP_DESK


@router.get("/categories", response_model=list[HelpdeskCategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    return await helpdesk_service.list_categories(db)


@router.get("/tickets", response_model=Page)
async def list_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.VIEW)),
):
    items, total = await helpdesk_service.list_tickets(
        db, engine, current_employee, offset=(page - 1) * page_size, limit=page_size
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/tickets", response_model=TicketOut, status_code=201)
async def create_ticket(
    payload: TicketCreate,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.CREATE)),
):
    return await helpdesk_service.create_ticket(db, current_employee, payload)


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(require_permission(FEATURE, Action.MANAGE)),
):
    return await helpdesk_service.update_ticket(db, current_employee, ticket_id, payload)

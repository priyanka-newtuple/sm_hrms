from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import FeatureKey
from hrms.authz.scope_filters import apply_helpdesk_scope
from hrms.core.audit import record_audit
from hrms.core.exceptions import NotFound
from hrms.models.employee import Employee
from hrms.models.enums import TicketStatus
from hrms.models.helpdesk import HelpdeskTicket
from hrms.repositories import helpdesk_repo
from hrms.schemas.helpdesk import TicketCreate, TicketOut, TicketUpdate

FEATURE = FeatureKey.HELP_DESK


async def list_tickets(db: AsyncSession, engine: AuthzEngine, current_employee: Employee, *, offset: int, limit: int):
    scope = await engine.get_scope(current_employee, FEATURE)
    stmt = apply_helpdesk_scope(helpdesk_repo.tickets_base_query(), scope, current_employee)
    tickets, total = await helpdesk_repo.list_paginated(db, stmt, offset=offset, limit=limit)
    items = [TicketOut.model_validate(t).model_dump(mode="json") for t in tickets]
    return items, total


async def list_categories(db: AsyncSession):
    return await helpdesk_repo.list_categories(db)


async def create_ticket(db: AsyncSession, actor: Employee, payload: TicketCreate) -> HelpdeskTicket:
    ticket = HelpdeskTicket(
        raised_by_id=actor.id,
        ticket_number=await helpdesk_repo.next_ticket_number(db),
        **payload.model_dump(),
    )
    db.add(ticket)
    await db.flush()
    await record_audit(db, actor_id=actor.user_id, action="create", entity_type="helpdesk_ticket", entity_id=str(ticket.id))
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def update_ticket(db: AsyncSession, actor: Employee, ticket_id: uuid.UUID, payload: TicketUpdate) -> HelpdeskTicket:
    ticket = await helpdesk_repo.get_ticket(db, ticket_id)
    if ticket is None:
        raise NotFound("Ticket not found")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(ticket, field, value)
    if changes.get("status") == TicketStatus.RESOLVED:
        ticket.resolved_at = datetime.now(UTC)
    if changes.get("assigned_to_id") and ticket.status == TicketStatus.OPEN:
        ticket.status = TicketStatus.ASSIGNED
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="update",
        entity_type="helpdesk_ticket",
        entity_id=str(ticket.id),
        diff=changes,
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket

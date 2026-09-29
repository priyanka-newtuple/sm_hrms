"""
Record-scope enforcement for single-record access.

`require_permission(feature, action)` in app/authz/deps.py answers "may this role
perform this action on this feature at all?" — it cannot answer "…on *this
particular record*?", because it never sees the record id. List endpoints get
that second half for free by running the query through a scope filter; single-record
GET / PATCH / archive endpoints do not, and must call into here explicitly.

Out-of-scope records raise 404, not 403: a Project Manager asking about another
manager's project should not be able to tell "exists but forbidden" apart from
"does not exist". Existing behaviour and tests rely on this (see
tests/test_api_permissions.py::test_employee_cannot_view_out_of_scope_colleague).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import FeatureKey, RecordScope
from hrms.authz.scope_filters import managed_project_ids_subquery
from hrms.core.exceptions import NotFound
from hrms.models.employee import Employee
from hrms.models.project import Project

ScopeFilter = Callable[[Select, RecordScope, Employee], Select]


async def assert_in_scope(
    db: AsyncSession,
    engine: AuthzEngine,
    current_employee: Employee,
    *,
    feature: FeatureKey,
    model,
    record_id: uuid.UUID,
    scope_filter: ScopeFilter,
    entity_label: str = "Record",
) -> None:
    """Raise NotFound unless `record_id` falls inside the caller's RecordScope."""
    scope = await engine.get_scope(current_employee, feature)
    stmt = scope_filter(select(model.id).where(model.id == record_id), scope, current_employee)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise NotFound(f"{entity_label} not found")


async def assert_project_writable(
    db: AsyncSession,
    engine: AuthzEngine,
    current_employee: Employee,
    *,
    feature: FeatureKey,
    project_id: uuid.UUID,
) -> None:
    """
    Write-scope check for records that hang off a project (allocations, timesheets).

    RecordScope is meaningless on CREATE — there is no row yet to scope against —
    but the project being *pointed at* must still be one the caller controls.
    Without this a Project Manager holding Manage-Assigned could allocate people
    onto a project managed by someone else simply by passing its id.
    """
    scope = await engine.get_scope(current_employee, feature)
    if scope == RecordScope.ALL:
        return
    if scope == RecordScope.NONE:
        raise NotFound("Project not found")

    managed = managed_project_ids_subquery(current_employee.id)
    result = await db.execute(select(Project.id).where(Project.id == project_id, Project.id.in_(managed)))
    if result.scalar_one_or_none() is None:
        raise NotFound("Project not found")

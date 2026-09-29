"""
Translates a RecordScope into a SQLAlchemy filter for a given feature's query.
Kept feature-specific (rather than one fully generic function) because "Self",
"Assigned", "Project Team" and "Team" each resolve differently depending on
which table is being queried — exactly the semantics documented per-feature
in the implementation plan.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, false, select
from sqlalchemy.sql import Selectable

from hrms.authz.enums import RecordScope
from hrms.models.allocation import Allocation
from hrms.models.asset import AssetAssignment
from hrms.models.employee import Employee
from hrms.models.helpdesk import HelpdeskTicket
from hrms.models.onboarding import OnboardingRecord
from hrms.models.project import Customer, Project
from hrms.models.timesheet import Timesheet


def managed_project_ids_subquery(manager_employee_id: uuid.UUID) -> Selectable:
    """Projects where the given employee is PM or Delivery Manager."""
    return select(Project.id).where(
        (Project.project_manager_id == manager_employee_id) | (Project.delivery_manager_id == manager_employee_id)
    )


def team_employee_ids_cte(root_employee_id: uuid.UUID):
    """Recursive CTE: root employee + everyone who reports to them, directly or indirectly."""
    base = select(Employee.id).where(Employee.id == root_employee_id).cte(name="team_ids", recursive=True)
    recursive = select(Employee.id).where(Employee.reports_to_id == base.c.id)
    return base.union_all(recursive)


def apply_employee_scope(stmt: Select, scope: RecordScope, current_employee: Employee) -> Select:
    """For Employee Directory / Onboarding / Offboarding feature queries against Employee rows."""
    if scope == RecordScope.ALL:
        return stmt
    if scope == RecordScope.NONE:
        return stmt.where(false())
    if scope in (RecordScope.SELF, RecordScope.ASSIGNED):
        return stmt.where(Employee.id == current_employee.id)
    if scope == RecordScope.TEAM:
        team_ids = team_employee_ids_cte(current_employee.id)
        return stmt.where(Employee.id.in_(select(team_ids.c.id)))
    if scope == RecordScope.PROJECT_TEAM:
        managed = managed_project_ids_subquery(current_employee.id)
        allocated_ids = select(Allocation.employee_id).where(Allocation.project_id.in_(managed))
        return stmt.where(Employee.id.in_(allocated_ids))
    return stmt.where(false())


def apply_onboarding_scope(stmt: Select, scope: RecordScope, current_employee: Employee) -> Select:
    if scope == RecordScope.ALL:
        return stmt
    if scope == RecordScope.NONE:
        return stmt.where(false())
    if scope in (RecordScope.SELF, RecordScope.ASSIGNED):
        return stmt.where(OnboardingRecord.employee_id == current_employee.id)
    if scope == RecordScope.TEAM:
        team_ids = team_employee_ids_cte(current_employee.id)
        return stmt.where(OnboardingRecord.employee_id.in_(select(team_ids.c.id)))
    if scope == RecordScope.PROJECT_TEAM:
        managed = managed_project_ids_subquery(current_employee.id)
        allocated_ids = select(Allocation.employee_id).where(Allocation.project_id.in_(managed))
        return stmt.where(OnboardingRecord.employee_id.in_(allocated_ids))
    return stmt.where(false())


def apply_project_scope(stmt: Select, scope: RecordScope, current_employee: Employee) -> Select:
    if scope == RecordScope.ALL:
        return stmt
    if scope == RecordScope.NONE:
        return stmt.where(false())
    # ASSIGNED covers both "projects I manage" (PM/DM) and "projects I'm allocated to"
    # (a plain Employee's "View - Assigned"). Self / Team / Project Team fall back here too.
    allocated_project_ids = select(Allocation.project_id).where(Allocation.employee_id == current_employee.id)
    return stmt.where(
        (Project.project_manager_id == current_employee.id)
        | (Project.delivery_manager_id == current_employee.id)
        | (Project.id.in_(allocated_project_ids))
    )


def apply_customer_scope(stmt: Select, scope: RecordScope, current_employee: Employee) -> Select:
    if scope == RecordScope.ALL:
        return stmt
    if scope == RecordScope.NONE:
        return stmt.where(false())
    managed = managed_project_ids_subquery(current_employee.id)
    customer_ids = select(Project.customer_id).where(Project.id.in_(managed))
    return stmt.where(Customer.id.in_(customer_ids))


def apply_allocation_scope(stmt: Select, scope: RecordScope, current_employee: Employee) -> Select:
    if scope == RecordScope.ALL:
        return stmt
    if scope == RecordScope.NONE:
        return stmt.where(false())
    if scope == RecordScope.SELF:
        return stmt.where(Allocation.employee_id == current_employee.id)
    if scope == RecordScope.ASSIGNED:
        managed = managed_project_ids_subquery(current_employee.id)
        return stmt.where(Allocation.project_id.in_(managed))
    return stmt.where(Allocation.employee_id == current_employee.id)


def apply_timesheet_scope(stmt: Select, scope: RecordScope, current_employee: Employee) -> Select:
    if scope == RecordScope.ALL:
        return stmt
    if scope == RecordScope.NONE:
        return stmt.where(false())
    if scope == RecordScope.SELF:
        return stmt.where(Timesheet.employee_id == current_employee.id)
    if scope == RecordScope.ASSIGNED:
        managed = managed_project_ids_subquery(current_employee.id)
        return stmt.where(Timesheet.project_id.in_(managed))
    if scope == RecordScope.PROJECT_TEAM:
        managed = managed_project_ids_subquery(current_employee.id)
        return stmt.where(Timesheet.project_id.in_(managed))
    return stmt.where(Timesheet.employee_id == current_employee.id)


def apply_asset_assignment_scope(stmt: Select, scope: RecordScope, current_employee: Employee) -> Select:
    """For an employee's own asset history / "View - Own"."""
    if scope == RecordScope.ALL:
        return stmt
    if scope == RecordScope.NONE:
        return stmt.where(false())
    if scope == RecordScope.SELF:
        return stmt.where(AssetAssignment.employee_id == current_employee.id)
    if scope == RecordScope.PROJECT_TEAM:
        managed = managed_project_ids_subquery(current_employee.id)
        allocated_ids = select(Allocation.employee_id).where(Allocation.project_id.in_(managed))
        return stmt.where(AssetAssignment.employee_id.in_(allocated_ids))
    return stmt.where(AssetAssignment.employee_id == current_employee.id)


def apply_helpdesk_scope(stmt: Select, scope: RecordScope, current_employee: Employee) -> Select:
    if scope == RecordScope.ALL:
        return stmt
    if scope == RecordScope.NONE:
        return stmt.where(false())
    if scope == RecordScope.SELF:
        return stmt.where(HelpdeskTicket.raised_by_id == current_employee.id)
    # "Relevant" in the matrix -> tickets the employee raised or is assigned to.
    return stmt.where(
        (HelpdeskTicket.raised_by_id == current_employee.id) | (HelpdeskTicket.assigned_to_id == current_employee.id)
    )

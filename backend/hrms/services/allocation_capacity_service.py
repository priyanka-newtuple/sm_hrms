"""Date-aware staffing summaries. No commercial or employee-private fields."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from hrms.models.allocation import Allocation
from hrms.models.employee import Employee
from hrms.models.enums import COMMITTED_ALLOCATION_STATUSES, EmploymentStatus
from hrms.models.project import Project
from hrms.models.role import Role
from hrms.repositories import allocation_repo
from hrms.services.notification_service import queue_email


def timeline(rows, start, end=None, proposed=0):
    stop = end or date.max
    events = {start: Decimal(str(proposed))}
    for row in rows:
        if row.status not in COMMITTED_ALLOCATION_STATUSES:
            continue
        lo, hi = max(start, row.start_date), min(stop, row.end_date or date.max)
        if lo > hi:
            continue
        pct = Decimal(str(row.allocation_percent))
        events[lo] = events.get(lo, Decimal(0)) + pct
        if hi < stop:
            after = hi + timedelta(days=1)
            events[after] = events.get(after, Decimal(0)) - pct
    points = sorted(events)
    total = Decimal(0)
    periods = []
    for i, point in enumerate(points):
        total += events[point]
        last = points[i + 1] - timedelta(days=1) if i + 1 < len(points) else stop
        entry = dict(
            start_date=point.isoformat(),
            end_date=last.isoformat() if last != date.max else None,
            total_allocation_percent=float(total),
            excess_percent=float(max(Decimal(0), total - 100)),
        )
        if periods and periods[-1]["total_allocation_percent"] == float(total):
            periods[-1]["end_date"] = entry["end_date"]
        else:
            periods.append(entry)
    return periods


async def employee_rows(db, employee_id):
    return list(
        (
            await db.execute(
                allocation_repo.base_query()
                .where(Allocation.employee_id == employee_id)
                .options(selectinload(Allocation.project).selectinload(Project.project_manager))
                .order_by(Allocation.start_date)
            )
        ).scalars()
    )


def summary(rows, start, end=None, proposed=0):
    periods = timeline(rows, start, end, proposed)
    return dict(
        total_allocation_percent=max((p["total_allocation_percent"] for p in periods), default=0),
        over_allocated=any(p["excess_percent"] > 0 for p in periods),
        periods=periods,
        overallocated_periods=[p for p in periods if p["excess_percent"] > 0],
    )


def staffing_row(row, rows):
    capacity = summary(rows, row.start_date, row.end_date) if row.status in COMMITTED_ALLOCATION_STATUSES else {}
    return dict(
        allocation_id=str(row.id),
        project_name=row.project.name,
        manager_name=row.project.project_manager.full_name if row.project.project_manager else "Unassigned",
        allocation_percent=float(row.allocation_percent),
        start_date=row.start_date.isoformat(),
        end_date=row.end_date.isoformat() if row.end_date else None,
        status=row.status.value,
        over_allocated=capacity.get("over_allocated", False),
        total_allocation_percent=capacity.get("total_allocation_percent", 0),
        overallocated_periods=capacity.get("overallocated_periods", []),
    )


async def annotate(db, allocations, serialize):
    if not allocations:
        return []
    all_rows = list(
        (
            await db.execute(
                allocation_repo.base_query().where(
                    Allocation.employee_id.in_({a.employee_id for a in allocations}),
                    Allocation.status.in_(COMMITTED_ALLOCATION_STATUSES),
                )
            )
        ).scalars()
    )
    grouped = {}
    for row in all_rows:
        grouped.setdefault(row.employee_id, []).append(row)
    result = []
    for allocation in allocations:
        item = serialize(allocation)
        capacity = summary(grouped.get(allocation.employee_id, []), allocation.start_date, allocation.end_date)
        if allocation.status not in COMMITTED_ALLOCATION_STATUSES:
            capacity = dict(over_allocated=False, total_allocation_percent=0, overallocated_periods=[])
        item.update({key: capacity[key] for key in ("over_allocated", "total_allocation_percent", "overallocated_periods")})
        result.append(item)
    return result


async def notify_overallocation(db, actor, allocation, reason, capacity):
    rows = await employee_rows(db, allocation.employee_id)
    employee = await db.get(Employee, allocation.employee_id)
    recipients = list(
        (
            await db.execute(
                select(Employee)
                .join(Role, Employee.role_id == Role.id)
                .where(
                    Employee.employment_status == EmploymentStatus.ACTIVE,
                    Role.name.in_(["HR - Full", "HR - Basic", "Super Admin"]),
                )
            )
        ).scalars()
    ) + [actor]
    periods = "\n".join(
        f"{p['start_date']} to {p['end_date'] or 'ongoing'}: {p['total_allocation_percent']:g}% "
        f"({p['excess_percent']:g}% above capacity)"
        for p in capacity["overallocated_periods"]
    )
    breakdown = "\n".join(
        f"{r.project.name}: {float(r.allocation_percent):g}% | {r.start_date} to {r.end_date or 'ongoing'}"
        for r in rows
        if r.status in COMMITTED_ALLOCATION_STATUSES
    )
    seen = set()
    for recipient in recipients:
        email = recipient.work_email.strip().lower()
        if email in seen:
            continue
        seen.add(email)
        queue_email(
            db,
            email_to=recipient.work_email,
            recipient_employee_id=recipient.id,
            template_key="allocation_overcapacity",
            payload=dict(
                employee_name=employee.full_name,
                actor_name=actor.full_name,
                reason=reason,
                periods=periods,
                breakdown=breakdown,
                allocation_id=str(allocation.id),
            ),
        )

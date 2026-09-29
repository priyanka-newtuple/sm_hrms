"""
Seeds roles + the full permission matrix (verbatim from the spreadsheet), plus
realistic sample data across every module so the prototype is usable
immediately after `docker compose up`.

Run with:  python -m app.seed.seed_data
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from hrms.authz.enums import RoleName
from hrms.database import AsyncSessionLocal, Base, engine
from hrms.models.allocation import Allocation
from hrms.models.asset import Asset, AssetAssignment
from hrms.models.employee import Employee
from hrms.models.enums import (
    AllocationStatus,
    ApprovalAction,
    AssetStatus,
    CustomerStatus,
    EmploymentType,
    EngagementType,
    OnboardingStatus,
    OnboardingType,
    ProjectHealth,
    ProjectStatus,
    TicketPriority,
    TicketStatus,
    TimesheetStatus,
)
from hrms.models.helpdesk import HelpdeskCategory, HelpdeskTicket
from hrms.models.onboarding import OnboardingRecord, OnboardingTask
from hrms.models.project import Customer, Project
from hrms.models.role import Role, RoleFeaturePermission, RolePermissionKey
from hrms.models.timesheet import Timesheet, TimesheetApproval
from hrms.models.user import User
from hrms.seed.permission_matrix import (
    FEATURE_PERMISSIONS,
    ROLE_DESCRIPTIONS,
    ROLE_PERMISSION_KEYS,
)

random.seed(42)


async def seed_roles_and_permissions(db) -> dict[RoleName, Role]:
    existing_roles = {
        role.name: role for role in (await db.execute(select(Role))).scalars().all()
    }
    roles: dict[RoleName, Role] = {}
    for role_name in RoleName:
        role = existing_roles.get(role_name.value)
        if role is None:
            role = Role(name=role_name.value, description=ROLE_DESCRIPTIONS[role_name])
            db.add(role)
        roles[role_name] = role
    await db.flush()

    existing_features = {
        (row.role_id, row.feature_key)
        for row in (await db.execute(select(RoleFeaturePermission))).scalars().all()
    }
    existing_keys = {
        (row.role_id, row.permission_key)
        for row in (await db.execute(select(RolePermissionKey))).scalars().all()
    }

    for role_name, feature_map in FEATURE_PERMISSIONS.items():
        role = roles[role_name]
        for feature_key, (actions, scope, profile) in feature_map.items():
            if (role.id, feature_key) in existing_features:
                continue
            db.add(
                RoleFeaturePermission(
                    role_id=role.id,
                    feature_key=feature_key,
                    actions=actions,
                    record_scope=scope,
                    data_profile=profile,
                )
            )

    for role_name, keys in ROLE_PERMISSION_KEYS.items():
        role = roles[role_name]
        for key in keys:
            if (role.id, key) in existing_keys:
                continue
            db.add(RolePermissionKey(role_id=role.id, permission_key=key))

    await db.flush()
    return roles


async def make_employee(
    db,
    *,
    first: str,
    last: str,
    role: Role,
    department: str,
    designation: str,
    reports_to: Employee | None,
    code_n: int,
    days_ago_joined: int,
    cost_rate: float | None = None,
    salary: float | None = None,
) -> Employee:
    email = f"{first.lower()}.{last.lower()}@newtuple.com"
    user = User(email=email)
    db.add(user)
    await db.flush()

    employee = Employee(
        user_id=user.id,
        role_id=role.id,
        reports_to_id=reports_to.id if reports_to else None,
        employee_code=f"NT{code_n:04d}",
        first_name=first,
        last_name=last,
        work_email=email,
        department=department,
        designation=designation,
        date_joined=date.today() - timedelta(days=days_ago_joined),
        employment_type=EmploymentType.FULL_TIME,
        work_location=random.choice(["Bengaluru HQ", "Remote - India", "Pune Office"]),
        probation_end_date=date.today() - timedelta(days=days_ago_joined) + timedelta(days=180),
        confirmation_date=(
            date.today() - timedelta(days=days_ago_joined) + timedelta(days=180) if days_ago_joined > 180 else None
        ),
        notice_period_days=random.choice([30, 60, 90]),
        phone=f"+91-9{random.randint(100000000, 999999999)}",
        skills=random.choice(["Python, React", "Node.js, AWS", "Product Strategy", "QA Automation", "DevOps, Kubernetes"]),
        personal_email=f"{first.lower()}.{last.lower()}.personal@gmail.com",
        date_of_birth=date(1985 + code_n % 15, (code_n % 12) + 1, (code_n % 27) + 1),
        address=f"{100 + code_n} MG Road, Bengaluru, India",
        salary_ctc=salary,
        bank_account_number=f"5021{code_n:08d}",
        bank_ifsc="HDFC0001234",
        employee_cost_rate=cost_rate,
    )
    db.add(employee)
    await db.flush()
    return employee


async def seed_employees(db, roles: dict[RoleName, Role]) -> dict[str, Employee]:
    from hrms.services.reference_data_service import ensure_reference_data

    await ensure_reference_data(db)
    emp: dict[str, Employee] = {}

    emp["super_admin"] = await make_employee(
        db,
        first="Ananya",
        last="Rao",
        role=roles[RoleName.SUPER_ADMIN],
        department="Leadership",
        designation="Chief Executive Officer",
        reports_to=None,
        code_n=1,
        days_ago_joined=2000,
        cost_rate=250000,
        salary=6000000,
    )
    emp["hr_full"] = await make_employee(
        db,
        first="Kavya",
        last="Menon",
        role=roles[RoleName.HR_FULL],
        department="Human Resources",
        designation="Head of HR",
        reports_to=emp["super_admin"],
        code_n=2,
        days_ago_joined=1500,
        cost_rate=90000,
        salary=2400000,
    )
    emp["hr_basic"] = await make_employee(
        db,
        first="Rohit",
        last="Sharma",
        role=roles[RoleName.HR_BASIC],
        department="Human Resources",
        designation="HR Executive",
        reports_to=emp["hr_full"],
        code_n=3,
        days_ago_joined=900,
        cost_rate=45000,
        salary=900000,
    )
    emp["recruiter"] = await make_employee(
        db,
        first="Rhea",
        last="Kapoor",
        role=roles[RoleName.RECRUITER],
        department="Human Resources",
        designation="Talent Acquisition Specialist",
        reports_to=emp["hr_full"],
        code_n=99,
        days_ago_joined=420,
        cost_rate=50000,
        salary=1100000,
    )
    emp["delivery_manager"] = await make_employee(
        db,
        first="Vikram",
        last="Iyer",
        role=roles[RoleName.DELIVERY_MANAGER],
        department="Delivery",
        designation="Delivery Manager",
        reports_to=emp["super_admin"],
        code_n=4,
        days_ago_joined=1800,
        cost_rate=120000,
        salary=3200000,
    )
    emp["finance"] = await make_employee(
        db,
        first="Neha",
        last="Gupta",
        role=roles[RoleName.FINANCE],
        department="Finance",
        designation="Finance Manager",
        reports_to=emp["super_admin"],
        code_n=5,
        days_ago_joined=1600,
        cost_rate=95000,
        salary=2600000,
    )
    emp["office_admin"] = await make_employee(
        db,
        first="Suresh",
        last="Nair",
        role=roles[RoleName.OFFICE_ADMIN],
        department="Administration",
        designation="Office Administrator",
        reports_to=emp["super_admin"],
        code_n=6,
        days_ago_joined=1200,
        cost_rate=40000,
        salary=750000,
    )
    emp["pm1"] = await make_employee(
        db,
        first="Priya",
        last="Desai",
        role=roles[RoleName.PROJECT_MANAGER],
        department="Delivery",
        designation="Project Manager",
        reports_to=emp["delivery_manager"],
        code_n=7,
        days_ago_joined=1100,
        cost_rate=85000,
        salary=2100000,
    )
    emp["pm2"] = await make_employee(
        db,
        first="Arjun",
        last="Kulkarni",
        role=roles[RoleName.PROJECT_MANAGER],
        department="Delivery",
        designation="Project Manager",
        reports_to=emp["delivery_manager"],
        code_n=8,
        days_ago_joined=950,
        cost_rate=85000,
        salary=2100000,
    )

    engineer_names = [
        ("Sanjay", "Bhat"),
        ("Meera", "Pillai"),
        ("Aditya", "Reddy"),
        ("Divya", "Krishnan"),
        ("Karan", "Malhotra"),
        ("Pooja", "Joshi"),
        ("Rahul", "Verma"),
        ("Sneha", "Chatterjee"),
        ("Amit", "Singh"),
        ("Ritu", "Agarwal"),
        ("Varun", "Kapoor"),
        ("Anjali", "Nambiar"),
        ("Deepak", "Choudhary"),
        ("Lakshmi", "Venkatesh"),
        ("Nikhil", "Bose"),
        ("Swati", "Mehta"),
        ("Manoj", "Pandey"),
    ]
    designations = ["Software Engineer", "Senior Software Engineer", "QA Engineer", "DevOps Engineer"]
    managers = [emp["pm1"], emp["pm2"]]
    for i, (first, last) in enumerate(engineer_names, start=9):
        emp[f"eng_{i}"] = await make_employee(
            db,
            first=first,
            last=last,
            role=roles[RoleName.EMPLOYEE],
            department="Engineering",
            designation=random.choice(designations),
            reports_to=managers[i % 2],
            code_n=i,
            days_ago_joined=random.randint(60, 1400),
            cost_rate=random.choice([35000, 45000, 55000, 65000]),
            salary=random.choice([700000, 950000, 1300000, 1700000]),
        )

    await db.flush()
    return emp


async def seed_projects(db, emp: dict[str, Employee]) -> tuple[list[Customer], list[Project]]:
    customers_data = [
        ("Orion Retail Group", "Retail", "Grace Liu", "grace.liu@orionretail.com", 4_500_000),
        ("Vertex Financial Services", "Financial Services", "Marcus Webb", "marcus.webb@vertexfs.com", 8_200_000),
        ("Helio Health Systems", "Healthcare", "Dr. Sara Ahmed", "sara.ahmed@heliohealth.com", 3_100_000),
    ]
    customers = []
    for i, (name, industry, contact_name, contact_email, contract_value) in enumerate(customers_data, start=1):
        c = Customer(
            code=f"CUS-{i:04d}",
            name=name,
            status=CustomerStatus.ACTIVE,
            industry=industry,
            contact_name=contact_name,
            contact_email=contact_email,
            contract_value=contract_value,
            account_owner_id=emp["delivery_manager"].id,
            contract_start_date=date.today() - timedelta(days=400),
            contract_end_date=date.today() + timedelta(days=365),
            currency="INR",
            payment_terms_days=45,
            country="India",
            billing_address=f"{name} Finance Dept, Bengaluru, India",
        )
        db.add(c)
        customers.append(c)
    await db.flush()

    projects_data = [
        ("Orion Storefront Modernization", customers[0], emp["pm1"], 180, 12000, 4_500_000 * 0.4, 28.5),
        ("Orion Inventory AI Agent", customers[0], emp["pm2"], 90, 14500, 1_800_000, 32.0),
        ("Vertex Core Banking Migration", customers[1], emp["pm2"], 240, 18000, 8_200_000 * 0.5, 24.0),
        ("Vertex Risk Dashboard", customers[1], emp["pm1"], 60, 16000, 2_400_000, 30.0),
        ("Helio Patient Portal Revamp", customers[2], emp["pm1"], 120, 13000, 3_100_000 * 0.45, 26.5),
    ]
    engagement_cycle = [
        EngagementType.TIME_AND_MATERIALS,
        EngagementType.FIXED_BID,
        EngagementType.RETAINER,
    ]
    projects = []
    for i, (name, customer, pm, days_ago_start, billing_rate, revenue, margin) in enumerate(projects_data, start=1):
        p = Project(
            code=f"PRJ-{i:04d}",
            name=name,
            customer_id=customer.id,
            project_manager_id=pm.id,
            delivery_manager_id=emp["delivery_manager"].id,
            status=ProjectStatus.ACTIVE,
            start_date=date.today() - timedelta(days=days_ago_start),
            billing_rate=billing_rate,
            revenue=revenue,
            margin_percent=margin,
            budget_amount=float(revenue) * 0.75,
            budgeted_hours=random.choice([1200, 2400, 4000]),
            engagement_type=engagement_cycle[i % len(engagement_cycle)],
            health=random.choice([ProjectHealth.GREEN, ProjectHealth.GREEN, ProjectHealth.AMBER]),
            currency="INR",
            practice=random.choice(["Data & AI", "Cloud Engineering", "Product Engineering"]),
            description=f"Engagement with {customer.name}.",
        )
        db.add(p)
        projects.append(p)
    await db.flush()
    return customers, projects


async def seed_allocations(db, emp: dict[str, Employee], projects: list[Project]) -> None:
    engineers = [v for k, v in emp.items() if k.startswith("eng_")]
    for i, engineer in enumerate(engineers):
        project = projects[i % len(projects)]
        # Keep seeded engineers at or under 100% so the capacity warning only
        # fires on allocations a user actually creates.
        primary_percent = 75 if i % 5 == 0 else random.choice([50, 75, 100])
        db.add(
            Allocation(
                employee_id=engineer.id,
                project_id=project.id,
                allocation_percent=primary_percent,
                role_on_project=random.choice(["Developer", "QA", "Tech Lead"]),
                start_date=project.start_date,
                status=AllocationStatus.ACTIVE,
                billable=True,
                allocated_by_id=emp["delivery_manager"].id,
            )
        )
        # A few engineers split time across two projects (75 + 25 = 100%).
        if i % 5 == 0:
            second_project = projects[(i + 1) % len(projects)]
            db.add(
                Allocation(
                    employee_id=engineer.id,
                    project_id=second_project.id,
                    allocation_percent=25,
                    role_on_project="Developer",
                    start_date=second_project.start_date,
                    status=AllocationStatus.ACTIVE,
                    billable=True,
                    allocated_by_id=emp["delivery_manager"].id,
                )
            )
    await db.flush()


async def seed_timesheets(db, emp: dict[str, Employee], projects: list[Project]) -> None:
    engineers = [v for k, v in emp.items() if k.startswith("eng_")]
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())

    for i, engineer in enumerate(engineers[:12]):
        project = projects[i % len(projects)]
        for week_offset in range(3, 0, -1):
            week_start = this_monday - timedelta(weeks=week_offset)
            status = random.choice([TimesheetStatus.APPROVED, TimesheetStatus.APPROVED, TimesheetStatus.SUBMITTED])
            ts = Timesheet(
                employee_id=engineer.id,
                project_id=project.id,
                week_start_date=week_start,
                hours=random.choice([35, 38, 40, 42]),
                status=status,
                submitted_at=datetime.now(UTC) - timedelta(weeks=week_offset),
            )
            db.add(ts)
            await db.flush()
            if status == TimesheetStatus.APPROVED:
                approver = emp["pm1"] if project.project_manager_id == emp["pm1"].id else emp["pm2"]
                db.add(
                    TimesheetApproval(
                        timesheet_id=ts.id,
                        approver_id=approver.id,
                        action=ApprovalAction.APPROVE,
                        comment="Looks good.",
                    )
                )
        # This week: draft, not yet submitted.
        db.add(
            Timesheet(
                employee_id=engineer.id,
                project_id=project.id,
                week_start_date=this_monday,
                hours=random.choice([20, 24, 30]),
                status=TimesheetStatus.DRAFT,
            )
        )
    await db.flush()


async def seed_assets(db, emp: dict[str, Employee]) -> None:
    asset_types = [
        ("Laptop", "Dell Latitude 5440"),
        ("Laptop", "MacBook Pro 14"),
        ("Monitor", "Dell 24-inch"),
        ("Phone", "iPhone 13"),
        ("Headset", "Jabra Evolve2"),
    ]
    engineers = [v for k, v in emp.items() if k.startswith("eng_")]
    n = 1
    for engineer in engineers:
        asset_type, name = random.choice(asset_types)
        asset = Asset(
            asset_tag=f"AST-{n:04d}",
            name=name,
            asset_type=asset_type,
            serial_number=f"SN{uuid.uuid4().hex[:10].upper()}",
            status=AssetStatus.ASSIGNED,
            purchase_date=date.today() - timedelta(days=random.randint(100, 900)),
        )
        db.add(asset)
        await db.flush()
        db.add(
            AssetAssignment(
                asset_id=asset.id,
                employee_id=engineer.id,
                assigned_date=engineer.date_joined,
            )
        )
        n += 1

    # A handful of unassigned stock + one returned history.
    for asset_type, name in asset_types:
        db.add(
            Asset(
                asset_tag=f"AST-{n:04d}",
                name=name,
                asset_type=asset_type,
                serial_number=f"SN{uuid.uuid4().hex[:10].upper()}",
                status=AssetStatus.IN_STOCK,
                purchase_date=date.today() - timedelta(days=random.randint(30, 400)),
            )
        )
        n += 1

    returned_asset = Asset(
        asset_tag=f"AST-{n:04d}",
        name="Dell Latitude 5440",
        asset_type="Laptop",
        serial_number=f"SN{uuid.uuid4().hex[:10].upper()}",
        status=AssetStatus.IN_STOCK,
        purchase_date=date.today() - timedelta(days=600),
    )
    db.add(returned_asset)
    await db.flush()
    db.add(
        AssetAssignment(
            asset_id=returned_asset.id,
            employee_id=engineers[0].id,
            assigned_date=date.today() - timedelta(days=500),
            returned_date=date.today() - timedelta(days=200),
            condition_notes="Returned in good condition on team transfer.",
        )
    )
    await db.flush()


async def seed_helpdesk(db, emp: dict[str, Employee]) -> None:
    categories_data = [("Payroll Query", "Finance"), ("IT Support", "IT"), ("Facilities", "Admin"), ("Onboarding Support", "HR")]
    categories = []
    for name, department in categories_data:
        c = HelpdeskCategory(name=name, department=department)
        db.add(c)
        categories.append(c)
    await db.flush()

    engineers = [v for k, v in emp.items() if k.startswith("eng_")]
    tickets_data = [
        (categories[1], "Laptop won't connect to VPN", TicketPriority.HIGH, TicketStatus.IN_PROGRESS, emp["office_admin"]),
        (categories[0], "Payslip discrepancy for last month", TicketPriority.MEDIUM, TicketStatus.OPEN, None),
        (categories[2], "AC not working on 3rd floor", TicketPriority.MEDIUM, TicketStatus.RESOLVED, emp["office_admin"]),
        (categories[1], "Need second monitor", TicketPriority.LOW, TicketStatus.ASSIGNED, emp["office_admin"]),
        (categories[3], "Access badge not issued yet", TicketPriority.HIGH, TicketStatus.OPEN, None),
        (categories[0], "Reimbursement pending approval", TicketPriority.MEDIUM, TicketStatus.CLOSED, emp["finance"]),
    ]
    for i, (category, subject, priority, status, assignee) in enumerate(tickets_data):
        db.add(
            HelpdeskTicket(
                ticket_number=f"HD-{i + 1:05d}",
                category_id=category.id,
                raised_by_id=engineers[i % len(engineers)].id,
                assigned_to_id=assignee.id if assignee else None,
                subject=subject,
                description=f"{subject}. Raised via HRMS Help Desk.",
                priority=priority,
                status=status,
                resolved_at=datetime.now(UTC) if status in (TicketStatus.RESOLVED, TicketStatus.CLOSED) else None,
            )
        )
    await db.flush()


async def seed_onboarding(db, emp: dict[str, Employee]) -> None:
    """Two in-flight template-driven onboardings so the pipeline board, my-actions
    queue and handoff emails are demonstrable immediately after seeding."""
    from hrms.services import onboarding_flow_service
    from hrms.workflows.native import DEFAULT_ONBOARDING_TASKS

    await onboarding_flow_service.ensure_default_template(db)

    engineers = [v for k, v in emp.items() if k.startswith("eng_")]
    newest_two = sorted(engineers, key=lambda e: e.date_joined, reverse=True)[:2]
    for i, engineer in enumerate(newest_two):
        record = OnboardingRecord(
            employee_id=engineer.id,
            workflow_type=OnboardingType.ONBOARDING,
            status=OnboardingStatus.IN_PROGRESS,
            started_at=datetime.now(UTC) - timedelta(days=3),
        )
        db.add(record)
        await db.flush()
        stamped = await onboarding_flow_service.stamp_template(db, record, engineer)
        if not stamped:  # template missing (shouldn't happen) — legacy checklist
            for j, title in enumerate(DEFAULT_ONBOARDING_TASKS):
                db.add(OnboardingTask(onboarding_record_id=record.id, title=title, is_complete=j < 2))
            continue
        # Move the first hire a few steps along: Newtuple ID done → invitation
        # auto-sent → profile/documents now waiting on the new hire.
        if i == 0:
            task1 = next(t for t in record.tasks if t.seq == 1)
            await onboarding_flow_service.complete_task(
                db, record, task1, actor=emp["office_admin"], note="Workspace account created"
            )
    await db.flush()


async def main() -> None:
    # Schema is owned by Alembic, not a silent runtime create_all.

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Employee))
        if existing.scalars().first() is not None:
            print("Seed data already present — skipping.")
            return

        roles = await seed_roles_and_permissions(db)
        emp = await seed_employees(db, roles)
        customers, projects = await seed_projects(db, emp)
        await seed_allocations(db, emp, projects)
        await seed_timesheets(db, emp, projects)
        await seed_assets(db, emp)
        await seed_helpdesk(db, emp)
        await seed_onboarding(db, emp)
        await db.commit()

    print(f"Seeded {len(RoleName)} roles and sample data across all modules.")
    print("Dev-login as any seeded user via POST /api/v1/auth/dev-login, e.g.:")
    print('  {"email": "ananya.rao@newtuple.com"}   -> Super Admin')
    print('  {"email": "sanjay.bhat@newtuple.com"}  -> Employee')


if __name__ == "__main__":
    asyncio.run(main())

"""Idempotently create clearly marked demo employees for every production role."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from hrms.authz.enums import RoleName
from hrms.database import AsyncSessionLocal
from hrms.models.employee import Employee
from hrms.models.enums import EmploymentType
from hrms.models.role import Role
from hrms.models.user import User
from hrms.seed.production_data import sync_roles_and_permissions
from hrms.services.reference_data_service import ensure_reference_data


@dataclass(frozen=True)
class DemoPersona:
    role: RoleName
    email: str
    employee_code: str
    first_name: str
    last_name: str
    department: str
    designation: str
    manager_role: RoleName | None


DEMO_PERSONAS = (
    DemoPersona(RoleName.SUPER_ADMIN, "demo.superadmin@newtuple.com", "DEMO0001", "Demo", "Superadmin", "Leadership", "Chief Executive Officer", None),
    DemoPersona(RoleName.HR_FULL, "demo.hrfull@newtuple.com", "DEMO0002", "Demo", "HR Full", "Human Resources", "Head of HR", RoleName.SUPER_ADMIN),
    DemoPersona(RoleName.HR_BASIC, "demo.hrbasic@newtuple.com", "DEMO0003", "Demo", "HR Basic", "Human Resources", "HR Executive", RoleName.HR_FULL),
    DemoPersona(RoleName.RECRUITER, "demo.recruiter@newtuple.com", "DEMO0004", "Demo", "Recruiter", "Human Resources", "Talent Acquisition Specialist", RoleName.HR_FULL),
    DemoPersona(RoleName.DELIVERY_MANAGER, "demo.deliverymanager@newtuple.com", "DEMO0005", "Demo", "Delivery Manager", "Delivery", "Delivery Manager", RoleName.SUPER_ADMIN),
    DemoPersona(RoleName.PROJECT_MANAGER, "demo.projectmanager@newtuple.com", "DEMO0006", "Demo", "Project Manager", "Delivery", "Project Manager", RoleName.DELIVERY_MANAGER),
    DemoPersona(RoleName.FINANCE, "demo.finance@newtuple.com", "DEMO0007", "Demo", "Finance", "Finance", "Finance Manager", RoleName.SUPER_ADMIN),
    DemoPersona(RoleName.OFFICE_ADMIN, "demo.officeadmin@newtuple.com", "DEMO0008", "Demo", "Office Admin", "Administration", "Office Administrator", RoleName.SUPER_ADMIN),
    DemoPersona(RoleName.EMPLOYEE, "demo.employee@newtuple.com", "DEMO0009", "Demo", "Employee", "Engineering", "Software Engineer", RoleName.PROJECT_MANAGER),
)
DEMO_EMAILS = frozenset(persona.email for persona in DEMO_PERSONAS)


async def ensure_production_demo_employees(db, roles: dict[RoleName, Role]) -> list[Employee]:
    """Upsert only the records owned by this demo seed and preserve their IDs."""
    employees_by_role: dict[RoleName, Employee] = {}
    employees: list[Employee] = []

    for persona in DEMO_PERSONAS:
        user = (await db.execute(select(User).where(User.email == persona.email))).scalar_one_or_none()
        if user is None:
            user = User(email=persona.email, is_active=True)
            db.add(user)
            await db.flush()
        else:
            user.is_active = True

        employee = (await db.execute(select(Employee).where(Employee.user_id == user.id))).scalar_one_or_none()
        manager = employees_by_role.get(persona.manager_role) if persona.manager_role else None
        if employee is None:
            employee = Employee(
                user_id=user.id,
                role_id=roles[persona.role].id,
                employee_code=persona.employee_code,
                first_name=persona.first_name,
                last_name=persona.last_name,
                work_email=persona.email,
                department=persona.department,
                designation=persona.designation,
                date_joined=date(2025, 1, 6),
                employment_type=EmploymentType.FULL_TIME,
            )
            db.add(employee)

        employee.role_id = roles[persona.role].id
        employee.reports_to_id = manager.id if manager else None
        employee.employee_code = persona.employee_code
        employee.first_name = persona.first_name
        employee.last_name = persona.last_name
        employee.work_email = persona.email
        employee.department = persona.department
        employee.designation = persona.designation
        employee.work_location = "Demo Office"
        employee.skills = "Demonstration account"
        await db.flush()
        employees_by_role[persona.role] = employee
        employees.append(employee)

    return employees


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_reference_data(db)
        roles = await sync_roles_and_permissions(db)
        employees = await ensure_production_demo_employees(db, roles)
        await db.commit()
    print(f"Production demo data is ready for {len(employees)} roles.")


if __name__ == "__main__":
    asyncio.run(main())

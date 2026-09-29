from __future__ import annotations

from sqlalchemy import select

from hrms.core.exceptions import ValidationFailed
from hrms.models.reference_data import Department, Designation, ProjectRole

DEPARTMENTS = (
    "Administration",
    "Data",
    "Delivery",
    "Design",
    "Engineering",
    "Finance",
    "Human Resources",
    "Leadership",
    "People",
    "Product",
)

DESIGNATIONS = (
    "Backend Engineer",
    "Business Analyst",
    "Chief Executive Officer",
    "Delivery Manager",
    "DevOps Engineer",
    "Engineer",
    "Finance Analyst",
    "Finance Manager",
    "Frontend Engineer",
    "Head of HR",
    "HR Executive",
    "Office Administrator",
    "People Partner",
    "Product Designer",
    "Project Manager",
    "QA Engineer",
    "Senior Data Engineer",
    "Senior Software Engineer",
    "Software Engineer",
    "UI/UX Designer",
    "Talent Acquisition Specialist",
)

PROJECT_ROLES = (
    "Business Analyst",
    "Delivery Manager",
    "Developer",
    "DevOps Engineer",
    "Engineer",
    "Product Designer",
    "Project Manager",
    "QA",
    "Senior Software Engineer",
    "Tech Lead",
)


async def ensure_reference_data(db) -> None:
    for model, values in (
        (Department, DEPARTMENTS),
        (Designation, DESIGNATIONS),
        (ProjectRole, PROJECT_ROLES),
    ):
        existing = set((await db.execute(select(model.name))).scalars())
        db.add_all(model(name=name, sort_order=index) for index, name in enumerate(values) if name not in existing)
    await db.flush()


async def active_options(db, model) -> list[dict]:
    rows = (await db.execute(select(model).where(model.is_active.is_(True)).order_by(model.sort_order, model.name))).scalars()
    return [{"id": row.id, "value": row.name, "label": row.name} for row in rows]


async def workforce_options(db) -> dict:
    return {
        "departments": await active_options(db, Department),
        "designations": await active_options(db, Designation),
    }


async def project_role_options(db) -> list[dict]:
    return await active_options(db, ProjectRole)


async def assert_active_value(db, model, value: str, label: str) -> None:
    found = (await db.execute(select(model.id).where(model.name == value, model.is_active.is_(True)))).scalar_one_or_none()
    if found is None:
        raise ValidationFailed(f"Select an active {label} from the predefined list.")


async def validate_employee_values(db, *, department: str, designation: str) -> None:
    await assert_active_value(db, Department, department, "department")
    await assert_active_value(db, Designation, designation, "designation")


async def validate_project_role(db, role_on_project: str) -> None:
    await assert_active_value(db, ProjectRole, role_on_project, "project role")

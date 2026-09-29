"""Seeded departments, designations and project roles.

Revision ID: e8b4c2107a93
Revises: d7a120fb9e62
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "e8b4c2107a93"
down_revision = "d7a120fb9e62"
branch_labels = None
depends_on = None

DEPARTMENTS = (
    "Administration", "Data", "Delivery", "Design", "Engineering", "Finance",
    "Human Resources", "Leadership", "People", "Product",
)
DESIGNATIONS = (
    "Backend Engineer", "Business Analyst", "Chief Executive Officer", "Delivery Manager", "DevOps Engineer",
    "Engineer", "Finance Analyst", "Finance Manager", "Frontend Engineer", "Head of HR",
    "HR Executive", "Office Administrator", "People Partner", "Product Designer",
    "Project Manager", "QA Engineer", "Senior Data Engineer", "Senior Software Engineer",
    "Software Engineer", "UI/UX Designer",
)
PROJECT_ROLES = (
    "Business Analyst", "Delivery Manager", "Developer", "DevOps Engineer", "Engineer",
    "Product Designer", "Project Manager", "QA", "Senior Software Engineer", "Tech Lead",
)


def _create_table(name):
    op.create_table(
        name,
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )


def _seed(table_name, values):
    table = sa.table(
        table_name,
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        table,
        [dict(id=uuid.uuid4(), name=value, is_active=True, sort_order=index) for index, value in enumerate(values)],
    )


def upgrade():
    _create_table("departments")
    _create_table("designations")
    _create_table("project_roles")
    _seed("departments", DEPARTMENTS)
    _seed("designations", DESIGNATIONS)
    _seed("project_roles", PROJECT_ROLES)

    op.execute("UPDATE employees SET department = btrim(department), designation = btrim(designation)")
    op.execute("UPDATE allocations SET role_on_project = btrim(role_on_project)")

    # Retain any organization-specific values already present before enforcing the lists.
    op.execute("""
        INSERT INTO departments (id, name, is_active, sort_order)
        SELECT md5('department:' || department)::uuid, department, true, 1000
        FROM employees GROUP BY department ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO designations (id, name, is_active, sort_order)
        SELECT md5('designation:' || designation)::uuid, designation, true, 1000
        FROM employees GROUP BY designation ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO project_roles (id, name, is_active, sort_order)
        SELECT md5('project-role:' || role_on_project)::uuid, role_on_project, true, 1000
        FROM allocations GROUP BY role_on_project ON CONFLICT (name) DO NOTHING
    """)

    op.create_foreign_key(
        "fk_employees_department", "employees", "departments", ["department"], ["name"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_employees_designation", "employees", "designations", ["designation"], ["name"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_allocations_project_role", "allocations", "project_roles", ["role_on_project"], ["name"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_allocations_project_role", "allocations", type_="foreignkey")
    op.drop_constraint("fk_employees_designation", "employees", type_="foreignkey")
    op.drop_constraint("fk_employees_department", "employees", type_="foreignkey")
    op.drop_table("project_roles")
    op.drop_table("designations")
    op.drop_table("departments")

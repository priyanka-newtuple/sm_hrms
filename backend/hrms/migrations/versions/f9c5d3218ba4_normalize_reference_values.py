"""Normalize legacy reference values.

Revision ID: f9c5d3218ba4
Revises: e8b4c2107a93
"""

from alembic import op

revision = "f9c5d3218ba4"
down_revision = "e8b4c2107a93"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO designations (id, name, is_active, sort_order)
        VALUES (md5('designation:Backend Engineer')::uuid, 'Backend Engineer', true, 100)
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO project_roles (id, name, is_active, sort_order)
        VALUES (md5('project-role:Senior Software Engineer')::uuid, 'Senior Software Engineer', true, 100)
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("UPDATE employees SET department = btrim(department), designation = btrim(designation)")
    op.execute("UPDATE allocations SET role_on_project = btrim(role_on_project)")
    op.execute("""
        UPDATE allocations SET role_on_project = 'Senior Software Engineer'
        WHERE lower(role_on_project) = lower('Senior Software Engineer')
    """)
    op.execute("""
        DELETE FROM departments d WHERE name <> btrim(name)
        AND NOT EXISTS (SELECT 1 FROM employees e WHERE e.department = d.name)
    """)
    op.execute("""
        DELETE FROM designations d WHERE name <> btrim(name)
        AND NOT EXISTS (SELECT 1 FROM employees e WHERE e.designation = d.name)
    """)
    op.execute("""
        DELETE FROM project_roles r
        WHERE lower(name) = lower('Senior Software Engineer') AND name <> 'Senior Software Engineer'
        AND NOT EXISTS (SELECT 1 FROM allocations a WHERE a.role_on_project = r.name)
    """)


def downgrade():
    # Restoring accidental whitespace or capitalization would corrupt clean data.
    pass

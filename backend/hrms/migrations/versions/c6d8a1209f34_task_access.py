"""Separate workflow module ownership from assigned task access.

Revision ID: c6d8a1209f34
Revises: b4c9e2d71a05
"""
from alembic import op

revision = "c6d8a1209f34"
down_revision = "b4c9e2d71a05"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE role_feature_permissions p
        SET actions = ARRAY['NONE']::action[], record_scope = 'NONE', data_profile = 'NONE'
        FROM roles r
        WHERE p.role_id = r.id
          AND r.name IN ('Employee', 'Project Manager', 'Delivery Manager', 'Finance', 'Office Admin')
          AND p.feature_key IN ('EMPLOYEE_ONBOARDING', 'EMPLOYEE_OFFBOARDING')
    """)


def downgrade():
    op.execute("""
        UPDATE role_feature_permissions p SET
          actions = CASE r.name
            WHEN 'Employee' THEN ARRAY['VIEW', 'COMPLETE']::action[]
            WHEN 'Office Admin' THEN ARRAY['MANAGE']::action[]
            ELSE ARRAY['VIEW']::action[] END,
          record_scope = (CASE r.name WHEN 'Employee' THEN 'SELF'
            WHEN 'Project Manager' THEN 'PROJECT_TEAM' ELSE 'ALL' END)::record_scope,
          data_profile = (CASE r.name WHEN 'Finance' THEN 'LIMITED'
            WHEN 'Office Admin' THEN 'BASIC' ELSE 'ALL' END)::data_profile
        FROM roles r WHERE p.role_id = r.id
          AND r.name IN ('Employee', 'Project Manager', 'Delivery Manager', 'Finance', 'Office Admin')
          AND p.feature_key IN ('EMPLOYEE_ONBOARDING', 'EMPLOYEE_OFFBOARDING')
    """)

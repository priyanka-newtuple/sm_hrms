"""Grant HR managers timesheet approval.

Revision ID: b1e7f5430dc6
Revises: a0d6e4329cb5
"""

from alembic import op

revision = "b1e7f5430dc6"
down_revision = "a0d6e4329cb5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE role_feature_permissions p
        SET actions = array_append(array_remove(actions, 'NONE'::action), 'APPROVE'::action)
        FROM roles r
        WHERE p.role_id = r.id
          AND r.name = 'HR - Full'
          AND p.feature_key = 'TIMESHEETS'
          AND NOT ('APPROVE'::action = ANY(p.actions))
    """)


def downgrade():
    op.execute("""
        UPDATE role_feature_permissions p
        SET actions = array_remove(actions, 'APPROVE'::action)
        FROM roles r
        WHERE p.role_id = r.id
          AND r.name = 'HR - Full'
          AND p.feature_key = 'TIMESHEETS'
    """)

"""Daily timesheets, holidays, and leave requests.

Revision ID: a0d6e4329cb5
Revises: f9c5d3218ba4
"""

import sqlalchemy as sa
from alembic import op

revision = "a0d6e4329cb5"
down_revision = "f9c5d3218ba4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("timesheets", sa.Column("work_date", sa.Date(), nullable=True))
    op.add_column("timesheets", sa.Column("task_details", sa.Text(), nullable=True))
    op.create_index("ix_timesheets_work_date", "timesheets", ["work_date"])
    op.create_unique_constraint("uq_timesheet_employee_project_day", "timesheets", ["employee_id", "project_id", "work_date"])

    op.create_table(
        "holidays",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True),
    )
    op.create_index("ix_holidays_holiday_date", "holidays", ["holiday_date"])

    op.create_table(
        "leave_requests",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("leave_type", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_leave_status"),
        sa.CheckConstraint("leave_type IN ('annual', 'sick', 'casual', 'unpaid', 'other')", name="ck_leave_type"),
    )
    op.create_index("ix_leave_requests_employee_id", "leave_requests", ["employee_id"])
    op.execute("""
        UPDATE role_feature_permissions p
        SET actions = ARRAY['VIEW', 'CREATE', 'EDIT']::action[], record_scope = 'SELF'::record_scope
        FROM roles r
        WHERE p.role_id = r.id AND r.name = 'Office Admin' AND p.feature_key = 'TIMESHEETS'
    """)


def downgrade():
    op.execute("""
        UPDATE role_feature_permissions p
        SET actions = ARRAY['NONE']::action[], record_scope = 'NONE'::record_scope
        FROM roles r
        WHERE p.role_id = r.id AND r.name = 'Office Admin' AND p.feature_key = 'TIMESHEETS'
    """)
    op.drop_table("leave_requests")
    op.drop_table("holidays")
    op.drop_constraint("uq_timesheet_employee_project_day", "timesheets", type_="unique")
    op.drop_index("ix_timesheets_work_date", table_name="timesheets")
    op.drop_column("timesheets", "task_details")
    op.drop_column("timesheets", "work_date")

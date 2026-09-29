"""Performance management cycles, goals, reviews, and project feedback.

Revision ID: c2f8a6541ed7
Revises: b1e7f5430dc6
"""

import sqlalchemy as sa
from alembic import op

revision = "c2f8a6541ed7"
down_revision = "b1e7f5430dc6"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE feature_key ADD VALUE IF NOT EXISTS 'PERFORMANCE_MANAGEMENT'")

    op.create_table(
        "performance_cycles",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("goal_due_date", sa.Date(), nullable=False),
        sa.Column("self_review_due_date", sa.Date(), nullable=False),
        sa.Column("manager_review_due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("created_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("approved_by_id", sa.UUID(), sa.ForeignKey("employees.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_approval', 'open', 'review', 'calibration', 'published', 'closed')",
            name="ck_performance_cycle_status",
        ),
    )
    op.create_table(
        "performance_goals",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), sa.ForeignKey("performance_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("measurement", sa.Text(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("manager_comment", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("weight > 0 AND weight <= 100", name="ck_performance_goal_weight"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_performance_goal_progress"),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'changes_requested')",
            name="ck_performance_goal_status",
        ),
    )
    op.create_index("ix_performance_goals_cycle_id", "performance_goals", ["cycle_id"])
    op.create_index("ix_performance_goals_employee_id", "performance_goals", ["employee_id"])
    op.create_table(
        "performance_reviews",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), sa.ForeignKey("performance_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", sa.UUID(), sa.ForeignKey("employees.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default="not_started"),
        sa.Column("self_summary", sa.Text()),
        sa.Column("self_rating", sa.Integer()),
        sa.Column("manager_summary", sa.Text()),
        sa.Column("manager_rating", sa.Integer()),
        sa.Column("calibration_comment", sa.Text()),
        sa.Column("calibrated_rating", sa.Integer()),
        sa.Column("calibrated_by_id", sa.UUID(), sa.ForeignKey("employees.id")),
        sa.Column("final_rating", sa.Integer()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("employee_comment", sa.Text()),
        sa.UniqueConstraint("cycle_id", "employee_id", name="uq_performance_review_cycle_employee"),
        sa.CheckConstraint(
            "status IN ('not_started', 'self_draft', 'submitted_to_manager', 'manager_submitted', 'calibrated', 'published', 'acknowledged')",
            name="ck_performance_review_status",
        ),
    )
    op.create_index("ix_performance_reviews_cycle_id", "performance_reviews", ["cycle_id"])
    op.create_index("ix_performance_reviews_employee_id", "performance_reviews", ["employee_id"])
    op.create_table(
        "project_feedback",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("review_id", sa.UUID(), sa.ForeignKey("performance_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("rating", sa.Integer()),
        sa.Column("contribution", sa.Text()),
        sa.Column("collaboration", sa.Text()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("review_id", "project_id", "reviewer_id", name="uq_project_feedback_reviewer"),
        sa.CheckConstraint("status IN ('pending', 'submitted')", name="ck_project_feedback_status"),
    )
    op.create_index("ix_project_feedback_review_id", "project_feedback", ["review_id"])
    op.create_index("ix_project_feedback_reviewer_id", "project_feedback", ["reviewer_id"])

    grants = {
        "Super Admin": ("ARRAY['FULL']::action[]", "ALL", "ALL"),
        "Employee": ("ARRAY['VIEW','CREATE','EDIT','SUBMIT']::action[]", "SELF", "ALL"),
        "HR - Basic": ("ARRAY['VIEW']::action[]", "ALL", "NON_SENSITIVE"),
        "HR - Full": ("ARRAY['MANAGE','APPROVE']::action[]", "ALL", "ALL"),
        "Project Manager": ("ARRAY['VIEW','CREATE','EDIT','SUBMIT','APPROVE']::action[]", "TEAM", "ALL"),
        "Delivery Manager": ("ARRAY['VIEW','CREATE','EDIT','SUBMIT','APPROVE']::action[]", "TEAM", "ALL"),
        "Finance": ("ARRAY['VIEW','CREATE','EDIT','SUBMIT']::action[]", "SELF", "ALL"),
        "Office Admin": ("ARRAY['VIEW','CREATE','EDIT','SUBMIT']::action[]", "SELF", "ALL"),
    }
    for role, (actions, scope, profile) in grants.items():
        op.execute(
            f"""INSERT INTO role_feature_permissions (id, role_id, feature_key, actions, record_scope, data_profile)
            SELECT md5(random()::text || clock_timestamp()::text)::uuid, id,
                   'PERFORMANCE_MANAGEMENT'::feature_key, {actions},
                   '{scope}'::record_scope, '{profile}'::data_profile
            FROM roles WHERE name = '{role}'
            ON CONFLICT (role_id, feature_key) DO NOTHING"""
        )


def downgrade():
    op.execute("DELETE FROM role_feature_permissions WHERE feature_key = 'PERFORMANCE_MANAGEMENT'")
    op.drop_table("project_feedback")
    op.drop_table("performance_reviews")
    op.drop_table("performance_goals")
    op.drop_table("performance_cycles")
    # PostgreSQL enum values cannot be removed safely.

"""Project drafts, approval requests and staged amendments.

Revision ID: d7a120fb9e62
Revises: c6d8a1209f34
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "d7a120fb9e62"
down_revision = "c6d8a1209f34"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE action ADD VALUE IF NOT EXISTS 'SUBMIT'")
    op.add_column("projects", sa.Column("approval_status", sa.String(30), nullable=False, server_default="approved"))
    op.add_column("projects", sa.Column("created_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True))
    op.create_check_constraint("ck_project_approval_status", "projects",
        "approval_status IN ('draft', 'pending', 'changes_requested', 'rejected', 'approved')")
    op.create_table("project_approval_requests",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("reviewed_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("proposed", postgresql.JSONB(), nullable=False),
        sa.Column("history", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'pending', 'changes_requested', 'rejected', 'approved')", name="ck_project_request_status"),
        sa.CheckConstraint("kind IN ('initial', 'amendment')", name="ck_project_request_kind"),
    )
    op.create_index("ix_project_approval_requests_project_id", "project_approval_requests", ["project_id"])
    op.execute("""UPDATE role_feature_permissions p
        SET actions = array_append(p.actions, 'SUBMIT'::action)
        FROM roles r WHERE p.role_id = r.id AND r.name IN ('Project Manager', 'Delivery Manager')
        AND p.feature_key = 'PROJECTS' AND NOT ('SUBMIT'::action = ANY(p.actions))""")


def downgrade():
    op.execute("UPDATE role_feature_permissions SET actions = array_remove(actions, 'SUBMIT'::action) WHERE feature_key = 'PROJECTS'")
    op.drop_table("project_approval_requests")
    op.drop_constraint("ck_project_approval_status", "projects", type_="check")
    op.drop_column("projects", "created_by_id")
    op.drop_column("projects", "approval_status")
    # PostgreSQL enum values cannot be dropped safely while other grants may use them.

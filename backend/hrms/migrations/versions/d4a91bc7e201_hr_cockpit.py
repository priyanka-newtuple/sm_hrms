"""HR content cockpit, recruiter role, and publishing workflow.

Revision ID: d4a91bc7e201
Revises: c2f8a6541ed7
"""
import sqlalchemy as sa
from alembic import op

revision = "d4a91bc7e201"
down_revision = "c2f8a6541ed7"
branch_labels = None
depends_on = None


def _base():
    return [sa.Column("id", sa.UUID(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE feature_key ADD VALUE IF NOT EXISTS 'HR_COCKPIT'")
    op.create_table("organization_policies", *_base(), sa.Column("title", sa.String(200), nullable=False), sa.Column("category", sa.String(60), nullable=False), sa.Column("summary", sa.Text(), nullable=False), sa.Column("body", sa.Text(), nullable=False), sa.Column("owner", sa.String(100), nullable=False, server_default="People"), sa.Column("version", sa.String(30), nullable=False, server_default="1.0"), sa.Column("effective_date", sa.Date(), nullable=False), sa.Column("review_date", sa.Date()), sa.Column("visibility", sa.String(20), nullable=False, server_default="public"), sa.Column("status", sa.String(30), nullable=False, server_default="draft"), sa.Column("created_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("approved_by_id", sa.UUID(), sa.ForeignKey("employees.id")), sa.Column("published_at", sa.DateTime(timezone=True)), sa.CheckConstraint("status IN ('draft','pending_approval','published','archived')", name="ck_policy_status"))
    op.create_table("learning_events", *_base(), sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text()), sa.Column("category", sa.String(40), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False), sa.Column("location", sa.String(200), nullable=False), sa.Column("audience", sa.String(200), nullable=False, server_default="All employees"), sa.Column("capacity", sa.Integer()), sa.Column("registration_url", sa.String(1000)), sa.Column("status", sa.String(30), nullable=False, server_default="draft"), sa.Column("created_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("approved_by_id", sa.UUID(), sa.ForeignKey("employees.id")), sa.Column("published_at", sa.DateTime(timezone=True)), sa.CheckConstraint("status IN ('draft','pending_approval','published','archived')", name="ck_learning_event_status"))
    op.create_table("job_descriptions", *_base(), sa.Column("title", sa.String(200), nullable=False), sa.Column("department", sa.String(100), nullable=False), sa.Column("level", sa.String(60), nullable=False), sa.Column("responsibilities", sa.Text(), nullable=False), sa.Column("requirements", sa.Text(), nullable=False), sa.Column("preferred_skills", sa.Text()), sa.Column("experience", sa.String(100)), sa.Column("employment_type", sa.String(50), nullable=False, server_default="Full-time"), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False))
    op.create_table("job_openings", *_base(), sa.Column("job_description_id", sa.UUID(), sa.ForeignKey("job_descriptions.id"), nullable=False), sa.Column("requisition_code", sa.String(40), nullable=False, unique=True), sa.Column("hiring_manager_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("openings", sa.Integer(), nullable=False, server_default="1"), sa.Column("location", sa.String(150), nullable=False), sa.Column("work_mode", sa.String(30), nullable=False), sa.Column("application_deadline", sa.Date(), nullable=False), sa.Column("referral_bonus", sa.String(100)), sa.Column("status", sa.String(30), nullable=False, server_default="draft"), sa.Column("created_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("approved_by_id", sa.UUID(), sa.ForeignKey("employees.id")), sa.Column("published_by_id", sa.UUID(), sa.ForeignKey("employees.id")), sa.Column("published_at", sa.DateTime(timezone=True)), sa.CheckConstraint("status IN ('draft','pending_approval','approved','published','paused','closed','archived')", name="ck_job_opening_status"))
    op.create_table("employee_referrals", *_base(), sa.Column("job_opening_id", sa.UUID(), sa.ForeignKey("job_openings.id"), nullable=False), sa.Column("referred_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=False), sa.Column("candidate_name", sa.String(200), nullable=False), sa.Column("candidate_email", sa.String(255), nullable=False), sa.Column("candidate_phone", sa.String(50)), sa.Column("message", sa.Text()), sa.Column("status", sa.String(30), nullable=False, server_default="submitted"))
    op.add_column("holidays", sa.Column("status", sa.String(30), nullable=False, server_default="published"))
    op.add_column("holidays", sa.Column("location", sa.String(100), nullable=False, server_default="All locations"))
    op.add_column("holidays", sa.Column("approved_by_id", sa.UUID(), sa.ForeignKey("employees.id")))
    op.add_column("holidays", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE holidays SET published_at = now() WHERE is_active")
    op.execute("INSERT INTO roles (id,name,description) VALUES (gen_random_uuid(),'Recruiter','Creates job descriptions, manages approved openings and employee referrals.') ON CONFLICT (name) DO NOTHING")
    grants = {
        "Super Admin": ("ARRAY['FULL']::action[]", "ALL", "ALL"),
        "HR - Basic": ("ARRAY['MANAGE','SUBMIT']::action[]", "ALL", "ALL"),
        "HR - Full": ("ARRAY['MANAGE','SUBMIT','APPROVE']::action[]", "ALL", "ALL"),
        "Recruiter": ("ARRAY['MANAGE','SUBMIT','APPROVE']::action[]", "ALL", "ALL"),
    }
    for name, (actions, scope, profile) in grants.items():
        op.execute(sa.text(f"INSERT INTO role_feature_permissions (id,role_id,feature_key,actions,record_scope,data_profile) SELECT gen_random_uuid(),id,'HR_COCKPIT',{actions},'{scope}','{profile}' FROM roles WHERE name=:name ON CONFLICT (role_id,feature_key) DO NOTHING").bindparams(name=name))
    for name in ["Employee", "Project Manager", "Delivery Manager", "Finance", "Office Admin"]:
        op.execute(sa.text("INSERT INTO role_feature_permissions (id,role_id,feature_key,actions,record_scope,data_profile) SELECT gen_random_uuid(),id,'HR_COCKPIT',ARRAY['NONE']::action[],'NONE','NONE' FROM roles WHERE name=:name ON CONFLICT (role_id,feature_key) DO NOTHING").bindparams(name=name))
    recruiter = {
        "EMPLOYEE_DIRECTORY": ("VIEW", "ALL", "BASIC"), "EMPLOYEE_ONBOARDING": ("NONE", "NONE", "NONE"), "EMPLOYEE_OFFBOARDING": ("NONE", "NONE", "NONE"), "CUSTOMERS": ("NONE", "NONE", "NONE"), "PROJECTS": ("VIEW", "ASSIGNED", "BASIC"), "ALLOCATIONS": ("VIEW", "SELF", "ALL"), "TIMESHEETS": ("VIEW,CREATE,EDIT", "SELF", "ALL"), "ASSET_MANAGEMENT": ("VIEW", "SELF", "ALL"), "EXPENSE_MANAGEMENT": ("VIEW,CREATE", "SELF", "ALL"), "HELP_DESK": ("VIEW,CREATE", "SELF", "ALL"), "PERFORMANCE_MANAGEMENT": ("VIEW,CREATE,EDIT,SUBMIT", "SELF", "ALL")}
    for feature, (actions, scope, profile) in recruiter.items():
        arr = "ARRAY[" + ",".join(f"'{x}'" for x in actions.split(",")) + "]::action[]"
        op.execute(sa.text(f"INSERT INTO role_feature_permissions (id,role_id,feature_key,actions,record_scope,data_profile) SELECT gen_random_uuid(),id,'{feature}',{arr},'{scope}','{profile}' FROM roles WHERE name='Recruiter' ON CONFLICT (role_id,feature_key) DO NOTHING"))


def downgrade():
    op.drop_table("employee_referrals"); op.drop_table("job_openings"); op.drop_table("job_descriptions"); op.drop_table("learning_events"); op.drop_table("organization_policies")
    op.drop_column("holidays", "published_at"); op.drop_column("holidays", "approved_by_id"); op.drop_column("holidays", "location"); op.drop_column("holidays", "status")
    op.execute("DELETE FROM role_feature_permissions WHERE feature_key='HR_COCKPIT'")
    op.execute("DELETE FROM roles WHERE name='Recruiter'")

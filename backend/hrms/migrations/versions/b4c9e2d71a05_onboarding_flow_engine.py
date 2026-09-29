"""onboarding flow engine: templates, task assignees, invitations, documents, outbox

Revision ID: b4c9e2d71a05
Revises: 28b7a3764fe6
Create Date: 2026-09-17

Hand-written. Existing onboarding_tasks rows are back-filled (status from
is_complete, seq by insertion order) so in-flight records keep working. The
default onboarding template is inserted here (idempotently, keyed on name)
rather than in seed_data, so already-seeded databases get it on upgrade
without a re-seed.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4c9e2d71a05"
down_revision: Union[str, None] = "28b7a3764fe6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


task_status = sa.Enum("PENDING", "READY", "DONE", "SKIPPED", name="task_status")
assignee_rule = sa.Enum("ROLE", "NEW_HIRE", "REPORTING_MANAGER", name="assignee_rule")
task_action_type = sa.Enum(
    "MANUAL",
    "INVITE_EMPLOYEE",
    "EMPLOYEE_PROFILE",
    "DOCUMENT_COLLECTION",
    "ASSET_ASSIGNMENT",
    "PROJECT_ALLOCATION",
    name="task_action_type",
)
invitation_status = sa.Enum("PENDING", "ACCEPTED", "EXPIRED", name="invitation_status")
document_type = sa.Enum(
    "ID_PROOF",
    "ADDRESS_PROOF",
    "PAN",
    "EDUCATION_CERTIFICATE",
    "EXPERIENCE_CERTIFICATE",
    "SIGNED_OFFER_LETTER",
    "OTHER",
    name="document_type",
)
document_status = sa.Enum("SUBMITTED", "VERIFIED", "REJECTED", name="document_status")
outbox_status = sa.Enum("QUEUED", "SENT", "FAILED", name="outbox_status")


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created type without re-issuing CREATE TYPE."""
    return postgresql.ENUM(name=name, create_type=False)


# Fixed UUIDs so the guarded insert below is deterministic and idempotent.
_TEMPLATE_ID = "0e9f3a7c-5b21-4c48-9a6d-1f2e8c4b7d10"
_STEP_IDS = [
    "a1b0c1d0-0001-4000-8000-000000000001",
    "a1b0c1d0-0002-4000-8000-000000000002",
    "a1b0c1d0-0003-4000-8000-000000000003",
    "a1b0c1d0-0004-4000-8000-000000000004",
    "a1b0c1d0-0005-4000-8000-000000000005",
    "a1b0c1d0-0006-4000-8000-000000000006",
    "a1b0c1d0-0007-4000-8000-000000000007",
    "a1b0c1d0-0008-4000-8000-000000000008",
]

# seq, step_key, title, description, rule, role, action, due_days, depends
_DEFAULT_STEPS = [
    (1, "newtuple_id", "Create Newtuple ID (Google Workspace account)",
     "Create the Google Workspace account and confirm the work email is active.",
     "ROLE", "Office Admin", "MANUAL", 2, None),
    (2, "razorpay_account", "Create Razorpay payroll account",
     "Create the payroll contact in Razorpay and record the reference ID on this step.",
     "ROLE", "Finance", "MANUAL", 3, None),
    (3, "hrms_invitation", "Invite employee to HRMS",
     "System sends the HRMS invitation email automatically once the Newtuple ID exists.",
     "ROLE", "HR - Full", "INVITE_EMPLOYEE", 3, [1]),
    (4, "employee_profile", "Employee fills personal & bank details",
     "The new hire completes the self-service wizard: personal info and payroll bank account.",
     "NEW_HIRE", None, "EMPLOYEE_PROFILE", 6, [3]),
    (5, "documents", "Upload documents & experience certificates",
     "ID proof, PAN, education certificates, experience certificates and signed offer "
     "letter — uploaded by the employee, verified by HR.",
     "NEW_HIRE", None, "DOCUMENT_COLLECTION", 8, [3]),
    (6, "asset_allocation", "Allocate laptop and access badge",
     "Assign assets in the Assets module; the step completes automatically.",
     "ROLE", "Office Admin", "ASSET_ASSIGNMENT", 8, [1]),
    (7, "hr_orientation", "HR orientation session",
     "Run the orientation session and mark this step done with the date in the note.",
     "ROLE", "HR - Basic", "MANUAL", 10, [4]),
    (8, "pm_allocation", "Allocate to project & project manager",
     "Create the allocation in the Allocations module; the step completes automatically.",
     "ROLE", "Delivery Manager", "PROJECT_ALLOCATION", 12, [4]),
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        task_status, assignee_rule, task_action_type,
        invitation_status, document_type, document_status, outbox_status,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- onboarding templates -------------------------------------------------
    op.create_table(
        "onboarding_templates",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("workflow_type", _enum("onboarding_type"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "onboarding_template_steps",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "template_id",
            sa.UUID(),
            sa.ForeignKey("onboarding_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assignee_rule", _enum("assignee_rule"), nullable=False, server_default="ROLE"),
        sa.Column("assignee_role", sa.String(length=100), nullable=True),
        sa.Column("action_type", _enum("task_action_type"), nullable=False, server_default="MANUAL"),
        sa.Column("due_days", sa.Integer(), nullable=True),
        sa.Column("depends_on_seqs", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.UniqueConstraint("template_id", "seq", name="uq_template_step_seq"),
    )

    # --- invitations ----------------------------------------------------------
    op.create_table(
        "employee_invitations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "employee_id",
            sa.UUID(),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", _enum("invitation_status"), nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- documents ------------------------------------------------------------
    op.create_table(
        "employee_documents",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "employee_id",
            sa.UUID(),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_type", _enum("document_type"), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("status", _enum("document_status"), nullable=False, server_default="SUBMITTED"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("uploaded_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("verified_by_id", sa.UUID(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_employee_documents_employee", "employee_documents", ["employee_id"])

    # --- onboarding task upgrades ----------------------------------------------
    op.add_column(
        "onboarding_tasks",
        sa.Column(
            "template_step_id",
            sa.UUID(),
            sa.ForeignKey(
                "onboarding_template_steps.id",
                ondelete="SET NULL",
                name="fk_onboarding_tasks_template_step",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "onboarding_tasks",
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("onboarding_tasks", sa.Column("step_key", sa.String(length=50), nullable=True))
    op.add_column("onboarding_tasks", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "onboarding_tasks",
        sa.Column("status", _enum("task_status"), nullable=False, server_default="READY"),
    )
    op.add_column(
        "onboarding_tasks",
        sa.Column("action_type", _enum("task_action_type"), nullable=False, server_default="MANUAL"),
    )
    op.add_column(
        "onboarding_tasks",
        sa.Column(
            "assignee_employee_id",
            sa.UUID(),
            sa.ForeignKey("employees.id", ondelete="SET NULL", name="fk_onboarding_tasks_assignee"),
            nullable=True,
        ),
    )
    op.add_column(
        "onboarding_tasks", sa.Column("assignee_role", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "onboarding_tasks",
        sa.Column("depends_on_seqs", postgresql.ARRAY(sa.Integer()), nullable=True),
    )
    op.add_column("onboarding_tasks", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column(
        "onboarding_tasks",
        sa.Column(
            "completed_by_id",
            sa.UUID(),
            sa.ForeignKey(
                "employees.id", ondelete="SET NULL", name="fk_onboarding_tasks_completed_by"
            ),
            nullable=True,
        ),
    )
    op.add_column("onboarding_tasks", sa.Column("completion_note", sa.Text(), nullable=True))
    op.add_column(
        "onboarding_tasks", sa.Column("linked_entity_type", sa.String(length=50), nullable=True)
    )
    op.add_column("onboarding_tasks", sa.Column("linked_entity_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_onboarding_tasks_assignee_status",
        "onboarding_tasks",
        ["assignee_employee_id", "status"],
    )

    # Back-fill legacy rows: DONE where complete, seq by insertion order.
    op.execute("UPDATE onboarding_tasks SET status = 'DONE' WHERE is_complete")
    op.execute(
        """
        UPDATE onboarding_tasks AS t SET seq = numbered.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY onboarding_record_id ORDER BY id) AS rn
            FROM onboarding_tasks
        ) AS numbered
        WHERE t.id = numbered.id AND t.seq = 0
        """
    )

    # --- notifications outbox ---------------------------------------------------
    op.create_table(
        "notifications_outbox",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "recipient_employee_id",
            sa.UUID(),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email_to", sa.String(length=255), nullable=False),
        sa.Column("template_key", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "related_task_id",
            sa.UUID(),
            sa.ForeignKey("onboarding_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", _enum("outbox_status"), nullable=False, server_default="QUEUED"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_outbox_status", "notifications_outbox", ["status"])

    # --- employees --------------------------------------------------------------
    op.add_column(
        "employees", sa.Column("payroll_reference", sa.String(length=100), nullable=True)
    )

    # --- default template (idempotent) -------------------------------------------
    op.execute(
        f"""
        INSERT INTO onboarding_templates (id, name, workflow_type, is_default, active, created_at, updated_at)
        SELECT '{_TEMPLATE_ID}', 'Default onboarding', 'ONBOARDING', true, true, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM onboarding_templates WHERE name = 'Default onboarding')
        """
    )
    for step_id, (seq, key, title, desc, rule, role, action, due, deps) in zip(
        _STEP_IDS, _DEFAULT_STEPS
    ):
        role_sql = f"'{role}'" if role else "NULL"
        deps_sql = "ARRAY[" + ",".join(str(d) for d in deps) + "]" if deps else "NULL"
        desc_sql = desc.replace("'", "''")
        title_sql = title.replace("'", "''")
        op.execute(
            f"""
            INSERT INTO onboarding_template_steps
                (id, template_id, seq, step_key, title, description, assignee_rule,
                 assignee_role, action_type, due_days, depends_on_seqs)
            SELECT '{step_id}', '{_TEMPLATE_ID}', {seq}, '{key}', '{title_sql}', '{desc_sql}',
                   '{rule}', {role_sql}, '{action}', {due}, {deps_sql}
            WHERE EXISTS (SELECT 1 FROM onboarding_templates WHERE id = '{_TEMPLATE_ID}')
              AND NOT EXISTS (
                SELECT 1 FROM onboarding_template_steps
                WHERE template_id = '{_TEMPLATE_ID}' AND seq = {seq}
              )
            """
        )


def downgrade() -> None:
    op.drop_column("employees", "payroll_reference")

    op.drop_index("ix_notifications_outbox_status", table_name="notifications_outbox")
    op.drop_table("notifications_outbox")

    op.drop_index("ix_onboarding_tasks_assignee_status", table_name="onboarding_tasks")
    for column in (
        "linked_entity_id", "linked_entity_type", "completion_note", "completed_by_id",
        "due_date", "depends_on_seqs", "assignee_role", "assignee_employee_id",
        "action_type", "status", "description", "step_key", "seq", "template_step_id",
    ):
        op.drop_column("onboarding_tasks", column)

    op.drop_index("ix_employee_documents_employee", table_name="employee_documents")
    op.drop_table("employee_documents")
    op.drop_table("employee_invitations")
    op.drop_table("onboarding_template_steps")
    op.drop_table("onboarding_templates")

    bind = op.get_bind()
    for enum_type in (
        outbox_status, document_status, document_type,
        invitation_status, task_action_type, assignee_rule, task_status,
    ):
        enum_type.drop(bind, checkfirst=True)

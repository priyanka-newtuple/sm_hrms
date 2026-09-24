"""Add audit.transition_attempts table.

Replaces the `transition_attempt` rows in the legacy `workflow_activity_log`
discriminator table. Records every transition execution outcome:
SUCCEEDED / BLOCKED / CONFLICT, with guard evaluations and IO snapshots.
This is the "why didn't this transition?" debug surface.

Same composite-FK pattern (org_id, entity_id) so tenant isolation is
enforced at the DB level. workflow_id is a plain column for now; the FK
to definitions.workflows lands in Wave 2.

Revision ID: 202605030004
Revises: 202605030003
Create Date: 2026-05-03
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "202605030004"
down_revision = "202605030003"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return app_schema, f"{app_schema}_runtime", f"{app_schema}_audit"


def upgrade() -> None:
    app_schema, runtime_schema, audit_schema = _schemas()

    op.create_table(
        "transition_attempts",
        sa.Column("transition_attempt_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("from_state", sa.String(length=128), nullable=True),
        sa.Column("to_state", sa.String(length=128), nullable=True),
        sa.Column("trigger", sa.String(length=128), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_role", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("inputs", JSONB(), nullable=True),
        sa.Column("outputs", JSONB(), nullable=True),
        sa.Column("guard_evaluations", JSONB(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{app_schema}.organizations.id"],
            ondelete="CASCADE",
            name="fk_transition_attempts_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "entity_id"],
            [
                f"{runtime_schema}.entities.organization_id",
                f"{runtime_schema}.entities.entity_id",
            ],
            ondelete="CASCADE",
            name="fk_transition_attempts_org_entity_id",
        ),
        sa.PrimaryKeyConstraint("transition_attempt_id", name="pk_transition_attempts"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_transition_attempts_org_idempotency_key",
        ),
        schema=audit_schema,
    )
    op.create_index(
        "ix_transition_attempts_entity_occurred",
        "transition_attempts",
        ["entity_id", "occurred_at"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_transition_attempts_workflow_id",
        "transition_attempts",
        ["workflow_id"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_transition_attempts_status",
        "transition_attempts",
        ["status"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_transition_attempts_organization_id",
        "transition_attempts",
        ["organization_id"],
        schema=audit_schema,
    )


def downgrade() -> None:
    _, _, audit_schema = _schemas()

    op.drop_index(
        "ix_transition_attempts_organization_id",
        table_name="transition_attempts",
        schema=audit_schema,
    )
    op.drop_index(
        "ix_transition_attempts_status",
        table_name="transition_attempts",
        schema=audit_schema,
    )
    op.drop_index(
        "ix_transition_attempts_workflow_id",
        table_name="transition_attempts",
        schema=audit_schema,
    )
    op.drop_index(
        "ix_transition_attempts_entity_occurred",
        table_name="transition_attempts",
        schema=audit_schema,
    )
    op.drop_table("transition_attempts", schema=audit_schema)

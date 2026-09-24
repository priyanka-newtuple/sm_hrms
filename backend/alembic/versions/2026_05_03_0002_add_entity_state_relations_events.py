"""Add entity_state, entity_relations, and audit.entity_events tables.

Wave 1 remainder of the state-machine rewrite. Lands the structural
unlock (one entity in many workflows via synthetic state_id PK), the
graph edges between entities, and the per-entity append-only timeline.

- runtime.entity_state    one row per (entity, workflow) enrollment
- runtime.entity_relations directed edges between entities
- audit (new schema)      append-only history bucket
- audit.entity_events     per-entity event log

All FKs to runtime.entities and definitions.entity_types use the
org-scoped composite-FK pattern established in 202605030001 so that
tenant isolation is enforced at the DB level.

Workflows still live in the legacy `workflow_state_machines` table
(Wave 2 renames it to `definitions.workflows`); we therefore reference
`workflow_id` as a plain column without a FK for now. The FK will be
added when that rename lands.

Revision ID: 202605030002
Revises: 202605030001
Create Date: 2026-05-03
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "202605030002"
down_revision = "202605030001"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str, str, str]:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return (
        app_schema,
        f"{app_schema}_definitions",
        f"{app_schema}_runtime",
        f"{app_schema}_audit",
    )


def upgrade() -> None:
    app_schema, definitions_schema, runtime_schema, audit_schema = _schemas()

    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{audit_schema}"'))

    # --- runtime.entities needs a UNIQUE on (org_id, entity_id) so the
    #     org-scoped composite FK from entity_state / entity_relations /
    #     entity_events has a valid target. entity_id is already PK
    #     (uniquely identifies a row); the constraint just exposes the
    #     pair for FK use, same pattern as 202605030001.
    op.create_unique_constraint(
        "uq_entities_org_id_entity_id",
        "entities",
        ["organization_id", "entity_id"],
        schema=runtime_schema,
    )

    # --- runtime.entity_state ---
    op.create_table(
        "entity_state",
        sa.Column("state_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("current_state", sa.String(length=128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "state_entered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{app_schema}.organizations.id"],
            ondelete="CASCADE",
            name="fk_entity_state_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "entity_id"],
            [
                f"{runtime_schema}.entities.organization_id",
                f"{runtime_schema}.entities.entity_id",
            ],
            ondelete="CASCADE",
            name="fk_entity_state_org_entity_id",
        ),
        sa.PrimaryKeyConstraint("state_id", name="pk_entity_state"),
        sa.UniqueConstraint(
            "entity_id", "workflow_id", name="uq_entity_state_entity_workflow"
        ),
        schema=runtime_schema,
    )
    op.create_index(
        "ix_entity_state_organization_id",
        "entity_state",
        ["organization_id"],
        schema=runtime_schema,
    )
    op.create_index(
        "ix_entity_state_entity_id",
        "entity_state",
        ["entity_id"],
        schema=runtime_schema,
    )
    op.create_index(
        "ix_entity_state_workflow_id",
        "entity_state",
        ["workflow_id"],
        schema=runtime_schema,
    )

    # --- runtime.entity_relations ---
    op.create_table(
        "entity_relations",
        sa.Column("relation_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("from_entity_id", sa.String(length=36), nullable=False),
        sa.Column("to_entity_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=128), nullable=False),
        sa.Column("relation_metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{app_schema}.organizations.id"],
            ondelete="CASCADE",
            name="fk_entity_relations_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "from_entity_id"],
            [
                f"{runtime_schema}.entities.organization_id",
                f"{runtime_schema}.entities.entity_id",
            ],
            ondelete="CASCADE",
            name="fk_entity_relations_org_from_entity_id",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "to_entity_id"],
            [
                f"{runtime_schema}.entities.organization_id",
                f"{runtime_schema}.entities.entity_id",
            ],
            ondelete="CASCADE",
            name="fk_entity_relations_org_to_entity_id",
        ),
        sa.PrimaryKeyConstraint("relation_id", name="pk_entity_relations"),
        sa.UniqueConstraint(
            "from_entity_id",
            "to_entity_id",
            "relation_type",
            name="uq_entity_relations_from_to_type",
        ),
        schema=runtime_schema,
    )
    op.create_index(
        "ix_entity_relations_from_type",
        "entity_relations",
        ["from_entity_id", "relation_type"],
        schema=runtime_schema,
    )
    op.create_index(
        "ix_entity_relations_to_type",
        "entity_relations",
        ["to_entity_id", "relation_type"],
        schema=runtime_schema,
    )
    op.create_index(
        "ix_entity_relations_organization_id",
        "entity_relations",
        ["organization_id"],
        schema=runtime_schema,
    )

    # --- audit.entity_events ---
    op.create_table(
        "entity_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
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
            name="fk_entity_events_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "entity_id"],
            [
                f"{runtime_schema}.entities.organization_id",
                f"{runtime_schema}.entities.entity_id",
            ],
            ondelete="CASCADE",
            name="fk_entity_events_org_entity_id",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_entity_events"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_entity_events_org_idempotency_key",
        ),
        schema=audit_schema,
    )
    op.create_index(
        "ix_entity_events_entity_occurred",
        "entity_events",
        ["entity_id", "occurred_at"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_entity_events_organization_id",
        "entity_events",
        ["organization_id"],
        schema=audit_schema,
    )
    op.create_index(
        "ix_entity_events_event_type",
        "entity_events",
        ["event_type"],
        schema=audit_schema,
    )


def downgrade() -> None:
    _, _, runtime_schema, audit_schema = _schemas()

    op.drop_index(
        "ix_entity_events_event_type", table_name="entity_events", schema=audit_schema
    )
    op.drop_index(
        "ix_entity_events_organization_id",
        table_name="entity_events",
        schema=audit_schema,
    )
    op.drop_index(
        "ix_entity_events_entity_occurred",
        table_name="entity_events",
        schema=audit_schema,
    )
    op.drop_table("entity_events", schema=audit_schema)

    op.drop_index(
        "ix_entity_relations_organization_id",
        table_name="entity_relations",
        schema=runtime_schema,
    )
    op.drop_index(
        "ix_entity_relations_to_type",
        table_name="entity_relations",
        schema=runtime_schema,
    )
    op.drop_index(
        "ix_entity_relations_from_type",
        table_name="entity_relations",
        schema=runtime_schema,
    )
    op.drop_table("entity_relations", schema=runtime_schema)

    op.drop_index(
        "ix_entity_state_workflow_id",
        table_name="entity_state",
        schema=runtime_schema,
    )
    op.drop_index(
        "ix_entity_state_entity_id",
        table_name="entity_state",
        schema=runtime_schema,
    )
    op.drop_index(
        "ix_entity_state_organization_id",
        table_name="entity_state",
        schema=runtime_schema,
    )
    op.drop_table("entity_state", schema=runtime_schema)

    op.drop_constraint(
        "uq_entities_org_id_entity_id",
        "entities",
        type_="unique",
        schema=runtime_schema,
    )

    op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{audit_schema}" CASCADE'))

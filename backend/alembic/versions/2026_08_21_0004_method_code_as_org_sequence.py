"""Make method_code a database-assigned, per-organization sequence number.

It was a user-entered string with a case-insensitive unique index per
organization among live rows. It becomes an integer the database hands out, so
each organization counts 1, 2, 3 of its own and numbers are never reused.

Numbering comes from method_library_org_counters, one row per organization,
incremented with INSERT ... ON CONFLICT DO UPDATE ... RETURNING. That is the
mechanism auto_number_counters already uses: the increment and the read are one
statement, so two concurrent creates in one organization cannot take the same
number the way a "max + 1" read would allow.

The column is replaced rather than cast: existing values are free text such as
"PBMC-01" and would not convert. Existing rows are renumbered per organization in
created_at order, then each counter is seeded to that organization's highest
number so later creates continue from there rather than colliding.

The old case-insensitive index goes. A plain unique constraint on
(organization_id, method_code) replaces it, since numbers are never reused and
archived rows keep theirs.

Revision ID: 202608210004
Revises: 202608210003
Create Date: 2026-08-21
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202608210004"
down_revision = "202608210003"
branch_labels = None
depends_on = None

IDENTIFIER_LENGTH = 36
METHODS_TABLE = "method_library_methods"
COUNTERS_TABLE = "method_library_org_counters"
OLD_INDEX = "uq_method_library_methods_org_code_active"
NEW_CONSTRAINT = "uq_method_library_methods_org_code"


def _definitions_schema() -> str:
    app_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return f"{app_schema}_definitions"


def upgrade() -> None:
    schema = _definitions_schema()

    op.create_table(
        COUNTERS_TABLE,
        sa.Column("organization_id", sa.String(IDENTIFIER_LENGTH), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("organization_id", name="pk_method_library_org_counters"),
        schema=schema,
    )

    op.drop_index(OLD_INDEX, table_name=METHODS_TABLE, schema=schema)

    # Replace rather than cast: the old values are free text.
    op.add_column(
        METHODS_TABLE,
        sa.Column("method_code_number", sa.Integer(), nullable=True),
        schema=schema,
    )
    # Renumber per organization in creation order. Inside the migration this
    # table is not taking concurrent writes, so a window function gives the same
    # result as claiming each number from the counter, deterministically.
    op.execute(
        sa.text(
            f"""
            UPDATE "{schema}".{METHODS_TABLE} AS m
            SET method_code_number = numbered.row_number
            FROM (
                SELECT
                    method_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY organization_id ORDER BY created_at, method_id
                    ) AS row_number
                FROM "{schema}".{METHODS_TABLE}
            ) AS numbered
            WHERE m.method_id = numbered.method_id
            """
        )
    )
    # Seed each counter to that organization's highest number, so the next create
    # continues the sequence instead of reissuing an existing number.
    op.execute(
        sa.text(
            f"""
            INSERT INTO "{schema}".{COUNTERS_TABLE} (organization_id, next_value)
            SELECT organization_id, MAX(method_code_number)
            FROM "{schema}".{METHODS_TABLE}
            GROUP BY organization_id
            ON CONFLICT (organization_id) DO UPDATE
                SET next_value = EXCLUDED.next_value
            """
        )
    )

    op.drop_column(METHODS_TABLE, "method_code", schema=schema)
    op.alter_column(
        METHODS_TABLE, "method_code_number", new_column_name="method_code", schema=schema
    )
    op.alter_column(
        METHODS_TABLE,
        "method_code",
        existing_type=sa.Integer(),
        nullable=False,
        schema=schema,
    )
    op.create_unique_constraint(
        NEW_CONSTRAINT, METHODS_TABLE, ["organization_id", "method_code"], schema=schema
    )


def downgrade() -> None:
    schema = _definitions_schema()
    op.drop_constraint(NEW_CONSTRAINT, METHODS_TABLE, schema=schema, type_="unique")
    # Back to free text, carrying the numbers across as their string form.
    op.alter_column(
        METHODS_TABLE,
        "method_code",
        existing_type=sa.Integer(),
        type_=sa.String(128),
        existing_nullable=False,
        postgresql_using="method_code::text",
        schema=schema,
    )
    op.create_index(
        OLD_INDEX,
        METHODS_TABLE,
        ["organization_id", sa.text("lower(method_code)")],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.drop_table(COUNTERS_TABLE, schema=schema)

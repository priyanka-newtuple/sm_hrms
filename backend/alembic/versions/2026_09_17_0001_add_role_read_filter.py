"""Add compound read filters to role permissions.

Revision ID: 202609170001
Revises: 202609160002
"""

import os

import sqlalchemy as sa

from alembic import op

revision = "202609170001"
down_revision = "202609160002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "role_permissions",
        sa.Column("read_filter", sa.JSON(none_as_null=True), nullable=True),
        schema=os.environ.get("POSTGRES_APP_SCHEMA", "public"),
    )


def downgrade() -> None:
    # Refuse to silently turn compound permissions into unrestricted permissions.
    schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    table = sa.table("role_permissions", sa.column("read_filter", sa.JSON()), schema=schema)
    if (
        op.get_bind()
        .execute(
            sa.select(sa.func.count()).select_from(table).where(table.c.read_filter.is_not(None))
        )
        .scalar_one()
    ):
        raise RuntimeError("Remove compound role read filters before downgrading.")
    op.drop_column("role_permissions", "read_filter", schema=schema)

"""Bind every HRMS table to the deployment organization.

Revises: d4a91bc7e201
"""
import sqlalchemy as sa
from alembic import op

from hrms.config import get_settings
from hrms.database import Base
import hrms.models  # noqa: F401 - register every HRMS model

revision = "2026_09_24_0001"
down_revision = "d4a91bc7e201"
branch_labels = None
depends_on = None


def upgrade():
    org_id = get_settings().HRMS_ORGANIZATION_ID
    for table in Base.metadata.sorted_tables:
        op.add_column(table.name, sa.Column("organization_id", sa.String(64), nullable=False, server_default=org_id))
        op.create_index(f"ix_{table.name}_organization_id", table.name, ["organization_id"])


def downgrade():
    for table in reversed(Base.metadata.sorted_tables):
        op.drop_index(f"ix_{table.name}_organization_id", table.name)
        op.drop_column(table.name, "organization_id")

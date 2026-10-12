"""Tenant-owned permission catalog entries; existing global permissions stay unchanged."""
import os
import sqlalchemy as sa
from alembic import op

revision = '202610120001'
down_revision = '202609180001'
branch_labels = None
depends_on = None


def upgrade():
    schema = os.environ.get('POSTGRES_APP_SCHEMA', 'public')
    op.add_column('permissions', sa.Column('organization_id', sa.String(36), nullable=True), schema=schema)
    op.create_index('ix_permissions_organization_id', 'permissions', ['organization_id'], schema=schema)


def downgrade():
    # Do not silently turn tenant permissions into global permissions on rollback.
    schema = os.environ.get('POSTGRES_APP_SCHEMA', 'public')
    if op.get_bind().execute(sa.text(f'SELECT 1 FROM "{schema}".permissions WHERE organization_id IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Remove tenant permission grants and entries before downgrading')
    op.drop_index('ix_permissions_organization_id', table_name='permissions', schema=schema)
    op.drop_column('permissions', 'organization_id', schema=schema)

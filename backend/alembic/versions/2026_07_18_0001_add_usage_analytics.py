"""Add usage analytics permission and audit query indexes.

Revision ID: 202607180001
Revises: 202608040001
Create Date: 2026-07-18
"""

from __future__ import annotations

import os

from alembic import op

revision = "202607180001"
down_revision = "202608040001"
branch_labels = None
depends_on = None


def _schemas() -> tuple[str, str]:
    app = os.environ.get("POSTGRES_APP_SCHEMA", "public")
    return app, f"{app}_audit"


def upgrade() -> None:
    app, audit = _schemas()

    op.execute(
        f"""
        INSERT INTO "{app}".permissions
            (id, key, resource, action, description, is_system, created_at, updated_at)
        SELECT md5('permission:analytics:read'), 'analytics:read', 'analytics', 'read',
               'View organization usage analytics', TRUE, NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM "{app}".permissions WHERE key = 'analytics:read'
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO "{app}".role_permissions
            (id, role_id, permission_key, entity_type, action, allowed, created_at)
        SELECT md5(r.id || ':analytics:read'), r.id, 'analytics:read', NULL, NULL, TRUE, NOW()
        FROM "{app}".roles r
        WHERE r.name IN ('admin', 'superadmin')
          AND r.archived_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM "{app}".role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_key = 'analytics:read'
          )
        """
    )

    op.execute(
        f'CREATE INDEX IF NOT EXISTS ix_audit_events_org_timestamp '
        f'ON "{audit}".audit_events (organization_id, event_timestamp)'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS ix_audit_events_org_user '
        f'ON "{audit}".audit_events (organization_id, user_id)'
    )


def downgrade() -> None:
    app, audit = _schemas()
    op.execute(f'DROP INDEX IF EXISTS "{audit}".ix_audit_events_org_user')
    op.execute(f'DROP INDEX IF EXISTS "{audit}".ix_audit_events_org_timestamp')
    op.execute(
        f'DELETE FROM "{app}".role_permissions WHERE permission_key = \'analytics:read\''
    )
    op.execute(f'DELETE FROM "{app}".permissions WHERE key = \'analytics:read\'')

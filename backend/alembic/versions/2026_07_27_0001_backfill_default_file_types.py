"""Backfill default file types for existing active organizations.

Default file types are provisioned when an organization is created or approved,
but organizations created before that hook was introduced have no system file
types. Bulk import depends on ``generic_document`` and therefore cannot store
its first upload for those organizations.

This migration is idempotent and preserves any existing organization-specific
configuration via ``ON CONFLICT DO NOTHING``.

Revision ID: 202607270001
Revises: 202607260001
Create Date: 2026-07-27
"""

from __future__ import annotations

import os

from alembic import op

revision = "202607270001"
down_revision = "202607260001"
branch_labels = None
depends_on = None


def _schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    schema = _schema()
    op.get_bind().exec_driver_sql(
        f"""
        INSERT INTO "{schema}".file_types (
            organization_id,
            type_id,
            display_name,
            description,
            folder,
            allowed_extensions,
            max_size_mb,
            is_active,
            is_system,
            metadata,
            created_at,
            updated_at
        )
        SELECT
            organization.id,
            defaults.type_id,
            defaults.display_name,
            defaults.description,
            defaults.folder,
            defaults.allowed_extensions,
            defaults.max_size_mb,
            TRUE,
            TRUE,
            defaults.metadata,
            NOW(),
            NOW()
        FROM "{schema}".organizations AS organization
        CROSS JOIN (
            VALUES
                (
                    'generic_text',
                    'Generic Text',
                    'Text documents',
                    'text_files',
                    '[".txt", ".md", ".json"]'::json,
                    10,
                    '{{
                        "llm_mode_default": "extract",
                        "_provisioned_by_migration": "202607270001"
                    }}'::json
                ),
                (
                    'generic_document',
                    'Generic Document',
                    'PDF and office documents',
                    'documents',
                    '[".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".png", ".jpg"]'::json,
                    20,
                    '{{
                        "llm_mode_default": "full",
                        "_provisioned_by_migration": "202607270001"
                    }}'::json
                ),
                (
                    'org_logo',
                    'Organization Logo',
                    'Organization branding logo image',
                    'branding',
                    '[".png", ".jpg", ".jpeg", ".svg", ".webp"]'::json,
                    5,
                    '{{"_provisioned_by_migration": "202607270001"}}'::json
                )
        ) AS defaults (
            type_id,
            display_name,
            description,
            folder,
            allowed_extensions,
            max_size_mb,
            metadata
        )
        WHERE organization.status = 'active'
        ON CONFLICT (organization_id, type_id) DO NOTHING
        """
    )


def downgrade() -> None:
    schema = _schema()
    op.get_bind().exec_driver_sql(
        f"""
        DELETE FROM "{schema}".file_types AS file_type
        WHERE file_type.metadata->>'_provisioned_by_migration' = '202607270001'
          AND NOT EXISTS (
              SELECT 1
              FROM "{schema}".files AS file
              WHERE file.organization_id = file_type.organization_id
                AND file.type_id = file_type.type_id
          )
        """
    )

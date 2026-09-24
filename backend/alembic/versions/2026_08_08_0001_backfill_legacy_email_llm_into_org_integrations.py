"""Backfill legacy email_configs and llm_api_keys into organization_integrations.

Copies any credentials still living in the legacy per-capability stores into the
canonical organization_integrations table, re-encrypting the secrets into the
single encrypted_secret_config blob that store expects. Idempotent: a provider
already present for an org is left untouched. The follow-up revision
(202608080002) drops the legacy tables.

Revision ID: 202608080001
Revises: 202607180001
Create Date: 2026-08-08
"""

from __future__ import annotations

import json
import os
import uuid

import sqlalchemy as sa

from alembic import op

revision = "202608080001"
down_revision = "202607180001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")

# Legacy llm_api_keys.provider -> integrations registry provider name.
_LLM_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google_gemini",
}

_INSERT_INTEGRATION = """
    INSERT INTO "{schema}".organization_integrations
        (id, organization_id, provider, auth_type, capabilities, display_name,
         status, config, encrypted_secret_config, secret_hints,
         validation_status, last_validated_at, last_error)
    SELECT :id, :organization_id, :provider, :auth_type,
           CAST(:capabilities AS json), NULL, 'configured',
           CAST(:config AS json), :encrypted_secret_config,
           CAST(:secret_hints AS json), :validation_status, :last_validated_at, NULL
    WHERE NOT EXISTS (
        SELECT 1 FROM "{schema}".organization_integrations
        WHERE organization_id = :organization_id AND provider = :provider
    )
"""


def _hint(value: str | None) -> str:
    """Masked display hint, e.g. 'AKIA...KT6L'."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _insert(conn, *, org_id, provider, auth_type, capabilities, config, secrets,
            validation_status, last_validated_at, enc) -> None:
    secret_hints = {k: _hint(v) for k, v in secrets.items()}
    conn.execute(
        sa.text(_INSERT_INTEGRATION.format(schema=_schema)),
        {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "provider": provider,
            "auth_type": auth_type,
            "capabilities": json.dumps(capabilities),
            "config": json.dumps(config),
            "encrypted_secret_config": enc.encrypt(json.dumps(secrets)),
            "secret_hints": json.dumps(secret_hints),
            "validation_status": validation_status,
            "last_validated_at": last_validated_at,
        },
    )


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT to_regclass(:qualified)"),
            {"qualified": f'"{_schema}".{name}'},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()

    email_rows = (
        list(conn.execute(sa.text(f'SELECT * FROM "{_schema}".email_configs')).mappings())
        if _table_exists(conn, "email_configs")
        else []
    )
    llm_rows = (
        list(conn.execute(sa.text(f'SELECT * FROM "{_schema}".llm_api_keys')).mappings())
        if _table_exists(conn, "llm_api_keys")
        else []
    )

    # No legacy data: pure no-op. Never touch the encryption service (so this
    # migration runs in environments where the key is absent and there is
    # nothing to migrate).
    if not email_rows and not llm_rows:
        return

    from common.encryption import get_encryption_service

    enc = get_encryption_service()

    for row in email_rows:
        provider = row["provider"]
        common = {
            "org_id": row["organization_id"],
            "provider": provider,
            "capabilities": ["communication"],
            "validation_status": row.get("validation_status"),
            "last_validated_at": row.get("last_validated_at"),
            "enc": enc,
        }
        if provider == "smtp":
            _insert(
                conn,
                auth_type="basic_auth",
                config={
                    "smtp_host": row.get("smtp_host"),
                    "smtp_port": row.get("smtp_port"),
                    "smtp_use_tls": row.get("smtp_use_tls"),
                    "from_email": row.get("from_email"),
                    "from_name": row.get("from_name"),
                    "reply_to_email": row.get("reply_to_email"),
                },
                secrets={
                    "username": enc.decrypt(row["encrypted_access_key_id"]),
                    "password": enc.decrypt(row["encrypted_secret_key"]),
                },
                **common,
            )
        elif provider == "ses":
            _insert(
                conn,
                auth_type="access_key_secret",
                config={
                    "region": row.get("region"),
                    "from_email": row.get("from_email"),
                    "from_name": row.get("from_name"),
                    "reply_to_email": row.get("reply_to_email"),
                },
                secrets={
                    "aws_access_key_id": enc.decrypt(row["encrypted_access_key_id"]),
                    "aws_secret_access_key": enc.decrypt(row["encrypted_secret_key"]),
                },
                **common,
            )
        elif provider == "azure_communication":
            _insert(
                conn,
                auth_type="custom",
                config={
                    "endpoint": row.get("acs_endpoint"),
                    "from_email": row.get("from_email"),
                    "from_name": row.get("from_name"),
                    "reply_to_email": row.get("reply_to_email"),
                },
                secrets={
                    "connection_string": enc.decrypt(row["encrypted_connection_string"])
                    if row.get("encrypted_connection_string")
                    else "",
                },
                **common,
            )
        # Unknown providers are skipped intentionally.

    for row in llm_rows:
        provider = _LLM_PROVIDER_MAP.get(row["provider"])
        if provider is None:
            continue
        _insert(
            conn,
            org_id=row["organization_id"],
            provider=provider,
            auth_type="api_key",
            capabilities=["llm"],
            config={},
            secrets={"api_key": enc.decrypt(row["encrypted_key"])},
            validation_status=row.get("validation_status"),
            last_validated_at=row.get("last_validated_at"),
            enc=enc,
        )


def downgrade() -> None:
    # Data backfill is intentionally not reversed: the copied rows are now the
    # canonical credentials in organization_integrations and cannot be safely
    # distinguished from natively-created ones. Downgrading this revision only
    # re-forks the history back to the two prior heads.
    pass

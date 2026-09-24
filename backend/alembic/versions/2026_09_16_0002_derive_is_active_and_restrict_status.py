"""Derive users.is_active from status; restrict status to the lifecycle values.

Two coupled schema changes that make the account sign-in switch impossible to
leave inconsistent:

  1. `users.is_active` becomes a GENERATED column computed as `status = 'active'`.
     Application code no longer writes it (the ORM column is `Computed`), so it can
     never drift from the account's lifecycle label again. Postgres cannot alter a
     plain column into a stored generated one in place, so the column is dropped and
     re-added — the re-add recomputes every existing row automatically.
  2. `users.status` is restricted to `('pending','active','rejected')` via a CHECK
     constraint. Account-level 'suspended' is retired; suspension now lives per-org
     on `user_organizations.status`.
  3. `user_organizations.status` is restricted to `('active','suspended')` via a
     CHECK constraint, so per-org membership status is DB-enforced too — mirroring
     the account-level restriction for a consistent, guaranteed shape on both tables.
     Any legacy membership status outside ('active','suspended') is normalized to
     'suspended' first, so ADD CONSTRAINT's full-table validation can't fail on a
     pre-existing row (idempotent; 0 rows on a clean database).

Depends on the repair migration (202609160001) having already converted any
account-level 'suspended' rows — the CHECK cannot be created while such rows exist.

Revision ID: 202609160002
Revises: 202609160001
Create Date: 2026-09-16
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202609160002"
down_revision = "202609160001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")
_STATUS_CHECK = "ck_users_status_lifecycle"
_MEMBERSHIP_STATUS_CHECK = "ck_user_organizations_status"


def upgrade() -> None:
    op.drop_column("users", "is_active", schema=_schema)
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            sa.Computed("status = 'active'", persisted=True),
            nullable=False,
        ),
        schema=_schema,
    )
    op.create_check_constraint(
        _STATUS_CHECK,
        "users",
        "status IN ('pending', 'active', 'rejected')",
        schema=_schema,
    )
    # Normalize any legacy out-of-range membership status before constraining, so
    # ADD CONSTRAINT can't fail its full-table validation on pre-existing rows.
    # Idempotent: 0 rows on a clean database. 'suspended' (not delete) preserves
    # the row and matches runtime behaviour — the app already treats any
    # non-'active' membership as no-access.
    op.execute(
        sa.text(
            f"UPDATE \"{_schema}\".user_organizations "
            f"SET status = 'suspended' "
            f"WHERE status NOT IN ('active', 'suspended')"
        )
    )
    op.create_check_constraint(
        _MEMBERSHIP_STATUS_CHECK,
        "user_organizations",
        "status IN ('active', 'suspended')",
        schema=_schema,
    )


def downgrade() -> None:
    # IF EXISTS keeps downgrade idempotent whether or not each CHECK was present.
    op.execute(
        sa.text(
            f'ALTER TABLE "{_schema}".user_organizations '
            f"DROP CONSTRAINT IF EXISTS {_MEMBERSHIP_STATUS_CHECK}"
        )
    )
    op.execute(
        sa.text(f'ALTER TABLE "{_schema}".users DROP CONSTRAINT IF EXISTS {_STATUS_CHECK}')
    )
    op.drop_column("users", "is_active", schema=_schema)
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        schema=_schema,
    )
    op.execute(
        sa.text(
            f'UPDATE "{_schema}".users SET is_active = (status = \'active\')'
        )
    )

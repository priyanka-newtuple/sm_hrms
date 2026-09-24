"""Repair globally-suspended accounts into the per-org suspension model.

Before this change, suspending a user set the account-level `users.status` to
'suspended' (and, due to a bug, left `is_active` true). Suspension is meant to be
per-organization. This migration converts every account currently flagged
'suspended' into the correct shape:

  1. Suspend that user's *active* memberships (`user_organizations.status`) — this
     preserves their current effective "no access anywhere" state, now recorded
     per-org where access is actually enforced.
  2. Restore the account label to 'active' — the account is a valid, real account;
     it just has no active org membership until an admin reactivates one.

Runs before the follow-up migration that adds the
`status IN ('pending','active','rejected')` CHECK constraint — that constraint
cannot be created while any account row is still 'suspended', so the repair must
come first.

Idempotent and safe on any dataset: both statements key off `status = 'suspended'`,
so on a database with no such accounts (e.g. a developer's local copy) they update
zero rows, and re-running is a no-op. Downgrade is intentionally a no-op — we do
not re-introduce the previous (buggy) global-suspension state.

Revision ID: 202609160001
Revises: 202609150001
Create Date: 2026-09-16
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "202609160001"
down_revision = "202609150001"
branch_labels = None
depends_on = None

_schema = os.environ.get("POSTGRES_APP_SCHEMA", "public")


def upgrade() -> None:
    # 1) Suspend the access-granting memberships of every account-suspended user.
    op.execute(
        sa.text(
            f'UPDATE "{_schema}".user_organizations '
            f"SET status = 'suspended' "
            f"WHERE status = 'active' "
            f'AND user_id IN (SELECT id FROM "{_schema}".users WHERE status = '
            f"'suspended')"
        )
    )
    # 2) Restore the account label so the account can authenticate again; the
    #    per-org suspension above is what now withholds access.
    op.execute(
        sa.text(
            f'UPDATE "{_schema}".users SET status = \'active\' WHERE status = '
            f"'suspended'"
        )
    )


def downgrade() -> None:
    # Data repair — not reversible without re-introducing the previous buggy
    # global-suspension state, which we deliberately will not do.
    pass

"""crud fields: codes, statuses, offboarding, allocation capacity

Revision ID: 28b7a3764fe6
Revises: fe5e5a4d0cc6
Create Date: 2026-08-28 11:18:40.521112

Hand-adjusted after autogenerate. Autogenerate cannot know how to fill NOT NULL
columns on rows that already exist, and it does not detect new values added to an
existing enum type — both are handled explicitly below. New required columns are
therefore added nullable, back-filled, then tightened to NOT NULL, so an existing
seeded database upgrades in place rather than needing a re-seed.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "28b7a3764fe6"
down_revision: Union[str, None] = "fe5e5a4d0cc6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


allocation_status = sa.Enum(
    "PLANNED", "ACTIVE", "COMPLETED", "CANCELLED", name="allocation_status"
)
customer_status = sa.Enum("PROSPECT", "ACTIVE", "ON_HOLD", "ARCHIVED", name="customer_status")
employment_type = sa.Enum("FULL_TIME", "CONTRACT", "INTERN", name="employment_type")
exit_type = sa.Enum(
    "RESIGNATION", "TERMINATION", "END_OF_CONTRACT", "RETIREMENT", name="exit_type"
)
engagement_type = sa.Enum(
    "TIME_AND_MATERIALS", "FIXED_BID", "RETAINER", name="engagement_type"
)
project_health = sa.Enum("GREEN", "AMBER", "RED", name="project_health")


def upgrade() -> None:
    bind = op.get_bind()

    # --- new enum types -----------------------------------------------------
    for enum_type in (
        allocation_status, customer_status, employment_type,
        exit_type, engagement_type, project_health,
    ):
        enum_type.create(bind, checkfirst=True)

    # Projects gain an ARCHIVED state (archive-only policy — nothing is deleted).
    # ALTER TYPE ... ADD VALUE is not detected by autogenerate.
    op.execute("ALTER TYPE project_status ADD VALUE IF NOT EXISTS 'ARCHIVED'")

    # --- allocations --------------------------------------------------------
    op.add_column(
        "allocations",
        sa.Column("status", allocation_status, nullable=False, server_default="ACTIVE"),
    )
    op.add_column(
        "allocations",
        sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("allocations", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("allocations", sa.Column("allocated_by_id", sa.UUID(), nullable=True))
    op.add_column(
        "allocations",
        sa.Column("billing_rate_override", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.create_foreign_key(
        "fk_allocations_allocated_by", "allocations", "employees", ["allocated_by_id"], ["id"]
    )

    # --- customers ----------------------------------------------------------
    op.add_column("customers", sa.Column("code", sa.String(length=20), nullable=True))
    op.add_column(
        "customers",
        sa.Column("status", customer_status, nullable=False, server_default="ACTIVE"),
    )
    op.add_column("customers", sa.Column("account_owner_id", sa.UUID(), nullable=True))
    op.add_column("customers", sa.Column("contract_start_date", sa.Date(), nullable=True))
    op.add_column("customers", sa.Column("contract_end_date", sa.Date(), nullable=True))
    op.add_column(
        "customers",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
    )
    op.add_column("customers", sa.Column("payment_terms_days", sa.Integer(), nullable=True))
    op.add_column("customers", sa.Column("billing_address", sa.String(length=500), nullable=True))
    op.add_column("customers", sa.Column("country", sa.String(length=100), nullable=True))
    op.add_column("customers", sa.Column("notes", sa.Text(), nullable=True))

    # Back-fill customer codes deterministically by creation order.
    op.execute(
        """
        UPDATE customers AS c SET code = numbered.generated_code
        FROM (
            SELECT id, 'CUS-' || LPAD(ROW_NUMBER() OVER (ORDER BY created_at, id)::text, 4, '0')
                   AS generated_code
            FROM customers
        ) AS numbered
        WHERE c.id = numbered.id AND c.code IS NULL
        """
    )
    op.alter_column("customers", "code", nullable=False)
    op.create_unique_constraint("uq_customers_code", "customers", ["code"])
    op.create_foreign_key(
        "fk_customers_account_owner", "customers", "employees", ["account_owner_id"], ["id"]
    )

    # --- employees ----------------------------------------------------------
    op.add_column(
        "employees",
        sa.Column(
            "employment_type", employment_type, nullable=False, server_default="FULL_TIME"
        ),
    )
    op.add_column("employees", sa.Column("work_location", sa.String(length=100), nullable=True))
    op.add_column("employees", sa.Column("probation_end_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("confirmation_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("notice_period_days", sa.Integer(), nullable=True))
    op.add_column("employees", sa.Column("last_working_day", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("exit_type", exit_type, nullable=True))
    op.add_column("employees", sa.Column("exit_reason", sa.Text(), nullable=True))
    op.add_column("employees", sa.Column("rehire_eligible", sa.Boolean(), nullable=True))

    # --- projects -----------------------------------------------------------
    op.add_column("projects", sa.Column("code", sa.String(length=20), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "engagement_type",
            engagement_type,
            nullable=False,
            server_default="TIME_AND_MATERIALS",
        ),
    )
    op.add_column(
        "projects",
        sa.Column("health", project_health, nullable=False, server_default="GREEN"),
    )
    op.add_column(
        "projects",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
    )
    op.add_column("projects", sa.Column("practice", sa.String(length=100), nullable=True))
    op.add_column("projects", sa.Column("budgeted_hours", sa.Integer(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("budget_amount", sa.Numeric(precision=14, scale=2), nullable=True),
    )

    op.execute(
        """
        UPDATE projects AS p SET code = numbered.generated_code
        FROM (
            SELECT id, 'PRJ-' || LPAD(ROW_NUMBER() OVER (ORDER BY created_at, id)::text, 4, '0')
                   AS generated_code
            FROM projects
        ) AS numbered
        WHERE p.id = numbered.id AND p.code IS NULL
        """
    )
    op.alter_column("projects", "code", nullable=False)
    op.create_unique_constraint("uq_projects_code", "projects", ["code"])


def downgrade() -> None:
    op.drop_constraint("uq_projects_code", "projects", type_="unique")
    for column in (
        "budget_amount", "budgeted_hours", "practice", "currency",
        "health", "engagement_type", "code",
    ):
        op.drop_column("projects", column)

    for column in (
        "rehire_eligible", "exit_reason", "exit_type", "last_working_day",
        "notice_period_days", "confirmation_date", "probation_end_date",
        "work_location", "employment_type",
    ):
        op.drop_column("employees", column)

    op.drop_constraint("fk_customers_account_owner", "customers", type_="foreignkey")
    op.drop_constraint("uq_customers_code", "customers", type_="unique")
    for column in (
        "notes", "country", "billing_address", "payment_terms_days", "currency",
        "contract_end_date", "contract_start_date", "account_owner_id", "status", "code",
    ):
        op.drop_column("customers", column)

    op.drop_constraint("fk_allocations_allocated_by", "allocations", type_="foreignkey")
    for column in (
        "billing_rate_override", "allocated_by_id", "notes", "billable", "status",
    ):
        op.drop_column("allocations", column)

    bind = op.get_bind()
    for enum_type in (
        project_health, engagement_type, exit_type,
        employment_type, customer_status, allocation_status,
    ):
        enum_type.drop(bind, checkfirst=True)
    # Note: the ARCHIVED value added to project_status is intentionally left in
    # place — PostgreSQL cannot remove a single enum value without rebuilding
    # the type, and leaving it is harmless.

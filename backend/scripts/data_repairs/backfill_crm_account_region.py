"""Backfill account.region on the 2 oldest accounts in the "CRM" org.

One-time, org-specific content fix - two UPDATE statements against two known
rows - not a schema change, so it lives here rather than in the Alembic
chain, the same way migrate_forms_to_method_blocks.py does for the wider
field-library rollout.

`region` is a real, actively-used field on the account form - every account
created after 2026-07-20 has it - except the very first two accounts this
org ever created (InRiver AB and Michelin Group), which predate the field
coming into use. Full investigation in design_docs/PROD_MIGRATION_RUNBOOK.md.

Unlike the project_start_date case, there is no need to invent a value: both
companies were independently re-entered as duplicate account records about a
day later, and those duplicates already have `region` filled in correctly
(InRiver AB -> "north_america", Michelin Group -> "europe"). This copies
those already-confirmed values onto the two original records.

Scoped to exactly the two known records (not a generic "any account missing
region" sweep) - these are the two specific rows the audit found, and
nothing else in this org is missing the field.

Idempotent: only fills the key in where it is still missing. Dry run is the
default and writes nothing; --apply performs the writes inside one
transaction. --revert removes the value, but only if it still matches
exactly what this script set (see `revert`).

Run from backend/ with the app's environment (DATABASE_URL or PG* vars,
POSTGRES_APP_SCHEMA):

    python scripts/data_repairs/backfill_crm_account_region.py             # dry run
    python scripts/data_repairs/backfill_crm_account_region.py --apply     # write
    python scripts/data_repairs/backfill_crm_account_region.py --revert --apply   # undo
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

ORG_NAME = "CRM"
ENTITY_TYPE_NAME = "account"
FIELD_KEY = "region"

# (entity_id, value) - value taken from each company's own duplicate account
# record, which already had `region` filled in correctly.
BACKFILL = (
    ("5a8708a6-9249-44b7-84ba-39fe18a08e25", "north_america"),  # InRiver AB
    ("f759dd57-0edf-461b-b4f2-6f1c8efec490", "europe"),  # Michelin Group
)


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _runtime_schema() -> str:
    return f"{_app_schema()}_runtime"


def _engine():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required (same env the app itself uses).")
    return create_engine(dsn)


def apply_(conn, *, write: bool) -> dict:
    runtime = _runtime_schema()
    report: dict = {"org_found": False, "rows_updated": []}

    org_id = conn.execute(
        sa.text(f'SELECT id FROM "{_app_schema()}".organizations WHERE name = :name'),
        {"name": ORG_NAME},
    ).scalar()
    if org_id is None:
        return report
    report["org_found"] = True

    for entity_id, value in BACKFILL:
        missing = conn.execute(
            sa.text(
                f'SELECT 1 FROM "{runtime}".entities '
                f"WHERE organization_id = :org_id AND entity_id = :entity_id "
                f"  AND NOT (data ? '{FIELD_KEY}')"
            ),
            {"org_id": org_id, "entity_id": entity_id},
        ).first()
        if missing is None:
            continue
        report["rows_updated"].append({"entity_id": entity_id, "value": value})
        if write:
            conn.execute(
                sa.text(
                    f'UPDATE "{runtime}".entities '
                    f"SET data = data || jsonb_build_object('{FIELD_KEY}', :value), "
                    f"    updated_at = now() "
                    f"WHERE organization_id = :org_id "
                    f"  AND entity_id = :entity_id "
                    f"  AND NOT (data ? '{FIELD_KEY}')"
                ),
                {"org_id": org_id, "entity_id": entity_id, "value": value},
            )
    return report


def revert(conn, *, write: bool) -> dict:
    """Only removes the value if it still matches exactly what this script
    set - if someone has since edited it by hand, revert leaves it alone
    rather than discarding their edit."""
    runtime = _runtime_schema()
    report: dict = {"org_found": False, "rows_cleared": []}

    org_id = conn.execute(
        sa.text(f'SELECT id FROM "{_app_schema()}".organizations WHERE name = :name'),
        {"name": ORG_NAME},
    ).scalar()
    if org_id is None:
        return report
    report["org_found"] = True

    for entity_id, value in BACKFILL:
        matches = conn.execute(
            sa.text(
                f'SELECT 1 FROM "{runtime}".entities '
                f"WHERE organization_id = :org_id AND entity_id = :entity_id "
                f"  AND data->>'{FIELD_KEY}' = :value"
            ),
            {"org_id": org_id, "entity_id": entity_id, "value": value},
        ).first()
        if matches is None:
            continue
        report["rows_cleared"].append({"entity_id": entity_id, "value": value})
        if write:
            conn.execute(
                sa.text(
                    f'UPDATE "{runtime}".entities '
                    f"SET data = data - '{FIELD_KEY}', updated_at = now() "
                    f"WHERE organization_id = :org_id "
                    f"  AND entity_id = :entity_id "
                    f"  AND data->>'{FIELD_KEY}' = :value"
                ),
                {"org_id": org_id, "entity_id": entity_id, "value": value},
            )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write. Default is a dry run.")
    parser.add_argument("--revert", action="store_true", help="Undo instead of apply.")
    args = parser.parse_args()

    engine = _engine()
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            report = revert(conn, write=args.apply) if args.revert else apply_(conn, write=args.apply)
        except Exception:
            trans.rollback()
            raise
        if args.apply:
            trans.commit()
        else:
            trans.rollback()

    mode = "REVERT" if args.revert else "APPLY"
    print(f"[{mode}] {'(dry run, nothing written)' if not args.apply else '(written)'}")
    print(json.dumps(report, indent=2))
    if not report.get("org_found"):
        print(f'Org "{ORG_NAME}" not found in this database - nothing to do.')


if __name__ == "__main__":
    main()

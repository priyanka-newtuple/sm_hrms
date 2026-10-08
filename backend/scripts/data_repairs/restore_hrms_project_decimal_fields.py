"""Restore the HRMS Project Form's money/hours fields to `float` before the Form migration.

Same shape of fix as the other scripts in this directory: a one-time content fix
to one Form's fields_json, not a schema change, so it does not go through Alembic.

Why it's needed: saving `hrms_project_form_v1` through Settings -> Forms ran the
editor's lossy type mapping (float -> "Integer" -> int), so the Form now says
`budget_amount`, `billing_rate` and `planned_hours` are `int`. The published
Project workflow still says `float`, and the HRMS application sends these as
decimals (`project_contracts.ProjectInput`: `float`, so even 0 goes out as 0.0).
scripts/migrate_forms_to_method_blocks.py publishes each field with its Form's
type, so without this fix it would retype them to `int` and every Project
create would fail "expects type 'int', got 'float'".

The fix: set those three fields back to `float`, which the migration then lands
on the Field Library's Decimal type (alembic 202610080001). Nothing else on the
Form is touched; records are never touched.

Idempotent: fields already `float` are left alone. Dry run is the default and
writes nothing; --apply performs the write. --revert sets them back to `int`.

Run from backend/ with the app's environment (DATABASE_URL, POSTGRES_APP_SCHEMA),
BEFORE scripts/migrate_forms_to_method_blocks.py:

    python scripts/data_repairs/restore_hrms_project_decimal_fields.py             # dry run
    python scripts/data_repairs/restore_hrms_project_decimal_fields.py --apply     # write
    python scripts/data_repairs/restore_hrms_project_decimal_fields.py --revert --apply   # undo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlalchemy as sa
from sqlalchemy import create_engine

ENTITY_TYPE_NAME = "HRMS.Project"
SCHEMA_KEY = "hrms_project_form_v1"
FIELD_KEYS = ("budget_amount", "billing_rate", "planned_hours")
DECIMAL_TYPE = "float"
DRIFTED_TYPE = "int"


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _definitions_schema() -> str:
    return f"{_app_schema()}_definitions"


def _content_hash(entity_type: str, fields: list[dict]) -> str:
    """Mirrors forms.db_models.schema_content_hash exactly - not imported,
    since this script only ever reaches the database directly."""
    serialized = json.dumps(
        {"entity_type": entity_type, "fields": fields},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


def _engine():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required (same env the app itself uses).")
    return create_engine(dsn)


def retype(conn, *, from_type: str, to_type: str, write: bool) -> dict:
    """Retype FIELD_KEYS from `from_type` to `to_type` on every active copy of the Form."""
    report: dict = {"forms_found": 0, "changed": []}
    rows = conn.execute(
        sa.text(
            f'SELECT id, organization_id, fields_json FROM "{_definitions_schema()}".entity_type_schema '
            f"WHERE schema_key = :schema_key AND is_active = true"
        ),
        {"schema_key": SCHEMA_KEY},
    ).all()
    report["forms_found"] = len(rows)
    for schema_id, org_id, fields_json in rows:
        fields = _as_list(fields_json)
        changed = [
            f["field"]
            for f in fields
            if f.get("field") in FIELD_KEYS and f.get("type") == from_type
        ]
        if not changed:
            continue
        report["changed"].append({"organization_id": org_id, "fields": changed, "to": to_type})
        if not write:
            continue
        new_fields = [{**f, "type": to_type} if f.get("field") in changed else f for f in fields]
        conn.execute(
            sa.text(
                f'UPDATE "{_definitions_schema()}".entity_type_schema '
                f"SET fields_json = CAST(:fields_json AS JSONB), "
                f"    content_hash = :content_hash, "
                f"    updated_at = now() "
                f"WHERE id = :schema_id"
            ),
            {
                "fields_json": json.dumps(new_fields),
                "content_hash": _content_hash(ENTITY_TYPE_NAME, new_fields),
                "schema_id": schema_id,
            },
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write. Default is a dry run.")
    parser.add_argument("--revert", action="store_true", help="Undo instead of apply.")
    args = parser.parse_args()

    from_type, to_type = (
        (DECIMAL_TYPE, DRIFTED_TYPE) if args.revert else (DRIFTED_TYPE, DECIMAL_TYPE)
    )
    engine = _engine()
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            report = retype(conn, from_type=from_type, to_type=to_type, write=args.apply)
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
    if not report["forms_found"]:
        print(f"No active '{SCHEMA_KEY}' Form in this database - nothing to do.")
    elif report["changed"] and args.apply and not args.revert:
        print("Next: run scripts/migrate_forms_to_method_blocks.py (dry run, then --apply).")


if __name__ == "__main__":
    main()

"""Add `project_projectname` to the active `project_task` Form in "Project
Mangement Workflow" - the fix for the "kaituple development" workflow.

Same shape of fix, same script, as add_project_details_field.py - just a
different workflow in the same org. A one-time, org-specific content fix
(one field appended to one Form's fields_json), not a schema change, so it
does not go through Alembic.

Why it's needed: the "kaituple development" workflow (machine_name
`workflow_vnpmtyn2_xc78nj`, entity type `project_task`) already has a
`project_projectname` field pinned into its published entity_schema (type
`string`, `source_states: []`, meaning nothing currently supplies it), but
no active Form defines the field - so validation on the merged branch
correctly flags it under "workflow entity_schema contains fields no active
form defines" (see the mismatch table in
design_docs/PROD_MIGRATION_RUNBOOK.md, step 7). The field existed once;
there is no way to recover what removed it, and re-adding it to the Form is
the right fix precisely because the workflow itself never stopped
declaring it.

The fix: add `project_projectname` (type `string`, matching what the
workflow already expects, label "Projectname" per the workflow's own
`description` for the field) as a plain field on the
`project_task__project_name` Form, alongside its existing ticket_id, title,
etc. fields - not routed through the Field Library up front, the same way
those aren't. Once it's a real Form field, re-running
scripts/migrate_forms_to_method_blocks.py with
--sync-plain-fields project_task__project_name picks it up and tops up the
org's existing 'Project Task Form' Method Block with it (a fresh block
would pick it up on its own; this Form's block already exists from an
earlier run, so it needs the explicit top-up opt-in - see that script's
own docstring for why it doesn't do this automatically):

    Form (ticket_id, title, ..., project_projectname)
      -> Method Block (topped up with project_projectname)
      -> Workflow (already expects project_projectname)
      -> match, publish succeeds

Idempotent: a no-op if the field is already on the Form. Dry run is the
default and writes nothing; --apply performs the write. --revert removes
the field from the Form only (never touches records' data - the field only
ever holds the empty-string default in the workflow's own persisted
schema, so there is nothing backfilled to undo).

Run from backend/ with the app's environment (DATABASE_URL or PG* vars,
POSTGRES_APP_SCHEMA):

    python scripts/data_repairs/add_project_task_projectname_field.py             # dry run
    python scripts/data_repairs/add_project_task_projectname_field.py --apply     # write
    python scripts/data_repairs/add_project_task_projectname_field.py --revert --apply   # undo

Then re-run scripts/migrate_forms_to_method_blocks.py --apply
--sync-plain-fields project_task__project_name to publish the field into
the workflow's Method Block.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

ORG_NAME = "Project Mangement Workflow"
ENTITY_TYPE_NAME = "project_task"
SCHEMA_KEY = "project_task__project_name"
FIELD_KEY = "project_projectname"
FIELD_LABEL = "Projectname"
FIELD_TYPE = "string"

NEW_FIELD = {
    "calc": None,
    "type": FIELD_TYPE,
    "field": FIELD_KEY,
    "source": None,
    "default": None,
    "col_span": None,
    "editable": None,
    "nullable": True,
    "required": False,
    "ownership": None,
    "description": FIELD_LABEL,
    "enum_values": [],
    "picklist_id": None,
    "placeholder": None,
    "table_config": None,
    "currency_config": None,
    "document_config": None,
    "auto_number_config": None,
}


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


def _find_schema(conn, org_id: str):
    return conn.execute(
        sa.text(
            f'SELECT id, fields_json FROM "{_definitions_schema()}".entity_type_schema '
            f"WHERE organization_id = :org_id AND schema_key = :schema_key "
            f"AND is_active = true"
        ),
        {"org_id": org_id, "schema_key": SCHEMA_KEY},
    ).first()


def apply_(conn, *, write: bool) -> dict:
    report: dict = {"org_found": False, "schema_found": False, "field_added": False}

    org_id = conn.execute(
        sa.text(f'SELECT id FROM "{_app_schema()}".organizations WHERE name = :name'),
        {"name": ORG_NAME},
    ).scalar()
    if org_id is None:
        return report
    report["org_found"] = True

    schema_row = _find_schema(conn, org_id)
    if schema_row is None:
        return report
    report["schema_found"] = True

    schema_id, fields_json = schema_row
    fields = _as_list(fields_json)
    if any(f.get("field") == FIELD_KEY for f in fields):
        # Already there - nothing to do.
        return report

    report["field_added"] = True
    if not write:
        return report

    new_fields = [*fields, NEW_FIELD]
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


def revert(conn, *, write: bool) -> dict:
    report: dict = {"org_found": False, "schema_found": False, "field_removed": False}

    org_id = conn.execute(
        sa.text(f'SELECT id FROM "{_app_schema()}".organizations WHERE name = :name'),
        {"name": ORG_NAME},
    ).scalar()
    if org_id is None:
        return report
    report["org_found"] = True

    schema_row = _find_schema(conn, org_id)
    if schema_row is None:
        return report
    report["schema_found"] = True

    schema_id, fields_json = schema_row
    fields = _as_list(fields_json)
    remaining = [f for f in fields if f.get("field") != FIELD_KEY]
    if len(remaining) == len(fields):
        # Wasn't there - nothing to do.
        return report

    report["field_removed"] = True
    if not write:
        return report

    conn.execute(
        sa.text(
            f'UPDATE "{_definitions_schema()}".entity_type_schema '
            f"SET fields_json = CAST(:fields_json AS JSONB), "
            f"    content_hash = :content_hash, "
            f"    updated_at = now() "
            f"WHERE id = :schema_id"
        ),
        {
            "fields_json": json.dumps(remaining),
            "content_hash": _content_hash(ENTITY_TYPE_NAME, remaining),
            "schema_id": schema_id,
        },
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
    elif report.get("field_added") and args.apply:
        print(
            "Next: re-run scripts/migrate_forms_to_method_blocks.py --apply "
            "--sync-plain-fields project_task__project_name to publish it."
        )


if __name__ == "__main__":
    main()

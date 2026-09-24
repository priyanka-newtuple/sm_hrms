"""Backfill project_start_date for the "Project Mangement Workflow" org.

This is a one-time, org-specific content fix, not a schema change - it
inserts rows (a field_library_fields entry, a version, a link into one
Form) and updates the `fields_json`/`data` of records that already belong
to one named organization. Nothing here alters a table's structure, so it
lives here rather than in the Alembic chain, the same way
migrate_forms_to_method_blocks.py does for the wider field-library rollout.

Investigation (full detail in design_docs/PROD_MIGRATION_RUNBOOK.md): the
entity_type_relations row linking `project` -> `project_task` declares
relation_metadata {"project.project_start_date":
"project_task.project_project_start_date"}, meaning a project_task's
project_project_start_date is supposed to be derived live from its parent
project's project_start_date. `project_task.project_project_start_date` is
a real, deliberately configured field. But `project` was never given a
matching `project_start_date` field at all, on any of the 6 project
records this org has ever created - so the relation has never once
resolved, on any of its 298 project_task rows.

This script does two things, in order, both scoped to this one org by name
and a no-op everywhere else:

  1. Gives `project` a real `project_start_date` field the same way the app
     itself would: a field_library_fields row + version + a link into the
     `project__project_name` form, with the merged projection appended to
     entity_type_schema.fields_json. Modeled as `datetime`, matching the
     equivalent field already used for this exact concept on `dm_project`.
  2. Backfills `project_start_date` on every project record in this org
     with the one honest, non-invented value available: the project's own
     `created_at`. There is no true recorded start date anywhere in this
     data; nobody ever typed one in. Only fills the key in when it is
     still missing, so a value a person enters by hand later is never
     overwritten by re-running this script.

Idempotent: safe to run repeatedly against the same database. Dry run is
the default and writes nothing; --apply performs the writes inside one
transaction. --revert undoes it (drops the field and the backfilled key;
see the docstring on `revert` for what that does and does not undo).

Run from backend/ with the app's environment (DATABASE_URL or PG* vars,
POSTGRES_APP_SCHEMA):

    python scripts/data_repairs/backfill_project_start_date.py             # dry run
    python scripts/data_repairs/backfill_project_start_date.py --apply     # write
    python scripts/data_repairs/backfill_project_start_date.py --revert --apply   # undo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

ORG_NAME = "Project Mangement Workflow"
ENTITY_TYPE_NAME = "project"
SCHEMA_KEY = "project__project_name"
FIELD_KEY = "project_start_date"
FIELD_NAME = "Project Start Date"
FIELD_TYPE = "datetime"


def _app_schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _definitions_schema() -> str:
    return f"{_app_schema()}_definitions"


def _runtime_schema() -> str:
    return f"{_app_schema()}_runtime"


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


def apply_(conn, *, write: bool) -> dict:
    """Runs the plan. `write` gates whether anything is actually committed;
    with write=False every lookup still runs so the report is accurate,
    the mutating statements just aren't reached."""
    definitions = _definitions_schema()
    runtime = _runtime_schema()
    report: dict = {"org_found": False, "field_added": False, "records_backfilled": 0}

    org_id = conn.execute(
        sa.text(f'SELECT id FROM "{_app_schema()}".organizations WHERE name = :name'),
        {"name": ORG_NAME},
    ).scalar()
    if org_id is None:
        return report
    report["org_found"] = True

    entity_type_id = conn.execute(
        sa.text(
            f'SELECT entity_type_id FROM "{definitions}".entity_types '
            f"WHERE organization_id = :org_id AND name = :name"
        ),
        {"org_id": org_id, "name": ENTITY_TYPE_NAME},
    ).scalar()
    if entity_type_id is None:
        return report

    existing_field_id = conn.execute(
        sa.text(
            f'SELECT library_field_id FROM "{definitions}".field_library_fields '
            f"WHERE organization_id = :org_id AND lower(field_key) = lower(:field_key) "
            f"AND archived_at IS NULL"
        ),
        {"org_id": org_id, "field_key": FIELD_KEY},
    ).scalar()

    if existing_field_id is None:
        schema_row = conn.execute(
            sa.text(
                f'SELECT id, fields_json FROM "{definitions}".entity_type_schema '
                f"WHERE organization_id = :org_id AND schema_key = :schema_key "
                f"AND is_active = true"
            ),
            {"org_id": org_id, "schema_key": SCHEMA_KEY},
        ).first()

        if schema_row is not None:
            report["field_added"] = True
            if write:
                schema_id, fields_json = schema_row
                fields = _as_list(fields_json)

                library_field_id = str(uuid.uuid4())
                version_id = str(uuid.uuid4())

                conn.execute(
                    sa.text(
                        f'INSERT INTO "{definitions}".field_library_fields '
                        f"(library_field_id, organization_id, name, field_key, field_type, "
                        f" created_by, created_at, updated_at) "
                        f"VALUES (:id, :org_id, :name, :field_key, :field_type, "
                        f" NULL, now(), now())"
                    ),
                    {
                        "id": library_field_id,
                        "org_id": org_id,
                        "name": FIELD_NAME,
                        "field_key": FIELD_KEY,
                        "field_type": FIELD_TYPE,
                    },
                )
                conn.execute(
                    sa.text(
                        f'INSERT INTO "{definitions}".field_library_field_versions '
                        f"(version_id, library_field_id, organization_id, version, name, "
                        f" field_type, description, settings, is_latest, created_by, created_at) "
                        f"VALUES (:version_id, :library_field_id, :org_id, 1, :name, "
                        f" :field_type, :description, CAST(:settings AS JSONB), true, NULL, now())"
                    ),
                    {
                        "version_id": version_id,
                        "library_field_id": library_field_id,
                        "org_id": org_id,
                        "name": FIELD_NAME,
                        "field_type": FIELD_TYPE,
                        "description": FIELD_NAME,
                        "settings": json.dumps(
                            {
                                "calc": None,
                                "source": None,
                                "default": None,
                                "col_span": None,
                                "editable": None,
                                "nullable": True,
                                "required": False,
                                "ownership": None,
                                "enum_values": [],
                                "picklist_id": None,
                                "placeholder": "Project Start Date",
                                "table_config": None,
                                "currency_config": None,
                                "auto_number_config": None,
                            }
                        ),
                    },
                )

                position = len(fields)
                conn.execute(
                    sa.text(
                        f'INSERT INTO "{definitions}".entity_type_schema_fields '
                        f"(id, schema_id, version_id, library_field_id, organization_id, "
                        f" position, metadata, created_at, updated_at) "
                        f"VALUES (:id, :schema_id, :version_id, :library_field_id, :org_id, "
                        f" :position, '{{}}'::jsonb, now(), now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "schema_id": schema_id,
                        "version_id": version_id,
                        "library_field_id": library_field_id,
                        "org_id": org_id,
                        "position": position,
                    },
                )

                projection = {
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
                    "description": FIELD_NAME,
                    "enum_values": [],
                    "picklist_id": None,
                    "placeholder": "Project Start Date",
                    "table_config": None,
                    "currency_config": None,
                    "auto_number_config": None,
                    "name": FIELD_NAME,
                    "label": FIELD_NAME,
                    "library_field_id": library_field_id,
                    "field_version_id": version_id,
                }
                new_fields = [f for f in fields if f.get("field") != FIELD_KEY]
                new_fields.insert(position, projection)

                conn.execute(
                    sa.text(
                        f'UPDATE "{definitions}".entity_type_schema '
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

    to_backfill = conn.execute(
        sa.text(
            f'SELECT count(*) FROM "{runtime}".entities '
            f"WHERE organization_id = :org_id AND entity_type_id = :entity_type_id "
            f"  AND NOT (data ? '{FIELD_KEY}')"
        ),
        {"org_id": org_id, "entity_type_id": entity_type_id},
    ).scalar()
    report["records_backfilled"] = to_backfill or 0

    if write:
        conn.execute(
            sa.text(
                f'UPDATE "{runtime}".entities '
                f"SET data = data || jsonb_build_object("
                f"       '{FIELD_KEY}', to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI')"
                f"     ), "
                f"    updated_at = now() "
                f"WHERE organization_id = :org_id "
                f"  AND entity_type_id = :entity_type_id "
                f"  AND NOT (data ? '{FIELD_KEY}')"
            ),
            {"org_id": org_id, "entity_type_id": entity_type_id},
        )

    return report


def revert(conn, *, write: bool) -> dict:
    """Undoes the field and the backfilled key. Same tradeoff any downgrade
    here accepts: removes the field's value from every record that has it,
    including one a person typed in by hand after this script ran."""
    definitions = _definitions_schema()
    runtime = _runtime_schema()
    report: dict = {"org_found": False, "field_removed": False, "records_cleared": 0}

    org_id = conn.execute(
        sa.text(f'SELECT id FROM "{_app_schema()}".organizations WHERE name = :name'),
        {"name": ORG_NAME},
    ).scalar()
    if org_id is None:
        return report
    report["org_found"] = True

    entity_type_id = conn.execute(
        sa.text(
            f'SELECT entity_type_id FROM "{definitions}".entity_types '
            f"WHERE organization_id = :org_id AND name = :name"
        ),
        {"org_id": org_id, "name": ENTITY_TYPE_NAME},
    ).scalar()

    if entity_type_id is not None:
        cleared = conn.execute(
            sa.text(
                f'SELECT count(*) FROM "{runtime}".entities '
                f"WHERE organization_id = :org_id AND entity_type_id = :entity_type_id "
                f"  AND data ? '{FIELD_KEY}'"
            ),
            {"org_id": org_id, "entity_type_id": entity_type_id},
        ).scalar()
        report["records_cleared"] = cleared or 0
        if write:
            conn.execute(
                sa.text(
                    f'UPDATE "{runtime}".entities '
                    f"SET data = data - '{FIELD_KEY}', updated_at = now() "
                    f"WHERE organization_id = :org_id AND entity_type_id = :entity_type_id "
                    f"  AND data ? '{FIELD_KEY}'"
                ),
                {"org_id": org_id, "entity_type_id": entity_type_id},
            )

    library_field_id = conn.execute(
        sa.text(
            f'SELECT library_field_id FROM "{definitions}".field_library_fields '
            f"WHERE organization_id = :org_id AND lower(field_key) = lower(:field_key)"
        ),
        {"org_id": org_id, "field_key": FIELD_KEY},
    ).scalar()
    if library_field_id is None:
        return report
    report["field_removed"] = True
    if not write:
        return report

    schema_row = conn.execute(
        sa.text(
            f'SELECT id, fields_json FROM "{definitions}".entity_type_schema '
            f"WHERE organization_id = :org_id AND schema_key = :schema_key"
        ),
        {"org_id": org_id, "schema_key": SCHEMA_KEY},
    ).first()
    if schema_row is not None:
        schema_id, fields_json = schema_row
        remaining = [
            f for f in _as_list(fields_json) if f.get("library_field_id") != library_field_id
        ]
        conn.execute(
            sa.text(
                f'UPDATE "{definitions}".entity_type_schema '
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
        conn.execute(
            sa.text(
                f'DELETE FROM "{definitions}".entity_type_schema_fields '
                f"WHERE schema_id = :schema_id AND library_field_id = :library_field_id"
            ),
            {"schema_id": schema_id, "library_field_id": library_field_id},
        )

    conn.execute(
        sa.text(
            f'DELETE FROM "{definitions}".field_library_field_versions '
            f"WHERE library_field_id = :library_field_id"
        ),
        {"library_field_id": library_field_id},
    )
    conn.execute(
        sa.text(
            f'DELETE FROM "{definitions}".field_library_fields '
            f"WHERE library_field_id = :library_field_id"
        ),
        {"library_field_id": library_field_id},
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
            if args.revert:
                report = revert(conn, write=args.apply)
            else:
                report = apply_(conn, write=args.apply)
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

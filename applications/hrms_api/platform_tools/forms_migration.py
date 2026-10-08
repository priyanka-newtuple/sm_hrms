"""Run the platform's Forms -> Field Library migration with the HRMS adjustments.

The platform script (backend/scripts/migrate_forms_to_method_blocks.py) stays
unchanged; this wrapper loads it and adjusts three things for this run only:

1. Decimal type. The catalogue has no code for the engine's `float` type, so
   decimal fields (money, percentages, hours) were skipped. On --apply the
   `decimal` catalogue row is created first; a dry run plans as if it existed.
2. Dates. The catalogue has no plain-date code; a `date` field lands on Date &
   Time, whose value check accepts the same "YYYY-MM-DD" strings.
3. Plain JSON fields (ProjectChange.proposed, PerformanceCycle.participants)
   share the Table / Grid code. The platform's pin converter turns a table
   field's non-empty settings into a table_config when there is no nested one,
   and a column-less table_config makes every save fail "expects table rows".
   Their library versions are therefore created with empty settings; the
   per-usage label/placeholder/required still live on the block field. The
   converter reads the version settings on every publish, so this holds for
   later publishes too, as long as nobody adds settings to those fields in the
   Field Library.

Runs inside the platform-api container, with its environment:

    python /app/hrms_platform_tools/forms_migration.py --org <id> --overwrite-drafts            # dry run
    python /app/hrms_platform_tools/forms_migration.py --org <id> --overwrite-drafts --apply    # write

Every other argument is passed to the platform script unchanged.
"""

from __future__ import annotations

import importlib.util
import os
import sys

PLATFORM_SCRIPT = os.environ.get(
    "PLATFORM_FORMS_MIGRATION", "/app/backend/scripts/migrate_forms_to_method_blocks.py"
)
DECIMAL = {"code": "decimal", "label": "Decimal", "engine_type": "float", "sort_order": 55}
ENGINE_TYPE_ALIASES = {"date": "datetime"}
TABLE_KIND = "table"


def load_platform_script(path: str = PLATFORM_SCRIPT):
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))
    spec = importlib.util.spec_from_file_location("migrate_forms_to_method_blocks", path)
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses resolve their module through sys.modules while loading.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def install_overrides(migration) -> None:
    """Patch the loaded platform script in place; the file on disk is untouched."""
    catalogue = migration._catalogue
    resolve_code = migration._resolve_code
    plan_fields = migration._plan_fields

    def _catalogue(conn):
        by_engine, kinds, engine_of = catalogue(conn)
        if DECIMAL["code"] not in kinds:
            # Dry run before the row exists: plan as it will be after --apply creates it.
            by_engine.setdefault(DECIMAL["engine_type"], DECIMAL["code"])
            kinds[DECIMAL["code"]] = "none"
            engine_of[DECIMAL["code"]] = DECIMAL["engine_type"]
        return by_engine, kinds, engine_of

    def _resolve_code(entry, encoding, by_engine):
        raw = str(entry.get("type") or "").strip().lower()
        alias = ENGINE_TYPE_ALIASES.get(raw)
        return resolve_code({**entry, "type": alias} if alias else entry, encoding, by_engine)

    def _plan_fields(slots, existing, kinds, plan):
        fields = plan_fields(slots, existing, kinds, plan)
        for field_plan in fields.values():
            for shape in field_plan.shapes:
                if kinds.get(shape.code) == TABLE_KIND and not shape.settings.get("table_config"):
                    shape.settings = {}
        return fields

    migration._catalogue = _catalogue
    migration._resolve_code = _resolve_code
    migration._plan_fields = _plan_fields
    # Plain JSON fields no longer reach the converter's whole-settings path.
    migration.CONVERTER_WHOLE_SETTINGS_KINDS = set(migration.CONVERTER_WHOLE_SETTINGS_KINDS) - {
        TABLE_KIND
    }


def ensure_decimal_type(migration) -> None:
    """Create the `decimal` catalogue row, and enable it for orgs that configure their types."""
    sa = migration.sa
    schema = migration._defs()
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                f'INSERT INTO "{schema}".field_type_catalogue '
                "(code, label, engine_type, config_kind, is_available, sort_order) "
                "VALUES (:code, :label, :engine_type, 'none', true, :sort_order) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            DECIMAL,
        )
        conn.execute(
            sa.text(
                f'INSERT INTO "{schema}".organization_field_types (id, organization_id, field_type_code, enabled) '
                "SELECT gen_random_uuid()::text, configured.organization_id, :code, true "
                f'FROM (SELECT DISTINCT organization_id FROM "{schema}".organization_field_types) AS configured '
                f'WHERE NOT EXISTS (SELECT 1 FROM "{schema}".organization_field_types existing '
                "WHERE existing.organization_id = configured.organization_id "
                "AND existing.field_type_code = :code)"
            ),
            DECIMAL,
        )


def main() -> int:
    migration = load_platform_script()
    install_overrides(migration)
    if "--apply" in sys.argv[1:]:
        ensure_decimal_type(migration)
    return migration.main()


if __name__ == "__main__":
    sys.exit(main())

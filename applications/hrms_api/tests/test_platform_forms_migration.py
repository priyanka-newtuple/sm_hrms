from types import SimpleNamespace

from platform_tools.forms_migration import install_overrides

CATALOGUE = (
    {"string": "text", "datetime": "datetime", "int": "integer", "json": "table"},
    {"text": "none", "datetime": "none", "integer": "none", "table": "table"},
    {"text": "string", "datetime": "datetime", "integer": "int", "table": "json"},
)


def platform_script(shapes=()):
    """The parts of migrate_forms_to_method_blocks.py the wrapper overrides."""

    def resolve_code(entry, encoding, by_engine):
        raw = entry["type"]
        return raw, by_engine.get(raw)

    def plan_fields(slots, existing, kinds, plan):
        return {"f": SimpleNamespace(shapes=list(shapes))}

    module = SimpleNamespace(
        _catalogue=lambda conn: tuple(dict(part) for part in CATALOGUE),
        _resolve_code=resolve_code,
        _plan_fields=plan_fields,
        CONVERTER_WHOLE_SETTINGS_KINDS={"currency", "table", "auto_number"},
    )
    install_overrides(module)
    return module


def test_a_date_field_lands_on_date_and_time():
    module = platform_script()
    by_engine, _, _ = module._catalogue(None)

    assert module._resolve_code({"type": "date"}, "", by_engine) == ("datetime", "datetime")


def test_a_decimal_field_lands_on_the_decimal_type_before_the_row_exists():
    module = platform_script()
    by_engine, kinds, engine_of = module._catalogue(None)

    assert module._resolve_code({"type": "float"}, "", by_engine) == ("float", "decimal")
    assert kinds["decimal"] == "none" and engine_of["decimal"] == "float"


def test_other_types_resolve_unchanged():
    module = platform_script()
    by_engine, _, _ = module._catalogue(None)

    assert module._resolve_code({"type": "int"}, "", by_engine) == ("int", "integer")
    assert module._resolve_code({"type": "json"}, "", by_engine) == ("json", "table")


def test_a_plain_json_field_gets_empty_library_settings():
    plain = SimpleNamespace(code="table", settings={"required": True, "nullable": True})
    grid = SimpleNamespace(
        code="table", settings={"required": True, "table_config": {"columns": [{"id": "a"}]}}
    )
    text = SimpleNamespace(code="text", settings={"required": True})
    module = platform_script([plain, grid, text])

    module._plan_fields([], {}, CATALOGUE[1], None)

    assert plain.settings == {}
    assert grid.settings["table_config"] == {"columns": [{"id": "a"}]}
    assert text.settings == {"required": True}
    assert "table" not in module.CONVERTER_WHOLE_SETTINGS_KINDS

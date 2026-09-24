"""Nested request bodies resolve, which is what the editor now lets users save.

The body column is JSONB and the contract is `dict[str, Any]`, so nesting has
always been storable, and `_PlaceholderResolver.resolve_value` already walks
dicts and lists. Only the frontend rejected it. These lock the backend half down
so the editor change cannot be undermined by a later narrowing here.
"""

from __future__ import annotations

import json

from connectors.manager import _build_body_and_headers, _PlaceholderResolver, run_connector_call
from connectors.models.interface import ConnectorContract


def _contract(**overrides: object) -> ConnectorContract:
    base: dict[str, object] = {
        "id": "conn-1",
        "organization_id": "test-org-1",
        "name": "inriver",
        "base_url": "https://example.test",
        "method": "POST",
        "path": "/entities",
        "content_type": "application/json",
        "headers": {},
        "query_params": {},
    }
    base.update(overrides)
    return ConnectorContract(**base)


def _resolve(
    template: object, entity: dict[str, str], inputs: dict[str, str] | None = None
) -> object:
    resolver = _PlaceholderResolver(inputs or {}, entity)
    body, _headers = _build_body_and_headers(_contract(body_template=template), resolver)
    return json.loads(str(body))


def test_placeholders_resolve_inside_an_array_of_objects() -> None:
    """The shape the editor used to reject outright."""
    body = _resolve(
        {"fieldValues": [{"fieldTypeId": "ProductName", "value": "$entity.product_name"}]},
        {"product_name": "Oat Milk"},
    )
    assert body == {"fieldValues": [{"fieldTypeId": "ProductName", "value": "Oat Milk"}]}


def test_placeholders_resolve_inside_a_nested_object() -> None:
    body = _resolve({"name": {"en": "$entity.product_name"}}, {"product_name": "Oat Milk"})
    assert body == {"name": {"en": "Oat Milk"}}


def test_a_sole_placeholder_keeps_its_json_type_when_nested() -> None:
    """A lone placeholder restores the value's type, so an Integer stays a number.

    This is why nesting is worth supporting properly rather than living on raw
    mode, where every value would be substituted as text.
    """
    body = _resolve(
        {"fieldValues": [{"value": "$entity.case_pack"}, {"value": "$entity.allergens"}]},
        {"case_pack": "12", "allergens": '["Milk","Gluten"]'},
    )
    assert body["fieldValues"][0]["value"] == 12
    assert body["fieldValues"][1]["value"] == ["Milk", "Gluten"]


def test_caller_inputs_resolve_inside_nesting_too() -> None:
    body = _resolve({"items": [{"qty": "{{quantity}}"}]}, {}, {"quantity": "3"})
    assert body == {"items": [{"qty": 3}]}


def test_booleans_and_nulls_survive_untouched() -> None:
    """The editor allows them as leaves, so they must pass through unchanged."""
    body = _resolve({"active": True, "note": None, "nested": {"flag": False}}, {})
    assert body == {"active": True, "note": None, "nested": {"flag": False}}


# ── Part B: a top-level array, for batch endpoints ──────────────────────────


def test_a_top_level_array_body_renders() -> None:
    """Batch endpoints take a list, not an object.

    inriver's entities:upsert rejects an object outright ("Expected an array"),
    and upsert is the idempotent call, so a workflow action that re-fires does
    not create duplicates. The contract had to accept a list for that to be
    configurable at all.
    """
    body = _resolve(
        [{"entityTypeId": "Product", "fieldValues": [{"value": "$entity.sku"}]}],
        {"sku": "ABC-1"},
    )
    assert body == [{"entityTypeId": "Product", "fieldValues": [{"value": "ABC-1"}]}]


def test_an_array_body_survives_the_contract() -> None:
    """The contract itself must accept the list, not just the renderer."""
    contract = _contract(body_template=[{"a": 1}, {"b": 2}])
    assert contract.body_template == [{"a": 1}, {"b": 2}]


# ── Phase 2: an unresolvable placeholder must fail the call ─────────────────


def test_an_unknown_entity_field_fails_the_call_instead_of_sending_blank() -> None:
    """A misspelt field used to send "" and the API would answer 200.

    The run was then recorded as a success while nothing useful was written,
    which is the silent failure this guards against.
    """
    resolver = _PlaceholderResolver({}, {"sku": "ABC-1"})
    result = run_connector_call(
        contract=_contract(body_template={"code": "$entity.skuu"}),
        secrets={},
        field_values={"sku": "ABC-1"},
    )
    assert result.ok is False
    assert "$entity.skuu" in (result.error or "")
    _ = resolver


def test_an_unknown_caller_input_fails_the_call() -> None:
    """The same rule for {{input}} placeholders the caller never supplied."""
    result = run_connector_call(
        contract=_contract(body_template={"qty": "{{quantity}}"}),
        secrets={},
        field_values={},
    )
    assert result.ok is False
    assert "{{quantity}}" in (result.error or "")


def test_every_unresolved_placeholder_is_named_at_once() -> None:
    """One failure lists them all, so a body is not fixed one round trip at a time."""
    result = run_connector_call(
        contract=_contract(body_template={"a": "$entity.one", "b": "$entity.two"}),
        secrets={},
        field_values={},
    )
    assert "$entity.one" in (result.error or "")
    assert "$entity.two" in (result.error or "")


def test_a_field_that_exists_but_is_empty_is_a_real_value() -> None:
    """An optional field left blank must still send, or valid payloads break."""
    resolver = _PlaceholderResolver({}, {"note": ""})
    assert resolver.resolve_value({"note": "$entity.note"}) == {"note": ""}
    assert resolver.missing == set()


def test_interactive_testing_stays_lenient() -> None:
    """Sample values are deliberately partial, so the test button must not fail here."""
    resolver = _PlaceholderResolver({}, {})
    resolver.resolve_value({"code": "$entity.missing"})
    assert resolver.missing == {"$entity.missing"}
    # ...but the call itself is allowed through when the caller opts out.
    result = run_connector_call(
        contract=_contract(base_url="https://127.0.0.1", body_template={"a": "$entity.nope"}),
        secrets={},
        field_values={},
        strict_placeholders=False,
    )
    # It fails on the network/SSRF guard, not on the placeholder check.
    assert "unresolved placeholders" not in (result.error or "")

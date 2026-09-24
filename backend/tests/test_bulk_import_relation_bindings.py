from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bulk_import.models import BulkImportFixedRelationBinding
from bulk_import.services.relation_bindings import BulkImportRelationBindingService
from exceptions import ValidationError


ACTOR = {"organization_id": "org-1", "user_id": "user-1"}


def _service():
    entities = MagicMock()
    entities.list_entity_type_records.return_value = [
        SimpleNamespace(entity_type_id="parent-type", name="Supplier")
    ]
    entities.list_entity_relation_declarations_for_actor.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                relation_def_id="rel-1",
                from_entity_type_id="parent-type",
                to_entity_type_id="product-type",
                relation_name=None,
                relation_type=SimpleNamespace(value="REFERENCE"),
            )
        ]
    )
    return BulkImportRelationBindingService(entities=entities), entities


def test_fixed_parent_is_validated_and_applied_to_every_row() -> None:
    service, entities = _service()
    entities.get_entity_record_for_actor.return_value = SimpleNamespace(
        entity_id="supplier-1",
        entity_type_id="parent-type",
        data={"identifier": "Acme"},
    )
    definitions = service.discover(ACTOR, "product-type")

    service.apply_fixed_choices(
        ACTOR,
        definitions,
        [BulkImportFixedRelationBinding(relation_def_id="rel-1", source_entity_id="supplier-1")],
    )
    binding = service.build_bindings(ACTOR, definitions, {}, {})[0]

    assert binding.status == "resolved"
    assert binding.mode == "fixed"
    assert binding.source_entity_id == "supplier-1"
    assert binding.source_entity_label == "Acme"


def test_parent_column_uses_exact_case_insensitive_identifier_match() -> None:
    service, entities = _service()
    definitions = service.discover(ACTOR, "product-type")
    entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                entity_id="supplier-1",
                entity_type_id="parent-type",
                data={"identifier": "Acme"},
            )
        ]
    )

    binding = service.build_bindings(
        ACTOR,
        definitions,
        {"rel-1": "Supplier"},
        {"Supplier": " acme "},
    )[0]

    assert binding.status == "resolved"
    assert binding.mode == "column"
    assert binding.source_value == "acme"
    assert binding.source_entity_id == "supplier-1"
    entities.list_entity_records_by_type_name_for_actor.assert_called_once_with(
        ACTOR, "Supplier", search="acme", limit=20
    )


def test_parent_column_prefers_unique_exact_case_match() -> None:
    service, entities = _service()
    definitions = service.discover(ACTOR, "product-type")
    entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(entity_id="lower", data={"identifier": "Acme"}),
            SimpleNamespace(entity_id="upper", data={"identifier": "ACME"}),
        ]
    )

    binding = service.build_bindings(
        ACTOR, definitions, {"rel-1": "Supplier"}, {"Supplier": "Acme"}
    )[0]

    assert binding.status == "resolved"
    assert binding.source_entity_id == "lower"


def test_parent_column_rejects_ambiguous_case_insensitive_match() -> None:
    service, entities = _service()
    definitions = service.discover(ACTOR, "product-type")
    entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(entity_id="mixed", data={"identifier": "Acme"}),
            SimpleNamespace(entity_id="upper", data={"identifier": "ACME"}),
        ]
    )

    binding = service.build_bindings(
        ACTOR, definitions, {"rel-1": "Supplier"}, {"Supplier": "acme"}
    )[0]

    assert binding.status == "missing"
    assert binding.source_entity_id is None
    assert "Ambiguous Supplier" in str(binding.error)


def test_parent_lookup_is_cached_for_repeated_source_value() -> None:
    service, entities = _service()
    definitions = service.discover(ACTOR, "product-type")
    entities.list_entity_records_by_type_name_for_actor.return_value = SimpleNamespace(
        items=[SimpleNamespace(entity_id="supplier-1", data={"identifier": "Acme"})]
    )
    lookups = {}

    for _ in range(2):
        service.build_bindings(
            ACTOR,
            definitions,
            {"rel-1": "Supplier"},
            {"Supplier": "Acme"},
            indexes=lookups,
        )

    entities.list_entity_records_by_type_name_for_actor.assert_called_once()


def test_unresolved_required_parent_is_an_explicit_exception() -> None:
    service, _ = _service()
    definitions = service.discover(ACTOR, "product-type")

    binding = service.build_bindings(ACTOR, definitions, {}, {})[0]

    assert binding.status == "missing"
    assert "fixed Supplier" in str(binding.error)


def test_fixed_parent_must_match_relationship_provider_type() -> None:
    service, entities = _service()
    definitions = service.discover(ACTOR, "product-type")
    entities.get_entity_record_for_actor.return_value = SimpleNamespace(
        entity_id="customer-1",
        entity_type_id="other-type",
        data={"identifier": "Wrong type"},
    )

    with pytest.raises(ValidationError, match="wrong entity type"):
        service.apply_fixed_choices(
            ACTOR,
            definitions,
            [BulkImportFixedRelationBinding(relation_def_id="rel-1", source_entity_id="customer-1")],
        )


def test_validate_column_mapping_rejects_unknown_relationship() -> None:
    service, _ = _service()
    definitions = service.discover(ACTOR, "product-type")

    with pytest.raises(ValidationError, match="unavailable relationship"):
        service.validate_column_mapping(definitions, {"missing-rel": "Supplier"}, {"Supplier"})


def test_validate_column_mapping_rejects_fixed_parent_mapping() -> None:
    service, _ = _service()
    definitions = service.discover(ACTOR, "product-type")
    definitions[0].fixed_source_entity_id = "supplier-1"

    with pytest.raises(ValidationError, match="fixed parent"):
        service.validate_column_mapping(definitions, {"rel-1": "Supplier"}, {"Supplier"})


def test_validate_column_mapping_rejects_unknown_column() -> None:
    service, _ = _service()
    definitions = service.discover(ACTOR, "product-type")

    with pytest.raises(ValidationError, match="unknown column"):
        service.validate_column_mapping(definitions, {"rel-1": "Missing"}, {"Supplier"})

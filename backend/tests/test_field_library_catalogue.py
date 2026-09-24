"""Field-type catalogue: seeding, per-organization enablement, and isolation.

The default matters most: an organization with no enablement rows must keep
seeing every available type, or this module breaks the other products.
"""

from __future__ import annotations

import uuid

import pytest

from exceptions import ServiceError
from field_library.db_models import FieldLibraryModelService, OrganizationFieldTypeModel
from field_library.manager import (
    NOT_ENABLED_REASON,
    FieldLibraryServiceManager,
)

# Seeded by 2026_08_18_0001. Codes 1-14 mirror the form builder's existing list.
EXPECTED_CATALOGUE_SIZE = 16
UNAVAILABLE_CODES: set[str] = set()
ORG_A = "test-org-1"
ORG_B = "test-org-2"


@pytest.fixture
def db_service(entities_db_service_manager) -> FieldLibraryModelService:
    return FieldLibraryModelService(entities_db_service_manager)


@pytest.fixture
def manager(db_service) -> FieldLibraryServiceManager:
    service = FieldLibraryServiceManager(db_service)
    service.start()
    return service


@pytest.fixture
def clean_org_settings(db_service):
    """Remove enablement rows for both test orgs before and after each test."""

    def _purge() -> None:
        with db_service._db_session() as session:
            session.query(OrganizationFieldTypeModel).filter(
                OrganizationFieldTypeModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.commit()

    _purge()
    yield
    _purge()


def _enable_only(db_service: FieldLibraryModelService, org_id: str, codes: list[str]) -> None:
    """Give `org_id` explicit enablement rows: `codes` on, everything else off."""
    with db_service._db_session() as session:
        for entry in db_service.list_catalogue():
            session.add(
                OrganizationFieldTypeModel(
                    id=str(uuid.uuid4()),
                    organization_id=org_id,
                    field_type_code=entry.code,
                    enabled=entry.code in codes,
                )
            )
        session.commit()


def test_catalogue_is_seeded_with_every_permitted_type(db_service) -> None:
    entries = db_service.list_catalogue()
    assert len(entries) == EXPECTED_CATALOGUE_SIZE
    codes = [entry.code for entry in entries]
    # The first and last of the 16, so a reordering or a dropped row is caught.
    assert codes[0] == "text"
    assert codes[-1] == "timer_duration", "sort_order is unchanged by availability"
    assert len(set(codes)) == len(codes), "catalogue codes must be unique"


def test_catalogue_is_returned_in_display_order(db_service) -> None:
    """The selector renders rows as given, so ordering is part of the contract."""
    sort_orders = [entry.sort_order for entry in db_service.list_catalogue()]
    assert sort_orders == sorted(sort_orders)


def test_every_built_type_maps_to_an_engine_type(db_service) -> None:
    """Document and Timer/Duration are both implemented after the merged features."""
    by_code = {entry.code: entry for entry in db_service.list_catalogue()}
    for code, entry in by_code.items():
        assert entry.is_available is True, f"{code} must be available"
        assert entry.engine_type, f"{code} is available but has no engine type"

    assert by_code["document"].engine_type == "document"
    assert by_code["timer_duration"].engine_type == "timer_duration"


def test_table_grid_maps_to_json(db_service) -> None:
    """Table/Grid is stored as a json field plus table_config, not its own type."""
    by_code = {entry.code: entry for entry in db_service.list_catalogue()}
    assert by_code["table"].engine_type == "json"
    assert by_code["table"].config_kind == "table"


def test_org_without_settings_gets_every_available_type(manager, clean_org_settings) -> None:
    """The backward-compatible default: no rows means nothing is switched off."""
    response = manager.list_field_types(organization_id=ORG_A)
    assert len(response.items) == EXPECTED_CATALOGUE_SIZE
    selectable = {item.code for item in response.items if item.selectable}
    unselectable = {item.code for item in response.items if not item.selectable}
    assert unselectable == UNAVAILABLE_CODES
    assert "text" in selectable
    assert len(selectable) == EXPECTED_CATALOGUE_SIZE - len(UNAVAILABLE_CODES)


def test_timer_type_is_selectable_when_enabled(
    manager, db_service, clean_org_settings
) -> None:
    """The frontend-recorded timer is a normal selectable engine field type."""
    _enable_only(db_service, ORG_A, ["text", "timer_duration"])
    response = manager.list_field_types(organization_id=ORG_A)
    timer = next(item for item in response.items if item.code == "timer_duration")
    assert timer.selectable is True
    assert timer.unavailable_reason is None


def test_org_with_settings_only_gets_its_enabled_subset(
    manager, db_service, clean_org_settings
) -> None:
    _enable_only(db_service, ORG_A, ["text", "integer"])
    response = manager.list_field_types(organization_id=ORG_A)
    selectable = {item.code for item in response.items if item.selectable}
    assert selectable == {"text", "integer"}
    currency = next(item for item in response.items if item.code == "currency")
    assert currency.unavailable_reason == NOT_ENABLED_REASON


def test_one_orgs_settings_never_affect_another_org(
    manager, db_service, clean_org_settings
) -> None:
    """Cross-organization isolation: org A narrowing its list leaves org B alone."""
    _enable_only(db_service, ORG_A, ["text"])
    org_a = {item.code for item in manager.list_field_types(organization_id=ORG_A).items
             if item.selectable}
    org_b = {item.code for item in manager.list_field_types(organization_id=ORG_B).items
             if item.selectable}
    assert org_a == {"text"}
    assert len(org_b) == EXPECTED_CATALOGUE_SIZE - len(UNAVAILABLE_CODES)
    assert "currency" in org_b


def test_settings_read_is_scoped_to_the_requested_org(db_service, clean_org_settings) -> None:
    _enable_only(db_service, ORG_A, ["text"])
    assert db_service.list_organization_settings(organization_id=ORG_B) == []
    org_a_settings = db_service.list_organization_settings(organization_id=ORG_A)
    assert org_a_settings
    assert {setting.organization_id for setting in org_a_settings} == {ORG_A}


def test_missing_organization_id_is_rejected(manager) -> None:
    """Error path: an empty organization must not silently fall back to a global list."""
    with pytest.raises(ServiceError, match="organization_id"):
        manager.list_field_types(organization_id="")


def test_actor_without_organization_is_rejected(manager) -> None:
    """Error path: the org comes from the actor, so a missing one is a hard failure."""
    with pytest.raises(ServiceError, match="organization_id"):
        manager.list_field_types_for_actor({"user_id": "someone"})

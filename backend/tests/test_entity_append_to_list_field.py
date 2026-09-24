"""append_to_data_list_field: a locked read-append-write for list-valued
entity.data fields.

Documents' upload flow used to read the entity, append the new document id
in Python, and write the whole `data` object back via update_entity_record.
Two overlapping calls (two simultaneous uploads to the same field, or an
upload racing an unrelated edit) would each read the same stale snapshot and
each replace `data` wholesale — the loser's change is silently lost. This
file proves the fix: locking the row for the entire read-append-write means
a second overlapping caller re-reads the first caller's committed change
instead of clobbering it.
"""

from __future__ import annotations

import concurrent.futures
import threading
import uuid

import pytest

from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from entities.models.request import (
    EntityRecordCreateRequest,
    EntityRecordUpdateRequest,
    EntityTypeCreateRequest,
)
from exceptions import ValidationError

ORG_A = "test-org-1"
ORG_B = "test-org-2"


@pytest.fixture
def entities_db(entities_db_service_manager) -> EntitiesModelService:
    return EntitiesModelService(entities_db_service_manager)


@pytest.fixture
def manager(entities_db, entities_db_service_manager) -> EntitiesServiceManager:
    return EntitiesServiceManager(entities_db, entities_db_service_manager, None, None)


def _entity(entities_db, org: str = ORG_A) -> str:
    entity_type = entities_db.create_entity_type(
        EntityTypeCreateRequest(
            organization_id=org, name=f"append_type_{uuid.uuid4().hex[:8]}"
        )
    )
    record = entities_db.create_entity_record(
        request=EntityRecordCreateRequest(
            organization_id=org, entity_type_id=entity_type.entity_type_id, data={}
        )
    )
    return record.entity_id


def _data(entities_db, entity_id: str, org: str = ORG_A) -> dict:
    return dict(
        entities_db.get_entity_record_by_id(organization_id=org, entity_id=entity_id).data
    )


def test_append_onto_an_empty_field_creates_a_single_item_list(entities_db, manager) -> None:
    entity_id = _entity(entities_db)

    manager.append_to_list_field(
        organization_id=ORG_A, entity_id=entity_id, field_key="attachments", value="doc-1"
    )

    assert _data(entities_db, entity_id)["attachments"] == ["doc-1"]


def test_append_preserves_prior_items_and_order(entities_db, manager) -> None:
    entity_id = _entity(entities_db)
    manager.append_to_list_field(
        organization_id=ORG_A, entity_id=entity_id, field_key="attachments", value="doc-1"
    )

    manager.append_to_list_field(
        organization_id=ORG_A, entity_id=entity_id, field_key="attachments", value="doc-2"
    )

    assert _data(entities_db, entity_id)["attachments"] == ["doc-1", "doc-2"]


def test_append_leaves_other_fields_on_the_record_untouched(entities_db, manager) -> None:
    entity_id = _entity(entities_db)
    entities_db.update_entity_record(
        organization_id=ORG_A,
        entity_id=entity_id,
        request=EntityRecordUpdateRequest(data={"name": "Example"}),
    )

    manager.append_to_list_field(
        organization_id=ORG_A, entity_id=entity_id, field_key="attachments", value="doc-1"
    )

    data = _data(entities_db, entity_id)
    assert data["name"] == "Example"
    assert data["attachments"] == ["doc-1"]


def test_append_onto_a_non_list_value_is_rejected(entities_db, manager) -> None:
    entity_id = _entity(entities_db)
    entities_db.update_entity_record(
        organization_id=ORG_A,
        entity_id=entity_id,
        request=EntityRecordUpdateRequest(data={"attachments": "not-a-list"}),
    )

    with pytest.raises(ValidationError, match="must contain a list"):
        manager.append_to_list_field(
            organization_id=ORG_A, entity_id=entity_id, field_key="attachments", value="doc-2"
        )


def test_append_to_an_unknown_entity_returns_none(entities_db, manager) -> None:
    result = manager.append_to_list_field(
        organization_id=ORG_A,
        entity_id=str(uuid.uuid4()),
        field_key="attachments",
        value="doc-1",
    )
    assert result is None


def test_one_org_cannot_append_to_another_orgs_entity(entities_db, manager) -> None:
    entity_id = _entity(entities_db, ORG_A)

    result = manager.append_to_list_field(
        organization_id=ORG_B, entity_id=entity_id, field_key="attachments", value="doc-1"
    )

    assert result is None
    assert "attachments" not in _data(entities_db, entity_id)


def test_two_concurrent_appends_to_the_same_field_both_survive(entities_db) -> None:
    """Forces the real race: two threads append to the same field at the same
    instant. Before this fix, both would read the same pre-append snapshot
    and the second commit would silently overwrite the first's id. The row
    lock in append_to_data_list_field means the second thread's SELECT only
    returns after the first thread's transaction commits, so it reads
    (and keeps) the first thread's item rather than clobbering it."""
    entity_id = _entity(entities_db)
    start_gate = threading.Barrier(2)

    def _append(value: str):
        start_gate.wait()
        return entities_db.append_to_data_list_field(
            organization_id=ORG_A, entity_id=entity_id, field_key="attachments", value=value
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(_append, ("doc-a", "doc-b")))

    assert sorted(_data(entities_db, entity_id)["attachments"]) == ["doc-a", "doc-b"]


def test_an_append_racing_an_unrelated_field_edit_loses_neither(
    entities_db, manager
) -> None:
    """The narrower but equally real case the bug report calls out: an
    upload racing an unrelated edit to the same record, not just two
    uploads racing each other."""
    from entities.models.request import EntityRecordUpdateRequest

    entity_id = _entity(entities_db)
    start_gate = threading.Barrier(2)

    def _append():
        start_gate.wait()
        return entities_db.append_to_data_list_field(
            organization_id=ORG_A, entity_id=entity_id, field_key="attachments", value="doc-1"
        )

    def _edit_unrelated_field():
        start_gate.wait()
        return entities_db.update_entity_record(
            organization_id=ORG_A,
            entity_id=entity_id,
            request=EntityRecordUpdateRequest(data={"priority": "high"}),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_append), executor.submit(_edit_unrelated_field)]
        for future in futures:
            future.result()

    data = _data(entities_db, entity_id)
    assert data.get("attachments") == ["doc-1"]
    assert data.get("priority") == "high"

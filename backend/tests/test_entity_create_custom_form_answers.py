"""Storing a new record's custom form answers at create time.

`_store_custom_form_answers_on_create` is intentionally the simplest possible
write: unlike the edit path (`_store_edited_custom_form_answers`), a brand
new record has no stored schema yet to validate answer keys against, so this
just persists what was supplied — the schema itself resolves lazily on the
record's first read (`resolve_custom_forms`), same as everywhere else. It is
also best-effort: a persistence failure is logged and swallowed rather than
failing the create, matching `_fetch_form`'s own "never blocks a record"
philosophy elsewhere in this module. The fake below matches
`EntitiesModelService.merge_custom_form_data`'s signature.
"""

from __future__ import annotations

from entities.manager import EntitiesServiceManager
from exceptions import PersistenceError


class _FakeEntitiesDb:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._raises = raises

    def merge_custom_form_data(self, *, organization_id: str, entity_id: str, values: dict) -> None:
        if self._raises is not None:
            raise self._raises
        self.calls.append(
            {"organization_id": organization_id, "entity_id": entity_id, "values": values}
        )


def _manager(*, raises: Exception | None = None) -> tuple[EntitiesServiceManager, _FakeEntitiesDb]:
    db = _FakeEntitiesDb(raises=raises)
    return EntitiesServiceManager(db, None, None), db


def test_no_answers_supplied_writes_nothing() -> None:
    manager, db = _manager()

    manager._store_custom_form_answers_on_create(
        organization_id="org-1", entity_id="entity-1", custom_form_data=None
    )

    assert db.calls == []


def test_an_empty_answers_dict_writes_nothing() -> None:
    manager, db = _manager()

    manager._store_custom_form_answers_on_create(
        organization_id="org-1", entity_id="entity-1", custom_form_data={}
    )

    assert db.calls == []


def test_supplied_answers_are_merged_onto_the_new_record() -> None:
    manager, db = _manager()

    manager._store_custom_form_answers_on_create(
        organization_id="org-1",
        entity_id="entity-1",
        custom_form_data={"cert_id__value": "CPCN-1"},
    )

    assert db.calls == [
        {
            "organization_id": "org-1",
            "entity_id": "entity-1",
            "values": {"cert_id__value": "CPCN-1"},
        }
    ]


def test_a_persistence_failure_is_logged_and_does_not_fail_the_create() -> None:
    """The entity row already exists by this point; a failed answer write must
    not surface as a create error the caller would wrongly retry."""
    manager, db = _manager(raises=PersistenceError("db unavailable"))

    manager._store_custom_form_answers_on_create(
        organization_id="org-1", entity_id="entity-1", custom_form_data={"cert_id__value": "CPCN-1"}
    )

    assert db.calls == []

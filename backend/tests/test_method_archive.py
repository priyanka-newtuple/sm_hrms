"""Archiving a method: a genuinely new capability, separate from delete.

Mirrors the field library's own archive_field: unconditional and reversible, a
visibility change rather than a removal. Nothing here touches delete_method,
which stays the unconditional hard-delete path it already was.

Decision made explicit, since it's a product call and not just an
implementation detail: archiving is allowed even while a method is in use
(there is no way to check that on this branch at all — workflow-to-method
linking lives on a separate, unmerged branch — so "allowed" here really means
"nothing blocks it," which is the deliberate default). Hard delete staying
blocked while in use is a decision for that sibling branch, not this one.
"""

from __future__ import annotations

import uuid

import pytest

from exceptions import NotFoundError
from field_library.db_models import FieldLibraryModelService
from method_library.db_models import MethodLibraryModelService
from method_library.manager import MethodLibraryServiceManager
from method_library.models.request import (
    MethodCreateRequest,
    MethodFieldInput,
    MethodFieldListUpdateRequest,
)

ORG_A = "test-org-1"
ORG_B = "test-org-2"
ACTOR_A = {"user_id": "user-a", "organization_id": ORG_A}
ACTOR_B = {"user_id": "user-b", "organization_id": ORG_B}


@pytest.fixture
def field_service(entities_db_service_manager) -> FieldLibraryModelService:
    return FieldLibraryModelService(entities_db_service_manager)


@pytest.fixture
def db_service(entities_db_service_manager) -> MethodLibraryModelService:
    return MethodLibraryModelService(entities_db_service_manager)


@pytest.fixture
def manager(db_service) -> MethodLibraryServiceManager:
    return MethodLibraryServiceManager(db_service)


@pytest.fixture(autouse=True)
def clean_rows(db_service):
    """Purge both orgs' method and field rows, children before parents."""
    from field_library.db_models import FieldLibraryFieldModel, FieldLibraryFieldVersionModel
    from method_library.db_models import (
        MethodLibraryCategoryModel,
        MethodLibraryMethodModel,
        MethodLibraryMethodVersionFieldModel,
        MethodLibraryMethodVersionModel,
        MethodLibraryOrgCounterModel,
    )

    def _purge() -> None:
        orgs = [ORG_A, ORG_B]
        with db_service._db_session() as session:
            for model in (
                MethodLibraryOrgCounterModel,
                MethodLibraryMethodVersionFieldModel,
                MethodLibraryMethodVersionModel,
                MethodLibraryMethodModel,
                MethodLibraryCategoryModel,
                FieldLibraryFieldVersionModel,
                FieldLibraryFieldModel,
            ):
                session.query(model).filter(
                    model.organization_id.in_(orgs)
                ).delete(synchronize_session=False)
            session.commit()

    _purge()
    yield
    _purge()


def _make_field(field_service, org: str = ORG_A):
    suffix = uuid.uuid4().hex[:8]
    created = field_service.create_field(
        organization_id=org,
        name=f"Volume {suffix}",
        field_key=f"volume_{suffix}",
        field_type="integer",
        description=None,
        settings={"unit": "mL"},
        created_by="user-a",
    )
    return created.identity.library_field_id


def _create_method(manager, actor=ACTOR_A, *, name: str = "Method", fields=None):
    return manager.create_method_for_actor(
        actor, MethodCreateRequest(name=name, fields=fields or [])
    )


# ── Archiving ────────────────────────────────────────────────────────────────


def test_archiving_an_unused_method_succeeds(manager) -> None:
    created = _create_method(manager)

    archived = manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    assert archived.is_archived is True
    assert archived.method_id == created.identity.method_id


def test_archiving_is_allowed_regardless_of_prior_activity(manager, field_service) -> None:
    """Stands in for "in use by a workflow," which nothing on this branch can
    check. A method with real history (fields, multiple versions) still
    archives unconditionally, the same as a brand new one — there is no
    in-use guard on this action, by design."""
    field_id = _make_field(field_service)
    created = _create_method(manager, fields=[MethodFieldInput(library_field_id=field_id)])
    manager.replace_method_fields_for_actor(
        ACTOR_A, created.identity.method_id, MethodFieldListUpdateRequest(fields=[])
    )

    archived = manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    assert archived.is_archived is True


def test_archiving_does_not_touch_versions_or_fields(manager, field_service) -> None:
    field_id = _make_field(field_service)
    created = _create_method(manager, fields=[MethodFieldInput(library_field_id=field_id)])

    manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    resolved = manager.get_method_with_fields_for_actor(ACTOR_A, created.identity.method_id)
    assert resolved.version.version == 1
    assert len(resolved.fields) == 1
    assert resolved.fields[0].library_field_id == field_id


def test_archiving_twice_is_a_no_op(manager) -> None:
    created = _create_method(manager)

    first = manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)
    second = manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    assert first.is_archived is True
    assert second.is_archived is True


def test_archiving_an_unknown_method_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.archive_method_for_actor(ACTOR_A, str(uuid.uuid4()))


def test_one_org_cannot_archive_another_orgs_method(manager) -> None:
    created = _create_method(manager, actor=ACTOR_A)
    with pytest.raises(NotFoundError):
        manager.archive_method_for_actor(ACTOR_B, created.identity.method_id)

    still_live = manager.get_method_with_fields_for_actor(ACTOR_A, created.identity.method_id)
    assert still_live.identity.is_archived is False


# ── Listing and resolving ─────────────────────────────────────────────────────


def test_an_archived_method_is_excluded_from_default_listing(manager) -> None:
    live = _create_method(manager, name="Still Here")
    archived = _create_method(manager, name="Archived Away")
    manager.archive_method_for_actor(ACTOR_A, archived.identity.method_id)

    items, total = manager.list_methods_for_actor(ACTOR_A)

    ids = {item.method_id for item in items}
    assert live.identity.method_id in ids
    assert archived.identity.method_id not in ids
    assert total == 1


def test_include_archived_brings_it_back_into_the_listing(manager) -> None:
    created = _create_method(manager)
    manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    items, total = manager.list_methods_for_actor(ACTOR_A, include_archived=True)

    assert created.identity.method_id in {item.method_id for item in items}
    assert total == 1


def test_an_archived_method_still_resolves_by_id(manager) -> None:
    """Existing references (a clone's history, a workflow pin) must keep working."""
    created = _create_method(manager)
    manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    resolved = manager.get_method_with_fields_for_actor(ACTOR_A, created.identity.method_id)

    assert resolved.identity.is_archived is True
    assert resolved.identity.method_id == created.identity.method_id


# ── Unarchiving ────────────────────────────────────────────────────────────────


def test_unarchiving_reverses_an_archive(manager) -> None:
    created = _create_method(manager)
    manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    unarchived = manager.unarchive_method_for_actor(ACTOR_A, created.identity.method_id)

    assert unarchived.is_archived is False


def test_unarchiving_makes_the_method_reappear_in_default_listing(manager) -> None:
    created = _create_method(manager)
    manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)
    items_while_archived, _total = manager.list_methods_for_actor(ACTOR_A)
    assert created.identity.method_id not in {item.method_id for item in items_while_archived}

    manager.unarchive_method_for_actor(ACTOR_A, created.identity.method_id)

    items, total = manager.list_methods_for_actor(ACTOR_A)
    assert created.identity.method_id in {item.method_id for item in items}
    assert total == 1


def test_unarchiving_a_live_method_is_a_no_op(manager) -> None:
    created = _create_method(manager)

    result = manager.unarchive_method_for_actor(ACTOR_A, created.identity.method_id)

    assert result.is_archived is False


def test_unarchiving_an_unknown_method_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.unarchive_method_for_actor(ACTOR_A, str(uuid.uuid4()))


def test_one_org_cannot_unarchive_another_orgs_method(manager) -> None:
    created = _create_method(manager, actor=ACTOR_A)
    manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    with pytest.raises(NotFoundError):
        manager.unarchive_method_for_actor(ACTOR_B, created.identity.method_id)

    still_archived = manager.get_method_with_fields_for_actor(ACTOR_A, created.identity.method_id)
    assert still_archived.identity.is_archived is True


def test_archive_and_unarchive_leave_delete_untouched(manager) -> None:
    """delete_method is a separate capability; nothing here should require it
    to check archived state, and an archived method can still be deleted the
    same as any other (delete's own in-use rules are unaffected by this work)."""
    created = _create_method(manager)
    manager.archive_method_for_actor(ACTOR_A, created.identity.method_id)

    manager.delete_method_for_actor(ACTOR_A, created.identity.method_id)

    with pytest.raises(NotFoundError):
        manager.get_method_with_fields_for_actor(ACTOR_A, created.identity.method_id)

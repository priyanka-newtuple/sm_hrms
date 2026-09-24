"""Method→Field version selection and repin.

Mirrors the Form→Field pattern (entity_type_schema_fields): a link pins one
Field Library version, resolved once and never re-resolved on its own. What's
new here is giving the caller control over that pin — an explicit version at
link time, and a dedicated repin afterwards — where previously it was always
"whatever is latest right now," silently.

Repin is deliberately its own targeted write, not an in-place edit: it produces
a new method version, the same as any other change to the field list, so a
method version already in use elsewhere is never altered after the fact. See
repin_method_field's docstring in method_library/db_models.py for the full
reasoning.
"""

from __future__ import annotations

import uuid

import pytest

from exceptions import NotFoundError, ValidationError
from field_library.db_models import FieldLibraryModelService
from method_library.db_models import MethodLibraryModelService
from method_library.manager import MethodLibraryServiceManager
from method_library.models.request import (
    MethodCreateRequest,
    MethodFieldInput,
    MethodFieldRepinRequest,
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


def _make_field(field_service, org: str = ORG_A, *, field_type: str = "integer"):
    """Create a library field, returning its id and version 1 id."""
    suffix = uuid.uuid4().hex[:8]
    created = field_service.create_field(
        organization_id=org,
        name=f"Volume {suffix}",
        field_key=f"volume_{suffix}",
        field_type=field_type,
        description=None,
        settings={"unit": "mL"},
        created_by="user-a",
    )
    return created.identity.library_field_id, created.version.version_id


def _field_input(library_field_id: str, position: int = 0, **overrides) -> MethodFieldInput:
    payload = {
        "library_field_id": library_field_id,
        "label": f"Field {position}",
        "placeholder": "e.g. 5",
        "required": True,
        "position": position,
    }
    payload.update(overrides)
    return MethodFieldInput(**payload)


def _create_method(manager, actor=ACTOR_A, *, name: str = "Method", fields=None):
    return manager.create_method_for_actor(
        actor, MethodCreateRequest(name=name, fields=fields or [])
    )


# ── Linking with an explicit version ────────────────────────────────────────


def test_linking_with_an_explicit_version_pins_that_version(manager, field_service) -> None:
    field_id, v1 = _make_field(field_service)
    v2 = field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description=None,
        settings={"unit": "L"},
        created_by="user-a",
        field_type="integer",
    )

    created = _create_method(manager, fields=[_field_input(field_id, version_id=v1)])

    entry = created.fields[0]
    assert entry.field_version_id == v1
    assert entry.field_version_id != v2.version_id
    assert entry.settings == {"unit": "mL"}, "pinned to v1's shape, not v2's"


def test_linking_with_no_version_pins_the_current_latest(manager, field_service) -> None:
    field_id, v1 = _make_field(field_service)
    v2 = field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description=None,
        settings={"unit": "L"},
        created_by="user-a",
        field_type="integer",
    )

    created = _create_method(manager, fields=[_field_input(field_id)])

    entry = created.fields[0]
    assert entry.field_version_id == v2.version_id
    assert entry.field_version_id != v1
    assert entry.settings == {"unit": "L"}


def test_linking_with_a_version_of_a_different_field_is_rejected(
    manager, field_service
) -> None:
    _mine, _ = _make_field(field_service)
    _theirs, theirs_version = _make_field(field_service)

    with pytest.raises(ValidationError, match="do not belong to their field"):
        _create_method(manager, fields=[_field_input(_mine, version_id=theirs_version)])


def test_linking_an_archived_fields_explicit_version_is_still_rejected(
    manager, field_service
) -> None:
    """Archiving stops new adoption entirely, whether or not a version is named."""
    field_id, v1 = _make_field(field_service)
    field_service.archive_field(organization_id=ORG_A, library_field_id=field_id)

    with pytest.raises(ValidationError, match="archived"):
        _create_method(manager, fields=[_field_input(field_id, version_id=v1)])


# ── Repin ────────────────────────────────────────────────────────────────────


def test_repin_moves_a_field_to_an_older_version(manager, field_service) -> None:
    field_id, v1 = _make_field(field_service)
    v2 = field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description=None,
        settings={"unit": "L"},
        created_by="user-a",
        field_type="integer",
    )
    created = _create_method(manager, fields=[_field_input(field_id)])
    assert created.fields[0].field_version_id == v2.version_id, "starts on latest"
    link_id = created.fields[0].id

    repinned = manager.repin_method_field_for_actor(
        ACTOR_A, created.identity.method_id, link_id, MethodFieldRepinRequest(version_id=v1)
    )

    entry = repinned.fields[0]
    assert entry.field_version_id == v1
    assert entry.settings == {"unit": "mL"}


def test_repin_bumps_the_method_version(manager, field_service) -> None:
    """Repin is its own targeted write, but still supersedes — never an in-place edit."""
    field_id, v1 = _make_field(field_service)
    # Only its side effect matters here: it moves the field off v1, so linking
    # with no version pins v2, giving the repin below somewhere to move from.
    field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description=None,
        settings={"unit": "L"},
        created_by="user-a",
        field_type="integer",
    )
    created = _create_method(manager, fields=[_field_input(field_id)])
    assert created.version.version == 1

    repinned = manager.repin_method_field_for_actor(
        ACTOR_A,
        created.identity.method_id,
        created.fields[0].id,
        MethodFieldRepinRequest(version_id=v1),
    )

    assert repinned.version.version == 2
    assert repinned.version.is_latest is True
    _items, total = manager.list_method_versions_for_actor(ACTOR_A, created.identity.method_id)
    assert total == 2


def test_repin_leaves_the_superseded_versions_pin_untouched(manager, field_service) -> None:
    """History stays traceable: the old method version still shows what it had."""
    field_id, v1 = _make_field(field_service)
    v2 = field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description=None,
        settings={"unit": "L"},
        created_by="user-a",
        field_type="integer",
    )
    created = _create_method(manager, fields=[_field_input(field_id)])
    first_version_id = created.version.version_id

    manager.repin_method_field_for_actor(
        ACTOR_A,
        created.identity.method_id,
        created.fields[0].id,
        MethodFieldRepinRequest(version_id=v1),
    )

    old_fields = manager.db_model_service.list_version_fields(
        organization_id=ORG_A, method_version_id=first_version_id
    )
    assert old_fields[0].field_version_id == v2.version_id, "superseded version is immutable"


def test_repin_to_a_version_that_does_not_belong_to_the_field_is_rejected(
    manager, field_service
) -> None:
    field_id, _ = _make_field(field_service)
    _other_field, other_version = _make_field(field_service)
    created = _create_method(manager, fields=[_field_input(field_id)])

    with pytest.raises(ValidationError, match="does not belong to field"):
        manager.repin_method_field_for_actor(
            ACTOR_A,
            created.identity.method_id,
            created.fields[0].id,
            MethodFieldRepinRequest(version_id=other_version),
        )

    # Nothing changed: no new version, original pin intact.
    _items, total = manager.list_method_versions_for_actor(ACTOR_A, created.identity.method_id)
    assert total == 1


def test_repin_does_not_disturb_a_different_field_link_on_the_same_method(
    manager, field_service
) -> None:
    """Confirms existing pinned links are unaffected by a repin on a different link."""
    field_a, a_v1 = _make_field(field_service)
    # Side effect only: moves field A off v1, so linking with no version below
    # starts field A on v2 and leaves something to repin back to a_v1.
    field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_a,
        description=None,
        settings={"unit": "L"},
        created_by="user-a",
        field_type="integer",
    )
    field_b, b_v1 = _make_field(field_service)
    created = _create_method(
        manager, fields=[_field_input(field_a, 0), _field_input(field_b, 1)]
    )
    link_a = next(f.id for f in created.fields if f.library_field_id == field_a)

    repinned = manager.repin_method_field_for_actor(
        ACTOR_A, created.identity.method_id, link_a, MethodFieldRepinRequest(version_id=a_v1)
    )

    by_field = {f.library_field_id: f for f in repinned.fields}
    assert by_field[field_a].field_version_id == a_v1
    assert by_field[field_b].field_version_id == b_v1, "field B's pin is untouched"
    assert by_field[field_b].label == "Field 1", "field B's own attributes carried over too"


def test_repin_an_archived_fields_own_historical_version_is_still_allowed(
    manager, field_service
) -> None:
    """Repin never adopts a field, so archiving it afterwards must not block
    moving among versions it already has."""
    field_id, v1 = _make_field(field_service)
    # Side effect only: gives the method something other than v1 to start on.
    field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description=None,
        settings={"unit": "L"},
        created_by="user-a",
        field_type="integer",
    )
    created = _create_method(manager, fields=[_field_input(field_id)])
    field_service.archive_field(organization_id=ORG_A, library_field_id=field_id)

    repinned = manager.repin_method_field_for_actor(
        ACTOR_A,
        created.identity.method_id,
        created.fields[0].id,
        MethodFieldRepinRequest(version_id=v1),
    )

    assert repinned.fields[0].field_version_id == v1


def test_repin_an_unknown_link_is_rejected(manager, field_service) -> None:
    field_id, v1 = _make_field(field_service)
    created = _create_method(manager, fields=[_field_input(field_id)])

    with pytest.raises(NotFoundError):
        manager.repin_method_field_for_actor(
            ACTOR_A,
            created.identity.method_id,
            str(uuid.uuid4()),
            MethodFieldRepinRequest(version_id=v1),
        )


def test_repin_on_an_unknown_method_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.repin_method_field_for_actor(
            ACTOR_A,
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            MethodFieldRepinRequest(version_id=str(uuid.uuid4())),
        )


def test_one_org_cannot_repin_another_orgs_method_field(manager, field_service) -> None:
    field_id, v1 = _make_field(field_service)
    # Side effect only: gives the method something other than v1 to start on.
    field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description=None,
        settings={"unit": "L"},
        created_by="user-a",
        field_type="integer",
    )
    created = _create_method(manager, fields=[_field_input(field_id)])

    with pytest.raises(NotFoundError):
        manager.repin_method_field_for_actor(
            ACTOR_B,
            created.identity.method_id,
            created.fields[0].id,
            MethodFieldRepinRequest(version_id=v1),
        )

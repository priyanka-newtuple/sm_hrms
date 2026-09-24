"""Method library: schema guards and the read API the workflow layer uses.

The behaviour worth most scrutiny is version pinning. A method resolves the field
shape it was built against, not the field's current shape, and the database is
what stops a pinned field being deleted out from under it.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

from exceptions import NotFoundError, ValidationError
from field_library.db_models import (
    FieldLibraryFieldModel,
    FieldLibraryFieldVersionModel,
    FieldLibraryModelService,
)
from method_library.db_models import (
    MethodLibraryCategoryModel,
    MethodLibraryMethodModel,
    MethodLibraryMethodVersionFieldModel,
    MethodLibraryMethodVersionModel,
    MethodLibraryModelService,
    MethodLibraryOrgCounterModel,
)
from method_library.manager import MethodLibraryServiceManager
from method_library.models.request import (
    MethodCategoryCreateRequest,
    MethodCategoryRenameRequest,
    MethodCloneRequest,
    MethodCreateRequest,
    MethodFieldInput,
    MethodFieldListUpdateRequest,
    MethodMetadataUpdateRequest,
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
    service = MethodLibraryServiceManager(db_service)
    service.start()
    return service


@pytest.fixture(autouse=True)
def clean_rows(db_service):
    """Purge both orgs' method and field rows, children before parents."""

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


def _make_field(field_service, org: str, *, field_type: str = "integer", settings=None):
    """Create a library field, returning its id and version 1 id."""
    suffix = uuid.uuid4().hex[:8]
    created = field_service.create_field(
        organization_id=org,
        name=f"Volume {suffix}",
        field_key=f"volume_{suffix}",
        field_type=field_type,
        description=None,
        settings=settings if settings is not None else {"unit": "mL"},
        created_by="user-a",
    )
    return created.identity.library_field_id, created.version.version_id


def _make_category(db_service, org: str, name: str | None = None) -> str:
    category_id = str(uuid.uuid4())
    with db_service._db_session() as session:
        session.add(
            MethodLibraryCategoryModel(
                id=category_id,
                organization_id=org,
                name=name or f"Prep {uuid.uuid4().hex[:6]}",
            )
        )
        session.commit()
    return category_id


def _make_method(db_service, org: str, *, category_id: str | None = None, **overrides) -> str:
    """Create a method through the service, which assigns its method_code."""
    return _create_method(db_service, org, category_id=category_id, **overrides).method_id


def _create_method(db_service, org: str, *, category_id: str | None = None, **overrides):
    payload = {"name": "PBMC Isolation", "description": "Isolate cells"}
    payload.update(overrides)
    return db_service.create_method(
        organization_id=org, category_id=category_id, created_by="user-a", **payload
    )


def _make_version(db_service, org: str, method_id: str, version: int = 1) -> str:
    version_id = str(uuid.uuid4())
    with db_service._db_session() as session:
        if version > 1:
            session.query(MethodLibraryMethodVersionModel).filter(
                MethodLibraryMethodVersionModel.method_id == method_id
            ).update({"is_latest": False}, synchronize_session=False)
            session.flush()
        session.add(
            MethodLibraryMethodVersionModel(
                version_id=version_id,
                method_id=method_id,
                organization_id=org,
                version=version,
                is_latest=True,
                created_by="user-a",
            )
        )
        session.commit()
    return version_id


def _list_ids(manager, actor, **kwargs) -> set[str]:
    """The method_ids on one page of the list."""
    items, _total = manager.list_methods_for_actor(actor, **kwargs)
    return {item.method_id for item in items}


def _list_total(manager, actor, **kwargs) -> int:
    """The total match count, which spans every page not just this one."""
    _items, total = manager.list_methods_for_actor(actor, **kwargs)
    return total


def _add_field_to_version(
    db_service,
    org: str,
    method_version_id: str,
    library_field_id: str,
    field_version_id: str,
    *,
    position: int = 0,
    label: str = "Volume collected",
    required: bool = True,
) -> str:
    row_id = str(uuid.uuid4())
    with db_service._db_session() as session:
        session.add(
            MethodLibraryMethodVersionFieldModel(
                id=row_id,
                method_version_id=method_version_id,
                library_field_id=library_field_id,
                field_version_id=field_version_id,
                label=label,
                placeholder="e.g. 5",
                required=required,
                position=position,
                organization_id=org,
            )
        )
        session.commit()
    return row_id


# ── Schema guards ─────────────────────────────────────────────────────────────


def test_category_name_is_unique_per_org_case_insensitively(db_service) -> None:
    _make_category(db_service, ORG_A, "Reagent Prep")
    with pytest.raises(IntegrityError, match="uq_method_library_categories_org_name"):
        _make_category(db_service, ORG_A, "REAGENT PREP")


def test_the_same_category_name_is_allowed_in_another_org(db_service) -> None:
    _make_category(db_service, ORG_A, "Reagent Prep")
    assert _make_category(db_service, ORG_B, "Reagent Prep")


def test_only_one_latest_version_per_method(db_service) -> None:
    method_id = _make_method(db_service, ORG_A)
    _make_version(db_service, ORG_A, method_id, version=1)
    def _add_a_second_latest() -> None:
        with db_service._db_session() as session:
            session.add(
                MethodLibraryMethodVersionModel(
                    version_id=str(uuid.uuid4()),
                    method_id=method_id,
                    organization_id=ORG_A,
                    version=2,
                    is_latest=True,
                )
            )
            session.commit()

    # A second flagged version without clearing the first is refused.
    with pytest.raises(IntegrityError, match="uq_method_library_versions_method_latest"):
        _add_a_second_latest()


def test_a_method_cannot_list_a_field_from_another_org(db_service, field_service) -> None:
    method_id = _make_method(db_service, ORG_A)
    version_id = _make_version(db_service, ORG_A, method_id)
    field_id, field_version_id = _make_field(field_service, ORG_B)
    with pytest.raises(IntegrityError):
        _add_field_to_version(db_service, ORG_A, version_id, field_id, field_version_id)


def test_field_version_and_field_cannot_be_mismatched(db_service, field_service) -> None:
    method_id = _make_method(db_service, ORG_A)
    version_id = _make_version(db_service, ORG_A, method_id)
    field_a, _ = _make_field(field_service, ORG_A)
    _, version_of_b = _make_field(field_service, ORG_A)
    with pytest.raises(
        IntegrityError, match="fk_method_library_version_fields_field_version"
    ):
        _add_field_to_version(db_service, ORG_A, version_id, field_a, version_of_b)


def test_a_field_listed_by_a_method_cannot_be_hard_deleted(db_service, field_service) -> None:
    """The whole point of not cascading: methods hold fields in place."""
    method_id = _make_method(db_service, ORG_A)
    version_id = _make_version(db_service, ORG_A, method_id)
    field_id, field_version_id = _make_field(field_service, ORG_A)
    _add_field_to_version(db_service, ORG_A, version_id, field_id, field_version_id)

    from field_library.db_models import FieldInUseError

    with pytest.raises((IntegrityError, FieldInUseError)):
        field_service.hard_delete_field(organization_id=ORG_A, library_field_id=field_id)


def test_deleting_a_method_removes_its_versions_and_field_rows(db_service, field_service) -> None:
    method_id = _make_method(db_service, ORG_A)
    version_id = _make_version(db_service, ORG_A, method_id)
    field_id, field_version_id = _make_field(field_service, ORG_A)
    _add_field_to_version(db_service, ORG_A, version_id, field_id, field_version_id)

    with db_service._db_session() as session:
        session.query(MethodLibraryMethodModel).filter(
            MethodLibraryMethodModel.method_id == method_id
        ).delete(synchronize_session=False)
        session.commit()
    with db_service._db_session() as session:
        assert (
            session.query(MethodLibraryMethodVersionFieldModel)
            .filter(MethodLibraryMethodVersionFieldModel.method_version_id == version_id)
            .count()
            == 0
        )
        # The library field itself survives.
        assert session.get(FieldLibraryFieldModel, field_id) is not None


# ── Write side: create with fields ────────────────────────────────────────────


def _field_input(library_field_id: str, position: int, **overrides) -> MethodFieldInput:
    payload = {
        "library_field_id": library_field_id,
        "label": f"Field {position}",
        "placeholder": "e.g. 5",
        "required": True,
        "position": position,
    }
    payload.update(overrides)
    return MethodFieldInput(**payload)


def test_create_with_fields_makes_version_one_in_order(manager, field_service) -> None:
    first, first_v = _make_field(field_service, ORG_A)
    second, second_v = _make_field(field_service, ORG_A)
    # Supplied out of order; position decides the order that comes back.
    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="PBMC Isolation",
            description="Isolate cells",
            fields=[
                _field_input(second, 1, label="Notes"),
                _field_input(first, 0, label="Volume"),
            ],
        ),
    )
    assert created.version.version == 1
    assert created.version.is_latest is True
    assert [f.label for f in created.fields] == ["Volume", "Notes"]
    assert [f.position for f in created.fields] == [0, 1]
    # Each field is pinned to that field's latest version at write time.
    assert created.fields[0].field_version_id == first_v
    assert created.fields[1].field_version_id == second_v
    assert created.fields[0].required is True


def test_create_rejects_a_field_from_another_organization(manager, field_service) -> None:
    foreign_field, _ = _make_field(field_service, ORG_B)
    with pytest.raises(ValidationError, match="not available in this organization"):
        manager.create_method_for_actor(
            ACTOR_A,
            MethodCreateRequest(name="Borrowed", fields=[_field_input(foreign_field, 0)]),
        )


def test_create_rejects_an_unknown_field(manager) -> None:
    with pytest.raises(ValidationError, match="not available in this organization"):
        manager.create_method_for_actor(
            ACTOR_A,
            MethodCreateRequest(name="Ghost", fields=[_field_input(str(uuid.uuid4()), 0)]),
        )


def test_create_rejects_the_same_field_listed_twice(manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    with pytest.raises(ValidationError, match="same field twice"):
        manager.create_method_for_actor(
            ACTOR_A,
            MethodCreateRequest(
                name="Doubled",
                fields=[_field_input(field_id, 0), _field_input(field_id, 1)],
            ),
        )


def test_a_rejected_create_leaves_nothing_behind(manager, field_service) -> None:
    """The whole create is one transaction, so a bad field rolls the method back."""
    before = _list_total(manager, ACTOR_A)
    with pytest.raises(ValidationError):
        manager.create_method_for_actor(
            ACTOR_A,
            MethodCreateRequest(name="Doomed", fields=[_field_input(str(uuid.uuid4()), 0)]),
        )
    assert _list_total(manager, ACTOR_A) == before


# ── Write side: metadata edits never version ──────────────────────────────────


def test_metadata_edit_creates_no_version(manager, field_service, db_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Before", fields=[_field_input(field_id, 0)])
    )
    method_id = created.identity.method_id
    category_id = _make_category(db_service, ORG_A, "Reagent Prep")

    updated = manager.update_method_metadata_for_actor(
        ACTOR_A,
        method_id,
        MethodMetadataUpdateRequest(
            name="After", description="Reworded", category_id=category_id
        ),
    )
    assert updated.name == "After"
    assert updated.description == "Reworded"
    assert updated.category_id == category_id

    with db_service._db_session() as session:
        count = (
            session.query(MethodLibraryMethodVersionModel)
            .filter(MethodLibraryMethodVersionModel.method_id == method_id)
            .count()
        )
    assert count == 1, "a metadata edit must not create a version"
    assert manager.get_method_with_fields_for_actor(ACTOR_A, method_id).version.version == 1


def test_metadata_edit_only_touches_what_was_supplied(manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="Keep Me", description="Keep this too", fields=[_field_input(field_id, 0)]
        ),
    )
    updated = manager.update_method_metadata_for_actor(
        ACTOR_A, created.identity.method_id, MethodMetadataUpdateRequest(name="Renamed")
    )
    assert updated.name == "Renamed"
    assert updated.description == "Keep this too", "an omitted member must not be cleared"


def test_metadata_edit_with_no_changes_is_rejected(manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Untouched", fields=[_field_input(field_id, 0)])
    )
    with pytest.raises(ValidationError, match="no changes"):
        manager.update_method_metadata_for_actor(
            ACTOR_A, created.identity.method_id, MethodMetadataUpdateRequest()
        )


# ── Write side: replacing the field list versions the method ───────────────────


def test_replacing_the_field_list_creates_version_two(manager, field_service) -> None:
    first, _ = _make_field(field_service, ORG_A)
    second, second_v = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Growing", fields=[_field_input(first, 0)])
    )
    method_id = created.identity.method_id
    first_version_id = created.version.version_id

    replaced = manager.replace_method_fields_for_actor(
        ACTOR_A,
        method_id,
        MethodFieldListUpdateRequest(fields=[_field_input(second, 0, label="Only Second")]),
    )
    assert replaced.version.version == 2
    assert replaced.version.is_latest is True
    assert replaced.version.version_id != first_version_id
    assert [f.label for f in replaced.fields] == ["Only Second"]
    assert replaced.fields[0].field_version_id == second_v
    # And get resolves the new version.
    resolved = manager.get_method_with_fields_for_actor(ACTOR_A, method_id)
    assert resolved.version.version == 2


def test_the_superseded_version_survives_and_is_demoted(
    manager, field_service, db_service
) -> None:
    """History stays traceable: the old row is demoted, never deleted."""
    first, first_v = _make_field(field_service, ORG_A)
    second, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Historied", fields=[_field_input(first, 0)])
    )
    method_id = created.identity.method_id
    old_version_id = created.version.version_id

    manager.replace_method_fields_for_actor(
        ACTOR_A, method_id, MethodFieldListUpdateRequest(fields=[_field_input(second, 0)])
    )

    with db_service._db_session() as session:
        old = session.get(MethodLibraryMethodVersionModel, old_version_id)
        assert old is not None, "the superseded version must not be deleted"
        assert old.is_latest is False
        assert old.version == 1
        # Its field rows survive too, still pinned to what it captured.
        rows = (
            session.query(MethodLibraryMethodVersionFieldModel)
            .filter(
                MethodLibraryMethodVersionFieldModel.method_version_id == old_version_id
            )
            .all()
        )
        assert [row.library_field_id for row in rows] == [first]
        assert [row.field_version_id for row in rows] == [first_v]
        # Exactly one version is current.
        latest = (
            session.query(MethodLibraryMethodVersionModel)
            .filter(
                MethodLibraryMethodVersionModel.method_id == method_id,
                MethodLibraryMethodVersionModel.is_latest.is_(True),
            )
            .count()
        )
        assert latest == 1


def test_replacing_with_an_empty_list_is_allowed(manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Emptied", fields=[_field_input(field_id, 0)])
    )
    replaced = manager.replace_method_fields_for_actor(
        ACTOR_A, created.identity.method_id, MethodFieldListUpdateRequest(fields=[])
    )
    assert replaced.version.version == 2
    assert replaced.fields == []


def test_one_org_cannot_replace_another_orgs_field_list(manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Mine", fields=[_field_input(field_id, 0)])
    )
    with pytest.raises(NotFoundError):
        manager.replace_method_fields_for_actor(
            ACTOR_B, created.identity.method_id, MethodFieldListUpdateRequest(fields=[])
        )


# ── Write side: delete ────────────────────────────────────────────────────────


def test_delete_through_the_service_cascades(manager, field_service, db_service) -> None:
    """Going through the real service, not a raw ORM delete."""
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Doomed", fields=[_field_input(field_id, 0)])
    )
    method_id = created.identity.method_id
    version_id = created.version.version_id

    manager.delete_method_for_actor(ACTOR_A, method_id)

    with pytest.raises(NotFoundError):
        manager.get_method_with_fields_for_actor(ACTOR_A, method_id)
    with db_service._db_session() as session:
        assert session.get(MethodLibraryMethodModel, method_id) is None
        assert session.get(MethodLibraryMethodVersionModel, version_id) is None
        assert (
            session.query(MethodLibraryMethodVersionFieldModel)
            .filter(MethodLibraryMethodVersionFieldModel.method_version_id == version_id)
            .count()
            == 0
        ), "version fields must cascade with the method"
        # The library field itself is untouched.
        assert session.get(FieldLibraryFieldModel, field_id) is not None


def test_deleting_an_unknown_method_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.delete_method_for_actor(ACTOR_A, str(uuid.uuid4()))


def test_one_org_cannot_delete_another_orgs_method(manager, field_service, db_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Protected", fields=[_field_input(field_id, 0)])
    )
    with pytest.raises(NotFoundError):
        manager.delete_method_for_actor(ACTOR_B, created.identity.method_id)
    assert manager.get_method_with_fields_for_actor(ACTOR_A, created.identity.method_id)


# ── method_code numbering ─────────────────────────────────────────────────────


def test_numbering_is_sequential_within_an_organization(db_service) -> None:
    codes = [_create_method(db_service, ORG_A).method_code for _ in range(3)]
    assert codes == [1, 2, 3]


def test_each_organization_numbers_independently_from_one(db_service) -> None:
    """Two organizations can both hold method_code 1."""
    a_first = _create_method(db_service, ORG_A).method_code
    b_first = _create_method(db_service, ORG_B).method_code
    a_second = _create_method(db_service, ORG_A).method_code
    assert (a_first, b_first) == (1, 1)
    assert a_second == 2, "org A continues its own sequence, unaffected by org B"


def test_archiving_does_not_free_a_number_for_reuse(db_service) -> None:
    from datetime import UTC, datetime

    first = _create_method(db_service, ORG_A)
    assert first.method_code == 1
    with db_service._db_session() as session:
        session.query(MethodLibraryMethodModel).filter(
            MethodLibraryMethodModel.method_id == first.method_id
        ).update({"archived_at": datetime.now(UTC)}, synchronize_session=False)
        session.commit()

    second = _create_method(db_service, ORG_A)
    assert second.method_code == 2, "the archived method keeps 1; it is never reissued"
    # And the archived row still holds its number.
    with db_service._db_session() as session:
        assert session.get(MethodLibraryMethodModel, first.method_id).method_code == 1


def test_concurrent_creates_never_share_a_number(db_service) -> None:
    """The counter is atomic, so simultaneous creates cannot collide.

    A "max + 1" read would let several of these see the same maximum before any
    committed and all take the same number.
    """
    import threading

    worker_count = 12
    results: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()
    ready = threading.Barrier(worker_count)

    def _create_one() -> None:
        try:
            # Line the threads up so they contend on the counter together.
            ready.wait(timeout=10)
            code = _create_method(db_service, ORG_A).method_code
            with lock:
                results.append(code)
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=_create_one) for _ in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"a concurrent create failed: {errors[0]!r}"
    assert len(results) == worker_count
    assert len(set(results)) == worker_count, f"numbers were reused: {sorted(results)}"
    assert sorted(results) == list(range(1, worker_count + 1)), "and there are no gaps"


# ── Read API: list ────────────────────────────────────────────────────────────


def test_list_returns_identities_with_the_category_name(db_service, manager) -> None:
    category_id = _make_category(db_service, ORG_A, "Reagent Prep")
    method_id = _make_method(db_service, ORG_A, category_id=category_id, name="PBMC")
    items, _total = manager.list_methods_for_actor(ACTOR_A)
    entry = next(item for item in items if item.method_id == method_id)
    assert isinstance(entry.method_code, int)
    assert entry.name == "PBMC"
    assert entry.description == "Isolate cells"
    assert entry.category_name == "Reagent Prep"
    assert entry.created_by == "user-a"
    assert entry.created_at is not None


def test_list_includes_a_method_with_no_category(db_service, manager) -> None:
    """The category join is an outer join, so an uncategorised method still lists."""
    method_id = _make_method(db_service, ORG_A, category_id=None)
    ids = _list_ids(manager, ACTOR_A)
    assert method_id in ids


def test_list_never_crosses_organizations(db_service, manager) -> None:
    method_id = _make_method(db_service, ORG_A)
    ids = _list_ids(manager, ACTOR_B)
    assert method_id not in ids


def test_list_hides_archived_methods_by_default(db_service, manager) -> None:
    from datetime import UTC, datetime

    method_id = _make_method(db_service, ORG_A)
    with db_service._db_session() as session:
        session.query(MethodLibraryMethodModel).filter(
            MethodLibraryMethodModel.method_id == method_id
        ).update({"archived_at": datetime.now(UTC)}, synchronize_session=False)
        session.commit()
    assert method_id not in _list_ids(manager, ACTOR_A)
    assert method_id in _list_ids(manager, ACTOR_A, include_archived=True)


# ── Read API: list pagination and search ──────────────────────────────────────


def test_list_pages_while_total_reflects_every_match(db_service, manager) -> None:
    for index in range(5):
        _make_method(db_service, ORG_A, name=f"Paged {index}")

    first, total = manager.list_methods_for_actor(ACTOR_A, limit=2, offset=0)
    second, total_again = manager.list_methods_for_actor(ACTOR_A, limit=2, offset=2)
    third, _ = manager.list_methods_for_actor(ACTOR_A, limit=2, offset=4)

    assert total == 5, "total counts every match, not just the page"
    assert total_again == 5
    assert (len(first), len(second), len(third)) == (2, 2, 1)
    # Pages must not overlap and must cover everything.
    ids = [m.method_id for m in first + second + third]
    assert len(set(ids)) == 5


def test_a_page_past_the_end_is_empty_but_still_reports_the_total(
    db_service, manager
) -> None:
    """The count comes from the query, not from len(items)."""
    _make_method(db_service, ORG_A)
    items, total = manager.list_methods_for_actor(ACTOR_A, limit=10, offset=50)
    assert items == []
    assert total == 1


def test_search_matches_part_of_the_name_case_insensitively(db_service, manager) -> None:
    match = _make_method(db_service, ORG_A, name="PBMC Isolation")
    _make_method(db_service, ORG_A, name="Glass Wash")
    for term in ("pbmc", "PBMC", "Isolation"):
        assert _list_ids(manager, ACTOR_A, search=term) == {match}, f"search={term!r}"


def test_search_matches_the_category_name_too(db_service, manager) -> None:
    category_id = _make_category(db_service, ORG_A, "Reagent Prep")
    match = _make_method(db_service, ORG_A, category_id=category_id, name="Unrelated Name")
    _make_method(db_service, ORG_A, name="Glass Wash")
    assert _list_ids(manager, ACTOR_A, search="reagent") == {match}


def test_search_with_no_match_returns_an_empty_page_and_zero_total(
    db_service, manager
) -> None:
    _make_method(db_service, ORG_A, name="PBMC Isolation")
    items, total = manager.list_methods_for_actor(ACTOR_A, search="zzz-no-such-method")
    assert items == []
    assert total == 0


def test_search_total_reflects_the_filter_not_the_whole_org(db_service, manager) -> None:
    _make_method(db_service, ORG_A, name="PBMC One")
    _make_method(db_service, ORG_A, name="PBMC Two")
    _make_method(db_service, ORG_A, name="Glass Wash")
    assert _list_total(manager, ACTOR_A) == 3
    assert _list_total(manager, ACTOR_A, search="pbmc") == 2


def test_blank_search_is_treated_as_no_filter(db_service, manager) -> None:
    method_id = _make_method(db_service, ORG_A)
    for term in ("", "   "):
        assert method_id in _list_ids(manager, ACTOR_A, search=term), f"search={term!r}"


def test_search_never_crosses_organizations(db_service, manager) -> None:
    a_method = _make_method(db_service, ORG_A, name="Shared Name")
    _make_method(db_service, ORG_B, name="Shared Name")
    assert _list_ids(manager, ACTOR_A, search="Shared") == {a_method}


# ── Read API: version history ─────────────────────────────────────────────────


def test_version_history_is_newest_first(db_service, manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Historied", fields=[_field_input(field_id, 0)])
    )
    method_id = created.identity.method_id
    for _ in range(2):
        manager.replace_method_fields_for_actor(
            ACTOR_A, method_id, MethodFieldListUpdateRequest(fields=[])
        )

    items, total = manager.list_method_versions_for_actor(ACTOR_A, method_id)
    assert [v.version for v in items] == [3, 2, 1]
    assert total == 3
    assert items[0].is_latest is True
    assert sum(1 for v in items if v.is_latest) == 1


def test_version_history_pages_with_the_full_total(
    db_service, manager, field_service
) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Many Versions", fields=[_field_input(field_id, 0)])
    )
    method_id = created.identity.method_id
    for _ in range(3):
        manager.replace_method_fields_for_actor(
            ACTOR_A, method_id, MethodFieldListUpdateRequest(fields=[])
        )

    first, total = manager.list_method_versions_for_actor(ACTOR_A, method_id, limit=2, offset=0)
    second, total_again = manager.list_method_versions_for_actor(
        ACTOR_A, method_id, limit=2, offset=2
    )
    assert total == 4 and total_again == 4
    assert [v.version for v in first] == [4, 3]
    assert [v.version for v in second] == [2, 1]


def test_a_new_method_has_exactly_one_version_in_its_history(
    manager, field_service
) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Brand New", fields=[_field_input(field_id, 0)])
    )
    items, total = manager.list_method_versions_for_actor(
        ACTOR_A, created.identity.method_id
    )
    assert total == 1
    assert [v.version for v in items] == [1]
    assert items[0].version_id == created.version.version_id


def test_version_history_for_an_unknown_method_is_rejected(manager) -> None:
    """An unknown id must 404, not read as a method with no history."""
    with pytest.raises(NotFoundError):
        manager.list_method_versions_for_actor(ACTOR_A, str(uuid.uuid4()))


def test_one_org_cannot_read_another_orgs_version_history(db_service, manager) -> None:
    method_id = _make_method(db_service, ORG_A)
    _make_version(db_service, ORG_A, method_id)
    with pytest.raises(NotFoundError):
        manager.list_method_versions_for_actor(ACTOR_B, method_id)


# ── Read API: get one, resolved ───────────────────────────────────────────────


def test_get_resolves_the_ordered_field_list_with_merged_shape(
    db_service, field_service, manager
) -> None:
    method_id = _make_method(db_service, ORG_A)
    version_id = _make_version(db_service, ORG_A, method_id)
    first, first_v = _make_field(field_service, ORG_A, settings={"unit": "mL"})
    second, second_v = _make_field(field_service, ORG_A, field_type="text", settings={})
    # Inserted out of order; position defines the order, not insertion.
    _add_field_to_version(
        db_service, ORG_A, version_id, second, second_v, position=1, label="Notes"
    )
    _add_field_to_version(
        db_service, ORG_A, version_id, first, first_v, position=0, label="Volume collected"
    )

    resolved = manager.get_method_with_fields_for_actor(ACTOR_A, method_id)
    assert resolved.identity.method_id == method_id
    assert resolved.version.version_id == version_id
    assert [f.position for f in resolved.fields] == [0, 1]
    volume, notes = resolved.fields
    # The method's own view of the field.
    assert volume.label == "Volume collected"
    assert volume.required is True
    assert volume.placeholder == "e.g. 5"
    # Merged with the pinned field's actual shape.
    assert volume.library_field_id == first
    assert volume.field_version_id == first_v
    assert volume.field_type == "integer"
    assert volume.settings == {"unit": "mL"}
    assert volume.field_key.startswith("volume_")
    assert notes.field_type == "text"


def test_get_resolves_the_pinned_shape_not_the_current_one(
    db_service, field_service, manager
) -> None:
    """A later field edit must not change what an existing method resolves."""
    method_id = _make_method(db_service, ORG_A)
    version_id = _make_version(db_service, ORG_A, method_id)
    field_id, pinned_version = _make_field(
        field_service, ORG_A, field_type="integer", settings={"unit": "mL"}
    )
    _add_field_to_version(db_service, ORG_A, version_id, field_id, pinned_version)

    # The field moves on: new version, new type and settings.
    field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description="edited",
        settings={"unit": "L"},
        created_by="user-a",
        field_type="text",
    )

    resolved = manager.get_method_with_fields_for_actor(ACTOR_A, method_id)
    entry = resolved.fields[0]
    assert entry.field_version_id == pinned_version
    assert entry.field_type == "integer", "must resolve the pinned type, not the current one"
    assert entry.settings == {"unit": "mL"}


def test_get_uses_the_latest_method_version(db_service, field_service, manager) -> None:
    method_id = _make_method(db_service, ORG_A)
    first_version = _make_version(db_service, ORG_A, method_id, version=1)
    field_id, field_version = _make_field(field_service, ORG_A)
    _add_field_to_version(db_service, ORG_A, first_version, field_id, field_version)

    second_version = _make_version(db_service, ORG_A, method_id, version=2)
    other_field, other_version = _make_field(field_service, ORG_A)
    _add_field_to_version(
        db_service, ORG_A, second_version, other_field, other_version, label="Newer"
    )

    resolved = manager.get_method_with_fields_for_actor(ACTOR_A, method_id)
    assert resolved.version.version == 2
    assert [f.label for f in resolved.fields] == ["Newer"]


def test_get_rejects_an_unknown_method(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.get_method_with_fields_for_actor(ACTOR_A, str(uuid.uuid4()))


def test_one_org_cannot_read_another_orgs_method(db_service, manager) -> None:
    method_id = _make_method(db_service, ORG_A)
    _make_version(db_service, ORG_A, method_id)
    with pytest.raises(NotFoundError):
        manager.get_method_with_fields_for_actor(ACTOR_B, method_id)


def test_actor_without_organization_is_rejected(manager) -> None:
    with pytest.raises(Exception, match="organization_id"):
        manager.list_methods_for_actor({"user_id": "nobody"})


# ── Categories ────────────────────────────────────────────────────────────────


def _create_category(manager, actor, name: str):
    return manager.create_category_for_actor(actor, MethodCategoryCreateRequest(name=name))


def test_creating_a_category_returns_it_with_its_id(manager) -> None:
    category = _create_category(manager, ACTOR_A, "Reagent Prep")
    assert category.name == "Reagent Prep"
    assert category.organization_id == ORG_A
    assert category.category_id
    assert category.created_at is not None


def test_a_category_name_is_taken_regardless_of_case(manager) -> None:
    _create_category(manager, ACTOR_A, "Reagent Prep")
    for clashing in ("Reagent Prep", "REAGENT PREP", "reagent prep"):
        with pytest.raises(ValidationError, match="already exists"):
            _create_category(manager, ACTOR_A, clashing)


def test_a_category_name_is_only_taken_within_one_organization(manager) -> None:
    """The name is per organization, so two tenants can both use it."""
    mine = _create_category(manager, ACTOR_A, "Reagent Prep")
    theirs = _create_category(manager, ACTOR_B, "Reagent Prep")
    assert mine.category_id != theirs.category_id
    assert (mine.organization_id, theirs.organization_id) == (ORG_A, ORG_B)


def test_a_category_name_is_stripped_before_it_is_stored(manager) -> None:
    category = _create_category(manager, ACTOR_A, "  Reagent Prep  ")
    assert category.name == "Reagent Prep"
    # And the stripped name is what uniqueness sees.
    with pytest.raises(ValidationError, match="already exists"):
        _create_category(manager, ACTOR_A, "reagent prep")


def test_listing_categories_is_ordered_by_name(manager) -> None:
    for name in ("Wash", "Analysis", "Reagent Prep"):
        _create_category(manager, ACTOR_A, name)
    names = [c.name for c in manager.list_categories_for_actor(ACTOR_A)]
    assert names == ["Analysis", "Reagent Prep", "Wash"]


def test_listing_categories_never_crosses_organizations(manager) -> None:
    mine = _create_category(manager, ACTOR_A, "Reagent Prep")
    _create_category(manager, ACTOR_B, "Theirs Only")
    assert [c.category_id for c in manager.list_categories_for_actor(ACTOR_A)] == [
        mine.category_id
    ]


def test_renaming_a_category_keeps_its_id(manager) -> None:
    category = _create_category(manager, ACTOR_A, "Reagent Prep")
    renamed = manager.rename_category_for_actor(
        ACTOR_A, category.category_id, MethodCategoryRenameRequest(name="Sample Prep")
    )
    assert renamed.category_id == category.category_id
    assert renamed.name == "Sample Prep"
    assert [c.name for c in manager.list_categories_for_actor(ACTOR_A)] == ["Sample Prep"]


def test_a_rename_cannot_take_a_name_another_category_already_has(manager) -> None:
    _create_category(manager, ACTOR_A, "Reagent Prep")
    other = _create_category(manager, ACTOR_A, "Wash")
    with pytest.raises(ValidationError, match="already exists"):
        manager.rename_category_for_actor(
            ACTOR_A, other.category_id, MethodCategoryRenameRequest(name="REAGENT PREP")
        )
    # The failed rename left the category as it was.
    assert [c.name for c in manager.list_categories_for_actor(ACTOR_A)] == [
        "Reagent Prep",
        "Wash",
    ]


def test_renaming_an_unknown_category_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.rename_category_for_actor(
            ACTOR_A, str(uuid.uuid4()), MethodCategoryRenameRequest(name="Anything")
        )


def test_one_org_cannot_rename_another_orgs_category(manager) -> None:
    category = _create_category(manager, ACTOR_B, "Theirs")
    with pytest.raises(NotFoundError):
        manager.rename_category_for_actor(
            ACTOR_A, category.category_id, MethodCategoryRenameRequest(name="Mine Now")
        )


def test_deleting_an_unused_category_removes_it(manager) -> None:
    category = _create_category(manager, ACTOR_A, "Reagent Prep")
    manager.delete_category_for_actor(ACTOR_A, category.category_id)
    assert manager.list_categories_for_actor(ACTOR_A) == []


def test_deleting_a_category_a_method_uses_is_refused(db_service, manager) -> None:
    """The foreign key refuses it, and that surfaces as a 4xx, not a 500."""
    category = _create_category(manager, ACTOR_A, "Reagent Prep")
    _make_method(db_service, ORG_A, category_id=category.category_id)
    with pytest.raises(ValidationError, match="still filed under this category"):
        manager.delete_category_for_actor(ACTOR_A, category.category_id)
    assert [c.category_id for c in manager.list_categories_for_actor(ACTOR_A)] == [
        category.category_id
    ]


def test_a_category_can_be_deleted_once_the_last_method_leaves_it(db_service, manager) -> None:
    category = _create_category(manager, ACTOR_A, "Reagent Prep")
    method_id = _make_method(db_service, ORG_A, category_id=category.category_id)
    db_service.delete_method(organization_id=ORG_A, method_id=method_id)
    manager.delete_category_for_actor(ACTOR_A, category.category_id)
    assert manager.list_categories_for_actor(ACTOR_A) == []


def test_deleting_an_unknown_category_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.delete_category_for_actor(ACTOR_A, str(uuid.uuid4()))


def test_one_org_cannot_delete_another_orgs_category(manager) -> None:
    category = _create_category(manager, ACTOR_B, "Theirs")
    with pytest.raises(NotFoundError):
        manager.delete_category_for_actor(ACTOR_A, category.category_id)
    assert [c.category_id for c in manager.list_categories_for_actor(ACTOR_B)] == [
        category.category_id
    ]


# ── Write side: clone ─────────────────────────────────────────────────────────


def _clone(manager, actor, method_id: str, name: str = "Cloned", **overrides):
    payload = {"name": name}
    payload.update(overrides)
    return manager.clone_method_for_actor(actor, method_id, MethodCloneRequest(**payload))


def _seed_source(manager, field_service, *, name: str = "Source", category_id=None):
    """A method with two fields on its version 1."""
    field_a, _ = _make_field(field_service, ORG_A)
    field_b, _ = _make_field(field_service, ORG_A)
    return manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name=name,
            category_id=category_id,
            fields=[_field_input(field_a, 0), _field_input(field_b, 1)],
        ),
    )


def test_cloning_without_a_version_copies_the_current_latest(manager, field_service) -> None:
    source = _seed_source(manager, field_service)
    field_c, _ = _make_field(field_service, ORG_A)
    manager.replace_method_fields_for_actor(
        ACTOR_A,
        source.identity.method_id,
        MethodFieldListUpdateRequest(fields=[_field_input(field_c, 0, label="Only C")]),
    )

    clone = _clone(manager, ACTOR_A, source.identity.method_id)
    assert [f.label for f in clone.fields] == ["Only C"]
    assert [f.library_field_id for f in clone.fields] == [field_c]


def test_cloning_a_named_version_copies_that_one_not_the_newest(
    manager, field_service
) -> None:
    """The source moving on afterwards must not change what the clone gets."""
    source = _seed_source(manager, field_service)
    original_version_id = source.version.version_id
    original_labels = [f.label for f in source.fields]
    field_c, _ = _make_field(field_service, ORG_A)
    manager.replace_method_fields_for_actor(
        ACTOR_A,
        source.identity.method_id,
        MethodFieldListUpdateRequest(fields=[_field_input(field_c, 0, label="Only C")]),
    )

    clone = _clone(
        manager, ACTOR_A, source.identity.method_id, source_version_id=original_version_id
    )
    assert [f.label for f in clone.fields] == original_labels
    assert "Only C" not in [f.label for f in clone.fields]


def test_a_clone_keeps_the_source_versions_field_pins(manager, field_service) -> None:
    """The point of cloning a version: reproduce it, never silently upgrade it."""
    field_id, pinned_version = _make_field(
        field_service, ORG_A, field_type="integer", settings={"unit": "mL"}
    )
    source = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Pinned", fields=[_field_input(field_id, 0)])
    )
    # The field moves on after the source version was built.
    newer = field_service.add_version(
        organization_id=ORG_A,
        library_field_id=field_id,
        description="edited",
        settings={"unit": "L"},
        created_by="user-a",
        field_type="text",
    )

    clone = _clone(manager, ACTOR_A, source.identity.method_id)
    entry = clone.fields[0]
    assert entry.field_version_id == pinned_version
    assert entry.field_version_id != newer.version_id
    assert entry.field_type == "integer", "must copy the pin, not re-resolve to the latest"
    assert entry.settings == {"unit": "mL"}


def test_a_clone_starts_at_version_one_whatever_it_was_cloned_from(
    manager, field_service
) -> None:
    source = _seed_source(manager, field_service)
    for _ in range(2):
        manager.replace_method_fields_for_actor(
            ACTOR_A, source.identity.method_id, MethodFieldListUpdateRequest(fields=[])
        )
    _items, source_total = manager.list_method_versions_for_actor(
        ACTOR_A, source.identity.method_id
    )
    assert source_total == 3, "the source is on version 3 before the clone"

    clone = _clone(manager, ACTOR_A, source.identity.method_id)
    assert clone.version.version == 1
    assert clone.version.is_latest is True
    _clone_items, clone_total = manager.list_method_versions_for_actor(
        ACTOR_A, clone.identity.method_id
    )
    assert clone_total == 1, "a clone carries no history from its source"


def test_a_clone_is_a_new_method_with_its_own_code(manager, field_service) -> None:
    source = _seed_source(manager, field_service)
    clone = _clone(manager, ACTOR_A, source.identity.method_id, name="Cloned Method")

    assert clone.identity.method_id != source.identity.method_id
    assert clone.identity.method_code == source.identity.method_code + 1
    assert clone.identity.name == "Cloned Method", "the caller names it, nothing invents one"
    # Editing the clone leaves the source alone: this is a copy, not a link.
    manager.replace_method_fields_for_actor(
        ACTOR_A, clone.identity.method_id, MethodFieldListUpdateRequest(fields=[])
    )
    assert manager.get_method_with_fields_for_actor(
        ACTOR_A, source.identity.method_id
    ).version.version == 1


def test_a_clone_inherits_the_sources_category_when_none_is_given(
    db_service, manager, field_service
) -> None:
    category_id = _make_category(db_service, ORG_A, "Reagent Prep")
    source = _seed_source(manager, field_service, category_id=category_id)
    clone = _clone(manager, ACTOR_A, source.identity.method_id)
    assert clone.identity.category_id == category_id
    assert clone.identity.category_name == "Reagent Prep"


def test_a_clone_uses_the_category_it_was_given(db_service, manager, field_service) -> None:
    source_category = _make_category(db_service, ORG_A, "Reagent Prep")
    target_category = _make_category(db_service, ORG_A, "Analysis")
    source = _seed_source(manager, field_service, category_id=source_category)
    clone = _clone(manager, ACTOR_A, source.identity.method_id, category_id=target_category)
    assert clone.identity.category_id == target_category
    assert clone.identity.category_name == "Analysis"


def test_cloning_a_version_belonging_to_another_method_is_rejected(
    manager, field_service
) -> None:
    source = _seed_source(manager, field_service, name="Source")
    other = _seed_source(manager, field_service, name="Other")
    with pytest.raises(NotFoundError, match="does not belong to method"):
        _clone(
            manager,
            ACTOR_A,
            source.identity.method_id,
            source_version_id=other.version.version_id,
        )
    # Nothing was created by the rejected clone.
    assert _list_total(manager, ACTOR_A) == 2


def test_cloning_a_version_from_another_org_is_rejected(manager, field_service) -> None:
    source = _seed_source(manager, field_service)
    with pytest.raises(NotFoundError):
        manager.clone_method_for_actor(
            ACTOR_B,
            source.identity.method_id,
            MethodCloneRequest(name="Theirs Now", source_version_id=source.version.version_id),
        )
    assert _list_total(manager, ACTOR_B) == 0


def test_cloning_an_unknown_method_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        _clone(manager, ACTOR_A, str(uuid.uuid4()))


# ── Review follow-ups: inputs that must be refused, not coerced ───────────────


def test_a_null_name_is_rejected_rather_than_stringified(manager, field_service) -> None:
    """Regression: str(None) would rename the method to the literal "None"."""
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Real Name", fields=[_field_input(field_id, 0)])
    )
    method_id = created.identity.method_id

    with pytest.raises(ValidationError, match="name is required"):
        manager.update_method_metadata_for_actor(
            ACTOR_A, method_id, MethodMetadataUpdateRequest.model_validate({"name": None})
        )

    assert manager.get_method_with_fields_for_actor(
        ACTOR_A, method_id
    ).identity.name == "Real Name", "the failed edit left the name alone"


def test_a_blank_name_is_still_rejected(manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Real Name", fields=[_field_input(field_id, 0)])
    )
    with pytest.raises(ValidationError, match="name is required"):
        manager.update_method_metadata_for_actor(
            ACTOR_A,
            created.identity.method_id,
            MethodMetadataUpdateRequest.model_validate({"name": "   "}),
        )


def test_an_archived_field_cannot_be_adopted_by_a_new_method(
    manager, field_service
) -> None:
    """A field that can take no further versions must not join a new method."""
    field_id, _ = _make_field(field_service, ORG_A)
    field_service.archive_field(organization_id=ORG_A, library_field_id=field_id)

    with pytest.raises(ValidationError, match="archived"):
        manager.create_method_for_actor(
            ACTOR_A, MethodCreateRequest(name="Uses Archived", fields=[_field_input(field_id, 0)])
        )


def test_an_archived_field_cannot_be_added_by_replacing_the_field_list(
    manager, field_service
) -> None:
    live_id, _ = _make_field(field_service, ORG_A)
    archived_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Grows Later", fields=[_field_input(live_id, 0)])
    )
    field_service.archive_field(organization_id=ORG_A, library_field_id=archived_id)

    with pytest.raises(ValidationError, match="archived"):
        manager.replace_method_fields_for_actor(
            ACTOR_A,
            created.identity.method_id,
            MethodFieldListUpdateRequest(fields=[_field_input(archived_id, 0)]),
        )


def test_archiving_a_field_leaves_methods_that_already_pin_it_readable(
    manager, field_service
) -> None:
    """Only new adoptions are refused; existing pins must keep resolving."""
    field_id, version_id = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Pinned Before", fields=[_field_input(field_id, 0)])
    )
    field_service.archive_field(organization_id=ORG_A, library_field_id=field_id)

    resolved = manager.get_method_with_fields_for_actor(ACTOR_A, created.identity.method_id)
    assert [f.field_version_id for f in resolved.fields] == [version_id]


def test_creating_with_an_unknown_category_is_a_validation_error(
    manager, field_service
) -> None:
    """The foreign key would refuse it too, but only as a 500."""
    field_id, _ = _make_field(field_service, ORG_A)
    with pytest.raises(ValidationError, match="was not found"):
        manager.create_method_for_actor(
            ACTOR_A,
            MethodCreateRequest(
                name="Bad Category",
                category_id=str(uuid.uuid4()),
                fields=[_field_input(field_id, 0)],
            ),
        )


def test_creating_with_another_orgs_category_is_a_validation_error(
    db_service, manager, field_service
) -> None:
    theirs = _make_category(db_service, ORG_B, "Theirs")
    field_id, _ = _make_field(field_service, ORG_A)
    with pytest.raises(ValidationError, match="was not found"):
        manager.create_method_for_actor(
            ACTOR_A,
            MethodCreateRequest(
                name="Borrowed Category",
                category_id=theirs,
                fields=[_field_input(field_id, 0)],
            ),
        )


def test_patching_to_an_unknown_category_is_a_validation_error(
    manager, field_service
) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Recategorised", fields=[_field_input(field_id, 0)])
    )
    with pytest.raises(ValidationError, match="was not found"):
        manager.update_method_metadata_for_actor(
            ACTOR_A,
            created.identity.method_id,
            MethodMetadataUpdateRequest(category_id=str(uuid.uuid4())),
        )


def test_cloning_into_an_unknown_category_is_a_validation_error(
    manager, field_service
) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Source", fields=[_field_input(field_id, 0)])
    )
    with pytest.raises(ValidationError, match="was not found"):
        manager.clone_method_for_actor(
            ACTOR_A,
            created.identity.method_id,
            MethodCloneRequest(name="Clone", category_id=str(uuid.uuid4())),
        )


def test_a_known_category_still_works_on_every_write_path(
    db_service, manager, field_service
) -> None:
    """The guard must not turn a legitimate category into a rejection."""
    category_id = _make_category(db_service, ORG_A, "Reagent Prep")
    field_id, _ = _make_field(field_service, ORG_A)

    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="Categorised", category_id=category_id, fields=[_field_input(field_id, 0)]
        ),
    )
    assert created.identity.category_id == category_id

    clone = manager.clone_method_for_actor(
        ACTOR_A,
        created.identity.method_id,
        MethodCloneRequest(name="Clone", category_id=category_id),
    )
    assert clone.identity.category_id == category_id

    patched = manager.update_method_metadata_for_actor(
        ACTOR_A, created.identity.method_id, MethodMetadataUpdateRequest(category_id=None)
    )
    assert patched.category_id is None, "clearing the category is still allowed"


# ── Review follow-ups: field order must be defined ───────────────────────────


def test_omitted_positions_follow_the_order_the_caller_sent(manager, field_service) -> None:
    """Regression: every field defaulted to 0, leaving the read order to Postgres."""
    first, _ = _make_field(field_service, ORG_A)
    second, _ = _make_field(field_service, ORG_A)
    third, _ = _make_field(field_service, ORG_A)

    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="Ordered",
            fields=[
                MethodFieldInput(library_field_id=field_id)
                for field_id in (first, second, third)
            ],
        ),
    )

    assert [f.position for f in created.fields] == [0, 1, 2]
    assert [f.library_field_id for f in created.fields] == [first, second, third]


def test_explicit_positions_are_honoured_as_given(manager, field_service) -> None:
    first, _ = _make_field(field_service, ORG_A)
    second, _ = _make_field(field_service, ORG_A)

    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="Explicitly Ordered",
            fields=[_field_input(first, 5), _field_input(second, 2)],
        ),
    )

    assert [f.library_field_id for f in created.fields] == [second, first]
    assert [f.position for f in created.fields] == [2, 5]


def test_repeated_explicit_positions_are_rejected(field_service) -> None:
    """Two fields claiming one slot has no order to honour."""
    first, _ = _make_field(field_service, ORG_A)
    second, _ = _make_field(field_service, ORG_A)
    with pytest.raises(PydanticValidationError, match="must be distinct"):
        MethodCreateRequest(
            name="Clashing", fields=[_field_input(first, 3), _field_input(second, 3)]
        )


def test_replacing_the_field_list_orders_the_same_way(manager, field_service) -> None:
    first, _ = _make_field(field_service, ORG_A)
    second, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Reordered", fields=[_field_input(first, 0)])
    )

    replaced = manager.replace_method_fields_for_actor(
        ACTOR_A,
        created.identity.method_id,
        MethodFieldListUpdateRequest(
            fields=[
                MethodFieldInput(library_field_id=second),
                MethodFieldInput(library_field_id=first),
            ]
        ),
    )

    assert [f.library_field_id for f in replaced.fields] == [second, first]
    assert [f.position for f in replaced.fields] == [0, 1]


def test_a_clone_keeps_the_order_of_the_version_it_copied(manager, field_service) -> None:
    first, _ = _make_field(field_service, ORG_A)
    second, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="Ordered Source",
            fields=[
                MethodFieldInput(library_field_id=second),
                MethodFieldInput(library_field_id=first),
            ],
        ),
    )

    clone = manager.clone_method_for_actor(
        ACTOR_A, created.identity.method_id, MethodCloneRequest(name="Ordered Clone")
    )

    assert [f.library_field_id for f in clone.fields] == [second, first]
    assert [f.position for f in clone.fields] == [0, 1]


# ── Source intent (entity-agnostic field resolution) ─────────────────────────


def test_create_persists_source_intent_and_a_subsequent_get_returns_it(
    manager, field_service
) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="Candidate Email Capture",
            fields=[
                _field_input(
                    field_id,
                    0,
                    source_entity_type="ATS.Candidate",
                    source_field_key="email",
                )
            ],
        ),
    )
    assert created.fields[0].source_entity_type == "ATS.Candidate"
    assert created.fields[0].source_field_key == "email"

    # Not just the create response echoing the input back — a separate read.
    fetched = manager.get_method_with_fields_for_actor(ACTOR_A, created.identity.method_id)
    assert fetched.fields[0].source_entity_type == "ATS.Candidate"
    assert fetched.fields[0].source_field_key == "email"


def test_field_without_source_intent_behaves_exactly_as_before(manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A, MethodCreateRequest(name="Plain", fields=[_field_input(field_id, 0)])
    )
    assert created.fields[0].source_entity_type is None
    assert created.fields[0].source_field_key is None


def test_source_intent_requires_both_entity_type_and_field_key(field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    with pytest.raises(PydanticValidationError, match="must both be set, or both omitted"):
        _field_input(field_id, 0, source_entity_type="ATS.Candidate")


def test_replace_fields_updates_source_intent_and_get_reflects_the_new_version(
    manager, field_service
) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="Repointed",
            fields=[
                _field_input(
                    field_id, 0, source_entity_type="ATS.Candidate", source_field_key="email"
                )
            ],
        ),
    )
    method_id = created.identity.method_id

    replaced = manager.replace_method_fields_for_actor(
        ACTOR_A,
        method_id,
        MethodFieldListUpdateRequest(
            fields=[
                _field_input(field_id, 0, source_entity_type="ATS.Job", source_field_key="title")
            ]
        ),
    )
    assert replaced.fields[0].source_entity_type == "ATS.Job"
    assert replaced.fields[0].source_field_key == "title"

    fetched = manager.get_method_with_fields_for_actor(ACTOR_A, method_id)
    assert fetched.fields[0].source_entity_type == "ATS.Job"
    assert fetched.fields[0].source_field_key == "title"


def test_clone_carries_source_intent_forward(manager, field_service) -> None:
    field_id, _ = _make_field(field_service, ORG_A)
    created = manager.create_method_for_actor(
        ACTOR_A,
        MethodCreateRequest(
            name="Source",
            fields=[
                _field_input(
                    field_id, 0, source_entity_type="ATS.Candidate", source_field_key="email"
                )
            ],
        ),
    )
    clone = manager.clone_method_for_actor(
        ACTOR_A, created.identity.method_id, MethodCloneRequest(name="Clone")
    )
    assert clone.fields[0].source_entity_type == "ATS.Candidate"
    assert clone.fields[0].source_field_key == "email"

"""Field library: immutable fields, uniqueness rules, and tenant isolation.

The rules worth most scrutiny are case-insensitive uniqueness of name and key
within an organization, and that no read or write crosses an org boundary.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from exceptions import NotFoundError, ValidationError
from field_library.db_models import (
    FieldInUseError,
    FieldLibraryFieldModel,
    FieldLibraryFieldVersionModel,
    FieldLibraryModelService,
)
from field_library.manager import (
    NOT_BUILT_REASON,
    NOT_ENABLED_REASON,
    FieldLibraryServiceManager,
)
from field_library.models.interface import FIELD_KEY_MAX_LENGTH, FIELD_NAME_MAX_LENGTH
from field_library.models.request import (
    FieldCreateRequest,
    FieldDescriptionUpdateRequest,
    FieldRenameRequest,
    FieldVersionCreateRequest,
)
from field_library.models.response import FieldTypeCatalogueResponse, FieldTypeOption

ORG_A = "test-org-1"
ORG_B = "test-org-2"
ACTOR_A = {"user_id": "user-a", "organization_id": ORG_A}
ACTOR_B = {"user_id": "user-b", "organization_id": ORG_B}


@pytest.fixture
def db_service(entities_db_service_manager) -> FieldLibraryModelService:
    return FieldLibraryModelService(entities_db_service_manager)


@pytest.fixture
def manager(db_service) -> FieldLibraryServiceManager:
    service = FieldLibraryServiceManager(db_service)
    service.start()
    return service


def _enable_only_types(db_service, org_id: str, codes: list[str]) -> None:
    """Give the org explicit enablement rows: `codes` on, everything else off."""
    from field_library.db_models import OrganizationFieldTypeModel

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


@pytest.fixture
def clean_org_type_settings(db_service):
    """Remove type-enablement rows so other tests keep the all-enabled default."""
    from field_library.db_models import OrganizationFieldTypeModel

    def _purge() -> None:
        with db_service._db_session() as session:
            session.query(OrganizationFieldTypeModel).filter(
                OrganizationFieldTypeModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.commit()

    _purge()
    yield
    _purge()


@pytest.fixture
def real_user(db_service):
    """A real users row, so created_by resolves to a display name."""
    from user.db_models import User

    user_id = str(uuid.uuid4())
    full_name = "Ada Lovelace"
    with db_service._db_session() as session:
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@example.test",
                full_name=full_name,
                hashed_password="x",
            )
        )
        session.commit()
    yield user_id, full_name
    with db_service._db_session() as session:
        session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        session.commit()


@pytest.fixture(autouse=True)
def clean_fields(db_service):
    """Drop both test orgs' fields before and after each test."""

    def _purge() -> None:
        with db_service._db_session() as session:
            session.query(FieldLibraryFieldVersionModel).filter(
                FieldLibraryFieldVersionModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.query(FieldLibraryFieldModel).filter(
                FieldLibraryFieldModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.commit()

    _purge()
    yield
    _purge()


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create(manager: FieldLibraryServiceManager, actor: dict, **overrides):
    payload = {
        "name": _unique("Volume"),
        "field_key": _unique("volume"),
        "field_type": "integer",
        "description": "millilitres captured at the bench",
        "settings": {"unit": "mL"},
    }
    payload.update(overrides)
    return manager.create_field_for_actor(actor, FieldCreateRequest(**payload))


def _identity(manager: FieldLibraryServiceManager, actor: dict, **overrides):
    """Create a field and return just its identity, which most tests assert on."""
    return _create(manager, actor, **overrides).identity


def _list_ids(manager: FieldLibraryServiceManager, actor: dict, **kwargs) -> set[str]:
    """The library_field_ids on one page of the list."""
    items, _total = manager.list_fields_for_actor(actor, **kwargs)
    return {item.identity.library_field_id for item in items}


def _list_total(manager: FieldLibraryServiceManager, actor: dict, **kwargs) -> int:
    """The total match count, which spans every page not just this one."""
    _items, total = manager.list_fields_for_actor(actor, **kwargs)
    return total


# ── Creation: identity plus version 1 ─────────────────────────────────────────


def test_create_field_makes_an_identity_and_version_one(manager) -> None:
    created = _create(manager, ACTOR_A)
    assert created.identity.library_field_id
    assert created.identity.name.startswith("Volume")
    assert created.identity.field_type == "integer"
    assert created.identity.created_by == "user-a"
    assert created.identity.is_archived is False
    # Editable content lives on the version, not the identity.
    assert created.version.version == 1
    assert created.version.is_latest is True
    assert created.version.description == "millilitres captured at the bench"
    assert created.version.settings == {"unit": "mL"}
    assert created.version.version_id != created.identity.library_field_id


def test_field_count_id_is_assigned_by_the_database(manager) -> None:
    """The counter is generated on insert, not supplied by the caller."""
    created = _identity(manager, ACTOR_A)
    assert isinstance(created.field_count_id, int)
    assert created.field_count_id > 0


def test_field_count_id_increments_across_fields(manager) -> None:
    first = _identity(manager, ACTOR_A)
    second = _identity(manager, ACTOR_A)
    assert second.field_count_id > first.field_count_id


def test_field_count_id_is_distinct_from_the_uuid(manager) -> None:
    created = _identity(manager, ACTOR_A)
    assert str(created.field_count_id) != created.library_field_id
    assert len(created.library_field_id) > len(str(created.field_count_id))


def test_settings_and_description_are_optional(manager) -> None:
    created = _create(manager, ACTOR_A, description=None, settings={})
    assert created.version.description is None
    assert created.version.settings == {}


def test_reading_a_field_back_returns_its_current_version(manager) -> None:
    created = _create(manager, ACTOR_A)
    fetched = manager.get_field_for_actor(ACTOR_A, created.identity.library_field_id)
    assert fetched.identity.library_field_id == created.identity.library_field_id
    assert fetched.identity.field_count_id == created.identity.field_count_id
    assert fetched.version.version_id == created.version.version_id
    assert fetched.version.settings == created.version.settings


# ── Versioning ────────────────────────────────────────────────────────────────


def test_new_version_bumps_the_number_and_moves_is_latest(manager) -> None:
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(description="v2", settings={"unit": "L"})
    )
    assert second.version == 2
    assert second.is_latest is True

    versions = manager.list_versions_for_actor(ACTOR_A, field_id)
    assert [v.version for v in versions] == [2, 1], "newest first"
    assert sum(1 for v in versions if v.is_latest) == 1, "exactly one version may be current"
    first = next(v for v in versions if v.version == 1)
    assert first.is_latest is False
    # Version 1's content is untouched by the edit.
    assert first.version_id == created.version.version_id
    assert first.settings == {"unit": "mL"}


def test_get_field_returns_the_newest_version_after_an_edit(manager) -> None:
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(description="v2")
    )
    assert manager.get_field_for_actor(ACTOR_A, field_id).version.version == 2


def test_key_and_type_survive_a_new_version(manager) -> None:
    """They live on the identity, so a version cannot carry them at all."""
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    manager.create_version_for_actor(ACTOR_A, field_id, FieldVersionCreateRequest())
    identity = manager.get_field_for_actor(ACTOR_A, field_id).identity
    assert identity.field_key == created.identity.field_key
    assert identity.field_type == created.identity.field_type
    assert not hasattr(FieldVersionCreateRequest(), "field_key")


def test_archived_field_cannot_take_a_new_version(manager) -> None:
    created = _create(manager, ACTOR_A)
    manager.archive_field_for_actor(ACTOR_A, created.identity.library_field_id)
    with pytest.raises(ValidationError, match="archived"):
        manager.create_version_for_actor(
            ACTOR_A, created.identity.library_field_id, FieldVersionCreateRequest()
        )


def test_version_list_is_newest_first(manager) -> None:
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    for label in ("v2", "v3"):
        manager.create_version_for_actor(
            ACTOR_A, field_id, FieldVersionCreateRequest(description=label)
        )
    versions = manager.list_versions_for_actor(ACTOR_A, field_id)
    assert [v.version for v in versions] == [3, 2, 1]
    assert versions[0].is_latest is True


def test_version_carries_the_resolved_creator_name(manager, real_user) -> None:
    """created_by keeps the id; created_by_name adds the display name."""
    actor = {"user_id": real_user[0], "organization_id": ORG_A}
    created = _create(manager, actor)
    assert created.version.created_by == real_user[0]
    assert created.version.created_by_name == real_user[1]
    assert created.identity.created_by == real_user[0]
    assert created.identity.created_by_name == real_user[1]


def test_unknown_creator_leaves_the_name_unresolved(manager) -> None:
    """A missing user must not break the response; the id still comes back."""
    created = _create(manager, ACTOR_A)
    assert created.version.created_by == "user-a"
    assert created.version.created_by_name is None


def test_creator_names_are_resolved_in_one_query(manager, real_user, db_service) -> None:
    """Batched, so a long version list does not become a query per row."""
    from sqlalchemy import event

    actor = {"user_id": real_user[0], "organization_id": ORG_A}
    field_id = _create(manager, actor).identity.library_field_id
    for _ in range(5):
        manager.create_version_for_actor(actor, field_id, FieldVersionCreateRequest())

    seen = {"n": 0}

    def _count(conn, cursor, statement, params, context, executemany):
        if " users" in statement.lower():
            seen["n"] += 1

    event.listen(db_service.current_db.engine, "before_cursor_execute", _count)
    try:
        versions = db_service.list_versions(
            organization_id=ORG_A, library_field_id=field_id
        )
    finally:
        event.remove(db_service.current_db.engine, "before_cursor_execute", _count)

    assert len(versions) == 6
    assert seen["n"] == 1, f"six versions must cost one users lookup, saw {seen['n']}"
    assert all(v.created_by_name == real_user[1] for v in versions)


# ── What a new version does with the description ──────────────────────────────


def test_a_settings_only_version_keeps_the_previous_description(manager) -> None:
    """Regression: omitting the key must not read as "clear it"."""
    created = _create(manager, ACTOR_A, description="millilitres at the bench")
    field_id = created.identity.library_field_id

    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(settings={"unit": "L"})
    )

    assert second.version == 2
    assert second.description == "millilitres at the bench"
    assert second.settings == {"unit": "L"}, "the settings the caller did send still applied"


def test_a_version_carrying_nothing_at_all_still_keeps_the_description(manager) -> None:
    created = _create(manager, ACTOR_A, description="wording worth keeping")
    field_id = created.identity.library_field_id
    second = manager.create_version_for_actor(ACTOR_A, field_id, FieldVersionCreateRequest())
    assert second.description == "wording worth keeping"


def test_an_explicit_null_description_clears_it(manager) -> None:
    """Sending the key with null is an instruction, not an omission."""
    created = _create(manager, ACTOR_A, description="about to be cleared")
    field_id = created.identity.library_field_id

    second = manager.create_version_for_actor(
        ACTOR_A,
        field_id,
        FieldVersionCreateRequest.model_validate({"description": None, "settings": {}}),
    )

    assert second.version == 2
    assert second.description is None


def test_a_new_description_replaces_the_old_one(manager) -> None:
    created = _create(manager, ACTOR_A, description="first wording")
    field_id = created.identity.library_field_id
    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(description="second wording")
    )
    assert second.description == "second wording"


def test_a_type_only_version_still_carries_the_description_forward(manager) -> None:
    """The type change and the carry-forward must not interfere with each other."""
    created = _create(
        manager, ACTOR_A, field_type="integer", description="millilitres at the bench"
    )
    field_id = created.identity.library_field_id

    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(field_type="text")
    )

    assert second.field_type == "text"
    assert second.description == "millilitres at the bench"
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.field_type == "text"


def test_the_description_carries_from_the_current_version_not_the_first(manager) -> None:
    """Each bump carries the wording as it stands now, not as it started."""
    created = _create(manager, ACTOR_A, description="v1 wording")
    field_id = created.identity.library_field_id
    manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(description="v2 wording")
    )

    third = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(settings={"unit": "L"})
    )

    assert third.version == 3
    assert third.description == "v2 wording"


def test_a_field_with_no_description_still_versions_cleanly(manager) -> None:
    created = _create(manager, ACTOR_A, description=None)
    field_id = created.identity.library_field_id
    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(settings={"unit": "L"})
    )
    assert second.description is None


# ── Editing the description in place ──────────────────────────────────────────


def test_description_edit_updates_the_latest_version_in_place(manager) -> None:
    created = _create(manager, ACTOR_A, description="first wording")
    field_id = created.identity.library_field_id

    updated = manager.update_description_for_actor(
        ACTOR_A, field_id, FieldDescriptionUpdateRequest(description="clearer wording")
    )
    assert updated.description == "clearer wording"
    # Same row, same number, still current: nothing was created or bumped.
    assert updated.version_id == created.version.version_id
    assert updated.version == created.version.version
    assert updated.is_latest is True

    versions = manager.list_versions_for_actor(ACTOR_A, field_id)
    assert len(versions) == 1, "a description edit must not create a version"
    assert versions[0].description == "clearer wording"


def test_description_edit_can_clear_the_description(manager) -> None:
    created = _create(manager, ACTOR_A, description="something")
    updated = manager.update_description_for_actor(
        ACTOR_A,
        created.identity.library_field_id,
        FieldDescriptionUpdateRequest(description=None),
    )
    assert updated.description is None


def test_description_edit_never_touches_older_versions(manager) -> None:
    """Only the is_latest row is rewritten; history stays as it was."""
    created = _create(manager, ACTOR_A, description="v1 wording", settings={"unit": "mL"})
    field_id = created.identity.library_field_id
    manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(description="v2 wording", settings={"unit": "L"})
    )

    manager.update_description_for_actor(
        ACTOR_A, field_id, FieldDescriptionUpdateRequest(description="v2 reworded")
    )

    by_number = {v.version: v for v in manager.list_versions_for_actor(ACTOR_A, field_id)}
    assert by_number[2].description == "v2 reworded"
    assert by_number[1].description == "v1 wording", "the older version must be untouched"
    assert by_number[1].version_id == created.version.version_id
    assert by_number[1].settings == {"unit": "mL"}
    assert len(by_number) == 2, "still two versions"


def test_description_edit_leaves_settings_and_name_alone(manager) -> None:
    created = _create(manager, ACTOR_A, name="Volume Kept", settings={"unit": "mL"})
    field_id = created.identity.library_field_id
    updated = manager.update_description_for_actor(
        ACTOR_A, field_id, FieldDescriptionUpdateRequest(description="reworded")
    )
    assert updated.settings == {"unit": "mL"}
    assert updated.name == "Volume Kept"


def test_creating_a_version_still_works_for_real_content_changes(manager) -> None:
    """POST /versions is unaffected: it still bumps and still takes a description."""
    created = _create(manager, ACTOR_A, description="v1", settings={"unit": "mL"})
    field_id = created.identity.library_field_id
    manager.update_description_for_actor(
        ACTOR_A, field_id, FieldDescriptionUpdateRequest(description="v1 reworded")
    )
    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(description="v2", settings={"unit": "L"})
    )
    assert second.version == 2
    assert second.is_latest is True
    assert second.settings == {"unit": "L"}
    assert second.description == "v2"
    # The in-place edit to v1 survived the new version.
    by_number = {v.version: v for v in manager.list_versions_for_actor(ACTOR_A, field_id)}
    assert by_number[1].description == "v1 reworded"
    assert by_number[1].is_latest is False


def test_one_org_cannot_edit_another_orgs_description(manager) -> None:
    a = _create(manager, ACTOR_A, description="mine")
    with pytest.raises(NotFoundError):
        manager.update_description_for_actor(
            ACTOR_B,
            a.identity.library_field_id,
            FieldDescriptionUpdateRequest(description="hijacked"),
        )
    versions = manager.list_versions_for_actor(ACTOR_A, a.identity.library_field_id)
    assert versions[0].description == "mine"


# ── The version name snapshot ─────────────────────────────────────────────────


def test_version_one_snapshots_the_creation_name(manager) -> None:
    created = _create(manager, ACTOR_A, name="Original Name")
    assert created.version.name == "Original Name"


def test_renaming_leaves_existing_version_snapshots_alone(manager) -> None:
    """Rename touches the identity only, so history keeps its old name."""
    created = _create(manager, ACTOR_A, name="Original Name")
    field_id = created.identity.library_field_id
    manager.rename_field_for_actor(ACTOR_A, field_id, FieldRenameRequest(name="New Name"))

    # The identity shows the live name immediately, with no new version.
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.name == "New Name"
    versions = manager.list_versions_for_actor(ACTOR_A, field_id)
    assert len(versions) == 1, "a rename must not create a version"
    assert versions[0].name == "Original Name", "the snapshot must not follow the rename"


def test_a_version_made_after_a_rename_captures_the_new_name(manager) -> None:
    created = _create(manager, ACTOR_A, name="Original Name")
    field_id = created.identity.library_field_id
    manager.rename_field_for_actor(ACTOR_A, field_id, FieldRenameRequest(name="New Name"))
    manager.create_version_for_actor(ACTOR_A, field_id, FieldVersionCreateRequest())

    versions = {v.version: v.name for v in manager.list_versions_for_actor(ACTOR_A, field_id)}
    assert versions == {1: "Original Name", 2: "New Name"}


# ── Versioned field_type ──────────────────────────────────────────────────────


def test_version_one_stamps_the_creation_type(manager) -> None:
    created = _create(manager, ACTOR_A, field_type="integer")
    assert created.version.field_type == "integer"
    assert created.identity.field_type == "integer"


def test_a_version_without_a_type_keeps_the_current_one(manager) -> None:
    """Regression: omitting field_type must behave exactly as before."""
    created = _create(manager, ACTOR_A, field_type="integer")
    field_id = created.identity.library_field_id
    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(description="v2", settings={"unit": "L"})
    )
    assert second.version == 2
    assert second.field_type == "integer", "the type carries on unchanged"
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.field_type == "integer"


def test_a_version_can_change_the_type_and_updates_the_identity(manager) -> None:
    created = _create(manager, ACTOR_A, field_type="integer")
    field_id = created.identity.library_field_id
    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(field_type="text")
    )
    assert second.version == 2
    assert second.field_type == "text"
    # The identity mirrors the newest version.
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.field_type == "text"
    # Every earlier version keeps the type it was created under.
    by_number = {v.version: v for v in manager.list_versions_for_actor(ACTOR_A, field_id)}
    assert by_number[1].field_type == "integer"
    assert by_number[2].field_type == "text"


def test_repeating_the_same_type_is_not_treated_as_a_change(manager) -> None:
    created = _create(manager, ACTOR_A, field_type="integer")
    second = manager.create_version_for_actor(
        ACTOR_A,
        created.identity.library_field_id,
        FieldVersionCreateRequest(field_type="integer", description="v2"),
    )
    assert second.field_type == "integer"


def test_a_version_can_change_to_timer_duration(manager) -> None:
    """Timer/Duration uses the normal immutable field-version flow."""
    created = _create(manager, ACTOR_A, field_type="integer")
    field_id = created.identity.library_field_id
    second = manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(field_type="timer_duration")
    )

    assert second.version == 2
    assert second.field_type == "timer_duration"
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.field_type == "timer_duration"
    versions_by_number = {
        version.version: version
        for version in manager.list_versions_for_actor(ACTOR_A, field_id)
    }
    assert versions_by_number[1].field_type == "integer"
    assert versions_by_number[2].field_type == "timer_duration"


def test_a_version_cannot_change_to_an_unknown_type(manager) -> None:
    created = _create(manager, ACTOR_A, field_type="integer")
    with pytest.raises(ValidationError, match="unknown field type"):
        manager.create_version_for_actor(
            ACTOR_A,
            created.identity.library_field_id,
            FieldVersionCreateRequest(field_type="not_a_real_type"),
        )


def test_a_version_cannot_change_to_a_type_the_org_disabled(
    manager, db_service, clean_org_type_settings
) -> None:
    """An org-disabled type is refused with the same message creation gives."""
    created = _create(manager, ACTOR_A, field_type="integer")
    field_id = created.identity.library_field_id
    _enable_only_types(db_service, ORG_A, ["integer"])
    with pytest.raises(ValidationError, match="not enabled for your organization"):
        manager.create_version_for_actor(
            ACTOR_A, field_id, FieldVersionCreateRequest(field_type="text")
        )
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.field_type == "integer"


def test_a_type_change_colliding_on_name_and_type_is_rejected(manager) -> None:
    """The identity keeps the (name, type) uniqueness rule when its type moves."""
    _identity(manager, ACTOR_A, name="Shared Name", field_type="text")
    integer_field = _identity(manager, ACTOR_A, name="Shared Name", field_type="integer")
    with pytest.raises(ValidationError, match="already uses this name"):
        manager.create_version_for_actor(
            ACTOR_A,
            integer_field.library_field_id,
            FieldVersionCreateRequest(field_type="text"),
        )


def test_a_pinned_version_keeps_its_type_after_a_later_type_change(
    manager, db_service, clean_links
) -> None:
    """A form on an older version_id resolves that version's type and settings."""
    created = _create(manager, ACTOR_A, field_type="integer", settings={"unit": "mL"})
    field_id = created.identity.library_field_id
    pinned_version_id = created.version.version_id
    _link_field_to_a_form(
        db_service,
        organization_id=ORG_A,
        field_id=field_id,
        version_id=pinned_version_id,
    )

    manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(field_type="text", settings={"unit": "L"})
    )

    pinned = next(
        v
        for v in manager.list_versions_for_actor(ACTOR_A, field_id)
        if v.version_id == pinned_version_id
    )
    assert pinned.field_type == "integer", "the pinned version keeps its original type"
    assert pinned.settings == {"unit": "mL"}
    assert pinned.is_latest is False
    # While the live field has moved on.
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.field_type == "text"


# ── Rename ────────────────────────────────────────────────────────────────────


def test_rename_creates_no_version(manager) -> None:
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    renamed = manager.rename_field_for_actor(
        ACTOR_A, field_id, FieldRenameRequest(name="Renamed Volume")
    )
    assert renamed.name == "Renamed Volume"
    versions = manager.list_versions_for_actor(ACTOR_A, field_id)
    assert len(versions) == 1, "a rename must not create a version"
    assert versions[0].version_id == created.version.version_id
    assert renamed.field_key == created.identity.field_key


def test_rename_to_a_case_variant_of_another_field_is_rejected(manager) -> None:
    first = _identity(manager, ACTOR_A, name="Volume Measured", field_type="integer")
    second = _identity(manager, ACTOR_A, field_type="integer")
    with pytest.raises(ValidationError, match="uses"):
        manager.rename_field_for_actor(
            ACTOR_A, second.library_field_id, FieldRenameRequest(name="VOLUME MEASURED")
        )
    assert first.name == "Volume Measured"


def test_one_org_cannot_rename_another_orgs_field(manager) -> None:
    a = _identity(manager, ACTOR_A)
    with pytest.raises(NotFoundError):
        manager.rename_field_for_actor(
            ACTOR_B, a.library_field_id, FieldRenameRequest(name="Hijacked")
        )
    assert manager.get_field_for_actor(ACTOR_A, a.library_field_id).identity.name == a.name


def test_one_org_cannot_version_another_orgs_field(manager) -> None:
    a = _create(manager, ACTOR_A)
    with pytest.raises(NotFoundError):
        manager.create_version_for_actor(
            ACTOR_B, a.identity.library_field_id, FieldVersionCreateRequest()
        )
    assert len(manager.list_versions_for_actor(ACTOR_A, a.identity.library_field_id)) == 1


# ── Type validation ───────────────────────────────────────────────────────────


def test_create_field_accepts_timer_duration(manager) -> None:
    created = _create(manager, ACTOR_A, field_type="timer_duration")

    assert created.identity.field_type == "timer_duration"
    assert created.version.field_type == "timer_duration"


def test_timer_duration_ignores_the_legacy_not_built_flag(manager, monkeypatch) -> None:
    """A stale catalogue row must not block the frontend-recorded timer field."""
    response = FieldTypeCatalogueResponse(
        organization_id=ORG_A,
        items=[
            FieldTypeOption(
                code="timer_duration",
                label="Timer/Duration",
                engine_type=None,
                config_kind="none",
                selectable=False,
                unavailable_reason=NOT_BUILT_REASON,
            )
        ],
    )
    monkeypatch.setattr(manager, "list_field_types", lambda **_kwargs: response)

    manager._assert_type_is_selectable(
        organization_id=ORG_A, field_type="timer_duration"
    )


def test_timer_duration_still_respects_organization_disablement(manager, monkeypatch) -> None:
    response = FieldTypeCatalogueResponse(
        organization_id=ORG_A,
        items=[
            FieldTypeOption(
                code="timer_duration",
                label="Timer/Duration",
                engine_type="timer_duration",
                config_kind="none",
                selectable=False,
                unavailable_reason=NOT_ENABLED_REASON,
            )
        ],
    )
    monkeypatch.setattr(manager, "list_field_types", lambda **_kwargs: response)

    with pytest.raises(ValidationError, match="not enabled for your organization"):
        manager._assert_type_is_selectable(
            organization_id=ORG_A, field_type="timer_duration"
        )


def test_other_legacy_unbuilt_types_remain_rejected(manager, monkeypatch) -> None:
    response = FieldTypeCatalogueResponse(
        organization_id=ORG_A,
        items=[
            FieldTypeOption(
                code="future_type",
                label="Future Type",
                engine_type=None,
                config_kind="none",
                selectable=False,
                unavailable_reason=NOT_BUILT_REASON,
            )
        ],
    )
    monkeypatch.setattr(manager, "list_field_types", lambda **_kwargs: response)

    with pytest.raises(ValidationError, match="not available in this release"):
        manager._assert_type_is_selectable(
            organization_id=ORG_A, field_type="future_type"
        )


def test_create_field_rejects_an_unknown_type(manager) -> None:
    with pytest.raises(ValidationError, match="unknown field type"):
        _create(manager, ACTOR_A, field_type="not_a_real_type")


def test_create_field_rejects_blank_name_and_key(manager) -> None:
    with pytest.raises(ValidationError, match="name is required"):
        _create(manager, ACTOR_A, name="   ")
    with pytest.raises(ValidationError, match="key is required"):
        _create(manager, ACTOR_A, field_key="   ")


def test_over_long_name_and_key_are_rejected_by_the_contract(manager) -> None:
    """Bounded at the contract, so the caller gets a 422 rather than a 500."""
    with pytest.raises(PydanticValidationError):
        FieldCreateRequest(
            name="x" * (FIELD_NAME_MAX_LENGTH + 1),
            field_key="volume",
            field_type="integer",
        )
    with pytest.raises(PydanticValidationError):
        FieldCreateRequest(
            name="Volume",
            field_key="x" * (FIELD_KEY_MAX_LENGTH + 1),
            field_type="integer",
        )


def test_name_and_key_at_the_maximum_length_are_accepted(manager) -> None:
    """The bound must match the column exactly, not sit one character inside it."""
    created = _identity(
        manager,
        ACTOR_A,
        name="n" * FIELD_NAME_MAX_LENGTH,
        field_key="k" * FIELD_KEY_MAX_LENGTH,
    )
    assert len(created.name) == FIELD_NAME_MAX_LENGTH
    assert len(created.field_key) == FIELD_KEY_MAX_LENGTH


# ── Uniqueness, case-insensitive, per organization, live rows only ────────────


def test_same_name_and_type_twice_is_rejected(manager) -> None:
    first = _identity(manager, ACTOR_A, field_type="integer")
    with pytest.raises(ValidationError, match="name and type"):
        _create(manager, ACTOR_A, name=first.name, field_type="integer")


def test_same_name_with_a_different_type_is_allowed(manager) -> None:
    """Uniqueness is on name plus type, so "Volume" can be integer and text."""
    integer_field = _identity(manager, ACTOR_A, name="Volume Shared", field_type="integer")
    text_field = _identity(manager, ACTOR_A, name="Volume Shared", field_type="text")
    assert integer_field.library_field_id != text_field.library_field_id
    assert integer_field.name == text_field.name
    assert {integer_field.field_type, text_field.field_type} == {"integer", "text"}


def test_duplicate_key_in_same_org_is_rejected(manager) -> None:
    first = _identity(manager, ACTOR_A)
    with pytest.raises(ValidationError, match="already exists"):
        _create(manager, ACTOR_A, field_key=first.field_key)


def test_duplicate_name_and_type_is_rejected_case_insensitively(manager) -> None:
    """"Volume" and "volume" are one field to an author, at the same type."""
    first = _identity(manager, ACTOR_A, name="Volume Measured", field_type="integer")
    with pytest.raises(ValidationError, match="name and type"):
        _create(manager, ACTOR_A, name=first.name.upper(), field_type="integer")
    with pytest.raises(ValidationError, match="name and type"):
        _create(manager, ACTOR_A, name=first.name.lower(), field_type="integer")
    # A different type is a different field, even case-insensitively.
    assert _identity(manager, ACTOR_A, name=first.name.upper(), field_type="text")


def test_key_uniqueness_ignores_name_and_type(manager) -> None:
    """field_key stays unique on its own, whatever the name or type is."""
    first = _identity(manager, ACTOR_A, name="Key Owner", field_key="shared_key")
    # Different name, different type, same key: still refused.
    with pytest.raises(ValidationError, match="key"):
        _create(
            manager, ACTOR_A, name="Totally Other", field_key=first.field_key, field_type="text"
        )


def test_duplicate_key_is_rejected_case_insensitively(manager) -> None:
    first = _identity(manager, ACTOR_A, field_key="volume_measured")
    with pytest.raises(ValidationError, match="already exists"):
        _create(manager, ACTOR_A, field_key=first.field_key.upper())


def test_author_casing_is_preserved_even_though_uniqueness_ignores_it(manager) -> None:
    """Only the comparison is case-insensitive; the stored value is untouched."""
    created = _identity(manager, ACTOR_A, name="Volume Measured", field_key="volumeKey")
    stored = manager.get_field_for_actor(ACTOR_A, created.library_field_id).identity
    assert stored.name == "Volume Measured"
    assert stored.field_key == "volumeKey"


# ── Archive ───────────────────────────────────────────────────────────────────


def test_archive_marks_the_field_and_frees_its_name_and_key(manager) -> None:
    created = _identity(manager, ACTOR_A)
    archived = manager.archive_field_for_actor(ACTOR_A, created.library_field_id)
    assert archived.is_archived is True
    reused = _identity(manager, ACTOR_A, name=created.name, field_key=created.field_key)
    assert reused.library_field_id != created.library_field_id


def test_case_variant_name_is_reusable_after_archiving(manager) -> None:
    """Case-insensitivity must not outlive the field: archiving frees the name."""
    created = _identity(manager, ACTOR_A, name="Volume Measured")
    manager.archive_field_for_actor(ACTOR_A, created.library_field_id)
    reused = _identity(manager, ACTOR_A, name="VOLUME MEASURED")
    assert reused.library_field_id != created.library_field_id


def test_archived_field_is_hidden_from_the_default_listing(manager) -> None:
    created = _identity(manager, ACTOR_A)
    manager.archive_field_for_actor(ACTOR_A, created.library_field_id)
    visible = _list_ids(manager, ACTOR_A)
    assert created.library_field_id not in visible
    with_archived = _list_ids(manager, ACTOR_A, include_archived=True)
    assert created.library_field_id in with_archived


def test_archived_field_is_still_readable_by_id(manager) -> None:
    """Archiving retires a field without deleting it, so references still resolve."""
    created = _identity(manager, ACTOR_A)
    manager.archive_field_for_actor(ACTOR_A, created.library_field_id)
    fetched = manager.get_field_for_actor(ACTOR_A, created.library_field_id).identity
    assert fetched.is_archived is True
    assert fetched.field_count_id == created.field_count_id


def test_archiving_twice_is_harmless(manager) -> None:
    created = _identity(manager, ACTOR_A)
    first = manager.archive_field_for_actor(ACTOR_A, created.library_field_id)
    second = manager.archive_field_for_actor(ACTOR_A, created.library_field_id)
    assert first.is_archived is True
    assert second.is_archived is True


def test_archiving_an_unknown_field_is_rejected(manager) -> None:
    with pytest.raises(NotFoundError):
        manager.archive_field_for_actor(ACTOR_A, str(uuid.uuid4()))


# ── Search and field_type filters ─────────────────────────────────────────────


def test_a_freshly_created_field_appears_in_the_list(manager) -> None:
    """Regression: list and get must agree for a live field.

    A report of "list is empty but get works" turned out to be an archived
    field, since list hides archived rows and get deliberately does not. This
    pins the live case so a real divergence would fail here.
    """
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    assert field_id in _list_ids(manager, ACTOR_A)
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.library_field_id == field_id


def test_list_hides_archived_while_get_still_resolves(manager) -> None:
    """The exact shape of that report, now asserted as intended behaviour."""
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    manager.archive_field_for_actor(ACTOR_A, field_id)
    assert field_id not in _list_ids(manager, ACTOR_A)
    assert field_id in _list_ids(manager, ACTOR_A, include_archived=True)
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.is_archived is True


# ── Each item carries its current version ─────────────────────────────────────


def test_each_list_item_includes_its_current_version(manager) -> None:
    """The grid needs settings and description without a call per row."""
    created = _create(
        manager, ACTOR_A, description="millilitres at the bench", settings={"unit": "mL"}
    )
    items, _total = manager.list_fields_for_actor(ACTOR_A)
    item = next(
        i for i in items if i.identity.library_field_id == created.identity.library_field_id
    )
    assert item.version.version == 1
    assert item.version.is_latest is True
    assert item.version.description == "millilitres at the bench"
    assert item.version.settings == {"unit": "mL"}


def test_list_shows_the_newest_version_after_an_edit(manager) -> None:
    created = _create(manager, ACTOR_A, settings={"unit": "mL"})
    field_id = created.identity.library_field_id
    manager.create_version_for_actor(
        ACTOR_A, field_id, FieldVersionCreateRequest(description="v2", settings={"unit": "L"})
    )
    items, _total = manager.list_fields_for_actor(ACTOR_A)
    item = next(i for i in items if i.identity.library_field_id == field_id)
    assert item.version.version == 2
    assert item.version.settings == {"unit": "L"}


def test_a_field_appears_once_however_many_versions_it_has(manager) -> None:
    """The join is on is_latest, so extra versions must not duplicate the row."""
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    for _ in range(3):
        manager.create_version_for_actor(ACTOR_A, field_id, FieldVersionCreateRequest())
    items, total = manager.list_fields_for_actor(ACTOR_A)
    assert [i.identity.library_field_id for i in items].count(field_id) == 1
    assert total == 1


# ── Pagination ────────────────────────────────────────────────────────────────


def test_pagination_splits_results_and_reports_the_full_total(manager) -> None:
    for index in range(5):
        _create(manager, ACTOR_A, name=f"Paged {index}", field_key=f"paged_{index}")

    first, total = manager.list_fields_for_actor(ACTOR_A, limit=2, offset=0)
    second, total_again = manager.list_fields_for_actor(ACTOR_A, limit=2, offset=2)
    third, _ = manager.list_fields_for_actor(ACTOR_A, limit=2, offset=4)

    assert total == 5, "total counts every match, not just the page"
    assert total_again == 5
    assert (len(first), len(second), len(third)) == (2, 2, 1)
    # Pages must not overlap and must cover everything.
    ids = [i.identity.library_field_id for i in first + second + third]
    assert len(set(ids)) == 5


def test_offset_past_the_end_returns_an_empty_page_with_the_total(manager) -> None:
    _create(manager, ACTOR_A)
    items, total = manager.list_fields_for_actor(ACTOR_A, limit=10, offset=50)
    assert items == []
    assert total == 1, "an empty page still reports how many matches exist"


def test_total_respects_the_active_filters(manager) -> None:
    _create(manager, ACTOR_A, name="Volume One", field_key="vol_one")
    _create(manager, ACTOR_A, name="Volume Two", field_key="vol_two")
    _create(manager, ACTOR_A, name="Sample Count", field_key="sample_count")
    assert _list_total(manager, ACTOR_A) == 3
    assert _list_total(manager, ACTOR_A, search="vol") == 2


def test_no_filters_returns_everything(manager) -> None:
    """Backward compatibility: the unfiltered call behaves exactly as before."""
    first = _identity(manager, ACTOR_A, name="Volume Measured", field_key="volume")
    second = _identity(manager, ACTOR_A, name="Sample Count", field_key="sample_count")
    listed = _list_ids(manager, ACTOR_A)
    assert {first.library_field_id, second.library_field_id} <= listed


def test_search_matches_part_of_the_name_case_insensitively(manager) -> None:
    match = _identity(manager, ACTOR_A, name="Volume Measured", field_key="vm_key")
    _create(manager, ACTOR_A, name="Sample Count", field_key="sample_count")
    for term in ("vol", "VOL", "Volume"):
        found = _list_ids(manager, ACTOR_A, search=term)
        assert found == {match.library_field_id}, f"search={term!r}"


def test_search_matches_the_field_key_too(manager) -> None:
    match = _identity(manager, ACTOR_A, name="Totally Different", field_key="volume_ml")
    _create(manager, ACTOR_A, name="Sample Count", field_key="sample_count")
    found = _list_ids(manager, ACTOR_A, search="volume")
    assert found == {match.library_field_id}


def test_search_treats_underscore_literally(manager) -> None:
    """`_` is a LIKE wildcard, so an unescaped term would over-match keys."""
    exact = _identity(manager, ACTOR_A, name="Underscore One", field_key="ab_cd")
    _create(manager, ACTOR_A, name="Underscore Two", field_key="abxcd")
    found = _list_ids(manager, ACTOR_A, search="ab_cd")
    assert found == {exact.library_field_id}


def test_search_with_no_match_returns_nothing(manager) -> None:
    _create(manager, ACTOR_A, name="Volume Measured", field_key="volume")
    assert _list_ids(manager, ACTOR_A, search="zzz-no-such-field") == set()


def test_blank_search_is_treated_as_no_filter(manager) -> None:
    created = _identity(manager, ACTOR_A)
    for term in ("", "   "):
        found = _list_ids(manager, ACTOR_A, search=term)
        assert created.library_field_id in found, f"search={term!r} must not filter"


def test_field_type_filter_returns_only_matching_entries(manager) -> None:
    integer_field = _identity(manager, ACTOR_A, field_type="integer")
    text_field = _identity(manager, ACTOR_A, field_type="text")
    integers = _list_ids(manager, ACTOR_A, field_type="integer")
    assert integer_field.library_field_id in integers
    assert text_field.library_field_id not in integers
    items, _ = manager.list_fields_for_actor(ACTOR_A, field_type="integer")
    assert all(i.identity.field_type == "integer" for i in items)


def test_search_and_field_type_narrow_together(manager) -> None:
    """Both filters apply, rather than one winning over the other."""
    wanted = _identity(manager, ACTOR_A, name="Volume Integer", field_key="vol_int", field_type="integer")
    # Matches the search but not the type.
    _create(manager, ACTOR_A, name="Volume Text", field_key="vol_txt", field_type="text")
    # Matches the type but not the search.
    _create(manager, ACTOR_A, name="Sample Count", field_key="sample_count", field_type="integer")
    found = _list_ids(manager, ACTOR_A, search="vol", field_type="integer")
    assert found == {wanted.library_field_id}


def test_filters_combine_with_include_archived(manager) -> None:
    live = _identity(manager, ACTOR_A, name="Volume Live", field_key="vol_live")
    archived = _identity(manager, ACTOR_A, name="Volume Gone", field_key="vol_gone")
    manager.archive_field_for_actor(ACTOR_A, archived.library_field_id)

    default = _list_ids(manager, ACTOR_A, search="vol")
    assert default == {live.library_field_id}

    with_archived = _list_ids(manager, ACTOR_A, search="vol", include_archived=True)
    assert with_archived == {live.library_field_id, archived.library_field_id}


def test_search_never_crosses_organizations(manager) -> None:
    a = _identity(manager, ACTOR_A, name="Volume Measured", field_key="volume")
    _create(manager, ACTOR_B, name="Volume Measured", field_key="volume")
    found = _list_ids(manager, ACTOR_A, search="volume")
    assert found == {a.library_field_id}


# ── Hard delete ───────────────────────────────────────────────────────────────


def _link_field_to_a_form(db_service, *, organization_id: str, field_id: str, version_id: str):
    """Attach a field version to a throwaway form, returning the form's id."""
    from field_library.db_models import EntityTypeSchemaFieldModel
    from forms.db_models import EntityTypeSchemaModel

    schema_id = str(uuid.uuid4())
    suffix = uuid.uuid4().hex[:8]
    with db_service._db_session() as session:
        session.add(
            EntityTypeSchemaModel(
                id=schema_id,
                organization_id=organization_id,
                schema_key=f"key_{suffix}",
                name=f"Form {suffix}",
                entity_type="Request",
                fields_json=[],
            )
        )
        session.flush()
        session.add(
            EntityTypeSchemaFieldModel(
                id=str(uuid.uuid4()),
                schema_id=schema_id,
                version_id=version_id,
                library_field_id=field_id,
                organization_id=organization_id,
                position=0,
            )
        )
        session.commit()
    return schema_id


@pytest.fixture
def clean_links(db_service):
    """Remove links and forms this module creates, so orgs stay reusable."""
    from field_library.db_models import EntityTypeSchemaFieldModel
    from forms.db_models import EntityTypeSchemaModel

    def _purge() -> None:
        with db_service._db_session() as session:
            session.query(EntityTypeSchemaFieldModel).filter(
                EntityTypeSchemaFieldModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.query(EntityTypeSchemaModel).filter(
                EntityTypeSchemaModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.commit()

    _purge()
    yield
    _purge()


def test_hard_delete_removes_an_unused_field_and_its_versions(manager, db_service) -> None:
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    manager.create_version_for_actor(ACTOR_A, field_id, FieldVersionCreateRequest())
    assert len(manager.list_versions_for_actor(ACTOR_A, field_id)) == 2

    manager.hard_delete_field_for_actor(ACTOR_A, field_id)

    with pytest.raises(NotFoundError):
        manager.get_field_for_actor(ACTOR_A, field_id)
    assert field_id not in _list_ids(manager, ACTOR_A, include_archived=True)
    # Versions went with it through the cascading foreign key.
    assert (
        db_service.list_versions(organization_id=ORG_A, library_field_id=field_id) == []
    )


def test_hard_delete_is_refused_while_a_form_uses_the_field(
    manager, db_service, clean_links
) -> None:
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    _link_field_to_a_form(
        db_service,
        organization_id=ORG_A,
        field_id=field_id,
        version_id=created.version.version_id,
    )
    with pytest.raises(ValidationError, match="used by 1 form and cannot be deleted"):
        manager.hard_delete_field_for_actor(ACTOR_A, field_id)
    # Nothing was removed by the failed attempt.
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.library_field_id == field_id


def test_hard_delete_message_counts_every_form_using_the_field(
    manager, db_service, clean_links
) -> None:
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    for _ in range(3):
        _link_field_to_a_form(
            db_service,
            organization_id=ORG_A,
            field_id=field_id,
            version_id=created.version.version_id,
        )
    with pytest.raises(ValidationError, match="used by 3 forms and cannot be deleted"):
        manager.hard_delete_field_for_actor(ACTOR_A, field_id)


def test_hard_delete_suggests_archiving_instead(manager, db_service, clean_links) -> None:
    created = _create(manager, ACTOR_A)
    _link_field_to_a_form(
        db_service,
        organization_id=ORG_A,
        field_id=created.identity.library_field_id,
        version_id=created.version.version_id,
    )
    with pytest.raises(ValidationError, match="Archive it instead"):
        manager.hard_delete_field_for_actor(ACTOR_A, created.identity.library_field_id)


def test_archive_still_works_on_a_field_in_use(manager, db_service, clean_links) -> None:
    """Archiving stays unconditional: it never checks references."""
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    _link_field_to_a_form(
        db_service,
        organization_id=ORG_A,
        field_id=field_id,
        version_id=created.version.version_id,
    )
    archived = manager.archive_field_for_actor(ACTOR_A, field_id)
    assert archived.is_archived is True
    # The link and its versions survive, so the form still resolves.
    assert manager.list_versions_for_actor(ACTOR_A, field_id)


def test_the_database_blocks_a_hard_delete_even_without_the_app_check(
    manager, db_service, clean_links
) -> None:
    """Defence in depth: bypass the manager and the foreign key still refuses."""
    created = _create(manager, ACTOR_A)
    field_id = created.identity.library_field_id
    _link_field_to_a_form(
        db_service,
        organization_id=ORG_A,
        field_id=field_id,
        version_id=created.version.version_id,
    )
    # Straight at the persistence layer, skipping the count check entirely.
    with pytest.raises(FieldInUseError):
        db_service.hard_delete_field(organization_id=ORG_A, library_field_id=field_id)
    assert manager.get_field_for_actor(ACTOR_A, field_id).identity.library_field_id == field_id


def test_one_org_cannot_hard_delete_another_orgs_field(manager) -> None:
    a = _create(manager, ACTOR_A)
    with pytest.raises(NotFoundError):
        manager.hard_delete_field_for_actor(ACTOR_B, a.identity.library_field_id)
    assert manager.get_field_for_actor(ACTOR_A, a.identity.library_field_id)


# ── Cross-organization isolation ──────────────────────────────────────────────


def test_same_name_and_key_allowed_in_different_orgs(manager) -> None:
    a = _identity(manager, ACTOR_A)
    b = _identity(manager, ACTOR_B, name=a.name, field_key=a.field_key)
    assert b.organization_id == ORG_B
    assert b.library_field_id != a.library_field_id


def test_case_variant_name_is_allowed_in_a_different_org(manager) -> None:
    a = _identity(manager, ACTOR_A, name="Volume Measured")
    b = _identity(manager, ACTOR_B, name=a.name.upper())
    assert b.organization_id == ORG_B


def test_one_org_cannot_read_another_orgs_field(manager) -> None:
    a = _identity(manager, ACTOR_A)
    with pytest.raises(NotFoundError):
        manager.get_field_for_actor(ACTOR_B, a.library_field_id)


def test_one_org_cannot_list_another_orgs_fields(manager) -> None:
    a = _identity(manager, ACTOR_A)
    org_b_ids = _list_ids(manager, ACTOR_B)
    assert a.library_field_id not in org_b_ids


def test_one_org_cannot_archive_another_orgs_field(manager) -> None:
    a = _identity(manager, ACTOR_A)
    with pytest.raises(NotFoundError):
        manager.archive_field_for_actor(ACTOR_B, a.library_field_id)
    still = manager.get_field_for_actor(ACTOR_A, a.library_field_id).identity
    assert still.is_archived is False


def test_actor_without_organization_is_rejected(manager) -> None:
    with pytest.raises(Exception, match="organization_id"):
        manager.list_fields_for_actor({"user_id": "nobody"})

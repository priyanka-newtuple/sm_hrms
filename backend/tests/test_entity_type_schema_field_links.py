"""The connector table linking forms to specific field versions.

Nothing reads or writes this table yet, so these exercise the constraints
directly: the composite foreign keys, the one-field-per-form rule, and that a
link stays pinned to the version it was created with.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from field_library.db_models import (
    EntityTypeSchemaFieldModel,
    FieldLibraryFieldModel,
    FieldLibraryFieldVersionModel,
    FieldLibraryModelService,
)
from forms.db_models import EntityTypeSchemaModel

ORG_A = "test-org-1"
ORG_B = "test-org-2"


@pytest.fixture
def db_service(entities_db_service_manager) -> FieldLibraryModelService:
    return FieldLibraryModelService(entities_db_service_manager)


@pytest.fixture(autouse=True)
def clean_rows(db_service):
    """Remove both test orgs' links, versions, fields and schemas."""

    def _purge() -> None:
        with db_service._db_session() as session:
            session.query(EntityTypeSchemaFieldModel).filter(
                EntityTypeSchemaFieldModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.query(FieldLibraryFieldVersionModel).filter(
                FieldLibraryFieldVersionModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.query(FieldLibraryFieldModel).filter(
                FieldLibraryFieldModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.query(EntityTypeSchemaModel).filter(
                EntityTypeSchemaModel.organization_id.in_([ORG_A, ORG_B])
            ).delete(synchronize_session=False)
            session.commit()

    _purge()
    yield
    _purge()


def _make_schema(db_service: FieldLibraryModelService, organization_id: str) -> str:
    """Insert a form and return its id."""
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
        session.commit()
    return schema_id


def _make_field(db_service: FieldLibraryModelService, organization_id: str) -> tuple[str, str]:
    """Insert a library field, returning its id and its version 1 id."""
    suffix = uuid.uuid4().hex[:8]
    created = db_service.create_field(
        organization_id=organization_id,
        name=f"Volume {suffix}",
        field_key=f"volume_{suffix}",
        field_type="integer",
        description=None,
        settings={},
        created_by="user-a",
    )
    return created.identity.library_field_id, created.version.version_id


def _new_version(
    db_service: FieldLibraryModelService, organization_id: str, library_field_id: str
) -> str:
    """Add a version to an existing field and return its version id."""
    version = db_service.add_version(
        organization_id=organization_id,
        library_field_id=library_field_id,
        description="edited",
        settings={"unit": "L"},
        created_by="user-a",
    )
    return version.version_id


def _link(
    db_service: FieldLibraryModelService,
    *,
    schema_id: str,
    library_field_id: str,
    version_id: str,
    organization_id: str,
    position: int = 0,
) -> str:
    """Insert one link row and return its id. Raises on constraint violation."""
    link_id = str(uuid.uuid4())
    with db_service._db_session() as session:
        session.add(
            EntityTypeSchemaFieldModel(
                id=link_id,
                schema_id=schema_id,
                version_id=version_id,
                library_field_id=library_field_id,
                organization_id=organization_id,
                position=position,
            )
        )
        session.commit()
    return link_id


# ── Happy path and ordering ───────────────────────────────────────────────────


def test_a_field_version_can_be_linked_to_a_form(db_service) -> None:
    schema_id = _make_schema(db_service, ORG_A)
    field_id, version_id = _make_field(db_service, ORG_A)
    link_id = _link(
        db_service,
        schema_id=schema_id,
        library_field_id=field_id,
        version_id=version_id,
        organization_id=ORG_A,
    )
    with db_service._db_session() as session:
        row = session.get(EntityTypeSchemaFieldModel, link_id)
        assert row.schema_id == schema_id
        assert row.library_field_id == field_id
        assert row.version_id == version_id
        assert row.organization_id == ORG_A
        assert row.position == 0
        assert row.created_at is not None


def test_position_preserves_field_order_within_a_form(db_service) -> None:
    schema_id = _make_schema(db_service, ORG_A)
    first, first_v = _make_field(db_service, ORG_A)
    second, second_v = _make_field(db_service, ORG_A)
    third, third_v = _make_field(db_service, ORG_A)
    # Inserted out of order on purpose; position, not insert order, defines order.
    for field_id, version_id, pos in (
        (third, third_v, 2),
        (first, first_v, 0),
        (second, second_v, 1),
    ):
        _link(
            db_service,
            schema_id=schema_id,
            library_field_id=field_id,
            version_id=version_id,
            organization_id=ORG_A,
            position=pos,
        )
    with db_service._db_session() as session:
        rows = (
            session.query(EntityTypeSchemaFieldModel)
            .filter(EntityTypeSchemaFieldModel.schema_id == schema_id)
            .order_by(EntityTypeSchemaFieldModel.position.asc())
            .all()
        )
        assert [row.library_field_id for row in rows] == [first, second, third]


def test_one_field_can_belong_to_several_forms(db_service) -> None:
    """Reuse across forms is the whole point of a shared library."""
    field_id, version_id = _make_field(db_service, ORG_A)
    for _ in range(2):
        _link(
            db_service,
            schema_id=_make_schema(db_service, ORG_A),
            library_field_id=field_id,
            version_id=version_id,
            organization_id=ORG_A,
        )
    with db_service._db_session() as session:
        count = (
            session.query(EntityTypeSchemaFieldModel)
            .filter(EntityTypeSchemaFieldModel.library_field_id == field_id)
            .count()
        )
        assert count == 2


# ── Version pinning ───────────────────────────────────────────────────────────


def test_a_link_keeps_resolving_to_its_original_version_after_an_edit(db_service) -> None:
    """Editing a field must never change what an already-linked form shows."""
    schema_id = _make_schema(db_service, ORG_A)
    field_id, first_version = _make_field(db_service, ORG_A)
    link_id = _link(
        db_service,
        schema_id=schema_id,
        library_field_id=field_id,
        version_id=first_version,
        organization_id=ORG_A,
    )
    second_version = _new_version(db_service, ORG_A, field_id)
    assert second_version != first_version

    with db_service._db_session() as session:
        row = session.get(EntityTypeSchemaFieldModel, link_id)
        assert row.version_id == first_version, "the link must not follow the newer version"
        pinned = session.get(FieldLibraryFieldVersionModel, row.version_id)
        assert pinned.version == 1
        assert pinned.is_latest is False, "no longer current, but still what the form uses"
        assert pinned.settings == {}


def test_the_same_field_cannot_be_linked_twice_under_different_versions(db_service) -> None:
    """One field per form, whichever version each link names."""
    schema_id = _make_schema(db_service, ORG_A)
    field_id, first_version = _make_field(db_service, ORG_A)
    _link(
        db_service,
        schema_id=schema_id,
        library_field_id=field_id,
        version_id=first_version,
        organization_id=ORG_A,
    )
    second_version = _new_version(db_service, ORG_A, field_id)
    with pytest.raises(IntegrityError, match="uq_entity_type_schema_fields_schema_field"):
        _link(
            db_service,
            schema_id=schema_id,
            library_field_id=field_id,
            version_id=second_version,
            organization_id=ORG_A,
            position=1,
        )


def test_version_and_field_cannot_be_mismatched(db_service) -> None:
    """The composite FK ties version_id to the field named beside it."""
    schema_id = _make_schema(db_service, ORG_A)
    field_a, _ = _make_field(db_service, ORG_A)
    _, version_of_b = _make_field(db_service, ORG_A)
    with pytest.raises(IntegrityError, match="fk_entity_type_schema_fields_version_field"):
        _link(
            db_service,
            schema_id=schema_id,
            library_field_id=field_a,
            version_id=version_of_b,
            organization_id=ORG_A,
        )


def test_link_to_an_unknown_version_is_rejected(db_service) -> None:
    schema_id = _make_schema(db_service, ORG_A)
    field_id, _ = _make_field(db_service, ORG_A)
    with pytest.raises(IntegrityError, match="fk_entity_type_schema_fields_version"):
        _link(
            db_service,
            schema_id=schema_id,
            library_field_id=field_id,
            version_id=str(uuid.uuid4()),
            organization_id=ORG_A,
        )


# ── Foreign keys ──────────────────────────────────────────────────────────────


def test_link_to_an_unknown_form_is_rejected(db_service) -> None:
    field_id, version_id = _make_field(db_service, ORG_A)
    with pytest.raises(IntegrityError, match="fk_entity_type_schema_fields_schema"):
        _link(
            db_service,
            schema_id=str(uuid.uuid4()),
            library_field_id=field_id,
            version_id=version_id,
            organization_id=ORG_A,
        )


def test_deleting_a_form_removes_its_links(db_service) -> None:
    """schema_id cascades: a link is meaningless once its form is gone."""
    schema_id = _make_schema(db_service, ORG_A)
    field_id, version_id = _make_field(db_service, ORG_A)
    _link(
        db_service,
        schema_id=schema_id,
        library_field_id=field_id,
        version_id=version_id,
        organization_id=ORG_A,
    )
    with db_service._db_session() as session:
        session.query(EntityTypeSchemaModel).filter(
            EntityTypeSchemaModel.id == schema_id
        ).delete(synchronize_session=False)
        session.commit()
    with db_service._db_session() as session:
        remaining = (
            session.query(EntityTypeSchemaFieldModel)
            .filter(EntityTypeSchemaFieldModel.schema_id == schema_id)
            .count()
        )
        assert remaining == 0
        # The library field itself survives; only the link went.
        assert session.get(FieldLibraryFieldModel, field_id) is not None


def test_a_linked_library_field_cannot_be_hard_deleted(db_service) -> None:
    """No cascade to the field, so a form cannot lose a field underneath it."""
    schema_id = _make_schema(db_service, ORG_A)
    field_id, version_id = _make_field(db_service, ORG_A)
    _link(
        db_service,
        schema_id=schema_id,
        library_field_id=field_id,
        version_id=version_id,
        organization_id=ORG_A,
    )

    def _hard_delete_the_field() -> None:
        with db_service._db_session() as session:
            session.query(FieldLibraryFieldModel).filter(
                FieldLibraryFieldModel.library_field_id == field_id
            ).delete(synchronize_session=False)
            session.commit()

    with pytest.raises(IntegrityError):
        _hard_delete_the_field()


# ── Multi-tenant isolation ────────────────────────────────────────────────────


def test_a_link_cannot_join_a_form_and_field_from_different_orgs(db_service) -> None:
    """Composite foreign keys make a cross-tenant link impossible."""
    schema_a = _make_schema(db_service, ORG_A)
    field_b, version_b = _make_field(db_service, ORG_B)
    # Claiming org A: the schema matches, the field and version do not.
    with pytest.raises(IntegrityError):
        _link(
            db_service,
            schema_id=schema_a,
            library_field_id=field_b,
            version_id=version_b,
            organization_id=ORG_A,
        )
    # Claiming org B: the field matches, the schema does not.
    with pytest.raises(IntegrityError):
        _link(
            db_service,
            schema_id=schema_a,
            library_field_id=field_b,
            version_id=version_b,
            organization_id=ORG_B,
        )


def test_a_link_cannot_claim_an_organization_neither_parent_belongs_to(db_service) -> None:
    """organization_id is denormalized, so it must also be pinned to both parents."""
    schema_a = _make_schema(db_service, ORG_A)
    field_a, version_a = _make_field(db_service, ORG_A)
    with pytest.raises(IntegrityError):
        _link(
            db_service,
            schema_id=schema_a,
            library_field_id=field_a,
            version_id=version_a,
            organization_id=ORG_B,
        )


def test_links_are_filterable_by_organization(db_service) -> None:
    a_field, a_version = _make_field(db_service, ORG_A)
    b_field, b_version = _make_field(db_service, ORG_B)
    a_link = _link(
        db_service,
        schema_id=_make_schema(db_service, ORG_A),
        library_field_id=a_field,
        version_id=a_version,
        organization_id=ORG_A,
    )
    b_link = _link(
        db_service,
        schema_id=_make_schema(db_service, ORG_B),
        library_field_id=b_field,
        version_id=b_version,
        organization_id=ORG_B,
    )
    with db_service._db_session() as session:
        org_a_ids = {
            row.id
            for row in session.query(EntityTypeSchemaFieldModel)
            .filter(EntityTypeSchemaFieldModel.organization_id == ORG_A)
            .all()
        }
    assert a_link in org_a_ids
    assert b_link not in org_a_ids


def test_two_orgs_can_link_their_own_fields_independently(db_service) -> None:
    """The uniqueness rule is per form, so it never collides across organizations."""
    a_field, a_version = _make_field(db_service, ORG_A)
    b_field, b_version = _make_field(db_service, ORG_B)
    _link(
        db_service,
        schema_id=_make_schema(db_service, ORG_A),
        library_field_id=a_field,
        version_id=a_version,
        organization_id=ORG_A,
    )
    _link(
        db_service,
        schema_id=_make_schema(db_service, ORG_B),
        library_field_id=b_field,
        version_id=b_version,
        organization_id=ORG_B,
    )
    with db_service._db_session() as session:
        assert (
            session.query(EntityTypeSchemaFieldModel)
            .filter(EntityTypeSchemaFieldModel.organization_id.in_([ORG_A, ORG_B]))
            .count()
            == 2
        )

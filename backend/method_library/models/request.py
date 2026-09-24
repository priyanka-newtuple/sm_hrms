"""Request contracts for the method library module."""

from __future__ import annotations

from pydantic import Field, model_validator

from common.data_model import BaseModel as PydanticBaseModel
from method_library.models.interface import (
    CATEGORY_NAME_MAX_LENGTH,
    INHERIT_FROM_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    METHOD_NAME_MAX_LENGTH,
    OWNERSHIP_MAX_LENGTH,
    PLACEHOLDER_MAX_LENGTH,
)
# The same enum the resulting EntityField is validated against, so 'inherited'
# means one thing on both sides of the pin. workflow.models.interface imports
# nothing from method_library, so this direction is cycle-free.
from workflow.models.interface import FieldOwnership


class MethodCategoryCreateRequest(PydanticBaseModel):
    """Create a category. Name only: a category is nothing but its name."""

    name: str = Field(min_length=1, max_length=CATEGORY_NAME_MAX_LENGTH)


class MethodCategoryRenameRequest(PydanticBaseModel):
    """Rename a category in place.

    The methods filed under it keep pointing at the same id, so a rename never
    moves a method out of its category.
    """

    name: str = Field(min_length=1, max_length=CATEGORY_NAME_MAX_LENGTH)


class MethodFieldInput(PydanticBaseModel):
    """One field as the caller wants it to appear in a method.

    `version_id` omitted pins the field's current latest; given explicitly,
    pins that exact version instead.

    `position` is optional. Leave it off the whole list and the order of the list
    itself is used; see `_ordered_fields`.
    """

    library_field_id: str
    version_id: str | None = None
    label: str | None = Field(default=None, max_length=LABEL_MAX_LENGTH)
    placeholder: str | None = Field(default=None, max_length=PLACEHOLDER_MAX_LENGTH)
    required: bool = False
    position: int = 0
    # Optional source intent: which entity type + field this field's value
    # should resolve from once the method is attached to a workflow state,
    # without the method itself knowing which entity type that will be. Both
    # set or both omitted — never one alone.
    source_entity_type: str | None = None
    source_field_key: str | None = None
    # "<EntityTypeName>.<field>" this usage should inherit its value from at
    # pin time, or None to enter it directly.
    inherit_from: str | None = Field(default=None, max_length=INHERIT_FROM_MAX_LENGTH)
    # Method-block-level inheritance. 'inherited' makes the source intent above
    # actually resolve, scoped to this Method only — see MethodVersionField.
    # Omitted means "not stated" and changes nothing.
    ownership: str | None = Field(default=None, max_length=OWNERSHIP_MAX_LENGTH)

    @model_validator(mode="after")
    def validate_source_intent(self) -> MethodFieldInput:
        if (self.source_entity_type is None) != (self.source_field_key is None):
            raise ValueError(
                "source_entity_type and source_field_key must both be set, or both omitted"
            )
        # An "after" validator must hand the model back; returning None here
        # made the next validator receive None as `self`.
        return self

    @model_validator(mode="after")
    def validate_ownership(self) -> MethodFieldInput:
        """Normalise ownership and refuse the one combination that can never
        resolve: 'inherited' with nowhere to inherit from."""
        if self.ownership is None:
            return self
        normalised = self.ownership.strip().lower()
        if normalised not in FieldOwnership:
            allowed = ", ".join(sorted(m.value for m in FieldOwnership))
            raise ValueError(f"ownership must be one of {allowed}, got: {self.ownership!r}")
        self.ownership = normalised
        if normalised == FieldOwnership.INHERITED and self.source_entity_type is None:
            # Both source columns are guaranteed set-or-unset together by the
            # validator above, so checking one is checking both.
            raise ValueError(
                "ownership='inherited' requires source_entity_type and source_field_key "
                "to say which related record the value comes from"
            )
        if normalised == FieldOwnership.INHERITED and self.inherit_from is not None:
            # The two mechanisms differ in exactly one way: `inherit_from` is
            # projected into the entity type's relation metadata at publish,
            # `ownership='inherited'` deliberately is not. One field asking for
            # both would be both global and block-scoped at once, which is a
            # contradiction rather than a combination. Refusing it here is also
            # what guarantees an ownership-inherited field is never projected:
            # projection is keyed on `inherit_from`, and it cannot be set.
            raise ValueError(
                "a field cannot set both inherit_from and ownership='inherited': "
                "inherit_from is shared across the entity type, ownership='inherited' "
                "is scoped to this method block. Choose one."
            )
        return self

    @model_validator(mode="after")
    def validate_inherit_from(self) -> "MethodFieldInput":
        """Reject a malformed inherit_from before it can ever reach a pin."""
        if self.inherit_from is None:
            return self
        entity_type, _, field = self.inherit_from.partition(".")
        if not entity_type.strip() or not field.strip():
            raise ValueError(
                "inherit_from must be '<EntityTypeName>.<field>', "
                f"got: {self.inherit_from!r}"
            )
        return self


def _ordered_fields(fields: list[MethodFieldInput]) -> list[MethodFieldInput]:
    """Give every field a position that reads back in a defined order.

    Reads order by position alone, so ties leave the order up to Postgres and a
    method's field order could differ between two reads of the same version. A
    caller who sets no positions gets the order they sent; a caller who sets any
    must make them all distinct, since two fields claiming one slot has no
    meaning to honour.
    """
    if not fields:
        return fields
    supplied = [field for field in fields if "position" in field.model_fields_set]
    if not supplied:
        return [
            field.model_copy(update={"position": index}) for index, field in enumerate(fields)
        ]
    positions = [field.position for field in fields]
    duplicates = sorted({item for item in positions if positions.count(item) > 1})
    if duplicates:
        raise ValueError(
            "method field positions must be distinct; these are repeated: "
            + ", ".join(str(item) for item in duplicates)
        )
    return fields


class MethodCreateRequest(PydanticBaseModel):
    """Create a method, optionally with its opening field list.

    `method_code` is absent on purpose: it is a per-organization sequence the
    database assigns, never something a caller supplies.
    """

    name: str = Field(min_length=1, max_length=METHOD_NAME_MAX_LENGTH)
    description: str | None = None
    category_id: str | None = None
    fields: list[MethodFieldInput] = Field(default_factory=list)
    # Entity types this method is offered on; empty is allowed and hides it
    # from every workflow state picker until tagged.
    entity_types: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_model(self) -> MethodCreateRequest:
        """Settle the field order before anything is written."""
        self.fields = _ordered_fields(self.fields)
        return self


class MethodCloneRequest(PydanticBaseModel):
    """Copy one version of a method's field list into a brand new method.

    A starting point, not a link: the clone has no ongoing relationship to the
    method it came from. The caller always names it, so nothing invents a
    "(Copy)" suffix.
    """

    name: str = Field(min_length=1, max_length=METHOD_NAME_MAX_LENGTH)
    # None clones the source's current latest version.
    source_version_id: str | None = None
    # None inherits the source method's category.
    category_id: str | None = None


class MethodMetadataUpdateRequest(PydanticBaseModel):
    """Edit a method's name, description or category in place.

    Every member is optional and only those present are applied, so a caller can
    change one without restating the rest. None of this versions the method.
    """

    name: str | None = Field(default=None, min_length=1, max_length=METHOD_NAME_MAX_LENGTH)
    description: str | None = None
    category_id: str | None = None
    # None leaves the tags untouched; a list (including []) replaces them wholesale.
    entity_types: list[str] | None = None


class MethodFieldListUpdateRequest(PydanticBaseModel):
    """Replace a method's field list wholesale, producing a new version.

    A full replacement rather than a patch: additions, removals and reordering
    all arrive as the list the method should now have.
    """

    fields: list[MethodFieldInput] = Field(default_factory=list)
    connector_id: str | None = None

    @model_validator(mode="after")
    def validate_model(self) -> MethodFieldListUpdateRequest:
        """Settle the field order before anything is written."""
        self.fields = _ordered_fields(self.fields)
        return self


class MethodFieldRepinRequest(PydanticBaseModel):
    """Move one of a method's fields to a different version of that same field."""

    version_id: str = Field(min_length=1)

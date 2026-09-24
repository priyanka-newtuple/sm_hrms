"""Cross-module contracts for the field library.

The catalogue is data, not code, so each product can expose its own type list.
Pickability needs both `is_available` (engine built it) and `enabled` (org wants it).
"""

from __future__ import annotations

import os

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from common.data_model import ExtendedStrEnum
from common.logger import logger

# The database column widths, fixed by migration 202608180002. The ORM and the
# migration use these; they are not configurable, because a running database's
# column cannot be widened by an environment variable.
NAME_COLUMN_WIDTH = 256
KEY_COLUMN_WIDTH = 128
TYPE_CODE_COLUMN_WIDTH = 64


def _validation_limit(env_var: str, column_width: int) -> int:
    """Read a request-validation length limit from the environment.

    Clamped to the column width on purpose. A limit above it would let the
    contract accept a value Postgres then truncates, which is the 500 these
    limits exist to prevent; a limit below it is a deliberate, safe narrowing.
    Anything unset, unparseable or non-positive falls back to the column width.
    """
    raw = os.environ.get(env_var)
    if raw is None:
        return column_width
    try:
        requested = int(raw)
    except ValueError:
        logger.warning(
            "%s is not an integer (%r); falling back to %s", env_var, raw, column_width
        )
        return column_width
    if requested < 1:
        logger.warning(
            "%s must be positive (got %s); falling back to %s", env_var, requested, column_width
        )
        return column_width
    if requested > column_width:
        logger.warning(
            "%s of %s exceeds the %s column width; clamping to %s",
            env_var,
            requested,
            column_width,
            column_width,
        )
    return min(requested, column_width)


# Request-validation limits, so an over-long value is rejected as a 4xx instead
# of reaching Postgres and surfacing as a 500.
FIELD_NAME_MAX_LENGTH = _validation_limit("FIELD_LIBRARY_NAME_MAX_LENGTH", NAME_COLUMN_WIDTH)
FIELD_KEY_MAX_LENGTH = _validation_limit("FIELD_LIBRARY_KEY_MAX_LENGTH", KEY_COLUMN_WIDTH)
FIELD_TYPE_CODE_MAX_LENGTH = _validation_limit(
    "FIELD_LIBRARY_TYPE_CODE_MAX_LENGTH", TYPE_CODE_COLUMN_WIDTH
)


class FieldTypeConfigKind(ExtendedStrEnum):
    """Which extra configuration block a field type needs, if any."""

    NONE = "none"
    PICKLIST = "picklist"
    TABLE = "table"
    CURRENCY = "currency"
    AUTO_NUMBER = "auto_number"
    ENUM_VALUES = "enum_values"


class FieldTypeCatalogueEntry(PydanticBaseModel):
    """One permitted field type as held in the catalogue.

    `engine_type` is what the workflow layer expects, or None when the engine
    cannot store the type yet, which always pairs with `is_available=False`.
    """

    code: str
    label: str
    engine_type: str | None = None
    config_kind: str = FieldTypeConfigKind.NONE.value
    is_available: bool = True
    sort_order: int = 0


class OrganizationFieldTypeSetting(PydanticBaseModel):
    """Whether one organization has turned one catalogue entry on."""

    organization_id: str
    field_type_code: str
    enabled: bool = True


class FieldIdentity(PydanticBaseModel):
    """A field's live state. field_key is its only permanent member.

    Name is edited in place. Type is versioned content: changing it creates a new
    version, and this reflects the newest version's type.
    """

    library_field_id: str
    field_count_id: int
    organization_id: str
    name: str
    field_key: str
    field_type: str
    created_by: str | None = None
    # Resolved display name for created_by. The id is kept alongside it so
    # anything already relying on the id is unaffected.
    created_by_name: str | None = None
    is_archived: bool = False


class FieldVersion(PydanticBaseModel):
    """One version of a field's editable content.

    `version_id` is what a form links to, so a consumer stays pinned to the
    version it chose even after newer ones exist.
    """

    version_id: str
    library_field_id: str
    organization_id: str
    version: int
    # The identity's name and type when this version was created, frozen
    # thereafter, so later changes leave older versions as they were.
    name: str
    field_type: str
    description: str | None = None
    settings: dict[str, object] = Field(default_factory=dict)
    is_latest: bool = False
    created_by: str | None = None
    created_by_name: str | None = None


class FormFieldLink(PydanticBaseModel):
    """One form's use of one Field Library version.

    `version_id` is a pin: the form keeps reading the version it linked, so a
    later edit to the field cannot change a form underneath it. `metadata` holds
    that form's own behaviour for the field.
    """

    id: str
    schema_id: str
    organization_id: str
    library_field_id: str
    version_id: str
    position: int = 0
    metadata: dict[str, object] = Field(default_factory=dict)


class FormFieldPlacement(PydanticBaseModel):
    """A linked field as a form needs to read it: the link, plus what it points at."""

    link: FormFieldLink
    identity: FieldIdentity
    version: FieldVersion


class FieldWithVersion(PydanticBaseModel):
    """A field's identity paired with one of its versions."""

    identity: FieldIdentity
    version: FieldVersion

"""PostgreSQL membership predicates matching the shared role-read evaluator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Numeric, Text, and_, case, cast, column, false, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

    from common.protocols import EntityConditionSpec


def _scalar_membership(
    value: ColumnElement, condition: EntityConditionSpec
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    kind = func.jsonb_typeof(value)
    text_value = value.op("#>>", return_type=Text())("{}")
    comparable = case((kind == "boolean", func.initcap(text_value)), else_=text_value)
    usable = and_(kind.in_(["string", "number", "boolean"]), text_value != "")
    # CASE protects the cast even if the query planner reorders other predicates.
    numeric = case((kind == "number", cast(text_value, Numeric)))
    matches = or_(
        and_(kind.in_(["string", "boolean"]), comparable.in_(sorted(condition.membership_values))),
        numeric.in_(sorted(condition.membership_numbers)),
    )
    # A nonnumeric text value leaves the numeric branch NULL. Negation must
    # operate on False, not SQL UNKNOWN, for NOT IN to include that value.
    return usable, func.coalesce(matches, false())


def membership_expression(
    stored: ColumnElement, condition: EntityConditionSpec
) -> ColumnElement[bool]:
    """Scalar fast path; one aggregate scan for multi-select arrays.

    Missing/empty fields and malformed nested containers satisfy neither operator.
    Arrays match IN when any usable selection matches, NOT IN when none match.
    """
    if not condition.membership_values:
        return false()

    usable, matches = _scalar_membership(stored, condition)
    scalar_result = and_(usable, matches if condition.operator == "in" else ~matches)
    is_array = func.jsonb_typeof(stored) == "array"
    elements = (
        func.jsonb_array_elements(case((is_array, stored), else_=literal([], type_=JSONB)))
        .table_valued(column("value", JSONB))
        .alias()
    )
    item = elements.c.value
    item_usable, item_matches = _scalar_membership(item, condition)
    has_value = func.coalesce(func.bool_or(item_usable), false())
    malformed = func.coalesce(
        func.bool_or(func.jsonb_typeof(item).in_(["object", "array"])), false()
    )
    any_match = func.coalesce(func.bool_or(and_(item_usable, item_matches)), false())
    array_result = (
        select(and_(has_value, ~malformed, any_match if condition.operator == "in" else ~any_match))
        .select_from(elements)
        .scalar_subquery()
    )
    return case((is_array, array_result), else_=scalar_result)

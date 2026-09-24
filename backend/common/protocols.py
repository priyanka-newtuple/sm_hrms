"""Shared Protocol definitions for cross-module type hints."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING, Any, Protocol

from common.condition_values import parse_membership_numbers, parse_membership_values
from common.logger import logger

if TYPE_CHECKING:
    from collections.abc import Callable

SYSTEM_USER = "system"
MASKED_FIELD_VALUE = "***"


class RolePermissionLike(Protocol):
    entity_field: str | None
    operator: str | None
    condition_value: str | None
    read_filter: dict[str, Any] | None


@dataclass(frozen=True)
class EntityConditionSpec:
    """One role's read-narrowing condition on an entity type (entity field permission filter)."""

    entity_field: str
    operator: str
    condition_value: str | None
    conditions: tuple[EntityConditionSpec, ...] | None = None

    @cached_property
    def membership_values(self) -> frozenset[str]:
        # A policy is reused across records: parse each condition only once.
        return parse_membership_values(self.condition_value)

    @cached_property
    def membership_numbers(self) -> frozenset[Decimal]:
        return parse_membership_numbers(self.membership_values)

    @property
    def field_names(self) -> set[str]:
        if self.conditions is not None:
            return {name for child in self.conditions for name in child.field_names}
        return {self.entity_field}

    @classmethod
    def from_permission(cls, permission: RolePermissionLike | Any) -> EntityConditionSpec | None:
        """Keep each role's group intact; separate roles still combine with OR."""
        group = getattr(permission, "read_filter", None)
        if group is not None:
            # AND binds more tightly than OR: A AND B OR C => (A AND B) OR C.
            alternatives: list[EntityConditionSpec] = []
            conjunction: list[EntityConditionSpec] = []
            for item in group["conditions"]:
                if item.get("conjunction", "AND") == "OR" and conjunction:
                    alternatives.append(cls("", "AND", None, tuple(conjunction)))
                    conjunction = []
                conjunction.append(
                    cls(item["entity_field"], item["operator"], item["condition_value"])
                )
            if conjunction:
                alternatives.append(cls("", "AND", None, tuple(conjunction)))
            return cls("", "OR", None, tuple(alternatives))
        if permission.entity_field and permission.operator:
            return cls(permission.entity_field, permission.operator, permission.condition_value)
        return None


@dataclass(frozen=True)
class EntityAccessCheck:
    """Result of evaluating a user's roles against an entity-type/action permission.

    `conditions` is only meaningful when `allowed` is True: empty means every granting
    role's access is unconditional; non-empty means access is granted only if at least
    one condition matches the record being read (most-permissive-role-wins).
    """

    allowed: bool
    conditions: list[EntityConditionSpec] = field(default_factory=list)


@dataclass(frozen=True)
class EntityReadPolicy:
    """Compiled per-type list-read policy, reusable for every row in a page."""

    conditions: list[EntityConditionSpec] = field(default_factory=list)
    visible_fields: set[str] | None = None
    masked_fields: set[str] = field(default_factory=set)


def resolve_and_compare(
    condition: EntityConditionSpec,
    record_data: dict[str, object] | None,
    *,
    entity_id: str | None = None,
) -> bool:
    """Evaluate one entity permission read condition against a record's data. Never
    raises — a missing/empty field value is always treated as "does not match", logged
    quietly for diagnostic visibility, since runtime records are routinely incomplete
    at a given moment and this must never look like a broken API.

    Shared by every read surface that must respect an entity field permission filter
    condition — not just entity reads themselves, but any other module (e.g. audit
    event reads for a specific entity) that exposes a record's data to an actor.
    """
    if condition.conditions is not None:
        # An empty or invalid group must never grant unrestricted read access.
        if not condition.conditions or condition.operator not in {"AND", "OR"}:
            return False
        matches = (
            resolve_and_compare(child, record_data, entity_id=entity_id)
            for child in condition.conditions
        )
        return all(matches) if condition.operator == "AND" else any(matches)
    field_value = (record_data or {}).get(condition.entity_field)
    if field_value is None or field_value == "":
        logger.debug(
            "entity permission condition field empty on record — treated as no-match",
            extra={"entity_id": entity_id, "entity_field": condition.entity_field},
        )
        return False
    if condition.operator == "==":
        return str(field_value) == condition.condition_value
    if condition.operator == "!=":
        return str(field_value) != condition.condition_value
    if condition.operator in {"in", "not_in"}:
        if not condition.membership_values:
            return False
        selections = field_value if isinstance(field_value, list) else [field_value]
        # Malformed structured values must not accidentally satisfy a negative filter.
        if any(not isinstance(value, (str, int, float, bool, type(None))) for value in selections):
            return False
        values = [value for value in selections if value is not None and value != ""]
        if not values:
            return False
        matches = any(
            Decimal(str(value)) in condition.membership_numbers
            if type(value) in (int, float)
            else str(value) in condition.membership_values
            for value in values
        )
        return matches if condition.operator == "in" else not matches
    logger.warning(
        "entity permission condition has an unsupported operator at check time",
        extra={"entity_field": condition.entity_field, "operator": condition.operator},
    )
    return False


def record_satisfies_any_condition(
    conditions: list[EntityConditionSpec],
    record_data: dict[str, object] | None,
    *,
    entity_id: str | None = None,
) -> bool:
    """True if there's no condition to satisfy, or at least one condition is
    satisfied (most-permissive-role-wins)."""
    if not conditions:
        return True
    return any(
        resolve_and_compare(condition, record_data, entity_id=entity_id) for condition in conditions
    )


class RolesServiceProtocol(Protocol):
    """Roles manager methods used across modules."""

    workflow_service_manager: Any

    def get_workflow_access_scope(self, actor: dict[str, object]) -> set[str] | None: ...
    def get_visible_fields(
        self, db: Any, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None: ...
    def get_editable_fields(
        self, db: Any, user_id: str, org_id: str, entity_type: str
    ) -> list[str] | None: ...
    def get_masked_fields(
        self, db: Any, user_id: str, org_id: str, entity_type: str
    ) -> list[str]: ...
    def check_entity_permission(
        self, db: Any, user_id: str, org_id: str, entity_type: str, action: str
    ) -> bool: ...
    def evaluate_entity_access(
        self, db: Any, user_id: str, org_id: str, entity_type: str, action: str
    ) -> EntityAccessCheck: ...
    def resolve_entity_read_policies(
        self, db: Any, user_id: str, org_id: str, entity_types: set[str]
    ) -> dict[str, EntityReadPolicy]: ...


class BackgroundTaskScheduler(Protocol):
    """Structural stand-in for `fastapi.BackgroundTasks`"""

    def add_task(self, func: Callable[..., object], *args: object, **kwargs: object) -> None: ...

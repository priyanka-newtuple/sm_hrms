"""Interface models and contracts for the roles module."""

from __future__ import annotations

from dataclasses import dataclass

from common.data_model import ExtendedStrEnum


class EntityConditionOperator(ExtendedStrEnum):
    """Supported comparison operators for an entity permission's read condition."""

    EQUALS = "=="
    NOT_EQUALS = "!="
    IN = "in"
    NOT_IN = "not_in"


class EntityConditionValueSource(ExtendedStrEnum):
    """Where a condition's comparison value comes from. Only LITERAL is supported today —
    the column is a plain string, deliberately, so a future source (e.g. a live external
    lookup) can be added without a schema change."""

    LITERAL = "LITERAL"


@dataclass(frozen=True)
class PermissionCheckResult:
    """Result of a DB-backed permission evaluation."""

    allowed: bool
    permission_key: str
    reason: str

    @classmethod
    def allow(cls, permission_key: str) -> PermissionCheckResult:
        return cls(allowed=True, permission_key=permission_key, reason="granted")

    @classmethod
    def deny(cls, permission_key: str, reason: str) -> PermissionCheckResult:
        return cls(allowed=False, permission_key=permission_key, reason=reason)

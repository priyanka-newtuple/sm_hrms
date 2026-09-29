from __future__ import annotations

import datetime
import decimal
import enum
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from hrms.models.audit import AuditLog


def _json_safe(value: Any) -> Any:
    """Recursively coerce values (UUIDs, dates, Decimals, enums...) coming
    straight from a Pydantic `.model_dump()` into what JSONB can store —
    callers pass domain objects here, not pre-serialized dicts."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (uuid.UUID, datetime.date, datetime.datetime, decimal.Decimal)):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    return value


async def record_audit(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: str,
    diff: dict | None = None,
) -> None:
    """Called for every Delete and every Full-level action, per the permission spec."""
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            diff=_json_safe(diff) if diff is not None else None,
        )
    )

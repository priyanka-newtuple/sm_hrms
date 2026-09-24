"""Database/domain exception primitives for modular backend modules."""

from __future__ import annotations

try:
    from exceptions.base import NotFoundError, PersistenceError
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.exceptions.base import NotFoundError, PersistenceError


class DBException(PersistenceError):
    """Base exception for persistence and manager-level data failures."""

    def __init__(self, detail: str, *, code: str | None = None, ctx: dict | None = None) -> None:
        super().__init__(detail, code=code or "db_error", ctx=ctx)


class RecordNotFoundException(NotFoundError):
    """Raised when a module-specific record cannot be resolved."""

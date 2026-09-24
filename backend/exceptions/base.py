"""Shared exception taxonomy for modular backend modules."""

from __future__ import annotations


class ModularError(Exception):
    """Base error class for modular backend failures."""

    # Optional HTTP status override, read by `_custom_status` (common/utils.py).
    status_code: int | None = None

    def __init__(self, detail: str, *, code: str | None = None, ctx: dict | None = None) -> None:
        self.detail = detail
        self.code = code
        self.ctx = ctx or {}
        super().__init__(detail)


class ValidationError(ModularError):
    """Raised for request or domain validation failures."""


class AuthorizationError(ModularError):
    """Raised for permission and tenancy scope failures."""


class NotFoundError(ModularError):
    """Raised when a required resource cannot be found."""


class ConflictError(ModularError):
    """Raised for state or uniqueness conflicts."""


class PersistenceError(ModularError):
    """Raised when persistence operations fail."""


class ServiceError(ModularError):
    """Raised for unexpected service orchestration failures."""


class ServiceUnavailableError(ModularError):
    """Raised when a required dependency (e.g. the roles/permission service) cannot
    be reached to evaluate a check. Callers must fail closed on this — an unevaluable
    permission is never treated as a granted one."""


class MicrosoftOAuthError(ServiceError):
    """Raised for Microsoft OAuth provider and token validation failures."""

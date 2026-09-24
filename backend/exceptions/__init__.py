"""Shared exception contracts for modular backend controllers/managers."""

from .base import (
    AuthorizationError,
    ConflictError,
    MicrosoftOAuthError,
    ModularError,
    NotFoundError,
    PersistenceError,
    ServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from .db import DBException, RecordNotFoundException

__all__ = [
    "AuthorizationError",
    "ConflictError",
    "DBException",
    "MicrosoftOAuthError",
    "ModularError",
    "NotFoundError",
    "PersistenceError",
    "RecordNotFoundException",
    "ServiceError",
    "ServiceUnavailableError",
    "ValidationError",
]

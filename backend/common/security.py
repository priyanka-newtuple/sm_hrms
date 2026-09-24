"""Security utilities for the auth module.

All cryptographic operations live here — password hashing, JWT creation/decoding,
token generation. No dependency on app/ — reads config from env vars directly.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from common.configuration import get_configuration

# ── Config from env (no app/ dependency) ─────────────────────────────────────

_JWT_SECRET_KEY: str = get_configuration().security_configuration.jwt_secret_key
_JWT_ALGORITHM: str = get_configuration().security_configuration.jwt_algorithm
_ACCESS_TOKEN_EXPIRE_MINUTES: int = (
    get_configuration().security_configuration.access_token_expire_minutes
)
_REFRESH_TOKEN_EXPIRE_DAYS: int = (
    get_configuration().security_configuration.refresh_token_expire_days
)


# ── Password hashing ──────────────────────────────────────────────────────────


def _pre_hash_password(password: str) -> bytes:
    """SHA256 pre-hash to avoid bcrypt's 72-byte limit."""
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    """Hash a plain password with SHA256 + bcrypt."""
    pre_hashed = _pre_hash_password(password)
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pre_hashed, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a stored bcrypt hash."""
    pre_hashed = _pre_hash_password(plain_password)
    try:
        return bcrypt.checkpw(pre_hashed, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT tokens ────────────────────────────────────────────────────────────────


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    organization_id: str | None = None,
    roles: list[str] | None = None,
) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "access"}
    if organization_id:
        payload["organization_id"] = organization_id
    if roles:
        payload["roles"] = roles
    return jwt.encode(payload, _JWT_SECRET_KEY, algorithm=_JWT_ALGORITHM)


def create_refresh_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT refresh token with a unique jti."""
    expire = datetime.now(UTC) + (expires_delta or timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS))
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _JWT_SECRET_KEY, algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT. Returns None if invalid or expired."""
    try:
        return jwt.decode(token, _JWT_SECRET_KEY, algorithms=[_JWT_ALGORITHM])
    except JWTError:
        return None


def hash_refresh_token(token: str) -> str:
    """SHA256 hash a refresh token for safe DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Password reset token ──────────────────────────────────────────────────────


def create_password_reset_token(user_id: str, password_hash: str) -> str:
    """Create a 1-hour JWT for password reset.

    Embeds a truncated hash of the current password so the token is
    automatically invalidated once the password changes.
    """
    phash = hashlib.sha256(password_hash.encode()).hexdigest()[:16]
    expire = datetime.now(UTC) + timedelta(hours=1)
    payload: dict[str, Any] = {
        "sub": user_id,
        "exp": expire,
        "purpose": "password_reset",
        "phash": phash,
    }
    return jwt.encode(payload, _JWT_SECRET_KEY, algorithm=_JWT_ALGORITHM)


def decode_password_reset_token(token: str) -> dict[str, Any] | None:
    """Decode a password reset JWT. Returns None if invalid, expired, or wrong purpose."""
    payload = decode_token(token)
    if not payload or payload.get("purpose") != "password_reset":
        return None
    return payload


# ── Form link tokens ─────────────────────────────────────────────────────────


def create_form_link_token(
    entity_id: str,
    run_id: str,
    org_id: str,
    hours: int = 24,
) -> str:
    """Create a signed JWT for a public form link."""
    expire = datetime.now(UTC) + timedelta(hours=hours)
    payload: dict[str, Any] = {
        "type": "form_link",
        "entity_id": entity_id,
        "run_id": run_id,
        "org_id": org_id,
        "exp": expire,
    }
    return jwt.encode(payload, _JWT_SECRET_KEY, algorithm=_JWT_ALGORITHM)


def decode_form_link_token(token: str) -> dict[str, str]:
    """Decode a form link JWT. Raises ValueError if invalid, expired, or wrong type."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "form_link":
        raise ValueError("invalid or expired form link token")
    return {
        "entity_id": str(payload["entity_id"]),
        "run_id": str(payload["run_id"]),
        "org_id": str(payload["org_id"]),
    }


# ── Misc ──────────────────────────────────────────────────────────────────────


def generate_random_password() -> str:
    """Generate a random password for OAuth users (never used for login)."""
    return uuid.uuid4().hex

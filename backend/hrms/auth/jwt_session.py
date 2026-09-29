from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from hrms.config import get_settings

settings = get_settings()


def create_session_token(user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "organization_id": settings.HRMS_ORGANIZATION_ID,
        "aud": "sm-hrms",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


class InvalidSessionToken(Exception):
    pass


def decode_session_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM], audience="sm-hrms")
        if payload.get("organization_id") != settings.HRMS_ORGANIZATION_ID:
            raise InvalidSessionToken("Wrong organization")
        return payload
    except JWTError as exc:
        raise InvalidSessionToken(str(exc)) from exc

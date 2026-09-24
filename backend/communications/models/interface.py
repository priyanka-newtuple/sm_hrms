"""Interface models and contracts for communications."""

from __future__ import annotations


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def normalize_mentions(raw_mentions: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for mention in raw_mentions:
        user_id = str(mention).strip()
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        normalized.append(user_id)
    return normalized


def validate_email(email: str) -> str:
    value = _non_empty(email, "email")
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("email must contain a valid @ separator")
    return value

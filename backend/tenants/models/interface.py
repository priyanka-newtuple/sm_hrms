"""Interface models for tenants."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrganizationsStatusContract:
    """Contract for module status payloads."""

    module: str
    status: str
    started: bool

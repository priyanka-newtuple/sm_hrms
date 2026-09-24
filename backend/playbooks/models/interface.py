"""Interface models for playbooks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlaybooksRuntimeStatusContract:
    """Contract for module status payloads."""

    module: str
    status: str
    started: bool

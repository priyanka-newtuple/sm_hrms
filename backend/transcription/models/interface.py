"""Interface models for transcription."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptionStatusContract:
    """Contract for module status payloads."""

    module: str
    status: str
    started: bool

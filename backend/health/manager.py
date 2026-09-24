"""Health manager placeholder."""

from __future__ import annotations


class HealthServiceManager:
    def health(self) -> dict[str, str]:
        return {"status": "ok"}

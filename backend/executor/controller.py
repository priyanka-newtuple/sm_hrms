"""Executor REST controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam


class ExecutorRestController:
    """Placeholder — action definition routes have moved to ActionsRestController."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Accept any arguments for interface compatibility."""
        _ = args, kwargs

    def prepare(self, app: APIRouter, security: DependsParam | None = None) -> None:
        """No routes to register — all executor routes live in ActionsRestController."""
        _ = app, security

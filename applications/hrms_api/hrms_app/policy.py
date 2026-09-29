"""HRMS capabilities are product configuration, not core permission catalog entries."""
import json
from pathlib import Path

from .errors import AppError

ROLE_CAPABILITIES = json.loads(Path(__file__).with_name('role_capabilities.json').read_text())


def capabilities(actor):
    return set().union(*(set(ROLE_CAPABILITIES.get(role, [])) for role in actor.roles))


def require(actor, capability):
    if capability not in capabilities(actor):
        raise AppError(403, f'{capability} permission is required')

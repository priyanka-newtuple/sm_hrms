"""HRMS capabilities are product configuration, not core permission catalog entries."""
import json
from pathlib import Path

from .errors import AppError

ROLE_CAPABILITIES = json.loads(Path(__file__).with_name('role_capabilities.json').read_text())


PROJECT_CAPABILITIES = frozenset({'project:view', 'project:read_all', 'project:create',
    'project:manage_assigned', 'project:manage_all', 'project:commercial_assigned',
    'project:commercial_all', 'project:approve', 'customer:create', 'allocation:request'})


COCKPIT_CAPABILITIES = frozenset({'cockpit:view', 'cockpit:author', 'cockpit:jobs', 'cockpit:approve', 'cockpit:publish'})

def role_capabilities(role, project_policy=None, cockpit_policy=None):
    result = set(ROLE_CAPABILITIES.get(role, []))
    if project_policy is not None and role in project_policy:
        result = (result - PROJECT_CAPABILITIES) | (set(project_policy[role]) & PROJECT_CAPABILITIES)
    if cockpit_policy is not None and role in cockpit_policy:
        result = (result - COCKPIT_CAPABILITIES) | (set(cockpit_policy[role]) & COCKPIT_CAPABILITIES)
    return result


def capabilities(actor):
    return set().union(*(role_capabilities(role, getattr(actor, 'project_policy', None), getattr(actor, 'cockpit_policy', None)) for role in actor.roles))


def require(actor, capability):
    if capability not in capabilities(actor):
        raise AppError(403, f'{capability} permission is required')

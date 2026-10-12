"""Read HRMS actions exclusively from native effective permission grants."""
from .errors import AppError


def permission_key(organization_id, capability):
    return f'tenant.{organization_id}.hrms.{capability}'


def capabilities(actor):
    prefix = f'tenant.{actor.organization_id}.hrms.'
    result = {key[len(prefix):] for key in actor.permissions if key.startswith(prefix)}
    # Configuration and account approval are explicitly reserved for native Super Admin.
    result -= {'platform:configure', 'employee:activate'}
    if 'superadmin' in actor.roles:
        if 'settings:access' in actor.permissions:
            result.add('platform:configure')
        if 'user:write' in actor.permissions:
            result.add('employee:activate')
    return result


def require(actor, capability):
    if capability not in capabilities(actor):
        raise AppError(403, f'{capability} permission is required')

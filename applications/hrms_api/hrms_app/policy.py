"""Read HRMS actions exclusively from native effective permission grants."""
from .errors import AppError


# Record visibility comes from Entity Access, not parallel hrms.*:view switches.
# These names are presentation aliases for existing API consumers, not grants.
ENTITY_READ_CAPABILITIES = {
    'employee:read': ('HRMS.Employee',),
    'customer:view': ('HRMS.Customer',),
    'project:view': ('HRMS.Project',),
    'allocation:view': ('HRMS.Allocation',),
    'asset:view': ('HRMS.Asset',),
    'offer:view': ('hrms_offer',),
    'content:policy:view': ('HRMS.Policy',),
    'content:learning:view': ('HRMS.LearningEvent',),
    'content:holiday:view': ('HRMS.HolidayCalendar',),
    'content:job-description:view': ('HRMS.JobDescription',),
    'content:job-opening:view': ('HRMS.JobOpening',),
}


def entity_allowed(actor, entity_type, action='view'):
    """Coarse entry check only. Native APIs enforce record filters and fields."""
    return actor.system_role or any(
        grant.get('entity_type') == entity_type and grant.get('action') == action
        and grant.get('allowed') is True for grant in actor.entity_permissions
    )


def require_entity(actor, entity_type, action='view'):
    if not entity_allowed(actor, entity_type, action):
        raise AppError(403, f'{action.capitalize()} access to {entity_type} is required')


def permission_key(organization_id, capability):
    return f'tenant.{organization_id}.hrms.{capability}'


def capabilities(actor):
    prefix = f'tenant.{actor.organization_id}.hrms.'
    result = {key[len(prefix):] for key in actor.permissions if key.startswith(prefix)}
    for capability, entities in ENTITY_READ_CAPABILITIES.items():
        result.discard(capability)
        if (actor.system_role or 'entity_record:read' in actor.permissions) and any(entity_allowed(actor, entity) for entity in entities):
            result.add(capability)
    # Account approvals remain backed by native user permissions.
    result -= {'platform:configure', 'employee:activate'}
    if 'superadmin' in actor.roles:
        if 'settings:access' in actor.permissions:
            result.add('platform:configure')
    if actor.roles & {'superadmin', 'hrms_hr_full'} and 'user:write' in actor.permissions:
        result.add('employee:activate')
    return result


def require(actor, capability):
    if capability not in capabilities(actor):
        raise AppError(403, f'{capability} permission is required')


def projected_records(platform, actor, entity_type, fields):
    """Native read projection for aggregates. Never fall back to the service identity."""
    try:
        rows = platform.records(entity_type, list(dict.fromkeys(fields)), token=actor.token)
    except AppError as exc:
        if exc.status == 403:
            return {}
        raise
    return {row['entity_id']: row for row in rows}

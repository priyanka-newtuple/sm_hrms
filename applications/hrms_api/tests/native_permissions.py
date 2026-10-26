"""Explicit native permission fixtures; production never derives grants from role names."""
from hrms_app.permission_migration import INITIAL_ROLE_GRANTS, legacy_grants
from hrms_app.policy import permission_key


def grants(roles, organization_id='org'):
    result = {permission_key(organization_id, cap) for role in roles for cap in legacy_grants(role)}
    if 'superadmin' in roles:
        result.update({'settings:access', 'user:write'})
    if {'superadmin','hrms_hr_full'} & set(roles):
        result.update({'user:read','user:write'})
    if roles:
        result.add(permission_key(organization_id,'onboarding:participate'))
        result.add(permission_key(organization_id, 'asset:view'))
    if {'superadmin', 'hrms_office_admin'} & set(roles):
        result.add(permission_key(organization_id, 'asset:manage'))
    return frozenset(result)

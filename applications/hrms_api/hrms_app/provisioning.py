"""Complete native self-host bootstrap through tenant-scoped public APIs."""


def ensure_tenant_administrator(api):
    token = api.service_token()
    # Refuse a platform-owner login or an inactive/mismatched membership before writing.
    actor = api.actor(token)
    organization = api.call('GET', '/organizations/current')
    if organization.get('id') != api.org or organization.get('status') != 'active':
        raise RuntimeError('The configured HRMS organization must exist and be active')
    if (organization.get('settings') or {}).get('is_platform'):
        raise RuntimeError('HRMS must use its own organization, not the platform organization')
    if 'superadmin' not in actor.roles:
        roles = api.call('GET', '/roles')
        role = next((r for r in roles if r['name'] == 'superadmin'), None)
        if role is None:
            raise RuntimeError('Native tenant Super Admin role is missing; check platform bootstrap')
        role = api.call('GET', f"/roles/{role['id']}")
        if role.get('organization_id') != api.org:
            raise RuntimeError('Super Admin role belongs to another organization')
        api.call('PUT', f'/roles/users/{actor.user_id}/role', json={'role_id': role['id']})
    verified = api.actor(token)
    if 'superadmin' not in verified.roles:
        raise RuntimeError('Tenant administrator role assignment could not be verified')
    return organization

from types import SimpleNamespace

import pytest

from hrms_app.provisioning import ensure_tenant_administrator


class Platform:
    org = 'hrms'

    def __init__(self):
        self.roles = {'admin'}
        self.organization = {'id': self.org, 'status': 'active', 'settings': None}
        self.role_org = self.org
        self.writes = []

    def service_token(self):
        return 'tenant-token'

    def actor(self, token):
        assert token == 'tenant-token'
        return SimpleNamespace(user_id='bootstrap-admin', roles=self.roles)

    def call(self, method, path, **kwargs):
        if method == 'PUT':
            self.writes.append((path, kwargs['json']))
            self.roles = {'superadmin'}
            return {}
        return {
            '/organizations/current': self.organization,
            '/roles': [{'id': 'tenant-superadmin', 'name': 'superadmin'}],
            '/roles/tenant-superadmin': {'id': 'tenant-superadmin', 'organization_id': self.role_org},
        }[path]


def test_native_bootstrap_admin_is_promoted_once_and_reruns_preserve_roles():
    api = Platform()
    ensure_tenant_administrator(api)
    api.roles.add('custom-role')
    ensure_tenant_administrator(api)
    assert api.roles == {'superadmin', 'custom-role'}
    assert api.writes == [('/roles/users/bootstrap-admin/role', {'role_id': 'tenant-superadmin'})]


@pytest.mark.parametrize('patch', [
    {'id': 'other'}, {'status': 'inactive'}, {'settings': {'is_platform': True}},
])
def test_wrong_or_inactive_organization_never_receives_a_grant(patch):
    api = Platform()
    api.organization.update(patch)
    with pytest.raises(RuntimeError):
        ensure_tenant_administrator(api)
    assert not api.writes


def test_cross_tenant_role_is_rejected():
    api = Platform()
    api.role_org = 'other'
    with pytest.raises(RuntimeError):
        ensure_tenant_administrator(api)
    assert not api.writes


def test_missing_membership_fails_before_any_writes():
    api = Platform()
    def denied(token):
        raise RuntimeError('Active membership required')
    api.actor = denied
    with pytest.raises(RuntimeError):
        ensure_tenant_administrator(api)
    assert not api.writes


@pytest.mark.parametrize('returned_org, expected_status', [('hrms', 200), ('other', 403)])
def test_organization_details_use_human_token_and_reject_other_tenants(returned_org, expected_status):
    from fastapi.testclient import TestClient
    from hrms_app.main import create_app
    from hrms_app.platform import Actor

    class OrganizationPlatform:
        def actor(self, token):
            return Actor('user', 'hrms', token, frozenset({'superadmin'}), frozenset())

        def request(self, method, path, *, token):
            assert (method, path, token) == ('GET', '/organizations/current', 'human-token')
            return {'id': returned_org, 'name': 'Test org', 'settings': {'private': 'not exposed'}}

    client = TestClient(create_app(OrganizationPlatform(), object()))
    assert client.get('/v1/api/hrms/organization').status_code == 401
    response = client.get('/v1/api/hrms/organization', headers={'Authorization': 'Bearer human-token'})
    assert response.status_code == expected_status
    if expected_status == 200:
        assert 'settings' not in response.json()

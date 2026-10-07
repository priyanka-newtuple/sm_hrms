import httpx
import pytest
from fastapi.testclient import TestClient

from hrms_app.main import create_app
from hrms_app.platform import Actor


@pytest.fixture
def surface():
    calls = []

    class Platform:
        org = 'org'

        def actor(self, token):
            return Actor(token, 'org', token, frozenset({token}), frozenset())

        def service_token(self):
            raise AssertionError('Settings must never use the application service identity')

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={'ok': True})

    platform = Platform()
    platform.http = httpx.Client(base_url='http://core/v1/api/', transport=httpx.MockTransport(upstream))
    return TestClient(create_app(platform, object())), calls


@pytest.mark.parametrize('path', ['entity-types', 'forms/config', 'field-library/fields', 'method-library/methods', 'roles', 'users', 'config/picklists', 'agent/definitions'])
def test_only_superadmin_can_read_settings(surface, path):
    client, calls = surface
    for role in ('hrms_employee', 'hrms_hr_full', 'hrms_delivery_manager', 'admin'):
        assert client.get('/v1/api/'+path, headers={'Authorization': 'Bearer '+role}).status_code == 403
    assert not calls
    assert client.get('/v1/api/'+path, headers={'Authorization':'Bearer superadmin'}).status_code == 200
    assert calls[-1].headers['authorization'] == 'Bearer superadmin'


def test_native_configuration_writes_preserve_user_and_body(surface):
    client, calls = surface
    payload = {'name':'HRMS.Test', 'organization_id':'org'}
    response = client.post('/v1/api/entity-types', headers={'Authorization':'Bearer superadmin'}, json=payload)
    assert response.status_code == 200
    assert calls[-1].headers['authorization'] == 'Bearer superadmin'
    assert calls[-1].read() == b'{"name":"HRMS.Test","organization_id":"org"}'


@pytest.mark.parametrize('path', ['entity-records', 'entities/123/transitions', 'workflow-state-machines/foo/enrollments', 'agent/runs', 'schedules/123/run-now', 'bulk/transitions'])
def test_settings_does_not_open_runtime_mutation_bypass(surface, path):
    client, calls = surface
    assert client.post('/v1/api/'+path, headers={'Authorization':'Bearer superadmin'}, json={}).status_code == 403
    assert not calls


def test_cross_organization_configuration_is_denied(surface):
    client, calls = surface
    headers = {'Authorization':'Bearer superadmin'}
    assert client.get('/v1/api/entity-types?organization_id=other', headers=headers).status_code == 403
    assert client.get('/v1/api/entity-types?org_id=org&org_id=other', headers=headers).status_code == 403
    assert client.post('/v1/api/entity-types', headers=headers, json={'organization_id':'other'}).status_code == 403
    assert client.get('/v1/api/organizations/other', headers=headers).status_code == 403
    assert not calls


def test_project_access_settings_authorization_validation_and_revision():
    from copy import deepcopy
    from hrms_app.errors import AppError
    class Platform:
        org = 'org'
        def actor(self, token):
            return Actor(token, 'org', token, frozenset({token}), frozenset())
        def request(self, method, path, token):
            assert token == 'superadmin' and path == '/roles'
            return [{'name': name} for name in ['superadmin', 'hrms_project_manager', 'hrms_application_service']]
    class Journal:
        policies = {}
        def project_policy(self, org):
            return deepcopy(self.policies.get(org, {'roles': {}, 'revision': 0}))
        def save_project_policy(self, actor, roles, revision):
            if self.project_policy(actor.organization_id)['revision'] != revision:
                raise AppError(409, 'Reload before saving')
            self.policies[actor.organization_id] = dict(roles=roles, revision=revision+1)
            return self.project_policy(actor.organization_id)
    journal=Journal()
    client=TestClient(create_app(Platform(), journal))
    path='/v1/api/hrms/settings/project-access'
    headers={'Authorization': 'Bearer superadmin'}
    assert client.get(path, headers={'Authorization':'Bearer hrms_project_manager'}).status_code == 403
    assert client.put(path, headers={'Authorization':'Bearer hrms_project_manager'}, json={'roles':{},'revision':0}).status_code == 403
    policy=client.get(path, headers=headers).json()
    assert 'hrms_application_service' not in policy['roles']
    assert 'allocation:request' in policy['roles']['hrms_project_manager']
    assert client.put(path,headers=headers,json={'roles':{'superadmin':['platform:configure']},'revision':0}).status_code == 422
    payload={'roles':{'hrms_project_manager':[]},'revision':0}
    assert client.put(path,headers=headers,json=payload).status_code == 200
    assert client.put(path,headers=headers,json=payload).status_code == 409
    assert client.get(path,headers=headers).json()['roles']['hrms_project_manager'] == []
    assert journal.project_policy('other')['roles'] == {}
    caps=client.get('/v1/api/hrms/capabilities',headers={'Authorization':'Bearer hrms_project_manager'}).json()['capabilities']
    assert 'project:view' not in caps


@pytest.mark.parametrize('method,path', [
    ('POST', 'users/user-id/approve'),
    ('POST', 'users/user-id/reject'),
    ('DELETE', 'config/picklists/picklist-id'),
])
def test_bodyless_settings_actions_preserve_human_token_and_empty_body(surface, method, path):
    client, calls = surface
    response = client.request(method, '/v1/api/' + path, headers={
        'Authorization': 'Bearer superadmin', 'Content-Type': 'application/json',
    })
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].headers['authorization'] == 'Bearer superadmin'
    assert calls[0].content == b''


@pytest.mark.parametrize('body', [b'{', b' ', b'\xff'])
def test_invalid_settings_json_returns_client_error_without_upstream_write(surface, body):
    client, calls = surface
    response = client.post('/v1/api/users/user-id/approve', headers={
        'Authorization': 'Bearer superadmin', 'Content-Type': 'application/json',
    }, content=body)
    assert response.status_code == 400
    assert not calls


def test_bodyless_settings_actions_keep_authorization_checks(surface):
    client, calls = surface
    assert client.post('/v1/api/users/user-id/approve', headers={
        'Authorization': 'Bearer hrms_employee', 'Content-Type': 'application/json',
    }).status_code == 403
    assert client.post('/v1/api/users/user-id/approve?organization_id=other', headers={
        'Authorization': 'Bearer superadmin', 'Content-Type': 'application/json',
    }).status_code == 403
    assert not calls

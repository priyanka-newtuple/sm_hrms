from native_permissions import grants
import httpx
import pytest
from fastapi.testclient import TestClient

from hrms_app.main import create_app
from hrms_app.platform import Actor


@pytest.fixture
def surface():
    calls = []

    class Platform:
        def records(self, kind, fields):
            return []
        org = 'org'

        def actor(self, token):
            return Actor(token, 'org', token, frozenset({token}), grants({token}))

        def service_token(self):
            raise AssertionError('Settings must never use the application service identity')

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={'ok': True})

    platform = Platform()
    platform.http = httpx.Client(base_url='http://core/v1/api/', transport=httpx.MockTransport(upstream))
    return TestClient(create_app(platform, object())), calls


@pytest.mark.parametrize('path', ['entity-types', 'forms/config', 'field-library/fields', 'method-library/methods', 'roles', 'users', 'config/picklists', 'agent/definitions', 'llm/models'])
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
    write = next(c for c in calls if c.method == 'POST')  # then HRMS tops up its own field access, as this admin
    assert write.headers['authorization'] == 'Bearer superadmin'
    assert write.read() == b'{"name":"HRMS.Test","organization_id":"org"}'
    assert all(c.headers['authorization'] == 'Bearer superadmin' for c in calls)


@pytest.mark.parametrize('path', ['entity-records', 'entities/123/transitions', 'workflow-state-machines/foo/enrollments', 'agent/runs/run-id/unknown-action', 'schedules/123/run-now', 'bulk/transitions'])
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


def test_removed_hrms_permission_editors_cannot_read_or_write(surface):
    client, calls = surface
    for suffix in ('project-access', 'cockpit-access', 'role-capabilities'):
        path = '/v1/api/hrms/settings/' + suffix
        for method in ('GET', 'PUT'):
            assert client.request(method, path, headers={'Authorization': 'Bearer superadmin'}).status_code == 403
    assert not calls


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


def test_model_discovery_is_tenant_scoped_and_read_only(surface):
    client, calls = surface
    headers = {'Authorization': 'Bearer superadmin'}
    assert client.get('/v1/api/llm/models?organization_id=other', headers=headers).status_code == 403
    assert client.post('/v1/api/llm/models', headers=headers, json={}).status_code == 403
    assert not calls
    assert client.get('/v1/api/llm/models?organization_id=org', headers=headers).status_code == 200
    assert calls[0].url.params['organization_id'] == 'org'
    assert calls[0].headers['authorization'] == 'Bearer superadmin'


def test_agent_board_reads_preserve_native_authorization(surface):
    client, calls = surface
    path = '/v1/api/workflow-enrollments'
    headers = {'Authorization': 'Bearer superadmin'}
    for role in ('hrms_employee', 'hrms_hr_full', 'admin'):
        assert client.get(path, headers={'Authorization': 'Bearer ' + role}).status_code == 403
    assert client.get(path + '?organization_id=other', headers=headers).status_code == 403
    for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        assert client.request(method, path, headers=headers, json={}).status_code == 403
    assert not calls
    params = {'machine_name': 'employee-flow', 'current_state': 'Onboarding Completed', 'limit': '20'}
    assert client.get(path, headers=headers, params=params).status_code == 200
    assert calls[0].headers['authorization'] == 'Bearer superadmin'
    assert dict(calls[0].url.params) == params


@pytest.mark.parametrize('method,path', [
    ('POST', 'agent/runs'), ('POST', 'agent/async_runs'),
    ('POST', 'agent/runs/run-id/resume'), ('POST', 'agent/runs/run-id/cancel'),
    ('PATCH', 'agent/sessions/session-id'), ('DELETE', 'agent/sessions/session-id'),
])
def test_native_agent_actions_preserve_human_identity_and_admin_boundary(surface, method, path):
    client, calls = surface
    payload = {'definition_id': 'native-agent', 'input': 'Hello'}
    for role in ('hrms_employee', 'hrms_hr_full', 'admin'):
        assert client.request(method, '/v1/api/' + path, headers={
            'Authorization': 'Bearer ' + role}, json=payload).status_code == 403
    assert client.request(method, '/v1/api/' + path + '?organization_id=other', headers={
        'Authorization': 'Bearer superadmin'}, json=payload).status_code == 403
    assert not calls
    assert client.request(method, '/v1/api/' + path, headers={
        'Authorization': 'Bearer superadmin'}, json=payload).status_code == 200
    assert len(calls) == 1
    assert calls[0].headers['authorization'] == 'Bearer superadmin'
    import json
    assert json.loads(calls[0].content) == payload


def test_native_agent_permission_denial_is_not_overridden(surface, monkeypatch):
    client, _ = surface
    original = httpx.Client.request

    def refuse(self, method, url, **kwargs):
        if str(self.base_url).startswith('http://core/'):
            return httpx.Response(403, json={'detail': 'Native agent permission denied'})
        return original(self, method, url, **kwargs)

    monkeypatch.setattr(httpx.Client, 'request', refuse)
    response = client.post('/v1/api/agent/runs', headers={'Authorization': 'Bearer superadmin'},
                           json={'definition_id': 'native-agent', 'input': 'Hello'})
    assert response.status_code == 403
    assert response.json()['detail'] == 'Native agent permission denied'

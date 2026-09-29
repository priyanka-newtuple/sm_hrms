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

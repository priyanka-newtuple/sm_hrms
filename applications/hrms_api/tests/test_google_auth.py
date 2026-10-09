import httpx
import pytest
from fastapi.testclient import TestClient
from hrms_app.main import create_app
from hrms_app.platform import PlatformClient

REDIRECT = 'https://hrms.newtuple.com/auth/google/callback'

@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', REDIRECT)
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'url': 'https://accounts.google.com/o/oauth2/v2/auth?client_id=test'})
        return httpx.Response(202, json={'approval_type': 'pending_org_admin'})
    platform = PlatformClient('http://platform/v1/api', 'org', 'service', 'secret', transport=httpx.MockTransport(handler))
    return TestClient(create_app(platform, object()), base_url='https://hrms.newtuple.com'), calls


def test_google_start_and_callback_preserve_native_approval(flow):
    from urllib.parse import parse_qs, urlsplit
    client, calls = flow
    response = client.get('/v1/api/auth/google/url', params={'redirect_uri': REDIRECT})
    params = parse_qs(urlsplit(response.json()['url']).query)
    assert params['hd'] == ['newtuple.com']
    assert params['redirect_uri'] == [REDIRECT]
    assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
    result = client.post('/v1/api/auth/google/callback', json={'code': 'test-code', 'state': params['state'][0], 'redirect_uri': REDIRECT})
    assert result.status_code == 202
    assert result.json()['approval_type'] == 'pending_org_admin'
    assert 'state' not in __import__('json').loads(calls[-1].content)
    assert not client.cookies.get('hrms_google_state')


@pytest.mark.parametrize('state', [None, '', 'wrong', '\u2603'])
def test_google_rejects_unbound_callback(flow, state):
    client, calls = flow
    client.get('/v1/api/auth/google/url')
    result = client.post('/v1/api/auth/google/callback', json={'code': 'code', 'state': state, 'redirect_uri': REDIRECT})
    assert result.status_code == 400
    assert len(calls) == 1


def test_google_rejects_external_redirect(flow):
    client, calls = flow
    assert client.get('/v1/api/auth/google/url', params={'redirect_uri': 'https://evil.example/auth/google/callback'}).status_code == 400
    assert not calls


def test_google_requires_https_configuration(flow, monkeypatch):
    client, calls = flow
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', 'http://62.238.103.67:8082/auth/google/callback')
    assert client.get('/v1/api/auth/google/url').status_code == 503
    assert not calls


@pytest.mark.parametrize('method,path', [('get','url'), ('post','callback'), ('post','id-token')])
def test_microsoft_is_unavailable(flow, method, path):
    client, calls = flow
    assert getattr(client, method)('/v1/api/auth/microsoft/' + path).status_code == 403
    assert not calls


def test_active_callback_checks_tenant_before_returning_tokens(flow):
    from hrms_app.errors import AppError
    from urllib.parse import parse_qs, urlsplit
    client, calls = flow
    start = client.get('/v1/api/auth/google/url')
    state = parse_qs(urlsplit(start.json()['url']).query)['state'][0]
    # Locate the gateway's platform through the injected HTTP transport closure.
    # Use a fresh app with the same browser cookie to model a token response.
    platform = PlatformClient('http://platform/v1/api', 'org', 'service', 'secret',
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'access_token': 'foreign-token'})))
    def reject(token):
        assert token == 'foreign-token'
        raise AppError(403, 'Wrong tenant')
    platform.actor = reject
    other = TestClient(create_app(platform, object()), base_url='https://hrms.newtuple.com')
    other.cookies.update(client.cookies)
    response = other.post('/v1/api/auth/google/callback', json={'code': 'code', 'state': state, 'redirect_uri': REDIRECT})
    assert response.status_code == 403
    assert 'foreign-token' not in response.text

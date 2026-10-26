from types import SimpleNamespace
import json

import pytest
from fastapi.testclient import TestClient

from hrms_app.main import create_app
from hrms_app.platform import Actor
from native_permissions import grants
from hrms_app.uat_mail import enabled


@pytest.fixture
def mailbox(monkeypatch):
    monkeypatch.setenv('HRMS_EMAIL_MODE', 'capture')
    monkeypatch.setenv('HRMS_UAT_INBOX_ENABLED', 'true')
    class Platform:
        org = 'org'
        def records(self, *args):
            return []
        def actor(self, token):
            role = token if token != 'foreign' else 'superadmin'
            org = 'other' if token == 'foreign' else self.org
            return Actor(token, org, token, frozenset({role}), grants({role}, org))
    calls = []
    def fetch(path, params=None):
        calls.append((path, params))
        return b'attachment' if '/part/' in path else json.dumps({'messages': [], 'total': 0}).encode()
    monkeypatch.setattr('hrms_app.uat_mail.fetch', fetch)
    return TestClient(create_app(Platform(), SimpleNamespace())), calls


@pytest.mark.parametrize('role', ['hrms_employee', 'hrms_office_admin', 'foreign'])
def test_denied_users_never_contact_mailpit(mailbox, role):
    client, calls = mailbox
    headers = {'Authorization': 'Bearer ' + role}
    assert client.get('/v1/api/hrms/uat-mail/status', headers=headers).json() == {'enabled': False}
    for path in ('messages', 'messages/test', 'messages/test/attachments/1'):
        assert client.get('/v1/api/hrms/uat-mail/' + path, headers=headers).status_code in {403, 404}
    assert not calls


@pytest.mark.parametrize('mode,flag', [('live', 'true'), ('capture', 'false'), ('', 'true')])
def test_off_switch_and_live_mode_block_existing_links(mailbox, monkeypatch, mode, flag):
    client, calls = mailbox
    monkeypatch.setenv('HRMS_EMAIL_MODE', mode)
    monkeypatch.setenv('HRMS_UAT_INBOX_ENABLED', flag)
    headers = {'Authorization': 'Bearer superadmin'}
    assert client.get('/v1/api/hrms/uat-mail/messages', headers=headers).status_code == 404
    assert not calls


@pytest.mark.parametrize('role', ['superadmin', 'hrms_hr_full'])
def test_hr_can_read_but_never_send_or_delete(mailbox, role):
    client, calls = mailbox
    headers = {'Authorization': 'Bearer ' + role}
    response = client.get('/v1/api/hrms/uat-mail/messages?search=to:test@example.com', headers=headers)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert calls == [('search', {'start': 0, 'limit': 50, 'query': 'to:test@example.com'})]
    assert client.get('/v1/api/hrms/uat-mail/messages/test/attachments/1.2', headers=headers).json()['content'] == 'YXR0YWNobWVudA=='
    for method in ('POST', 'DELETE', 'PUT'):
        assert client.request(method, '/v1/api/hrms/uat-mail/messages', headers=headers).status_code >= 400
    assert client.get('/v1/api/hrms/uat-mail/messages/test/attachments/invalid', headers=headers).status_code == 422


def test_inbox_requires_login(mailbox):
    client, calls = mailbox
    assert client.get('/v1/api/hrms/uat-mail/messages').status_code == 401
    assert not calls


@pytest.mark.parametrize('role', ['superadmin', 'hrms_hr_full'])
def test_inbox_honors_configured_management_permission(monkeypatch, role):
    monkeypatch.setenv('HRMS_EMAIL_MODE', 'capture')
    monkeypatch.setenv('HRMS_UAT_INBOX_ENABLED', 'true')
    permissions = grants({role})
    assert 'tenant.org.hrms.onboarding:review' not in permissions
    actor = Actor('user', 'org', 'HR', frozenset({role}), permissions)
    assert enabled(actor, 'org')
    restricted = permissions - {'tenant.org.hrms.onboarding:manage'}
    assert not enabled(Actor('user', 'org', 'HR', frozenset({role}), restricted), 'org')

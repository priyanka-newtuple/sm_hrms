import pytest

from hrms_app.recover_onboarding_email import recover


class API:
    org = 'org'

    def __init__(self):
        self.sent = []
        self.host = 'mailpit'
        self.status = 'active'

    def call(self, method, path):
        return {'items': [{'provider': 'smtp', 'configured': True, 'config': {'smtp_host': self.host, 'smtp_port': 1025}}]}

    def record(self, eid):
        return {'organization_id': self.org, 'data': {'platform_user_id': 'user', 'work_email': 'test@example.com'}}

    def users(self):
        return [{'id': 'user', 'organization_id': self.org, 'status': self.status, 'auth_type': 'local', 'email': 'test@example.com'}]

    def request(self, method, path, **kwargs):
        self.sent.append((method, path, kwargs))
        return {'message': 'generic response'}


def test_requires_actual_new_capture():
    api = API()
    counts = iter([{'old'}, {'old', 'new'}])
    assert recover(api, {'created_user_id': 'user'}, 'employee', lambda _: next(counts))['new_email_captured']
    assert api.sent[0][:2] == ('POST', '/auth/forgot-password')


def test_generic_success_is_not_delivery(monkeypatch):
    monkeypatch.setattr('hrms_app.recover_onboarding_email.time.sleep', lambda _: None)
    assert not recover(API(), {'created_user_id': 'user'}, 'employee', lambda _: {'old'})['new_email_captured']


@pytest.mark.parametrize('change', ['live_host', 'pending', 'foreign_handoff'])
def test_refuses_unsafe_or_unapproved_recovery(change):
    api = API()
    progress = {'created_user_id': 'user'}
    if change == 'live_host':
        api.host = 'smtp.example.com'
    elif change == 'pending':
        api.status = 'pending'
    else:
        progress['created_user_id'] = 'someone-else'
    with pytest.raises(ValueError):
        recover(api, progress, 'employee', lambda _: set())
    assert not api.sent

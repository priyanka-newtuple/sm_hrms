from types import SimpleNamespace

import httpx
import pytest

from hrms_app.employee_access import google_sign_in_ready, setup_access
from hrms_app.errors import AppError
from hrms_app.onboarding_template import DEFAULT_ONBOARDING_STEPS
from hrms_app.service import HrmsService
from test_employee_access import Journal, Platform, actor

HTTPS_CALLBACK = 'https://hrms.example.com/auth/google/callback'


class OnboardingPlatform(Platform):
    """An active onboarding case for the employee, with the ID step done or not."""

    def __init__(self, id_step_done=True, fail_transition=False):
        super().__init__()
        self.tasks_by_step = {s.sequence: dict(id=f'task-{s.sequence}', stage=f'onboarding-step-{s.sequence}', status='OPEN')
                              for s in DEFAULT_ONBOARDING_STEPS}
        if id_step_done:
            self.tasks_by_step[1]['status'] = 'COMPLETED'
        self.fail_transition = fail_transition
        self.transitions = []

    def records(self, kind, *args):
        if kind == 'HRMS.OnboardingCase':
            return [dict(entity_id='case', data=dict(employee_id='employee'))]
        return super().records(kind, *args)

    def states(self, machine):
        return {'case': 'in_progress'}

    def tasks(self, case_id):
        return list(self.tasks_by_step.values())

    def call(self, method, path, **kwargs):
        if path.endswith('/transitions'):
            if self.fail_transition:
                raise AppError(503, 'Platform unavailable')
            self.transitions.append(kwargs['json']['entity_id'])
            return {}
        return super().call(method, path, **kwargs)


def activate(platform):
    return setup_access(HrmsService(platform, Journal(), 'newtuple.com'), actor('hr', 'hrms_hr_full'), 'employee', 'access-op-1')


def test_activation_completes_the_invite_step_once_the_work_account_exists():
    platform = OnboardingPlatform()
    assert activate(platform)['account_status'] == 'active'
    assert platform.transitions == ['task-3']


def test_activation_leaves_the_invite_step_while_the_work_account_is_missing():
    platform = OnboardingPlatform(id_step_done=False)
    assert activate(platform)['account_status'] == 'active'
    assert platform.transitions == []


def test_a_failed_step_update_never_fails_the_activation():
    assert activate(OnboardingPlatform(fail_transition=True))['account_status'] == 'active'


def google_service(status=200, domain='newtuple.com'):
    http = httpx.Client(base_url='http://platform.test/', transport=httpx.MockTransport(lambda request: httpx.Response(status, json={})))
    return SimpleNamespace(domain=domain, platform=SimpleNamespace(http=http))


@pytest.mark.parametrize(('callback', 'email', 'status', 'ready'), [
    (HTTPS_CALLBACK, 'new@newtuple.com', 200, True),
    ('http://62.238.103.67:8082/auth/google/callback', 'new@newtuple.com', 200, False),  # browser flow needs HTTPS
    (HTTPS_CALLBACK, 'new@gmail.com', 200, False),                                        # not the work domain
    (HTTPS_CALLBACK, 'new@newtuple.com', 503, False),                                     # platform not configured
])
def test_google_sign_in_readiness(monkeypatch, callback, email, status, ready):
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', callback)
    assert google_sign_in_ready(google_service(status), email) is ready


def test_a_google_ready_account_activates_without_an_email_provider(monkeypatch):
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', HTTPS_CALLBACK)
    platform = Platform()
    platform.configured = False  # no email provider
    platform.http = google_service().platform.http
    result = setup_access(HrmsService(platform, Journal(), 'newtuple.com'), actor('hr', 'hrms_hr_full'), 'employee', 'access-op-2')
    assert result['email_status'] == 'not_required' and 'Google' in result['message']
    assert '/auth/forgot-password' not in platform.writes

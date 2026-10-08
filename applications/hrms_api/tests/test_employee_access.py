from copy import deepcopy

import pytest

from hrms_app.employee_access import setup_access
from hrms_app.errors import AppError
from hrms_app.service import HrmsService
from test_performance import Journal, actor


class Platform:
    def __init__(self):
        self.identity = dict(id='user', email='new@newtuple.com', organization_id='org', status='pending', auth_type='password')
        self.employee = dict(entity_id='employee', data=dict(platform_user_id='user', work_email='new@newtuple.com', employment_status='active'))
        self.roles = {'hrms_employee'}
        self.configured = True
        self.writes = []
        self.fail_email = False

    def records(self, *args):
        return [deepcopy(self.employee)]

    def users(self):
        return [deepcopy(self.identity)]

    def call(self, method, path, **kwargs):
        if path.endswith('/roles'):
            return [dict(organization_id='org', role_name=r, role_id=r) for r in self.roles]
        if path.startswith('/integrations/'):
            return dict(organization_id='org', items=[dict(provider='smtp', configured=self.configured)])
        self.writes.append(path)
        if path.endswith('/approve'):
            self.identity['status'] = 'active'
            self.roles.add('viewer')
        elif method == 'DELETE':
            self.roles.remove(path.rsplit('/', 1)[-1])
        else:
            raise AssertionError(path)

    def request(self, method, path, **kwargs):
        assert kwargs['json'] == {'email': self.identity['email']}
        self.writes.append(path)
        if self.fail_email:
            raise AppError(503, 'Timeout')
        return {'message': 'Generic native reset response'}


def system():
    p = Platform()
    return p, HrmsService(p, Journal(), 'newtuple.com')


def test_hr_can_activate_standard_employee_without_settings_and_retries_do_not_send_again():
    p, s = system()
    who = actor('hr', 'hrms_hr_basic')
    result = setup_access(s, who, 'employee', 'operation-1')
    assert result['account_status'] == 'active'
    assert result['email_status'] == 'requested'
    assert p.roles == {'hrms_employee'}
    assert p.writes == ['/users/user/approve', '/roles/users/user/roles/viewer', '/auth/forgot-password']
    assert setup_access(s, who, 'employee', 'operation-1')['idempotent']
    assert p.writes.count('/auth/forgot-password') == 1


@pytest.mark.parametrize('roles', [{'superadmin'}, {'hrms_employee', 'hrms_hr_full'}, {'hrms_project_manager'}, set()])
def test_hr_cannot_activate_privileged_accounts_even_if_employee_role_claims_standard(roles):
    p, s = system()
    p.roles = roles
    with pytest.raises(AppError) as exc:
        setup_access(s, actor('hr', 'hrms_hr_full'), 'employee', 'operation-1')
    assert exc.value.status == 403
    assert not p.writes


@pytest.mark.parametrize('change', [
    {'organization_id': 'other'}, {'email': 'other@newtuple.com'}, {'status': 'suspended'}, {'status': 'rejected'},
])
def test_invalid_account_links_and_disabled_accounts_are_not_activated(change):
    p, s = system()
    p.identity.update(change)
    with pytest.raises(AppError):
        setup_access(s, actor('admin', 'superadmin'), 'employee', 'operation-1')
    assert not p.writes


def test_missing_email_configuration_does_not_activate_account():
    p, s = system()
    p.configured = False
    with pytest.raises(AppError) as exc:
        setup_access(s, actor('hr', 'hrms_hr_basic'), 'employee', 'operation-1')
    assert exc.value.status == 409
    assert not p.writes


def test_email_timeout_keeps_activation_and_retry_does_not_duplicate_email():
    p, s = system()
    p.fail_email = True
    who = actor('hr', 'hrms_hr_basic')
    with pytest.raises(AppError):
        setup_access(s, who, 'employee', 'operation-1')
    with pytest.raises(AppError) as exc:
        setup_access(s, who, 'employee', 'operation-1')
    assert exc.value.status == 409
    assert p.identity['status'] == 'active'
    assert p.writes.count('/auth/forgot-password') == 1


def test_google_account_uses_sso_without_password_email():
    p, s = system()
    p.identity['auth_type'] = 'google'
    p.configured = False
    assert setup_access(s, actor('hr', 'hrms_hr_basic'), 'employee', 'operation-1')['email_status'] == 'not_required'
    assert '/auth/forgot-password' not in p.writes


def test_employee_cannot_activate_accounts():
    p, s = system()
    with pytest.raises(AppError) as exc:
        setup_access(s, actor('employee', 'hrms_employee'), 'employee', 'operation-1')
    assert exc.value.status == 403
    assert not p.writes


class ProvisioningPlatform(Platform):
    def __init__(self, existing=True):
        super().__init__()
        self.has_identity = existing
        self.rows = {}
        self.registered = 0

    def users(self):
        return super().users() if self.has_identity else []

    def records(self, kind, fields):
        return deepcopy([r for r in self.rows.values() if r['kind'] == kind])

    def create_record(self, kind, data, owner):
        key = f'row-{len(self.rows)}'
        row = dict(entity_id=key, kind=kind, data={**data, 'identifier': key})
        self.rows[key] = row
        return deepcopy(row)

    def record(self, key):
        return deepcopy(self.rows[key])

    def enroll(self, *args):
        return 'in_progress'

    def tasks(self, case):
        return [dict(id=r['entity_id'], stage=f"onboarding-step-{r['data']['sequence']}", status='OPEN')
                for r in self.rows.values() if r['kind'] == 'HRMS.OnboardingStep']

    def request(self, method, path, **kwargs):
        assert path == '/auth/register'
        self.registered += 1
        self.has_identity = True
        return dict(organization_id='org', approval_type='pending_org_admin', user_id='user')

    def call(self, method, path, **kwargs):
        if path == '/organizations/current':
            return {'domain': 'newtuple.com'}
        if path == '/roles':
            return [dict(id=r, name=r) for r in ['hrms_employee', 'hrms_project_manager']]
        if path.endswith('/role'):
            self.writes.append(path)
            self.roles = {kwargs['json']['role_id']}
            return
        if path.startswith('/entity-records/'):
            self.rows[path.rsplit('/', 1)[-1]]['data'] = kwargs['json']['data']
            return
        return super().call(method, path, **kwargs)


def employee_request(**values):
    from hrms_app.requests import EmployeeCreateRequest
    return EmployeeCreateRequest(**{**dict(first_name='New', last_name='Employee', work_email='new@newtuple.com',
        department='Engineering', designation='Engineer', date_joined='2026-10-08', idempotency_key='employee-op'), **values})


@pytest.mark.parametrize('existing', [True, False])
def test_creation_links_or_provisions_once_and_starts_onboarding(existing):
    p = ProvisioningPlatform(existing)
    s = HrmsService(p, Journal(), 'newtuple.com')
    who = actor('hr', 'hrms_hr_basic')
    result = s.create_employee(who, employee_request())
    assert result['account_status'] == 'pending'
    assert result['onboarding_task_count'] > 0
    assert p.registered == (0 if existing else 1)
    assert sum(r['kind'] == 'HRMS.Employee' for r in p.rows.values()) == 1
    assert s.create_employee(who, employee_request())['idempotent']
    assert p.registered == (0 if existing else 1)
    if existing:
        assert '/roles/users/user/role' not in p.writes


def test_creation_preserves_active_account_and_rejects_privileged_link_before_employee_write():
    p = ProvisioningPlatform()
    p.identity['status'] = 'active'
    s = HrmsService(p, Journal(), 'newtuple.com')
    p.roles.add('superadmin')
    with pytest.raises(AppError):
        s.create_employee(actor('hr', 'hrms_hr_basic'), employee_request())
    assert not p.rows
    p.roles = {'hrms_employee'}
    result = s.create_employee(actor('hr', 'hrms_hr_basic'), employee_request())
    assert result['account_status'] == 'active'
    assert not p.writes


def test_project_role_requires_superadmin_and_designation_does_not_grant_it():
    p = ProvisioningPlatform(False)
    s = HrmsService(p, Journal(), 'newtuple.com')
    with pytest.raises(AppError):
        s.create_employee(actor('hr', 'hrms_hr_full'), employee_request(role='hrms_project_manager'))
    assert not p.rows
    s.create_employee(actor('admin', 'superadmin'), employee_request(role='hrms_project_manager'))
    assert p.roles == {'hrms_project_manager'}


def test_setup_route_accepts_operation_key_and_authenticates_before_writes():
    from fastapi.testclient import TestClient
    from hrms_app.main import create_app
    p = Platform()
    p.actor = lambda token: actor('hr', 'hrms_hr_basic')
    client = TestClient(create_app(p, Journal()))
    path = '/v1/api/hrms/employees/employee/setup-access'
    assert client.post(path, json={'idempotency_key': 'operation-1'}).status_code == 401
    assert not p.writes
    response = client.post(path, headers={'Authorization': 'Bearer human'}, json={'idempotency_key': 'operation-1'})
    assert response.status_code == 200, response.text
    assert response.json()['email_status'] == 'requested'

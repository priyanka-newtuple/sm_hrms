from employee_form_fixture import ROUTES as EMPLOYEE_FORM_ROUTES
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
        if method == 'GET' and path in EMPLOYEE_FORM_ROUTES:
            return deepcopy(EMPLOYEE_FORM_ROUTES[path])
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
        if path.endswith('/approve'):
            assert 'token' in kwargs
            return self.call(method, path)
        assert kwargs['json'] == {'email': self.identity['email']}
        self.writes.append(path)
        if self.fail_email:
            raise AppError(503, 'Timeout')
        return {'message': 'Generic native reset response'}


def system():
    p = Platform()
    return p, HrmsService(p, Journal(), 'newtuple.com')


def test_superadmin_approves_using_human_token_and_retries_do_not_send_again():
    p, s = system()
    who = actor('admin', 'superadmin')
    result = setup_access(s, who, 'employee', 'operation-1')
    assert result['account_status'] == 'active'
    assert result['email_status'] == 'requested'
    assert p.roles == {'hrms_employee'}
    assert p.writes == ['/users/user/approve', '/roles/users/user/roles/viewer', '/auth/forgot-password']
    assert setup_access(s, who, 'employee', 'operation-1')['idempotent']
    assert p.writes.count('/auth/forgot-password') == 1


@pytest.mark.parametrize('roles', [{'hrms_employee'}, {'superadmin'}, {'hrms_employee','hrms_hr_full'}, {'hrms_project_manager'}])
def test_hr_full_approves_all_native_employee_roles(roles):
    p,s=system();p.roles=roles
    assert setup_access(s,actor('hr','hrms_hr_full'),'employee','operation-1')['account_status']=='active'
    assert p.roles==roles


def test_roleless_account_requires_reconciliation():
    p,s=system();p.roles=set()
    with pytest.raises(AppError): setup_access(s,actor('hr','hrms_hr_full'),'employee','operation-1')
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
        setup_access(s, actor('admin', 'superadmin'), 'employee', 'operation-1')
    assert exc.value.status == 409
    assert not p.writes


def test_email_timeout_keeps_activation_and_retry_does_not_duplicate_email():
    p, s = system()
    p.fail_email = True
    who = actor('admin', 'superadmin')
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
    assert setup_access(s, actor('admin', 'superadmin'), 'employee', 'operation-1')['email_status'] == 'not_required'
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
        self.workflows = [dict(entity_type='HRMS.Employee', is_active=True, machine_name='configured_employee', definition={})]
        self.enrollments = {}
        self.enroll_calls = 0
        self.fail_enroll = False

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

    def states(self, machine):
        return {key: state for (key, name), state in self.enrollments.items() if name == machine}

    def enroll(self, key, machine):
        assert self.rows[key]['data']['platform_user_id'] == 'user'
        self.enroll_calls += 1
        self.enrollments[key, machine] = 'Employee Registration'
        if self.fail_enroll:
            raise AppError(503, 'Response lost after enrollment')
        return 'Employee Registration'

    def tasks(self, case):
        return self.steps_by_case().get(case, [])

    def steps_by_case(self):
        grouped = {}
        for r in self.rows.values():
            if r['kind'] == 'HRMS.OnboardingStep':
                grouped.setdefault(r['data'].get('case_id'), []).append(dict(
                    id=r['entity_id'], stage=f"onboarding-step-{r['data']['sequence']}", status='OPEN',
                    assigned_to=r['data'].get('assigned_to')))
        return grouped

    def request(self, method, path, **kwargs):
        assert path == '/auth/register'
        self.registered += 1
        self.has_identity = True
        return dict(organization_id='org', approval_type='pending_org_admin', user_id='user')

    def call(self, method, path, **kwargs):
        if path == '/workflow-state-machines':
            return {'published_items': deepcopy(self.workflows)}
        if method == 'GET' and path in EMPLOYEE_FORM_ROUTES:
            return deepcopy(EMPLOYEE_FORM_ROUTES[path])
        if path == '/organizations/current':
            return {'domain': 'newtuple.com'}
        if path == '/roles':
            return [dict(id=r, name=r, display_name=r) for r in ['hrms_employee', 'hrms_project_manager']]
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


def test_registration_without_email_creates_only_employee_and_enrollment(monkeypatch):
    from hrms_app import form_config
    fields = [{'field': key, 'type': 'string'} for key in ['first_name', 'last_name', 'department', 'designation', 'hrms_role']]
    fields.append({'field': 'date_joined', 'type': 'datetime'})
    monkeypatch.setattr(form_config, 'registration_form', lambda p: {'fields': fields})
    p = ProvisioningPlatform(False)
    def enroll(eid, machine):
        p.enroll_calls += 1
        p.enrollments[eid, machine] = 'Employee Registration'
        return 'Employee Registration'
    p.enroll = enroll
    s = HrmsService(p, Journal(), 'newtuple.com')
    who = actor('admin', 'superadmin')
    req = employee_request(work_email=None)
    result = s.create_employee(who, req)
    assert result['account_status'] == 'not_created'
    assert p.registered == 0 and p.enroll_calls == 1
    assert 'work_email' not in next(iter(p.rows.values()))['data']
    assert s.create_employee(who, req)['idempotent']
    assert p.enroll_calls == 1


@pytest.mark.parametrize('existing', [True, False])
def test_creation_links_or_provisions_once_without_custom_onboarding(existing):
    p = ProvisioningPlatform(existing)
    s = HrmsService(p, Journal(), 'newtuple.com')
    who = actor('admin', 'superadmin')
    result = s.create_employee(who, employee_request())
    assert result['account_status'] == 'pending'
    assert not any(r['kind'] in {'HRMS.OnboardingCase', 'HRMS.OnboardingStep'} for r in p.rows.values())
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


def test_hr_can_propose_native_role_but_account_stays_pending():
    p = ProvisioningPlatform(False)
    s = HrmsService(p, Journal(), 'newtuple.com')
    s.create_employee(actor('hr', 'hrms_hr_full'), employee_request(role='hrms_project_manager'))
    assert p.roles == {'hrms_project_manager'}
    assert p.identity['status'] == 'pending'
    assert not any(path.endswith('/approve') for path in p.writes)


def test_roles_come_from_native_catalog_and_unknown_or_service_role_is_rejected():
    p = ProvisioningPlatform(False)
    original = p.call
    def call(method, path, **kwargs):
        if path == '/roles':
            return [{'id': 'custom', 'name': 'delivery_lead', 'display_name': 'Delivery Lead'},
                    {'id': 'svc', 'name': 'hrms_application_service', 'display_name': 'Internal service'}]
        return original(method, path, **kwargs)
    p.call = call
    s = HrmsService(p, Journal(), 'newtuple.com')
    options = s.form_options(actor('hr', 'hrms_hr_basic'))
    assert options['roles'] == ['delivery_lead']
    assert options['role_labels'] == {'delivery_lead': 'Delivery Lead'}
    for role in ['hrms_application_service', 'deleted_role']:
        with pytest.raises(AppError) as exc:
            s.create_employee(actor('hr', 'hrms_hr_basic'), employee_request(role=role))
        assert exc.value.status == 403
    assert not p.rows


def test_setup_route_accepts_operation_key_and_authenticates_before_writes():
    from fastapi.testclient import TestClient
    from hrms_app.main import create_app
    p = Platform()
    p.actor = lambda token: actor('admin', 'superadmin')
    client = TestClient(create_app(p, Journal()))
    path = '/v1/api/hrms/employees/employee/setup-access'
    assert client.post(path, json={'idempotency_key': 'operation-1'}).status_code == 401
    assert not p.writes
    response = client.post(path, headers={'Authorization': 'Bearer human'}, json={'idempotency_key': 'operation-1'})
    assert response.status_code == 200, response.text
    assert response.json()['email_status'] == 'requested'


def test_local_activation_skips_setup_email(monkeypatch):
    monkeypatch.setenv('HRMS_LOCAL_DISABLE_EMAIL', 'true')
    monkeypatch.setenv('HRMS_ORGANIZATION_ID', '11111111-1111-1111-1111-111111111111')
    monkeypatch.setenv('PLATFORM_API_URL', 'http://platform-api:8000/v1/api')
    p, s = system()
    p.configured = False
    result = setup_access(s, actor('admin', 'superadmin'), 'employee', 'local-test')
    assert result['account_status'] == 'active'
    assert result['email_status'] == 'disabled_local'
    assert '/auth/forgot-password' not in p.writes


def test_local_email_switch_does_not_disable_other_tenants(monkeypatch):
    monkeypatch.setenv('HRMS_LOCAL_DISABLE_EMAIL', 'true')
    monkeypatch.setenv('HRMS_ORGANIZATION_ID', 'production-tenant')
    p, s = system()
    result = setup_access(s, actor('admin', 'superadmin'), 'employee', 'production-test')
    assert result['email_status'] == 'requested'
    assert '/auth/forgot-password' in p.writes


def test_pending_user_inbox_supports_hr_full_and_superadmin_with_native_human_session():
    from fastapi.testclient import TestClient
    from hrms_app.main import create_app
    p = Platform()
    p.actor = lambda token: actor('hr', 'hrms_hr_full')
    calls = []
    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return [dict(id='pending', full_name='New Hire', email='new@newtuple.com',
                     organization_id='org', status='pending'),
                dict(id='other', full_name='Other Tenant', email='other@example.com',
                     organization_id='other', status='pending'),
                dict(id='active', full_name='Active User', email='active@newtuple.com',
                     organization_id='org', status='active')]
    p.request = request
    client = TestClient(create_app(p, Journal()))
    url = '/v1/api/hrms/user-approvals'
    assert client.get(url).status_code == 401
    assert client.get(url, headers={'Authorization': 'Bearer human'}).status_code == 200
    calls.clear()
    from dataclasses import replace
    p.actor = lambda token: replace(actor('admin', 'superadmin'), token=token)
    response = client.get(url, headers={'Authorization': 'Bearer human'})
    assert response.status_code == 200
    assert response.json() == [{'id': 'pending', 'full_name': 'New Hire', 'email': 'new@newtuple.com'}]
    assert calls == [('GET', '/users/pending', {'token': 'human'})]


@pytest.mark.parametrize('workflows', [[], [dict(entity_type='HRMS.Employee', is_active=False)],
    [dict(entity_type='HRMS.Employee', is_active=True)] * 2])
def test_employee_requires_one_published_active_workflow_before_writes(workflows):
    p = ProvisioningPlatform(False)
    p.workflows = workflows
    with pytest.raises(AppError) as exc:
        HrmsService(p, Journal(), 'newtuple.com').create_employee(actor('admin', 'superadmin'), employee_request())
    assert exc.value.status == 409
    assert not p.rows and not p.registered


def test_employee_enrollment_retry_reconciles_without_repeating_initial_actions():
    p = ProvisioningPlatform(False)
    p.fail_enroll = True
    service = HrmsService(p, Journal(), 'newtuple.com')
    who = actor('admin', 'superadmin')
    with pytest.raises(AppError):
        service.create_employee(who, employee_request())
    p.workflows[0]['machine_name'] = 'replacement_workflow'
    result = service.create_employee(who, employee_request())
    assert result['workflow'] == dict(machine_name='configured_employee', current_state='Employee Registration')
    assert p.enroll_calls == 1 and p.registered == 1
    assert service.create_employee(who, employee_request())['idempotent']
    assert p.enroll_calls == 1


def test_uncertain_employee_enrollment_is_not_reissued_without_evidence():
    p = ProvisioningPlatform(False)
    p.fail_enroll = True
    service = HrmsService(p, Journal(), 'newtuple.com')
    who = actor('admin', 'superadmin')
    with pytest.raises(AppError):
        service.create_employee(who, employee_request())
    p.enrollments.clear()
    with pytest.raises(AppError) as exc:
        service.create_employee(who, employee_request())
    assert exc.value.status == 409
    assert p.enroll_calls == 1 and p.registered == 1

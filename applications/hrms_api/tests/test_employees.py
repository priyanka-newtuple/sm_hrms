from employee_form_fixture import ROUTES as EMPLOYEE_FORM_ROUTES
from native_permissions import grants
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from hrms_app.errors import AppError
from hrms_app.platform import Actor
from hrms_app.policy import capabilities
from hrms_app.requests import EmployeeExitRequest, EmployeeUpdateRequest
from hrms_app.service import HrmsService, LeaveApprovers
from test_onboarding import Journal as OnboardingJournal
from test_onboarding import Platform as OnboardingPlatform

TODAY = date.today()


def actor(user_id, role):
    return Actor(user_id, 'org', 'human', frozenset({role}), grants({role}))


class DirectoryPlatform:
    """One employee created as a standard employee whose account was later made Finance in Settings."""
    org = 'org'

    def records(self, kind, fields):
        if kind != 'HRMS.Employee':
            return []
        return [dict(entity_id='e1', data=dict(first_name='Fin', last_name='Person', employee_code='E1',
                                               work_email='fin@newtuple.com', employment_status='active',
                                               platform_user_id='u1', hrms_role='hrms_employee'))]

    def users(self):
        return [dict(id='u1', role='hrms_finance', status='active', auth_type='local', organization_id='org')]

    def request(self, method, path, **kwargs):
        assert method == 'GET' and path == '/workflow-enrollments'
        assert kwargs['token'] == 'human'
        return {'items': [dict(entity_id='e1', organization_id='org', entity_type='HRMS.Employee',
                               current_state='Email Setup', transition_options=[])], 'has_more': False}

    def states(self, machine):
        return {}

    def call(self, method, path, **kwargs):
        if method == 'GET' and path in EMPLOYEE_FORM_ROUTES:
            return deepcopy(EMPLOYEE_FORM_ROUTES[path])
        if path == '/roles':
            return [dict(name=r, display_name=r) for r in ['hrms_employee', 'hrms_office_admin', 'hrms_finance']]
        assert path == '/roles/users/u1/roles'
        return [dict(role_name='hrms_finance', organization_id='org')]


def test_hr_who_assigns_roles_can_add_office_admin_and_finance_staff():
    service = HrmsService(DirectoryPlatform(), None, 'newtuple.com')
    assert {'hrms_office_admin', 'hrms_finance'} <= set(service.form_options(actor('hr', 'hrms_hr_full'))['roles'])
    assert service.form_options(actor('hr', 'hrms_hr_basic'))['roles'] == ['hrms_employee', 'hrms_office_admin', 'hrms_finance']


def test_the_directory_shows_the_accounts_current_role():
    rows = HrmsService(DirectoryPlatform(), None, 'newtuple.com').directory(actor('hr', 'hrms_hr_full'))
    assert [(r['entity_id'], r['role']) for r in rows] == [('e1', 'hrms_finance')]
    assert rows[0]['onboarding_state'] == 'Email Setup'


def test_onboarding_cases_need_onboarding_view_not_directory_read():
    service = HrmsService(OnboardingPlatform(), OnboardingJournal(), 'newtuple.com')
    assert service.onboarding(actor('viewer-user', 'viewer')) == []        # viewer reads the directory only
    assert len(service.onboarding(actor('hr-user', 'hrms_hr_basic'))) == 1
    assert len(service.onboarding(actor('owner', 'hrms_employee'))) == 1   # a step owner still sees their case


def test_only_superadmin_has_account_activation():
    caps = capabilities(actor('admin-user', 'admin'))
    assert 'employee:create' in caps
    assert 'employee:activate' not in caps
    assert 'employee:activate' in capabilities(actor('super', 'superadmin'))



class Journal:
    def __init__(self):
        self.ops, self.audits = {}, []

    @contextmanager
    def lock(self, org):
        yield self

    def operation(self, db, who, key, payload):
        op = self.ops.setdefault(key, SimpleNamespace(result=None, progress={}))
        op.checkpoint = lambda **kw: op.progress.update(kw)
        op.finish = lambda result: setattr(op, 'result', result)
        return op

    def audit(self, db, who, event, target):
        self.audits.append(event)


class StaffPlatform:
    """boss <- lead <- dev; dev has a login with the given roles."""

    def __init__(self, dev_roles=('hrms_employee',)):
        def person(key, code, manager=None, **extra):
            return dict(entity_id=key, data=dict(first_name=key.title(), last_name='Person', employee_code=code,
                                                 reports_to_employee_code=manager, employment_status='active',
                                                 platform_user_id=f'{key}-user', department='Engineering',
                                                 designation='Engineer', date_joined='2026-01-05', **extra))
        self.rows = {r['entity_id']: r for r in (person('boss', 'B1'), person('lead', 'L1', 'B1'), person('dev', 'D1', 'L1'))}
        self.status = {f'{k}-user': 'active' for k in self.rows}
        self.dev_roles = dev_roles
        self.writes = []

    def records(self, kind, fields):
        return deepcopy(list(self.rows.values())) if kind == 'HRMS.Employee' else []

    def record(self, key):
        return deepcopy(self.rows[key])

    def users(self):
        return [dict(id=u, status=s, role='hrms_employee', organization_id='org') for u, s in self.status.items()]

    def states(self, machine):
        return {}

    def call(self, method, path, **kwargs):
        if method == 'GET' and path in EMPLOYEE_FORM_ROUTES:
            return deepcopy(EMPLOYEE_FORM_ROUTES[path])
        if path == '/roles':
            return [dict(name='hrms_employee', display_name='Employee')]
        if path.startswith('/roles/users/'):
            return [dict(role_name=r, organization_id='org') for r in self.dev_roles]
        self.writes.append((method, path))
        if method == 'PUT' and path.startswith('/entity-records/'):
            self.rows[path.rsplit('/', 1)[-1]]['data'] = kwargs['json']['data']
        elif path.endswith('/suspend'):
            if self.status[path.split('/')[2]] == 'suspended':
                raise AppError(400, 'User is not an active member of this organization')
            self.status[path.split('/')[2]] = 'suspended'
        elif path.endswith('/reject'):
            self.status[path.split('/')[2]] = 'rejected'


def hr(role='hrms_hr_full'):
    return actor('hr-user', role)


def service(platform):
    return HrmsService(platform, Journal(), 'newtuple.com')


def update(**values):
    return EmployeeUpdateRequest(**{**dict(first_name='Dev', last_name='Renamed', department='Engineering', designation='Engineer',
                                           reports_to_entity_id='lead', date_joined='2026-01-05', idempotency_key='update-0001'), **values})


def exit_request(days_from_today, **values):
    return EmployeeExitRequest(**{**dict(last_working_day=(TODAY + timedelta(days=days_from_today)).isoformat(),
                                         reason='resignation', idempotency_key='exit-0001'), **values})


def test_hr_can_correct_an_employees_details():
    platform = StaffPlatform()
    result = service(platform).update_employee(hr(), 'dev', update(work_location='Pune', phone='+91 90000 00000'))
    assert result['full_name'] == 'Dev Renamed' and result['reports_to_name'] == 'Lead Person'
    saved = platform.rows['dev']['data']
    assert (saved['work_location'], saved['phone'], saved['reports_to_employee_code']) == ('Pune', '+91 90000 00000', 'L1')


@pytest.mark.parametrize('manager', ['dev', 'unknown'])
def test_an_employee_cannot_report_to_themselves_or_an_unknown_manager(manager):
    with pytest.raises(AppError) as error:
        service(StaffPlatform()).update_employee(hr(), 'dev', update(reports_to_entity_id=manager))
    assert error.value.status == 400


def test_reporting_lines_cannot_loop():
    # boss -> lead -> dev: making boss report to dev would close a loop.
    with pytest.raises(AppError) as error:
        service(StaffPlatform()).update_employee(hr(), 'boss', update(reports_to_entity_id='dev'))
    assert 'reports to them' in error.value.detail


def test_a_department_no_longer_offered_can_be_kept_but_not_newly_chosen():
    platform = StaffPlatform()
    platform.rows['dev']['data']['department'] = 'Retired team'
    assert service(platform).update_employee(hr(), 'dev', update(department='Retired team'))
    with pytest.raises(AppError):
        service(platform).update_employee(hr(), 'dev', update(department='Made up', idempotency_key='update-0002'))


def test_employees_cannot_edit_records():
    with pytest.raises(AppError) as error:
        service(StaffPlatform()).update_employee(actor('dev-user', 'hrms_employee'), 'dev', update())
    assert error.value.status == 403


def test_a_future_last_working_day_puts_the_employee_on_notice():
    platform = StaffPlatform()
    result = service(platform).exit_employee(hr(), 'dev', exit_request(30))
    assert result['employment_status'] == 'active' and result['on_notice'] and result['exit_reason'] == 'resignation'
    assert platform.status['dev-user'] == 'active' and ('POST', '/users/dev-user/suspend') not in platform.writes


@pytest.mark.parametrize('days', [0, -3])
def test_on_or_after_the_last_working_day_the_employee_is_offboarded_and_signed_out(days):
    platform = StaffPlatform()
    result = service(platform).exit_employee(hr(), 'dev', exit_request(days))
    assert result['employment_status'] == 'offboarded' and not result['on_notice']
    assert platform.status['dev-user'] == 'suspended'
    with pytest.raises(AppError) as error:  # leavers' records are kept, not changed
        service(platform).update_employee(hr(), 'dev', update(idempotency_key='update-after-exit'))
    assert error.value.status == 409


def test_a_resignation_can_be_withdrawn_during_notice():
    platform = StaffPlatform()
    service(platform).exit_employee(hr(), 'dev', exit_request(30))
    result = service(platform).withdraw_exit(hr(), 'dev', 'withdraw-0001')
    assert not result['on_notice'] and result['last_working_day'] is None


def test_exits_of_privileged_accounts_need_super_admin():
    with pytest.raises(AppError) as error:
        service(StaffPlatform(dev_roles=('hrms_hr_full',))).exit_employee(hr(), 'dev', exit_request(0))
    assert error.value.status == 403


def test_the_last_working_day_cannot_precede_joining():
    with pytest.raises(AppError) as error:
        service(StaffPlatform()).exit_employee(hr(), 'dev', exit_request(0, last_working_day='2025-12-31'))
    assert 'joining date' in error.value.detail


def test_a_leaver_no_longer_approves_anyones_leave():
    platform = StaffPlatform()
    platform.rows['lead']['data']['employment_status'] = 'offboarded'
    employees = platform.records('HRMS.Employee', [])
    approvers = LeaveApprovers(SimpleNamespace(states=lambda m: {}, records=lambda k, f: [], users=lambda: []), employees)
    assert approvers(platform.rows['dev'], '2044-03-07', '2044-03-08') == set()


def test_completing_a_notice_period_keeps_the_resignation_note():
    platform = StaffPlatform()
    service(platform).exit_employee(hr(), 'dev', exit_request(30, note='Moving cities'))
    day = platform.rows['dev']['data']['last_working_day']
    platform.rows['dev']['data']['last_working_day'] = (TODAY - timedelta(days=1)).isoformat()  # notice ran out
    result = service(platform).exit_employee(hr(), 'dev', exit_request(-1, idempotency_key='exit-0002'))
    assert day and result['employment_status'] == 'offboarded'
    assert platform.rows['dev']['data']['exit_note'] == 'Moving cities'


def test_hr_basic_cannot_record_exits():
    with pytest.raises(AppError) as error:
        service(StaffPlatform()).exit_employee(hr('hrms_hr_basic'), 'dev', exit_request(30))
    assert error.value.status == 403


def test_an_invite_never_activated_is_rejected_when_the_hire_leaves():
    platform = StaffPlatform()
    platform.status['dev-user'] = 'pending'
    service(platform).exit_employee(hr(), 'dev', exit_request(0))
    assert platform.status['dev-user'] == 'rejected'
    assert [p for _, p in platform.writes if p.startswith('/users/')] == ['/users/dev-user/suspend', '/users/dev-user/reject']


def test_an_interrupted_offboarding_can_be_retried():
    platform = StaffPlatform()
    hrms = service(platform)
    original = platform.call

    def fail_after_suspend(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if path.endswith('/suspend'):
            raise AppError(503, 'Platform unavailable')
        return result
    platform.call = fail_after_suspend
    with pytest.raises(AppError):
        hrms.exit_employee(hr(), 'dev', exit_request(0))
    platform.call = original
    assert hrms.exit_employee(hr(), 'dev', exit_request(0))['employment_status'] == 'offboarded'


def test_a_hire_who_never_joined_is_offboarded_straight_away():
    platform = StaffPlatform()
    platform.rows['dev']['data']['date_joined'] = (TODAY + timedelta(days=14)).isoformat()  # due to join in two weeks
    result = service(platform).exit_employee(hr(), 'dev', exit_request(0, reason='did_not_join'))
    assert result['employment_status'] == 'offboarded' and platform.status['dev-user'] == 'suspended'


@pytest.mark.parametrize('status', [403, 502])
def test_directory_workflow_errors_are_not_shown_as_not_started(status):
    platform = DirectoryPlatform()
    def fail(*args, **kwargs):
        raise AppError(status, 'Workflow lookup failed')
    platform.request = fail
    service = HrmsService(platform, None, 'newtuple.com')
    if status == 403:
        item = service.directory(actor('hr', 'hrms_hr_full'))[0]
        assert item['onboarding_state'] is None
        assert item['onboarding_status_message'] == 'Workflow access restricted'
    else:
        with pytest.raises(AppError):
            service.directory(actor('hr', 'hrms_hr_full'))

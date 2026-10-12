from native_permissions import grants
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from hrms_app.catalog import pack_by_type
from hrms_app.errors import AppError
from hrms_app.platform import Actor
from hrms_app.requests import LeaveCreateRequest
from hrms_app.service import HrmsService, LeaveApprovers, leave_days
from hrms_app.wfh import WfhService
from test_performance import UNMIGRATED_TENANT

LEAVE_START, LEAVE_END = '2044-03-07', '2044-03-08'


def actor(user_id, role):
    return Actor(user_id, 'org', 'human', frozenset({role}), grants({role}))


def person(key, code, manager=None):
    return dict(entity_id=key, data=dict(platform_user_id=f'{key}-user', employee_code=code,
                                         reports_to_employee_code=manager, first_name=key.title(), last_name='Person'))


class Platform:
    """`boss` manages `lead`, who manages `dev`. Projects P1 and P2 are run by `pm1` and `pm2`."""

    def __init__(self, state='pending', allocations=(), people=None, start=LEAVE_START, old_workflow=False):
        self.state, self.start, self.old_workflow = state, start, old_workflow
        self.form_fields = [{'field': 'leave_type', 'type': 'enum', 'enum_values': ['annual', 'sick', 'casual', 'unpaid', 'other']},
                            {'field': 'reason', 'type': 'text'}]
        self.people = people or [person('boss', 'B1'), person('lead', 'L1', 'B1'), person('dev', 'D1', 'L1'),
                                 person('pm1', 'P1'), person('pm2', 'P2')]
        self.allocations = list(allocations)  # (employee, project, start, end, state)
        self.leave = []
        self.accounts = []

    def users(self):
        return self.accounts

    def records(self, kind, fields):
        if kind == 'HRMS.Allocation':
            return [dict(entity_id=f'alloc-{i}', data=dict(employee_id=e, project_id=p, start_date=s, end_date=t))
                    for i, (e, p, s, t, _) in enumerate(self.allocations)]
        if kind == 'HRMS.Project':
            return [dict(entity_id='P1', data=dict(pm_id='pm1-user')), dict(entity_id='P2', data=dict(pm_id='pm2-user')),
                    dict(entity_id='OWN', data=dict(pm_id='dev-user'))]
        if kind == 'HRMS.LeaveRequest':
            return self.leave
        return self.people

    def record(self, entity_id):
        employee = entity_id.removesuffix('-leave')
        return dict(entity_id=entity_id, entity_type_id='leave-type',
                    data=dict(employee_id=employee, start_date=self.start, end_date=LEAVE_END))

    def call(self, method, path, **kwargs):
        assert method == 'GET'
        if path in UNMIGRATED_TENANT:  # the leave form is read from the legacy Form below
            return UNMIGRATED_TENANT[path]
        if path == '/forms/config':
            return {'items': [{'schema_key': pack_by_type('HRMS.LeaveRequest').schema_key, 'name': 'Leave',
                               'fields': self.form_fields}]}
        if path.endswith('/transitions/available'):
            steps = {'pending': [{'trigger': 'approve', 'to_state': 'approved'}, {'trigger': 'reject', 'to_state': 'rejected'},
                                 {'trigger': 'cancel', 'to_state': 'cancelled'}],
                     'approved': [] if self.old_workflow else [{'trigger': 'cancel', 'to_state': 'cancelled'}]}
            return {'current_state': self.state, 'available_transitions': steps.get(self.state, [])}
        assert path == '/entity-types/HRMS.LeaveRequest'
        return {'entity_type_id': 'leave-type'}

    def states(self, machine):
        if machine == 'hrms_allocation':
            return {f'alloc-{i}': state for i, (*_, state) in enumerate(self.allocations)}
        return {f'{p["entity_id"]}-leave': self.state for p in self.people}


def triggers(platform, who, leave, role='hrms_employee'):
    result = HrmsService(platform, None, 'example.com').leave_actions(actor(who, role), f'{leave}-leave')
    return [t['trigger'] for t in result['available_transitions']]


def denied(platform, who, leave):
    with pytest.raises(AppError) as error:
        triggers(platform, who, leave)
    return error.value.status == 404


def on(project, state='active', start='2044-01-01', end='2044-12-31', employee='dev'):
    return (employee, project, start, end, state)


def test_the_project_manager_decides_leave_over_the_project():
    platform = Platform(allocations=[on('P1')])
    assert triggers(platform, 'pm1-user', 'dev') == ['approve', 'reject']
    assert denied(platform, 'lead-user', 'dev')  # the reporting manager is not the approver now


def test_any_project_manager_of_the_employee_decides():
    platform = Platform(allocations=[on('P1'), on('P2', state='planned')])
    assert triggers(platform, 'pm1-user', 'dev') == ['approve', 'reject']
    assert triggers(platform, 'pm2-user', 'dev') == ['approve', 'reject']


@pytest.mark.parametrize('allocation', [
    on('P1', start='2044-04-01'),        # starts after the leave
    on('P1', end='2044-03-06'),          # ended before the leave
    on('P1', state='cancelled'),
    on('P1', state='completed'),
    on('P1', employee='lead'),           # someone else's allocation
    on('OWN'),                           # the employee manages that project themself
])
def test_without_a_project_manager_for_the_dates_the_reporting_manager_decides(allocation):
    platform = Platform(allocations=[allocation])
    assert triggers(platform, 'lead-user', 'dev') == ['approve', 'reject']
    assert denied(platform, 'pm1-user', 'dev')


@pytest.mark.parametrize('role', ['hrms_manager', 'hrms_delivery_manager', 'superadmin', 'admin',
                                  'hrms_hr_full', 'hrms_project_manager', 'hrms_finance', 'hrms_employee'])
def test_approvers_decide_whatever_their_role(role):
    assert triggers(Platform(allocations=[on('P1')]), 'pm1-user', 'dev', role) == ['approve', 'reject']
    assert triggers(Platform(), 'lead-user', 'dev', role) == ['approve', 'reject']


def test_the_employee_can_only_cancel_their_own_pending_leave():
    assert triggers(Platform(), 'dev-user', 'dev') == ['cancel']


def test_the_managers_manager_cannot_see_or_decide():
    assert denied(Platform(), 'boss-user', 'dev')


@pytest.mark.parametrize('state', ['approved', 'rejected', 'cancelled'])
def test_decided_leave_offers_the_approver_no_actions(state):
    assert triggers(Platform(state), 'lead-user', 'dev') == []


def test_the_employee_can_cancel_approved_leave_until_it_starts():
    assert triggers(Platform('approved'), 'dev-user', 'dev') == ['cancel']
    today = date.today().isoformat()
    assert triggers(Platform('approved', start=today), 'dev-user', 'dev') == []
    assert triggers(Platform('approved', start='2020-01-06'), 'dev-user', 'dev') == []


def test_leave_approved_on_a_workflow_without_the_cancel_step_is_not_offered_cancel():
    # Enrollments keep the workflow version they started on; a broken button is worse than none.
    assert triggers(Platform('approved', old_workflow=True), 'dev-user', 'dev') == []


@pytest.mark.parametrize('state', ['rejected', 'cancelled'])
def test_finished_leave_cannot_be_cancelled(state):
    assert triggers(Platform(state), 'dev-user', 'dev') == []


def test_the_leave_workflow_lets_approved_leave_be_cancelled():
    pack = pack_by_type('HRMS.LeaveRequest')
    assert ('approved', 'cancel', 'cancelled') in pack.transitions
    assert 'approved' not in pack.terminal_states


def test_approvals_list_follows_the_approver(monkeypatch):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self, *args: set())
    monkeypatch.setattr(WfhService, 'holiday_calendars', lambda self: [])
    platform = Platform(allocations=[on('P1')])
    platform.leave = [dict(entity_id='dev-leave', data=dict(employee_id='dev', start_date=LEAVE_START,
                                                            end_date=LEAVE_END, leave_type='annual'))]
    service = HrmsService(platform, None, 'example.com')
    approvals = service.leave(actor('pm1-user', 'hrms_project_manager'), 'approvals', 100, 0)
    assert [r['entity_id'] for r in approvals] == ['dev-leave']
    assert service.leave(actor('lead-user', 'hrms_manager'), 'approvals', 100, 0) == []


# 2044-03-04 is a Friday; 03-05/06 the weekend; 03-07 a Monday.
@pytest.mark.parametrize(('start', 'end', 'holidays', 'days'), [
    ('2044-03-04', '2044-03-07', set(), 2),             # Friday to Monday skips the weekend
    ('2044-03-05', '2044-03-06', set(), 0),             # weekend only
    ('2044-03-07', '2044-03-11', {'2044-03-09'}, 4),    # a published holiday mid-week
    ('2044-03-07', '2044-03-07', set(), 1),
])
def test_leave_counts_working_days_only(start, end, holidays, days):
    assert leave_days(start, end, holidays) == days


class Journal:
    def __init__(self):
        self.ops = {}

    @contextmanager
    def lock(self, org):
        yield self

    def operation(self, db, who, key, payload):
        return self.ops.setdefault(key, SimpleNamespace(result=None))


def create(platform, start, end, monkeypatch, holidays=frozenset(), leave_type='annual', reason=None):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self, *args: set(holidays))
    monkeypatch.setattr(WfhService, 'holiday_calendars', lambda self: [])
    request = LeaveCreateRequest(start_date=start, end_date=end, leave_type=leave_type, reason=reason,
                                 idempotency_key='create-0001')
    with pytest.raises(AppError) as error:
        HrmsService(platform, Journal(), 'example.com').create_leave(actor('dev-user', 'hrms_employee'), request)
    return error.value


@pytest.mark.parametrize(('start', 'end'), [('2044-03-05', '2044-03-06'), ('2044-03-09', '2044-03-09')])
def test_leave_on_weekends_or_holidays_only_is_refused(monkeypatch, start, end):
    error = create(Platform(), start, end, monkeypatch, {'2044-03-09'})
    assert error.status == 422 and 'working day' in error.detail


def test_leave_nobody_can_approve_is_refused(monkeypatch):
    error = create(Platform(people=[person('dev', 'D1')]), LEAVE_START, LEAVE_END, monkeypatch)
    assert error.status == 400 and 'Nobody can approve' in error.detail


def test_hr_full_decides_leave_for_someone_nobody_manages():
    platform = Platform(people=[person('ceo', 'C1'), person('hr', 'H1')])
    platform.accounts = [dict(id='hr-user', role='hrms_hr_full', status='active'),
                         dict(id='ceo-user', role='hrms_hr_full', status='active'),   # not their own leave
                         dict(id='old-hr', role='hrms_hr_full', status='suspended')]
    employees = platform.records('HRMS.Employee', [])
    ceo = next(e for e in employees if e['entity_id'] == 'ceo')
    assert LeaveApprovers(platform, employees)(ceo, LEAVE_START, LEAVE_END) == {'hr-user'}


def test_leave_lists_carry_their_working_days(monkeypatch):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self, *args: set())
    monkeypatch.setattr(WfhService, 'holiday_calendars', lambda self: [])
    platform = Platform()
    platform.leave = [dict(entity_id='dev-leave', data=dict(employee_id='dev', start_date='2044-03-04',
                                                            end_date='2044-03-07', leave_type='annual'))]
    rows = HrmsService(platform, Journal(), 'example.com').leave(actor('dev-user', 'hrms_employee'), 'mine', 100, 0)
    assert [(r['entity_id'], r['days']) for r in rows] == [('dev-leave', 2)]


def test_self_service_needs_exactly_one_linked_employee_profile():
    linked = HrmsService(Platform(), None, 'example.com')
    assert linked.has_employee_profile(actor('dev-user', 'hrms_employee'))
    assert not linked.has_employee_profile(actor('bootstrap-admin', 'superadmin'))
    twice = Platform(people=[person('dev', 'D1'), {**person('dev', 'D2'), 'entity_id': 'dev-copy'}])
    assert not HrmsService(twice, None, 'example.com').has_employee_profile(actor('dev-user', 'hrms_employee'))


def test_a_reason_required_in_settings_is_required_by_the_server(monkeypatch):
    platform = Platform()
    platform.form_fields[1]['required'] = True
    error = create(platform, LEAVE_START, LEAVE_END, monkeypatch)
    assert error.status == 422 and 'Reason is required' in error.detail


def test_a_leave_type_removed_in_settings_is_refused(monkeypatch):
    platform = Platform()
    platform.form_fields[0]['enum_values'] = ['sick', 'casual']
    error = create(platform, LEAVE_START, LEAVE_END, monkeypatch, leave_type='annual')
    assert error.status == 422 and 'configured options' in error.detail


def test_a_configured_leave_type_and_reason_pass_the_form_check(monkeypatch):
    platform = Platform(people=[person('dev', 'D1')])  # stops at "nobody can approve", after the form check
    platform.form_fields[0]['enum_values'] = ['sick']
    platform.form_fields[1]['required'] = True
    error = create(platform, LEAVE_START, LEAVE_END, monkeypatch, leave_type='sick', reason='Fever')
    assert 'Nobody can approve' in error.detail


def test_leave_lists_are_newest_first_and_filter_by_state(monkeypatch):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self, *args: set())
    monkeypatch.setattr(WfhService, 'holiday_calendars', lambda self: [])
    platform = Platform()
    states = {'old': 'approved', 'new': 'pending', 'mid': 'pending'}
    platform.leave = [dict(entity_id=key, data=dict(employee_id='dev', start_date=start, end_date=start, leave_type='annual'))
                      for key, start in (('old', '2044-01-04'), ('new', '2044-06-06'), ('mid', '2044-03-07'))]
    platform.states = lambda machine: {} if machine == 'hrms_allocation' else states
    service = HrmsService(platform, None, 'example.com')
    who = actor('dev-user', 'hrms_employee')
    assert [r['entity_id'] for r in service.leave(who, 'mine', 100, 0)] == ['new', 'mid', 'old']
    assert [r['entity_id'] for r in service.leave(who, 'mine', 100, 0, 'pending')] == ['new', 'mid']
    assert [r['entity_id'] for r in service.leave(who, 'mine', 1, 0, 'pending')] == ['new']


@pytest.mark.parametrize(('days_ago', 'leave_type', 'allowed'), [
    (0, 'annual', True),
    (1, 'annual', False),     # planned leave cannot be backdated
    (3, 'sick', True),        # sick leave is recorded after it began...
    (7, 'sick', True),
    (8, 'sick', False),       # ...within a week
])
def test_only_sick_leave_can_be_backdated_and_only_within_a_week(monkeypatch, days_ago, leave_type, allowed):
    from datetime import timedelta
    start = date.today() - timedelta(days=days_ago)
    end = max(start, date.today())
    # A lone employee makes an allowed request stop later, at "nobody can approve".
    error = create(Platform(people=[person('dev', 'D1')]), start.isoformat(), end.isoformat(), monkeypatch,
                   leave_type=leave_type)
    assert ('Nobody can approve' in error.detail) is allowed
    assert ('must start today or later' in error.detail) is not allowed


def test_steps_follow_their_names_in_settings_and_disappear_when_removed():
    platform = Platform()
    original = platform.call

    def renamed(method, path, **kwargs):
        if path.endswith('/transitions/available'):
            return {'current_state': 'pending', 'available_transitions': [
                {'trigger': 'manager_approve', 'label': 'Approve leave', 'to_state': 'approved'}]}  # reject removed
        return original(method, path, **kwargs)
    platform.call = renamed
    result = HrmsService(platform, None, 'example.com').leave_actions(actor('lead-user', 'hrms_manager'), 'dev-leave')
    assert [(t['trigger'], t['label']) for t in result['available_transitions']] == [('approve', 'Approve leave')]

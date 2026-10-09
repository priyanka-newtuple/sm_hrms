from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from hrms_app.errors import AppError
from hrms_app.platform import Actor
from hrms_app.requests import LeaveCreateRequest
from hrms_app.service import HrmsService, leave_days
from hrms_app.wfh import WfhService

LEAVE_START, LEAVE_END = '2044-03-07', '2044-03-08'


def actor(user_id, role):
    return Actor(user_id, 'org', 'human', frozenset({role}), frozenset())


def person(key, code, manager=None):
    return dict(entity_id=key, data=dict(platform_user_id=f'{key}-user', employee_code=code,
                                         reports_to_employee_code=manager, first_name=key.title(), last_name='Person'))


class Platform:
    """`boss` manages `lead`, who manages `dev`. Projects P1 and P2 are run by `pm1` and `pm2`."""

    def __init__(self, state='pending', allocations=(), people=None):
        self.state = state
        self.people = people or [person('boss', 'B1'), person('lead', 'L1', 'B1'), person('dev', 'D1', 'L1'),
                                 person('pm1', 'P1'), person('pm2', 'P2')]
        self.allocations = list(allocations)  # (employee, project, start, end, state)
        self.leave = []

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
                    data=dict(employee_id=employee, start_date=LEAVE_START, end_date=LEAVE_END))

    def call(self, method, path, **kwargs):
        assert (method, path) == ('GET', '/entity-types/HRMS.LeaveRequest')
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
def test_decided_leave_offers_no_actions(state):
    assert triggers(Platform(state), 'lead-user', 'dev') == []


def test_approvals_list_follows_the_approver(monkeypatch):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self: set())
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


def create(platform, start, end, monkeypatch, holidays=frozenset()):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self: set(holidays))
    request = LeaveCreateRequest(start_date=start, end_date=end, leave_type='annual', idempotency_key='create-0001')
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


def test_leave_lists_carry_their_working_days(monkeypatch):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self: set())
    platform = Platform()
    platform.leave = [dict(entity_id='dev-leave', data=dict(employee_id='dev', start_date='2044-03-04',
                                                            end_date='2044-03-07', leave_type='annual'))]
    rows = HrmsService(platform, Journal(), 'example.com').leave(actor('dev-user', 'hrms_employee'), 'mine', 100, 0)
    assert [(r['entity_id'], r['days']) for r in rows] == [('dev-leave', 2)]

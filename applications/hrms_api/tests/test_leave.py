from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from hrms_app.errors import AppError
from hrms_app.platform import Actor
from hrms_app.requests import LeaveCreateRequest
from hrms_app.service import HrmsService, leave_days
from hrms_app.wfh import WfhService


def actor(user_id, role):
    return Actor(user_id, 'org', 'human', frozenset({role}), frozenset())


class Platform:
    """An organization where `boss` (any role) manages `lead`, who manages `dev`."""

    def __init__(self, state='pending'):
        self.state = state
        self.people = [
            dict(entity_id='boss', data=dict(platform_user_id='boss-user', employee_code='B1')),
            dict(entity_id='lead', data=dict(platform_user_id='lead-user', employee_code='L1', reports_to_employee_code='B1')),
            dict(entity_id='dev', data=dict(platform_user_id='dev-user', employee_code='D1', reports_to_employee_code='L1')),
        ]

    def records(self, kind, fields):
        return self.people

    def record(self, entity_id):
        employee = entity_id.removesuffix('-leave')
        return dict(entity_id=entity_id, entity_type_id='leave-type', data=dict(employee_id=employee))

    def call(self, method, path, **kwargs):
        assert (method, path) == ('GET', '/entity-types/HRMS.LeaveRequest')
        return {'entity_type_id': 'leave-type'}

    def states(self, machine):
        return {f'{p["entity_id"]}-leave': self.state for p in self.people}


def triggers(platform, who, role, leave):
    result = HrmsService(platform, None, 'example.com').leave_actions(actor(who, role), f'{leave}-leave')
    return [t['trigger'] for t in result['available_transitions']]


@pytest.mark.parametrize('role', ['hrms_manager', 'hrms_delivery_manager', 'superadmin', 'admin',
                                  'hrms_hr_full', 'hrms_project_manager', 'hrms_finance', 'hrms_employee'])
def test_the_reporting_manager_decides_whatever_their_role(role):
    assert triggers(Platform(), 'boss-user', role, 'lead') == ['approve', 'reject']


def test_the_employee_can_only_cancel_their_own_pending_leave():
    assert triggers(Platform(), 'lead-user', 'hrms_manager', 'lead') == ['cancel']


@pytest.mark.parametrize('who', ['boss-user', 'dev-user'])
def test_people_other_than_the_direct_manager_cannot_see_or_decide(who):
    # The manager's manager and the employee's own reports are not the approver.
    target = 'dev' if who == 'boss-user' else 'lead'
    with pytest.raises(AppError) as error:
        triggers(Platform(), who, 'superadmin', target)
    assert error.value.status == 404


@pytest.mark.parametrize('state', ['approved', 'rejected', 'cancelled'])
def test_decided_leave_offers_no_actions(state):
    assert triggers(Platform(state), 'boss-user', 'superadmin', 'lead') == []


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


@pytest.mark.parametrize(('start', 'end'), [('2044-03-05', '2044-03-06'), ('2044-03-09', '2044-03-09')])
def test_leave_on_weekends_or_holidays_only_is_refused(monkeypatch, start, end):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self: {'2044-03-09'})
    request = LeaveCreateRequest(start_date=start, end_date=end, leave_type='annual', idempotency_key='weekend-0001')
    with pytest.raises(AppError) as error:
        HrmsService(Platform(), Journal(), 'example.com').create_leave(actor('dev-user', 'hrms_employee'), request)
    assert error.value.status == 422 and 'working day' in error.value.detail


def test_leave_lists_carry_their_working_days(monkeypatch):
    monkeypatch.setattr(WfhService, 'holiday_dates', lambda self: set())
    platform = Platform()
    leave = dict(entity_id='dev-leave', data=dict(employee_id='dev', start_date='2044-03-04', end_date='2044-03-07',
                                                  leave_type='annual'))
    platform.records = lambda kind, fields: [leave] if kind == 'HRMS.LeaveRequest' else platform.people
    rows = HrmsService(platform, Journal(), 'example.com').leave(actor('dev-user', 'hrms_employee'), 'mine', 100, 0)
    assert [(r['entity_id'], r['days']) for r in rows] == [('dev-leave', 2)]
